"""Transactional offline model; no database or provider calls, including concurrency."""
import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import UUID
import hashlib
import operator

import pytest
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BindParameter, BooleanClauseList, Null, True_, False_, Grouping
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.functions import Function
from sqlalchemy.sql.selectable import Select, ScalarSelect
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.result import IteratorResult, SimpleResultMetaData

from oaf_website import notification_delivery as service
from oaf_website.notification_delivery_schema import TABLES, verification, limits, events, deliveries, attempts, suppressions
from oaf_website.confirmation_outbox_schema import TABLES as OUTBOX_TABLES
from oaf_website.notification_management_schema import changes
from oaf_website.release_approval_schema import revisions
from oaf_website.notifications import SubscriptionStore, validate_subscription
from test_notifications import choices

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
SECRET = b"synthetic-persistent-notification-key-6G1"
EVENT = str(UUID(int=1))


class Result:
    def __init__(self, value): self.value = value
    def scalar_one(self): return self.value
    def scalar_one_or_none(self): return self.value
    def mappings(self): return self.value


class Model:
    """Serialized transaction/row-lock model; not proof of PostgreSQL semantics."""
    def __init__(self):
        self.records = {t.name: [] for t in (service.notifications, *TABLES, *OUTBOX_TABLES, changes, revisions)}
        self.now, self.lock, self.failure = NOW, RLock(), None
        self.statements = []

    def elapse(self, **values): self.now += timedelta(**values)

    @contextmanager
    def begin(self):
        with self.lock:
            if self.failure == "connect": raise RuntimeError("synthetic private connection failure")
            pending = deepcopy(self.records)
            model = self

            def evaluate(node, row):
                if isinstance(node, ScalarSelect):
                    statement = node.element
                    column = list(statement.selected_columns)[0]
                    return [r[column.name] for r in pending[column.table.name]
                            if all(evaluate(c, r) for c in statement._where_criteria)]
                if isinstance(node, BindParameter): return node.value
                if isinstance(node, Null): return None
                if isinstance(node, True_): return True
                if isinstance(node, False_): return False
                if isinstance(node, Grouping): return evaluate(node.element, row)
                if isinstance(node, BooleanClauseList):
                    values = [evaluate(n, row) for n in node.clauses]
                    return all(values) if node.operator is operators.and_ else any(values)
                if isinstance(node, Function):
                    if node.name == "current_timestamp": return model.now
                    assert node.name == "greatest"
                    return max(evaluate(n, row) for n in node.clauses)
                if hasattr(node, "left"):
                    left, right = evaluate(node.left, row), evaluate(node.right, row)
                    if node.operator in {operators.le, operators.lt} and (left is None or right is None):
                        return False
                    return {operators.eq: operator.eq, operators.le: operator.le, operators.lt: operator.lt,
                            operators.in_op: lambda a, b: a in b, operators.is_: operator.is_}[node.operator](left, right)
                return row[node.name]

            class Connection:
                def execute(self, statement):
                    model.statements.append(str(statement.compile(dialect=postgresql.dialect())))
                    if model.failure == "execute": raise RuntimeError("synthetic private SQL body")
                    if isinstance(statement, Select):
                        if isinstance(list(statement.selected_columns)[0], Function): return Result(model.now)
                        item = statement.get_final_froms()[0]
                        rows = [deepcopy(r) for r in pending[item.name]
                                if all(evaluate(c, r) for c in statement._where_criteria)]
                        for column in reversed(tuple(statement._order_by_clauses)):
                            rows.sort(key=lambda row: row[column.name])
                        if statement._limit_clause is not None:
                            rows = rows[:statement._limit_clause.value]
                        names = [column.name for column in statement.selected_columns]
                        return IteratorResult(SimpleResultMetaData(names),
                            iter(tuple(row[name] for name in names) for row in rows))
                    if isinstance(statement, Insert):
                        item = statement.table
                        values = statement.compile().params
                        if item.name == "notifications":
                            values.update(created_at=model.now, unsubscribed_at=None, preferences_revision=0)
                        if item.name == "notification_confirmation_intents":
                            values.setdefault("purpose", "confirmation")
                            values.setdefault("management_revision", None)
                        pk = [c.name for c in item.primary_key.columns]
                        duplicate = any(all(r[c] == values[c] for c in pk) for r in pending[item.name])
                        if item.name == "notifications":
                            duplicate |= any(r["email"] == values["email"] and r["unsubscribed_at"] is None for r in pending[item.name])
                        if item.name == "notification_verification":
                            duplicate |= any(r["token_digest"] == values["token_digest"] for r in pending[item.name])
                        if item.name == "notification_preference_changes":
                            duplicate |= any(r["subscription"] == values["subscription"] and r["revision"] == values["revision"] for r in pending[item.name])
                        if duplicate and statement._post_values_clause is None:
                            raise RuntimeError("synthetic unique constraint rejection")
                        if not duplicate: pending[item.name].append(deepcopy(values))
                        return Result(values["unsubscribe_digest"] if statement._returning and not duplicate else None)
                    if isinstance(statement, Update):
                        for row in pending[statement.table.name]:
                            if all(evaluate(c, row) for c in statement._where_criteria):
                                row.update({getattr(k, "name", k): evaluate(v, row) for k, v in statement._values.items()})
                        return Result(None)
                    assert str(statement) == "SELECT pg_catalog.pg_advisory_xact_lock(67210401)"
                    return Result(None)
            yield Connection()
            if model.failure == "commit": raise RuntimeError("synthetic rejected commit")
            self.records = pending
            if model.failure == "uncertain": raise RuntimeError("synthetic lost commit acknowledgement")

    def rows(self, item): return self.records[item.name]


@pytest.fixture
def setup():
    model = Model()
    return model, service.NotificationDeliveryStore(model, SECRET, "testing")


def subscribe(model, number=1, **overrides):
    values = validate_subscription(choices(**dict(dict(email=f"subscriber{number}@example.invalid", token=f"{number:064x}",
                                         android_launch=True, ios_launch=True), **overrides)))
    SubscriptionStore(model).subscribe(values)
    return values["unsubscribe_digest"]


def payload(platform="android", **changes):
    values = dict(event_id=EVENT, source_approval_id=str(UUID(int=2)), environment="testing", platform=platform,
                  release_id="org.oaf.gramanna" if platform == "android" else "123456789",
                  release_url="https://play.google.com/store/apps/details?id=org.oaf.gramanna" if platform == "android" else "https://apps.apple.com/app/id123456789",
                  approved_at=NOW.isoformat(), audience_cutoff=NOW.isoformat(), content_version="mobile-launch-v1")
    values.update(changes)
    return values


def ready(model, store, number=1):
    digest = subscribe(model, number)
    token = store.request_confirmation(f"subscriber{number}@example.invalid")
    assert store.confirm(token) == "verified"
    store.accept_event(payload())
    assert store.prepare_event(EVENT) == "ready"
    return digest


def submit(model, store):
    digest = ready(model, store)
    claim = store.claim(EVENT, digest)
    assert store.begin_submission(EVENT, digest, claim) == "subscriber1@example.invalid"
    return digest, claim


def test_new_and_existing_subscriptions_stay_unverified_and_preferences_immutable(setup):
    model, store = setup
    digest = subscribe(model)
    subscribe(model, android_launch=False, ios_launch=False)
    assert model.rows(service.notifications)[0]["android_launch"] is True
    assert not model.rows(verification)
    store.accept_event(payload())
    assert store.recover_event(EVENT) == "received"
    assert store.prepare_event(EVENT) == "completed"
    assert store.prepare_event(EVENT) == "completed"
    assert store.claim(EVENT, digest) is None


def test_confirmation_single_purpose_pending_coalescing_replay_and_revocation(setup):
    model, store = setup
    digest = subscribe(model)
    token = store.request_confirmation("subscriber1@example.invalid")
    assert token and token not in repr(model.records)
    assert store.confirm("f" * 64) == "unavailable"
    assert store.request_confirmation("subscriber1@example.invalid") is None
    model.elapse(seconds=60)
    replacement = store.request_confirmation("subscriber1@example.invalid")
    assert replacement == token and len(model.rows(OUTBOX_TABLES[0])) == 1
    assert store.confirm(replacement) == "verified"
    assert store.confirm(replacement) == "already_verified"
    model.elapse(seconds=60)
    assert store.request_confirmation("subscriber1@example.invalid") is None
    SubscriptionStore(model).unsubscribe(digest)
    assert store.confirm(replacement) == "unavailable"
    new_digest = subscribe(model, 2, email="subscriber1@example.invalid")
    assert new_digest != digest and len(model.rows(verification)) == 1
    assert store.confirm(replacement) == "unavailable"


@pytest.mark.parametrize("token", [None, "", "secret", "A"*64, [], 3])
def test_invalid_confirmation_is_generic(setup, token):
    assert setup[1].confirm(token) == "unavailable"


@pytest.mark.parametrize("offset", [timedelta(days=1), timedelta(seconds=-1)])
def test_confirmation_expiry_and_future_timestamp(setup, offset):
    model, store = setup
    subscribe(model)
    token = store.request_confirmation("subscriber1@example.invalid")
    model.now += offset
    assert store.confirm(token) == "unavailable"


def test_durable_mailbox_and_global_limits_unknown_and_suppressed(setup):
    model, store = setup
    subscribe(model)
    for _ in range(5):
        assert store.request_confirmation("subscriber1@example.invalid")
        model.elapse(seconds=60)
    assert store.request_confirmation("subscriber1@example.invalid") is None
    model.elapse(days=1)
    assert store.request_confirmation("subscriber1@example.invalid")
    assert store.request_confirmation("absent@example.invalid") is None
    store.suppress("subscriber1@example.invalid", "complaint")
    model.elapse(seconds=60)
    assert store.request_confirmation("subscriber1@example.invalid") is None
    global_bucket = next(r for r in model.rows(limits) if r["bucket"] == store._digest("budget", "global"))
    global_bucket["requests"] = 1000
    assert store.request_confirmation("new@example.invalid") is None
    assert "subscriber1@" not in repr(model.rows(limits) + model.rows(suppressions))


def test_confirmation_suppression_and_concurrency(setup):
    model, store = setup
    subscribe(model)
    with ThreadPoolExecutor(max_workers=8) as pool:
        tokens = list(pool.map(lambda _: store.request_confirmation("subscriber1@example.invalid"), range(8)))
    token = next(t for t in tokens if t)
    assert sum(t is not None for t in tokens) == 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: store.confirm(token), range(8)))
    assert outcomes.count("verified") == 1 and outcomes.count("already_verified") == 7
    verified_at = model.rows(verification)[0]["verified_at"]
    model.elapse(seconds=1)
    assert store.confirm(token) == "already_verified" and model.rows(verification)[0]["verified_at"] == verified_at
    store.suppress("subscriber1@example.invalid", "hard_bounce")
    assert store.confirm(token) == "unavailable"


@pytest.mark.parametrize("changes", [dict(recipients=[]), dict(content="mass email"), dict(event_id="bad"),
    dict(event_id=1), dict(source_approval_id="00000000000000000000000000000002"), dict(environment="production"),
    dict(platform="web"), dict(content_version="arbitrary"), dict(release_id=4), dict(release_url=None),
    dict(release_id="bad"), dict(release_url="https://evil.invalid/"), dict(release_url="https://play.google.com.evil.invalid/store/apps/details?id=org.oaf.gramanna"),
    dict(approved_at=NOW), dict(approved_at="2026-10-15T12:00:00"), dict(approved_at="invalid"),
    dict(approved_at=(NOW+timedelta(days=1)).isoformat()), dict(audience_cutoff=(NOW+timedelta(seconds=1)).isoformat())])
def test_release_payload_negative_contract(setup, changes):
    with pytest.raises((ValueError, TypeError)):
        setup[1].accept_event(payload(**changes))
    assert not setup[0].rows(events)


def test_events_idempotent_conflicts_independent_platforms_and_environments(setup):
    model, store = setup
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert set(pool.map(lambda _: store.accept_event(payload()), range(8))) == {EVENT}
    assert len(model.rows(events)) == 1
    for changes in (dict(release_id="org.oaf.other", release_url="https://play.google.com/store/apps/details?id=org.oaf.other"), dict(event_id=str(UUID(int=5)))):
        with pytest.raises(service.EventConflict): store.accept_event(payload(**changes))
    assert store.accept_event(payload("ios", event_id=str(UUID(int=3)))) == str(UUID(int=3))
    foreign = service.NotificationDeliveryStore(model, SECRET, "development")
    assert foreign.prepare_event(EVENT) is None and foreign.claim(EVENT, "unknown") is None
    assert foreign.begin_submission(EVENT, "unknown", "f"*64) is None
    assert foreign.recover_event(EVENT) is None
    assert foreign.record_outcome(EVENT, "unknown", "f"*64, "provider_accepted") is False
    assert store.prepare_event("unknown") is None


def test_audience_cutoff_preferences_withdrawal_suppression_and_lifecycle(setup):
    model, store = setup
    digest = ready(model, store)
    assert store.prepare_event(EVENT) == "ready" and len(model.rows(deliveries)) == 1
    for number, changes in ((2, {}), (3, dict(android_launch=False))):
        new_digest = subscribe(model, number, **changes)
        token = store.request_confirmation(f"subscriber{number}@example.invalid")
        if number == 2: model.elapse(seconds=1)
        assert store.confirm(token) == "verified"
        assert store.claim(EVENT, new_digest) is None
    SubscriptionStore(model).unsubscribe(digest)
    subscribe(model, 4, email="subscriber1@example.invalid")
    assert store.claim(EVENT, digest) is None
    assert model.rows(deliveries)[0]["status"] == "suppressed"


def test_audience_initial_selection_cases(setup):
    model, store = setup
    for number in range(1, 7):
        digest = subscribe(model, number, android_launch=number != 4)
        if number != 2:
            token = store.request_confirmation(f"subscriber{number}@example.invalid")
            assert store.confirm(token) == "verified"
        if number == 3: SubscriptionStore(model).unsubscribe(digest)
        if number == 5: store.suppress(f"subscriber{number}@example.invalid", "provider_block")
        if number == 6: model.rows(service.notifications)[-1]["created_at"] += timedelta(seconds=1)
    store.accept_event(payload())
    store.prepare_event(EVENT)
    assert len(model.rows(deliveries)) == 1


@pytest.mark.parametrize("action", ["withdraw", "suppress"])
def test_recheck_before_dispatch_prevents_revived_work(setup, action):
    model, store = setup
    digest = ready(model, store)
    claim = store.claim(EVENT, digest)
    if action == "withdraw": SubscriptionStore(model).unsubscribe(digest)
    else: store.suppress("subscriber1@example.invalid", "owner_policy")
    assert store.begin_submission(EVENT, digest, claim) is None
    assert model.rows(deliveries)[0]["status"] == "suppressed"
    assert model.rows(attempts)[0]["outcome"] == "ineligible"


def test_claims_are_concurrent_single_use_expiring_and_hashed(setup):
    model, store = setup
    digest = ready(model, store)
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: store.claim(EVENT, digest), range(8)))
    assert sum(c is not None for c in claims) == 1
    claim = next(c for c in claims if c)
    assert claim not in repr(model.records)
    assert store.begin_submission(EVENT, digest, "f" * 64) is None
    assert store.begin_submission(EVENT, digest, None) is None
    assert store.begin_submission(EVENT, digest, "bad") is None
    model.elapse(minutes=5)
    assert store.begin_submission(EVENT, digest, claim) is None
    assert store.recover_event(EVENT) == "ready"
    assert store.claim(EVENT, digest) is None
    model.elapse(seconds=60)
    assert store.claim(EVENT, digest)
    assert len(model.rows(attempts)) == 2


@pytest.mark.parametrize("outcome,status", list(service.OUTCOMES.items()))
def test_provider_outcomes_and_acceptance_is_not_final_delivery(setup, outcome, status):
    model, store = setup
    digest, claim = submit(model, store)
    assert store.begin_submission(EVENT, digest, claim) is None
    assert store.record_outcome(EVENT, digest, "f"*64, outcome) is False
    assert store.record_outcome(EVENT, digest, claim, outcome, "synthetic-message-1")
    record = model.rows(deliveries)[0]
    assert record["status"] == status
    assert record["provider_message_id"] == "synthetic-message-1"
    assert (record["accepted_at"] is not None) == (status == "accepted")
    assert store.record_outcome(EVENT, digest, claim, outcome) is False
    if status != "failed":
        model.elapse(days=1)
        assert store.claim(EVENT, digest) is None


def test_bounded_retries_preserve_attempt_audit_and_no_administrator_override(setup):
    model, store = setup
    digest = ready(model, store)
    for number in range(1, 4):
        claim = store.claim(EVENT, digest)
        assert store.begin_submission(EVENT, digest, claim)
        assert store.record_outcome(EVENT, digest, claim, "not_submitted")
        assert model.rows(deliveries)[0]["attempts"] == number
        if number < 3:
            assert store.claim(EVENT, digest) is None
            model.elapse(seconds=60 * 5 ** (number - 1))
    assert store.claim(EVENT, digest) is None
    assert model.rows(events)[0]["status"] == "completed"
    assert [r["outcome"] for r in model.rows(attempts)] == ["not_submitted"] * 3


def test_timeout_recovery_is_uncertain_never_an_automatic_resend(setup):
    model, store = setup
    digest, claim = submit(model, store)
    assert store.recover_event(EVENT) == "ready"
    model.elapse(minutes=5)
    assert store.recover_event(EVENT) == "attention"
    assert model.rows(attempts)[0]["outcome"] == "submission_unknown"
    model.elapse(days=1)
    assert store.recover_event(EVENT) == "attention" and store.claim(EVENT, digest) is None
    assert store.record_outcome(EVENT, digest, claim, "provider_accepted") is False


@pytest.mark.parametrize("outcome,message", [("raw-error-body", None), ("provider_accepted", "secret\nbody"), ("provider_accepted", 4)])
def test_only_sanitized_provider_metadata_allowed(setup, outcome, message):
    with pytest.raises(ValueError): setup[1].record_outcome(EVENT, "unknown", "f"*64, outcome, message)


@pytest.mark.parametrize("reason", ["raw-provider-error", "", None])
def test_suppression_is_allowlisted_and_immutable(setup, reason):
    model, store = setup
    with pytest.raises(ValueError): store.suppress("person@example.invalid", reason)
    store.suppress("person@example.invalid", "complaint")
    store.suppress("person@example.invalid", "hard_bounce")
    assert len(model.rows(suppressions)) == 1 and model.rows(suppressions)[0]["reason"] == "complaint"


@pytest.mark.parametrize("failure", ["connect", "execute", "commit"])
def test_atomic_rollback_and_safe_event_repeat(setup, failure):
    model, store = setup
    original = deepcopy(model.records)
    model.failure = failure
    with pytest.raises(RuntimeError): store.accept_event(payload())
    assert model.records == original
    model.failure = None
    assert store.accept_event(payload()) == EVENT


def test_lost_commit_on_submission_does_not_authorize_retry(setup):
    model, store = setup
    digest = ready(model, store)
    claim = store.claim(EVENT, digest)
    model.failure = "uncertain"
    with pytest.raises(RuntimeError): store.begin_submission(EVENT, digest, claim)
    model.failure = None
    assert model.rows(deliveries)[0]["status"] == "submitting"
    assert store.begin_submission(EVENT, digest, claim) is None
    model.elapse(minutes=5)
    assert store.recover_event(EVENT) == "attention"


def test_preparation_rollback_never_marks_incomplete_audience_completed(setup, monkeypatch):
    model, store = setup
    subscribe(model)
    token = store.request_confirmation("subscriber1@example.invalid")
    store.confirm(token)
    store.accept_event(payload())
    original = store._refresh
    def fail(*args): raise RuntimeError("synthetic preparation interruption")
    monkeypatch.setattr(store, "_refresh", fail)
    with pytest.raises(RuntimeError): store.prepare_event(EVENT)
    assert not model.rows(deliveries) and model.rows(events)[0]["status"] == "received"
    monkeypatch.setattr(store, "_refresh", original)
    assert store.prepare_event(EVENT) == "ready"


def test_invalid_protected_configuration():
    with pytest.raises(ValueError): service.NotificationDeliveryStore(None, b"short", "testing")
    with pytest.raises(ValueError): service.NotificationDeliveryStore(None, SECRET, "unknown")


def test_eligibility_rechecked_after_late_verification(setup):
    model, store = setup
    digest = ready(model, store)
    # Independent evidence of verification after the frozen audience cutoff
    # is never eligible, even if queued work already exists.
    model.rows(verification)[0]["verified_at"] += timedelta(seconds=1)
    assert store.claim(EVENT, digest) is None


def test_suppressing_a_retry_does_not_rewrite_previous_attempt_evidence(setup):
    model, store = setup
    digest, claim = submit(model, store)
    assert store.record_outcome(EVENT, digest, claim, "retryable_rejection")
    store.suppress("subscriber1@example.invalid", "complaint")
    model.elapse(seconds=60)
    assert store.claim(EVENT, digest) is None
    assert model.rows(attempts)[0]["outcome"] == "retryable_rejection"


def test_withdrawal_resubscribe_never_resets_mailbox_abuse_budget(setup):
    model, store = setup
    digest = subscribe(model)
    assert store.request_confirmation("subscriber1@example.invalid")
    SubscriptionStore(model).unsubscribe(digest)
    subscribe(model, 2, email="subscriber1@example.invalid")
    assert store.request_confirmation("subscriber1@example.invalid") is None
    model.elapse(seconds=60)
    token=store.request_confirmation("subscriber1@example.invalid")
    assert token and store.confirm(token)=="verified"
    assert len(model.rows(verification))==2


def test_duplicate_claim_cannot_be_completed_by_another_environment(setup):
    model,store=setup
    digest,claim=submit(model,store)
    other=service.NotificationDeliveryStore(model,SECRET,"development")
    assert other.record_outcome(EVENT,digest,claim,"provider_accepted") is False
    assert model.rows(deliveries)[0]["status"]=="submitting"


# Work Unit 1: additive official approval history uses the existing transaction model.
def changed_release(model, **overrides):
    return payload(action="correct", previous_approval_id=str(UUID(int=2)),
        source_approval_id=str(UUID(int=3)), approved_at=model.now.isoformat(),
        **overrides)


@pytest.mark.parametrize("platform,identity,url,valid", [
    ("android", "org.oaf.GraManna", "https://play.google.com/store/apps/details?id=org.oaf.GraManna", True),
    ("ios", "123456789", "https://apps.apple.com/us/app/gramanna/id123456789", True),
    ("ios", "123456789", "https://apps.apple.com/us/app/id123456789", True),
    ("ios", "123456789", "https://apps.apple.com/app/gramanna/id123456789", True),
    ("ios", "123456789", "https://apps.apple.com/app/id123456789?ref=bad", False),
    ("ios", "123456789", "https://apps.apple.com/us/app/gramanna/id987654321", False),
    ("ios", "123456789", "https://apps.apple.com.evil.invalid/app/id123456789", False),
    ("ios", "123456789", "https://user@apps.apple.com/app/id123456789", False),
    ("ios", "123456789", "https://apps.apple.com/app/id123456789#bad", False),
    ("ios", "0123456789", "https://apps.apple.com/app/id0123456789", False),
    ("android", "org.oaf.gramanna", "https://play.google.com/store/apps/details?id=org.oaf.other", False),
    ("android", "a" * 151, "https://play.google.com/store/apps/details?id=" + "a" * 151, False),
    ("ios", "123456789", "x" * 301, False),
    ("web", "org.oaf.gramanna", "https://example.invalid", False),
    ("desktop", "org.oaf.gramanna", "https://play.google.com/store/apps/details?id=org.oaf.gramanna", False),
])
def test_official_reference_compatibility_is_strict(platform, identity, url, valid):
    assert service.official_release_reference(platform, identity, url) is valid


def test_correction_keeps_original_event_cutoff_audience_and_attempts(setup):
    model, _ = setup
    store = service.NotificationDeliveryStore(model, SECRET, "testing", releases_enabled=True)
    digest = ready(model, store)
    original = deepcopy(model.rows(events))
    claim = store.claim(EVENT, digest)
    model.elapse(seconds=1)
    correction = changed_release(model)
    correction.update(release_id="org.oaf.corrected", release_url="https://play.google.com/store/apps/details?id=org.oaf.corrected")
    assert store.accept_release_change(correction) == EVENT
    assert store.accept_release_change(correction) == EVENT
    seen = []
    assert store.begin_submission(EVENT, digest, claim, prepare=lambda sub, now, event: seen.append(event))[0] == "subscriber1@example.invalid"
    assert seen[0]["release_url"] == correction["release_url"]
    assert seen[0]["audience_cutoff"] == NOW
    assert model.rows(events)[0]["payload_digest"] == original[0]["payload_digest"]
    assert len(model.rows(revisions)) == len(model.rows(attempts)) == 1
    assert store.record_outcome(EVENT, digest, claim, "provider_accepted")
    history = deepcopy(model.rows(attempts))
    model.elapse(seconds=1)
    withdrawal = dict(correction, action="withdraw", previous_approval_id=str(UUID(int=3)),
        source_approval_id=str(UUID(int=4)), approved_at=model.now.isoformat())
    assert store.accept_release_change(withdrawal) == EVENT
    assert model.rows(attempts) == history
    assert store.accept_event(payload()) == EVENT
    assert store.prepare_event(EVENT) == "completed"


@pytest.mark.parametrize("state", ["received", "pending", "claimed", "failed", "submitting", "accepted", "uncertain"])
def test_withdrawal_stops_unsent_work_and_preserves_provider_evidence(setup, state):
    model, _ = setup
    store = service.NotificationDeliveryStore(model, SECRET, "testing", releases_enabled=True)
    if state == "received":
        store.accept_event(payload())
    else:
        digest = ready(model, store)
        if state != "pending":
            claim = store.claim(EVENT, digest)
            if state != "claimed":
                store.begin_submission(EVENT, digest, claim)
                if state != "submitting":
                    store.record_outcome(EVENT, digest, claim, {"failed":"not_submitted", "accepted":"provider_accepted", "uncertain":"submission_unknown"}[state])
    before = deepcopy(model.rows(attempts))
    model.elapse(seconds=1)
    withdrawal = changed_release(model)
    withdrawal["action"] = "withdraw"
    store.accept_release_change(withdrawal)
    store.accept_release_change(withdrawal)
    store.accept_event(payload())
    store.prepare_event(EVENT)
    if state == "received":
        assert not model.rows(deliveries)
    elif state in {"pending", "claimed", "failed"}:
        assert model.rows(deliveries)[0]["status"] == "suppressed"
        assert store.claim(EVENT, digest) is None
        if state != "claimed":
            assert model.rows(attempts) == before
    else:
        assert model.rows(deliveries)[0]["status"] == state
        assert model.rows(attempts) == before
        if state == "submitting":
            model.elapse(minutes=6)
            assert store.recover_event(EVENT) == "attention"
            assert model.rows(deliveries)[0]["status"] == "uncertain"


@pytest.mark.parametrize("override", [dict(action="send"), dict(previous_approval_id="bad"),
    dict(previous_approval_id=str(UUID(int=88))), dict(source_approval_id=str(UUID(int=2))),
    dict(platform="ios", release_id="123456789", release_url="https://apps.apple.com/app/id123456789"),
    dict(audience_cutoff=(NOW-timedelta(seconds=1)).isoformat()), dict(approved_at=NOW.isoformat())])
def test_release_change_rejects_invalid_stale_or_enlarged_authority(setup, override):
    model, _ = setup
    store = service.NotificationDeliveryStore(model, SECRET, "testing", releases_enabled=True)
    store.accept_event(payload())
    model.elapse(seconds=1)
    values = changed_release(model)
    values.update(override)
    before = deepcopy(model.records)
    with pytest.raises(ValueError): store.accept_release_change(values)
    assert model.records == before


def test_release_change_missing_withdrawn_conflicting_and_failed_transactions(setup):
    model, disabled = setup
    store = service.NotificationDeliveryStore(model, SECRET, "testing", releases_enabled=True)
    model.elapse(seconds=1)
    values = changed_release(model)
    with pytest.raises(ValueError): disabled.accept_release_change(values)
    with pytest.raises(ValueError): store.accept_release_change(None)
    with pytest.raises(service.EventConflict): store.accept_release_change(values)
    store.accept_event(payload())
    model.failure = "commit"
    with pytest.raises(RuntimeError): store.accept_release_change(values)
    assert not model.rows(revisions)
    model.failure = None
    store.accept_release_change(values)
    with pytest.raises(service.EventConflict): store.accept_release_change(dict(values, action="withdraw"))
    model.elapse(seconds=1)
    withdrawal = dict(values, action="withdraw", previous_approval_id=str(UUID(int=3)),
        source_approval_id=str(UUID(int=4)), approved_at=model.now.isoformat())
    store.accept_release_change(withdrawal)
    with pytest.raises(service.EventConflict): store.accept_release_change(dict(withdrawal,
        action="correct", previous_approval_id=str(UUID(int=4)), source_approval_id=str(UUID(int=5))))
    assert store.pending_release_events() == []



@pytest.mark.parametrize("previous", [5, "00000000000000000000000000000002"])
def test_release_change_requires_canonical_internal_predecessor_identity(setup, previous):
    model,_=setup
    store=service.NotificationDeliveryStore(model,SECRET,"testing",releases_enabled=True)
    values=changed_release(model)
    values["previous_approval_id"]=previous
    with pytest.raises(ValueError): store.accept_release_change(values)
    assert not model.rows(revisions)


def test_release_activation_requires_a_boolean_and_cross_environment_selection_is_bound(setup):
    model,_=setup
    with pytest.raises(ValueError): service.NotificationDeliveryStore(model,SECRET,"testing",releases_enabled=1)
    testing=service.NotificationDeliveryStore(model,SECRET,"testing",releases_enabled=True)
    development=service.NotificationDeliveryStore(model,SECRET,"development",releases_enabled=True)
    testing.accept_event(payload())
    other=str(UUID(int=9))
    development.accept_event(payload(event_id=other,environment="development"))
    assert testing.pending_release_events()==[EVENT]
    assert development.pending_release_events()==[other]


# WU2 synthetic canonical reference only; never a configured production destination.
WEB_URL = "https://gramanna.example.org/app"


def web_payload(**overrides):
    return dict(payload("web", release_id="gramanna-web", release_url=WEB_URL,
                        content_version="web-launch-v1"), **overrides)


def web_store(model, **overrides):
    return service.NotificationDeliveryStore(model, SECRET, "testing", **dict(dict(
        management_enabled=True, releases_enabled=True, web_launch_url=WEB_URL), **overrides))


def state_payload(state_code="CA", **overrides):
    return dict(web_payload(platform="state", release_id=state_code,
                            content_version="state-availability-v1"), **overrides)


@pytest.mark.parametrize("state", service.STATE_CODES)
def test_state_contract_accepts_exactly_existing_fifty_state_codes(state):
    values = service.release_payload(state_payload(state), "testing", NOW, web_launch_url=WEB_URL)
    assert values["release_id"] == state and values["content_version"] == "state-availability-v1"


@pytest.mark.parametrize("override", [dict(release_id=value) for value in
    (None, 3, [], "", "ca", "DC", "PR", "USA", "CA ", "California", "NY\n")] + [
    dict(content_version="web-launch-v1"), dict(content_version="mobile-launch-v1"),
    dict(environment="development"), dict(platform="State"), dict(recipients=[]),
    dict(subject="caller copy"), dict(release_url=WEB_URL + "/"),
    dict(release_url="https://other.example.org/app")])
def test_state_contract_rejects_invalid_scope_copy_and_destination(override):
    with pytest.raises(ValueError):
        service.release_payload(state_payload(**override), "testing", NOW, web_launch_url=WEB_URL)


def test_state_contract_requires_configured_destination_and_cannot_cross_existing_content_types():
    with pytest.raises(ValueError): service.release_payload(state_payload(), "testing", NOW)
    for original in (payload(), payload("ios"), web_payload()):
        with pytest.raises(ValueError):
            service.release_payload(dict(original, content_version="state-availability-v1"),
                                    "testing", NOW, web_launch_url=WEB_URL)


def test_concurrent_state_acceptance_replay_and_restart_preserve_per_state_identity():
    model = Model(); store = web_store(model)
    original = state_payload()
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert set(pool.map(lambda _: store.accept_event(original), range(8))) == {EVENT}
    model.elapse(seconds=1)
    assert web_store(model).accept_event(original) == EVENT
    for values in (state_payload(event_id=str(UUID(int=8))),
                   state_payload(audience_cutoff=(NOW - timedelta(seconds=1)).isoformat()),
                   state_payload("NY")):
        with pytest.raises(service.EventConflict): store.accept_event(values)
    other = str(UUID(int=9))
    assert store.accept_event(state_payload("NY", event_id=other)) == other
    for index, original in enumerate((payload(), payload("ios"), web_payload()), 10):
        store.accept_event(dict(original, event_id=str(UUID(int=index))))
        with pytest.raises(service.EventConflict):
            store.accept_event(dict(original, event_id=str(UUID(int=index + 100))))
    assert len(model.rows(events)) == 5
    assert model.rows(events)[0]["audience_cutoff"] == NOW
    assert len(store.pending_release_events()) == 4
    assert EVENT in store.pending_release_events() and other not in store.pending_release_events()


def state_preference(model, digest, state):
    from oaf_website.notification_management import NotificationManagementStore
    manager = NotificationManagementStore(model, SECRET, "testing")
    current = next(row for row in model.rows(service.notifications) if row["unsubscribe_digest"] == digest)
    revision = current["preferences_revision"]
    manager.save(manager.capabilities.issue(digest, revision, model.now), f"{revision + 200:064x}", revision,
        dict(web_launch=current["web_launch"], android_launch=current["android_launch"],
             ios_launch=current["ios_launch"], state=state, consent=True))


@pytest.mark.parametrize("case", ["eligible", "no_state", "other_state", "unverified", "late_signup",
    "late_verification", "early_grant", "late_grant", "changed_away", "changed_back", "removed",
    "withdrawn", "suppressed", "new_lifecycle", "audit_missing", "unrelated_late_change", "invalid_consent"])
def test_state_audience_requires_exact_current_state_and_original_lifecycle_cutoffs(case):
    model = Model(); store = web_store(model)
    if case == "late_signup": model.elapse(seconds=1)
    initial = None if case in {"no_state", "early_grant", "late_grant"} else "NY" if case == "other_state" else "CA"
    digest = subscribe(model, state=initial)
    token = store.request_confirmation("subscriber1@example.invalid")
    if case == "late_verification": model.elapse(seconds=1)
    if case != "unverified": assert store.confirm(token) == "verified"
    if case in {"early_grant", "late_grant"}:
        if case == "late_grant": model.elapse(seconds=1)
        state_preference(model, digest, "CA")
    if case in {"changed_away", "changed_back", "removed"}:
        model.elapse(seconds=1)
        state_preference(model, digest, None if case == "removed" else "NY")
        if case == "changed_back":
            model.elapse(seconds=1); state_preference(model, digest, "CA")
    if case == "unrelated_late_change":
        from oaf_website.notification_management import NotificationManagementStore
        model.elapse(seconds=1)
        manager = NotificationManagementStore(model, SECRET, "testing")
        manager.save(manager.capabilities.issue(digest, 0, model.now), "a" * 64, 0,
            dict(web_launch=False, android_launch=False, ios_launch=True, state="CA", consent=True))
    if case == "audit_missing": model.rows(service.notifications)[0]["preferences_revision"] = 1
    if case == "invalid_consent": model.rows(service.notifications)[0]["consent_version"] = "unapproved"
    if case in {"withdrawn", "new_lifecycle"}: SubscriptionStore(model).unsubscribe(digest)
    if case == "new_lifecycle":
        model.elapse(seconds=60); subscribe(model, 2, email="subscriber1@example.invalid", state="CA")
    if case == "suppressed": store.suppress("subscriber1@example.invalid", "complaint")
    store.accept_event(state_payload()); store.prepare_event(EVENT)
    assert len(model.rows(deliveries)) == int(case in {"eligible", "early_grant", "unrelated_late_change"})
    assert model.rows(events)[0]["audience_cutoff"] == NOW


@pytest.mark.parametrize("status", ["pending", "claimed", "submitting", "accepted", "uncertain", "failed"])
def test_state_ordered_correction_and_terminal_withdrawal_preserve_cutoff_and_outcomes(status):
    model = Model(); store = web_store(model)
    digest = subscribe(model, state="CA")
    assert store.confirm(store.request_confirmation("subscriber1@example.invalid")) == "verified"
    store.accept_event(state_payload()); store.prepare_event(EVENT)
    if status != "pending":
        claim = store.claim(EVENT, digest)
        if status != "claimed": store.begin_submission(EVENT, digest, claim)
        if status in {"accepted", "uncertain", "failed"}:
            store.record_outcome(EVENT, digest, claim,
                {"accepted":"provider_accepted", "uncertain":"submission_unknown", "failed":"retryable_rejection"}[status])
    original = deepcopy(model.rows(events)[0]); history = deepcopy(model.rows(attempts))
    model.elapse(seconds=1)
    correction = state_payload(action="correct", previous_approval_id=str(UUID(int=2)),
        source_approval_id=str(UUID(int=3)), approved_at=model.now.isoformat())
    for bad in (dict(correction, release_id="NY"), dict(correction, previous_approval_id=str(UUID(int=8))),
                dict(correction, audience_cutoff=model.now.isoformat())):
        with pytest.raises(service.EventConflict): store.accept_release_change(bad)
    assert store.accept_release_change(correction) == EVENT
    assert store.accept_release_change(correction) == EVENT
    assert store.dispatch_batch(EVENT)[0]["source_approval_id"] == str(UUID(int=3))
    model.elapse(seconds=1)
    withdrawal = dict(correction, action="withdraw", previous_approval_id=str(UUID(int=3)),
                      source_approval_id=str(UUID(int=4)), approved_at=model.now.isoformat())
    store.accept_release_change(withdrawal); store.accept_release_change(withdrawal)
    assert store.accept_event(state_payload()) == EVENT
    with pytest.raises(service.EventConflict):
        store.accept_release_change(dict(withdrawal, action="correct", previous_approval_id=str(UUID(int=4)),
                                        source_approval_id=str(UUID(int=5))))
    model.elapse(minutes=6); web_store(model).recover_event(EVENT)
    assert store.dispatch_batch(EVENT)[1] == [] and store.claim(EVENT, digest) is None
    for name in ("payload_digest", "audience_cutoff", "release_id", "source_approval_id"):
        assert model.rows(events)[0][name] == original[name]
    assert len(model.rows(revisions)) == 2
    if status in {"accepted", "uncertain", "failed"}: assert model.rows(attempts) == history
    if status == "submitting": assert model.rows(deliveries)[0]["status"] == "uncertain"


def test_state_discovery_rotates_held_and_backoff_work_and_remains_environment_bound():
    model = Model(); store = web_store(model)
    ids = [str(UUID(int=i)) for i in range(10, 60)]
    for index, state in enumerate(service.STATE_CODES):
        digest = subscribe(model, index + 1, state=state)
        assert store.confirm(store.request_confirmation(f"subscriber{index + 1}@example.invalid")) == "verified"
        store.accept_event(state_payload(state, event_id=ids[index]))
        store.prepare_event(ids[index])
        claim = store.claim(ids[index], digest)
        store.begin_submission(ids[index], digest, claim)
        store.record_outcome(ids[index], digest, claim, "submission_unknown" if index % 2 else "retryable_rejection")
    foreign = service.NotificationDeliveryStore(
        model, SECRET, "development", releases_enabled=True, management_enabled=True, web_launch_url=WEB_URL)
    foreign.accept_event(dict(state_payload(event_id=str(UUID(int=100))), environment="development"))
    visited = []
    for _ in ids:
        model.elapse(seconds=1)
        selected = web_store(model).pending_release_events()
        assert len(selected) == 1
        visited.extend(selected)
        assert web_store(model).recover_event(selected[0]) in {"attention", "ready"}
    assert visited == ids
    assert foreign.pending_release_events() == [str(UUID(int=100))]


@pytest.mark.parametrize("value", [None, 3, True, [], {}, "", "http://gramanna.example.org/app",
    "https://localhost", "https://127.0.0.1/app", "https://[::1]/", "https://10.0.0.1/",
    "https://host.local/", "https://host.internal/", "https://host.test/", "https://host.invalid/",
    "https://host.localhost/", "https://user@gramanna.example.org/app", WEB_URL + "?", WEB_URL + "?x=1",
    WEB_URL + "#", WEB_URL + "#fragment", "https://gramanna.example.org:443/app",
    "https://apps.apple.com/app/id123456789", "https://play.google.com/store/apps/details",
    WEB_URL + "\n", "https://gramanna.example.org/" + "x" * 300])
def test_web_canonical_configuration_rejects_nonpublic_or_decorated_destinations(value):
    assert not service.canonical_web_url(value)
    if value is not None:
        with pytest.raises(ValueError, match="configured public"):
            web_store(Model(), web_launch_url=value)


@pytest.mark.parametrize("override", [dict(release_id="gramanna"), dict(release_id=None),
    dict(release_url=WEB_URL + "/"), dict(release_url="https://other.example.org/app"),
    dict(release_url=None), dict(content_version="mobile-launch-v1"), dict(environment="development"),
    dict(platform="Web"), dict(recipients=[]), dict(subject="caller copy")])
def test_web_contract_requires_exact_identity_url_environment_and_nine_fields(override):
    with pytest.raises(ValueError):
        service.release_payload(web_payload(**override), "testing", NOW, web_launch_url=WEB_URL)


def test_web_configuration_is_required_and_mobile_content_cannot_cross_types():
    with pytest.raises(ValueError): service.release_payload(web_payload(), "testing", NOW)
    for platform in ("android", "ios"):
        with pytest.raises(ValueError):
            service.release_payload(payload(platform, content_version="web-launch-v1"), "testing", NOW,
                                    web_launch_url=WEB_URL)
    assert service.canonical_web_url(WEB_URL)
    assert service.canonical_web_url("https://gramanna.example.org")


def test_web_replay_restart_conflicts_and_three_independent_launches():
    model = Model(); store = web_store(model)
    original = web_payload()
    assert store.accept_event(original) == EVENT
    model.elapse(minutes=1)
    assert web_store(model).accept_event(original) == EVENT
    assert model.rows(events)[0]["audience_cutoff"] == NOW
    for values in (web_payload(audience_cutoff=(NOW-timedelta(seconds=1)).isoformat()),
                   web_payload(event_id=str(UUID(int=9)))):
        with pytest.raises(service.EventConflict): store.accept_event(values)
    store.accept_event(payload(event_id=str(UUID(int=10))))
    store.accept_event(payload("ios", event_id=str(UUID(int=11))))
    assert store.pending_release_events() == [EVENT, str(UUID(int=10)), str(UUID(int=11))]


@pytest.mark.parametrize("case", ["eligible", "mobile_only", "unverified", "late_signup", "late_verification",
    "early_preference", "late_preference", "withdrawn", "suppressed", "new_lifecycle"])
def test_web_audience_uses_verified_current_lifecycle_and_original_grant_cutoff(case):
    from oaf_website.notification_management import NotificationManagementStore
    model = Model(); store = web_store(model)
    if case == "late_signup": model.elapse(seconds=1)
    digest = subscribe(model, web_launch=case not in {"mobile_only", "early_preference", "late_preference"})
    token = store.request_confirmation("subscriber1@example.invalid")
    if case == "late_verification": model.elapse(seconds=1)
    if case != "unverified": assert store.confirm(token) == "verified"
    if case in {"early_preference", "late_preference"}:
        if case == "late_preference": model.elapse(seconds=1)
        management = NotificationManagementStore(model, SECRET, "testing")
        management.save(management.capabilities.issue(digest, 0, model.now), "a" * 64, 0,
                        dict(web_launch=True, android_launch=True, ios_launch=True, state=None, consent=True))
    if case in {"withdrawn", "new_lifecycle"}: SubscriptionStore(model).unsubscribe(digest)
    if case == "new_lifecycle":
        model.elapse(seconds=60); subscribe(model, 2, email="subscriber1@example.invalid", web_launch=True)
    if case == "suppressed": store.suppress("subscriber1@example.invalid", "complaint")
    store.accept_event(web_payload())
    store.prepare_event(EVENT)
    assert len(model.rows(deliveries)) == int(case in {"eligible", "early_preference"})
    assert model.rows(events)[0]["audience_cutoff"] == NOW


@pytest.mark.parametrize("state", ["pending", "claimed", "submitting", "accepted", "uncertain", "failed"])
def test_web_official_correction_withdrawal_preserves_original_and_attempt_uncertainty(state):
    model = Model(); store = web_store(model)
    digest = subscribe(model, web_launch=True)
    assert store.confirm(store.request_confirmation("subscriber1@example.invalid")) == "verified"
    store.accept_event(web_payload()); store.prepare_event(EVENT)
    if state != "pending":
        claim = store.claim(EVENT, digest)
        if state != "claimed": store.begin_submission(EVENT, digest, claim)
        if state in {"accepted", "uncertain", "failed"}:
            store.record_outcome(EVENT, digest, claim, {"accepted":"provider_accepted", "uncertain":"submission_unknown",
                                                      "failed":"retryable_rejection"}[state])
    old_attempts = deepcopy(model.rows(attempts)); original = deepcopy(model.rows(events)[0])
    model.elapse(seconds=1)
    correction = web_payload(action="correct", previous_approval_id=str(UUID(int=2)),
        source_approval_id=str(UUID(int=3)), approved_at=model.now.isoformat())
    store.accept_release_change(correction)
    assert store.dispatch_batch(EVENT)[0]["source_approval_id"] == str(UUID(int=3))
    model.elapse(seconds=1)
    withdrawal = dict(correction, action="withdraw", previous_approval_id=str(UUID(int=3)),
        source_approval_id=str(UUID(int=4)), approved_at=model.now.isoformat())
    store.accept_release_change(withdrawal); store.accept_release_change(withdrawal)
    assert store.accept_event(web_payload()) == EVENT
    model.elapse(minutes=6); web_store(model).recover_event(EVENT)
    assert store.dispatch_batch(EVENT)[1] == []
    assert store.claim(EVENT, digest) is None
    assert model.rows(events)[0]["audience_cutoff"] == original["audience_cutoff"]
    assert model.rows(events)[0]["payload_digest"] == original["payload_digest"]
    if state in {"accepted", "uncertain", "failed"}: assert model.rows(attempts) == old_attempts
    if state == "submitting": assert model.rows(deliveries)[0]["status"] == "uncertain"
