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
        self.records = {t.name: [] for t in (service.notifications, *TABLES, *OUTBOX_TABLES, changes)}
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
