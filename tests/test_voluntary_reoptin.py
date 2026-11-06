"""Explicit consent, synthetic provider operations and serialized offline persistence."""
import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import json
from unittest.mock import Mock

import pytest

from oaf_website import brevo as b, confirmation_outbox as o, reoptin
from oaf_website.notification_delivery_schema import verification, suppressions, limits
from oaf_website.notification_management_schema import changes
from oaf_website.notifications import SubscriptionStore, validate_subscription, notifications
from oaf_website.notification_management import NotificationManagementStore
from oaf_website.reoptin_schema import intents
from test_notification_delivery import Model, SECRET, subscribe, payload
from test_notifications import choices, post
from test_brevo import CONFIG, KEY, PAGE, response, Connection

EMAIL = "subscriber1@example.invalid"


def signup(model, store, number=2):
    values = validate_subscription(choices(email=EMAIL, token=f"{number:064x}",
                                         android_launch=True, ios_launch=True))
    SubscriptionStore(model, confirmation_store=store).subscribe(values)
    return values["unsubscribe_digest"]


def setup_reoptin(reason="provider_block"):
    model = Model()
    store = o.ConfirmationOutboxStore(model, SECRET, "testing", management_enabled=True)
    old = subscribe(model)
    old_token = store.request_confirmation(EMAIL)
    initial = o.ConfirmationDispatcher(store, CONFIG, PAGE, transport=Mock(return_value=response()))
    assert initial.process().processed == 1
    assert store.confirm(old_token) == "verified"
    SubscriptionStore(model).unsubscribe(old)
    if reason:
        store.suppress(EMAIL, reason)
    model.elapse(seconds=61)
    history = deepcopy(model.records)
    current = signup(model, store)
    unblock = Mock(return_value=b.ProviderResponse(204, "", b""))
    send = Mock(return_value=response())
    dispatcher = o.ConfirmationDispatcher(store, CONFIG, PAGE, transport=send, unblock_transport=unblock)
    return model, store, old, current, unblock, send, dispatcher, history


def rows_for(model, subscription, purpose):
    return [r for r in model.rows(intents) if r["subscription"] == subscription and r["purpose"] == purpose]


def drain(dispatcher):
    # Different purpose records may be selected in either random intent order.
    for _ in range(3):
        result = dispatcher.process()
        assert result.status == "processed"


@pytest.mark.parametrize("reason", [None, "provider_block", "complaint"])
def test_full_fresh_consent_unblock_confirmation_and_notification_flow(reason):
    model, store, old, current, unblock, send, dispatcher, history = setup_reoptin(reason)
    confirmation = rows_for(model, current, "confirmation")[0]
    token = o.capability(store, current, confirmation["intent"])
    assert store.confirm(token) == "unavailable"
    with store._transaction() as (connection, now):
        subscriber = store._get(connection, notifications, unsubscribe_digest=current)
        assert not store._eligible(connection, subscriber, dict(payload(), audience_cutoff=now))
    def accept(key, email):
        assert key == KEY and email == EMAIL
        assert rows_for(model, current, "reoptin")[0]["status"] == "submitting"
        assert send.call_count == 0
        return b.ProviderResponse(204, "", b"")
    unblock.side_effect = accept
    drain(dispatcher)
    assert unblock.call_count == send.call_count == 1
    assert token in json.loads(send.call_args.args[1])["textContent"]
    assert model.rows(verification)[-1]["verified_at"] is None
    assert store.confirm(token) == "verified"
    assert store.confirm(token) == "already_verified"
    with store._transaction() as (connection, now):
        subscriber = store._get(connection, notifications, unsubscribe_digest=current)
        assert store._eligible(connection, subscriber, dict(payload(), audience_cutoff=now))
        assert not store._eligible(connection, subscriber, dict(payload(), audience_cutoff=history[notifications.name][0]["created_at"]))
    assert model.rows(suppressions) == history[suppressions.name]
    assert model.rows(verification)[0] == history[verification.name][0]
    assert model.rows(notifications)[0] == history[notifications.name][0]
    assert model.rows(changes) == history[changes.name]
    assert token not in repr(model.records) and KEY not in repr(model.records)
    assert store.confirm(o.capability(store, old, history[intents.name][0]["intent"])) == "unavailable"


@pytest.mark.parametrize("reason", ["hard_bounce", "owner_policy"])
def test_other_local_restrictions_keep_their_existing_resolution(reason):
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin(reason)
    assert not rows_for(model, current, "reoptin")
    drain(dispatcher)
    unblock.assert_not_called()
    send.assert_not_called()


def test_lookup_and_recovery_cannot_authorize_reoptin_or_repeat_unblock():
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin()
    # Simulate a pre-upgrade pending lifecycle, which has no new consent authority.
    model.records[intents.name] = [r for r in model.rows(intents) if r["subscription"] != current]
    model.records[verification.name] = [r for r in model.rows(verification) if r["subscription"] != current]
    model.elapse(seconds=61)
    assert store.request_confirmation(EMAIL) is None
    management = NotificationManagementStore(model, SECRET, "testing")
    model.elapse(seconds=61)
    management.request_recovery(EMAIL)
    assert not rows_for(model, current, "reoptin")
    drain(dispatcher)
    unblock.assert_not_called()
    # A fresh explicit action with that lifecycle's receipt authorizes recovery.
    model.elapse(seconds=61)
    signup(model, store)
    drain(dispatcher)
    assert unblock.call_count == send.call_count == 1
    model.elapse(seconds=61)
    store.request_confirmation(EMAIL)
    drain(dispatcher)
    assert unblock.call_count == 1


def test_duplicate_consent_concurrency_reserves_one_unblock_and_preserves_preferences():
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin()
    model.elapse(seconds=61)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _: signup(model, store), range(12)))
    assert len(rows_for(model, current, "reoptin")) == 1
    assert len(rows_for(model, current, "confirmation")) == 1
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: dispatcher.process(), range(4)))
    drain(dispatcher)
    assert unblock.call_count == send.call_count == 1
    assert len(model.rows(notifications)) == 2


@pytest.mark.parametrize("outcome,status,count", [("provider_rejected", "rejected", 1),
    ("submission_unknown", "uncertain", 1), ("not_submitted", "failed", 3),
    ("retryable_rejection", "failed", 3)])
def test_unblock_failure_retry_bounds_and_uncertainty_hold(outcome, status, count):
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin()
    unblock.return_value = b.ProviderOutcome(outcome)
    for seconds in (0, 60, 300, 1500):
        model.elapse(seconds=seconds)
        drain(dispatcher)
    record = rows_for(model, current, "reoptin")[0]
    assert record["status"] == status and record["attempts"] == count
    assert unblock.call_count == count
    send.assert_not_called()
    assert model.rows(verification)[-1]["verified_at"] is None
    model.elapse(days=2)
    drain(dispatcher)
    assert unblock.call_count == count


@pytest.mark.parametrize("outcome,status", [("provider_rejected", "rejected"), ("submission_unknown", "uncertain")])
def test_confirmation_refusal_or_uncertainty_does_not_restore_ordinary_eligibility(outcome, status):
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin()
    send.return_value = b.ProviderOutcome(outcome)
    drain(dispatcher)
    assert rows_for(model, current, "confirmation")[0]["status"] == status
    assert model.rows(verification)[-1]["verified_at"] is None
    assert unblock.call_count == send.call_count == 1


@pytest.mark.parametrize("submitting", [False, True])
def test_restart_lease_recovery_does_not_repeat_uncertain_unblock(submitting):
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin()
    record = rows_for(model, current, "reoptin")[0]
    claim = store.claim_confirmation(record["intent"])
    if submitting:
        assert isinstance(store.prepare_confirmation(record["intent"], claim, PAGE), o.UnblockRecipient)
    model.elapse(minutes=5)
    restarted = o.ConfirmationOutboxStore(model, SECRET, "testing", management_enabled=True)
    dispatcher = o.ConfirmationDispatcher(restarted, CONFIG, PAGE, transport=send, unblock_transport=unblock)
    drain(dispatcher)
    assert rows_for(model, current, "reoptin")[0]["status"] == ("uncertain" if submitting else "failed")
    model.elapse(seconds=60)
    drain(dispatcher)
    assert unblock.call_count == send.call_count == int(not submitting)


@pytest.mark.parametrize("phase", ["pending", "submitting", "accepted", "verified"])
def test_new_suppression_revokes_only_authority_and_preserves_acceptance_evidence(phase):
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin()
    record = rows_for(model, current, "reoptin")[0]
    if phase == "submitting":
        def race(*args):
            store.suppress(EMAIL, "complaint")
            return b.ProviderResponse(204, "", b"")
        unblock.side_effect = race
    if phase in {"accepted", "verified"}:
        drain(dispatcher)
        if phase == "verified":
            confirmation = rows_for(model, current, "confirmation")[0]
            assert store.confirm(o.capability(store, current, confirmation["intent"])) == "verified"
    evidence = deepcopy(model.rows(o.confirmation_attempts))
    if phase != "submitting":
        store.suppress(EMAIL, "complaint")
    drain(dispatcher)
    assert rows_for(model, current, "reoptin")[0]["revoked_at"] is not None
    assert send.call_count == int(phase in {"accepted", "verified"})
    if phase == "submitting":
        assert rows_for(model, current, "reoptin")[0]["status"] == "accepted"
        assert model.rows(o.confirmation_attempts)[-1]["outcome"] == "provider_accepted"
    else:
        assert model.rows(o.confirmation_attempts)[:len(evidence)] == evidence
    with store._transaction() as (connection, now):
        subscriber = store._get(connection, notifications, unsubscribe_digest=current)
        assert store._suppressed(connection, subscriber)


@pytest.mark.parametrize("failure", ["execute", "commit", "uncertain"])
def test_signup_atomicity_and_same_receipt_retry_after_commit_uncertainty(failure):
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin()
    SubscriptionStore(model).unsubscribe(current)
    model.elapse(seconds=61)
    model.failure = failure
    with pytest.raises(RuntimeError):
        signup(model, store, 3)
    model.failure = None
    model.elapse(seconds=61)
    latest = signup(model, store, 3)
    assert len(rows_for(model, latest, "reoptin")) == 1
    drain(dispatcher)
    assert unblock.call_count == send.call_count == 1


def test_budget_survives_lifecycle_changes_and_throttled_signup_recovers_explicitly():
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin()
    SubscriptionStore(model).unsubscribe(current)
    latest = signup(model, store, 3)  # Still in mailbox cooldown.
    assert not rows_for(model, latest, "reoptin")
    model.elapse(seconds=60)
    signup(model, store, 3)
    assert len(rows_for(model, latest, "reoptin")) == 1
    mailbox = next(r for r in model.rows(limits) if r["bucket"] == store._digest("mailbox", EMAIL))
    assert mailbox["requests"] == 3
    drain(dispatcher)
    assert unblock.call_count == send.call_count == 1


@pytest.mark.parametrize("bucket,count", [("mailbox", 5), ("global", 1000)])
def test_mailbox_and_global_exhaustion_cannot_authorize_unblock(bucket, count):
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin()
    SubscriptionStore(model).unsubscribe(current)
    model.elapse(seconds=61)
    key = store._digest("mailbox", EMAIL) if bucket == "mailbox" else store._digest("budget", "global")
    next(r for r in model.rows(limits) if r["bucket"] == key)["requests"] = count
    latest = signup(model, store, 3)
    assert not rows_for(model, latest, "reoptin")
    drain(dispatcher)
    unblock.assert_not_called()
    send.assert_not_called()


@pytest.mark.parametrize("phase", ["prepare_confirmation", "confirmation_outcome"])
@pytest.mark.parametrize("failure", ["commit", "uncertain"])
def test_unacknowledged_database_boundaries_never_blindly_repeat_provider_mutations(monkeypatch, phase, failure):
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin()
    original = getattr(store, phase)
    def intervene(*args, **kwargs):
        model.failure = failure
        return original(*args, **kwargs)
    monkeypatch.setattr(store, phase, intervene)
    assert dispatcher.process().status == "unavailable"
    assert unblock.call_count == int(phase == "confirmation_outcome")
    send.assert_not_called()
    model.failure = None
    monkeypatch.setattr(store, phase, original)
    model.elapse(minutes=5)
    drain(dispatcher)
    model.elapse(seconds=60)
    drain(dispatcher)
    if phase == "prepare_confirmation" and failure == "commit":
        assert unblock.call_count == send.call_count == 1
    elif phase == "confirmation_outcome" and failure == "uncertain":
        assert unblock.call_count == send.call_count == 1
    else:
        assert unblock.call_count == int(phase == "confirmation_outcome")
        send.assert_not_called()


@pytest.mark.parametrize("stage", ["before_claim", "before_prepare", "after_unblock"])
def test_new_withdrawal_cancels_confirmation_and_never_revives_old_lifecycle(stage):
    model, store, old, current, unblock, send, dispatcher, history = setup_reoptin()
    record = rows_for(model, current, "reoptin")[0]
    if stage == "before_prepare":
        claim = store.claim_confirmation(record["intent"])
        SubscriptionStore(model).unsubscribe(current)
        assert store.prepare_confirmation(record["intent"], claim, PAGE) is None
    elif stage == "after_unblock":
        def withdraw(*args):
            SubscriptionStore(model).unsubscribe(current)
            return b.ProviderResponse(204, "", b"")
        unblock.side_effect = withdraw
    else:
        SubscriptionStore(model).unsubscribe(current)
    drain(dispatcher)
    send.assert_not_called()
    assert model.rows(notifications)[0] == history[notifications.name][0]


@pytest.mark.parametrize("validity", ["valid", "no_consent", "csrf", "origin", "preferences_differ"])
def test_public_fresh_consent_can_recover_stalled_lifecycle_but_lookups_cannot(validity, monkeypatch):
    from oaf_website import state_requests as runtime
    from test_state_requests import ORIGIN
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin()
    model.records[intents.name] = [r for r in model.rows(intents) if r["subscription"] != current]
    original = deepcopy(model.rows(notifications)[-1])
    app = runtime._build_app(None, runtime.BrowserRecognition(SECRET), ORIGIN,
        subscription_store=SubscriptionStore(model, confirmation_store=store))
    client = app.test_client()
    csrf = client.get('/api/notifications/session', base_url=ORIGIN).json['csrf_token']
    forbidden = Mock(side_effect=AssertionError("Web cannot call provider"))
    monkeypatch.setattr(b.BrevoAdapter, "unblock", forbidden)
    model.elapse(seconds=61)
    values = choices(email=EMAIL, token="f"*64, android_launch=True, ios_launch=True)
    if validity == "no_consent": values["consent"] = False
    if validity == "preferences_differ": values["android_launch"] = False
    options = {}
    if validity == "origin": options['headers'] = {'Origin':'https://other.invalid','X-CSRF-Token':csrf}
    reply = post(client, 'bad' if validity == 'csrf' else csrf, values, **options)
    assert reply.status_code == (400 if validity == "no_consent" else 403 if validity in {"csrf", "origin"} else 200)
    assert len(rows_for(model, current, "reoptin")) == int(validity == "valid")
    assert model.rows(notifications)[-1] == original
    forbidden.assert_not_called()


@pytest.mark.parametrize("phase,expected", [("connect", "not_submitted"), ("request", "submission_unknown"),
    ("response", "submission_unknown"), ("read", "submission_unknown"), ("close", "provider_accepted")])
def test_unblock_https_uncertainty_and_no_automatic_transport_retry(monkeypatch, phase, expected):
    from types import SimpleNamespace
    connection = Connection(phase)
    def getresponse():
        connection.hit("response")
        return SimpleNamespace(status=204, getheader=lambda name, default: default,
                               read=lambda limit: (connection.hit("read", limit), b"")[1])
    connection.getresponse = getresponse
    factory = Mock(return_value=connection)
    monkeypatch.setattr(b, "HTTPSConnection", factory)
    outcome = b.BrevoHTTPS().unblock(KEY, EMAIL)
    assert outcome.outcome == expected and KEY not in repr(outcome)
    assert factory.call_count == 1
    assert sum(phase == "request" for phase, _ in connection.calls) <= 1


def test_pending_confirmation_cannot_starve_its_unblock_at_batch_limit():
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin()
    # Pending confirmation sorts before its authority by intent; SQL purpose
    # priority must select unblock even with a one-item batch.
    record = rows_for(model, current, "confirmation")[0]
    record['intent'] = '0'*64
    assert store.candidates(1) == [rows_for(model, current, "reoptin")[0]['intent']]
    assert dispatcher.process(limit=1).processed == 1
    assert unblock.call_count == 1


@pytest.mark.parametrize("original", ["provider_block", "complaint"])
@pytest.mark.parametrize("new_reason", ["hard_bounce", "owner_policy"])
@pytest.mark.parametrize("existing_authority", [False, True])
def test_later_stronger_restriction_survives_future_fresh_lifecycles(original, new_reason, existing_authority):
    model, store, old, current, unblock, send, dispatcher, history = setup_reoptin(original)
    if not existing_authority:
        model.records[intents.name] = [r for r in model.rows(intents) if r["purpose"] != "reoptin"]
    store.suppress(EMAIL, new_reason)
    block = deepcopy(model.rows(suppressions)[0])
    assert block["reason"] == original and block["created_at"] == history[suppressions.name][0]["created_at"]
    assert block["reoptin_blocked_at"] == model.now
    model.elapse(seconds=61)
    SubscriptionStore(model).unsubscribe(current)
    latest = signup(model, store, 3)
    assert not rows_for(model, latest, "reoptin")
    drain(dispatcher)
    unblock.assert_not_called()
    send.assert_not_called()
    assert model.rows(suppressions)[0] == block


def test_another_voluntary_withdrawal_still_allows_another_fresh_confirmed_lifecycle():
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin()
    drain(dispatcher)
    previous_confirmation = rows_for(model, current, "confirmation")[0]
    assert store.confirm(o.capability(store, current, previous_confirmation["intent"])) == "verified"
    SubscriptionStore(model).unsubscribe(current)
    store.suppress(EMAIL, "provider_block")
    assert rows_for(model, current, "reoptin")[0]["revoked_at"] is not None
    evidence = deepcopy(model.rows(o.confirmation_attempts))
    model.elapse(seconds=61)
    latest = signup(model, store, 3)
    drain(dispatcher)
    token = o.capability(store, latest, rows_for(model, latest, "confirmation")[0]["intent"])
    assert store.confirm(token) == "verified"
    assert unblock.call_count == send.call_count == 2
    assert model.rows(o.confirmation_attempts)[:len(evidence)] == evidence
    assert model.rows(suppressions)[0]["reoptin_blocked_at"] is None


@pytest.mark.parametrize("phase", ["backoff", "claimed", "submitting", "exhausted"])
def test_waiting_dependency_does_not_starve_an_unrelated_mailbox(phase):
    model, store, old, current, unblock, send, dispatcher, _ = setup_reoptin()
    reoptin_row = rows_for(model, current, "reoptin")[0]
    confirmation = rows_for(model, current, "confirmation")[0]
    confirmation["intent"] = "0"*64
    if phase in {"backoff", "exhausted"}:
        reoptin_row.update(status="failed", outcome="not_submitted", attempts=3 if phase == "exhausted" else 1,
            next_attempt_at=None if phase == "exhausted" else model.now + timedelta(minutes=5))
    else:
        claim = store.claim_confirmation(reoptin_row["intent"])
        if phase == "submitting":
            store.prepare_confirmation(reoptin_row["intent"], claim, PAGE)
    other = subscribe(model, 9)
    other_token = store.request_confirmation("subscriber9@example.invalid")
    assert other_token
    if phase != "exhausted":
        assert store.candidates(1) == [rows_for(model, other, "confirmation")[0]["intent"]]
    else:
        # Terminal authority promptly suppresses its dependency, then leaves
        # the next finite batch free for the other mailbox.
        assert dispatcher.process(limit=1).processed == 0
        assert rows_for(model, current, "confirmation")[0]["status"] == "suppressed"
    assert dispatcher.process(limit=1).processed == 1
    assert json.loads(send.call_args.args[1])["to"] == [{"email":"subscriber9@example.invalid"}]
    unblock.assert_not_called()


@pytest.mark.parametrize("status,data,expected", [(204, None, "provider_accepted"),
    (404, {"code":"document_not_found", "message":"Absent"}, "provider_accepted"),
    (403, {"code":"permission_denied", "message":"Denied"}, "provider_rejected"),
    (404, {"code":"invalid_parameter", "message":"Denied"}, "provider_rejected"),
    (429, {"code":"too_many_requests", "message":"Wait"}, "retryable_rejection"),
    (500, {"code":"internal_error", "message":"Unknown"}, "submission_unknown"),
    (201, {"messageId":"<unexpected@relay.example>"}, "submission_unknown")])
def test_provider_unblock_acknowledgement_contract(status, data, expected):
    reply = b.ProviderResponse(status, "application/json", json.dumps(data).encode() if data else b"")
    assert b.classify_unblock(reply, KEY).outcome == expected


def test_https_unblock_uses_one_fixed_host_encoded_delete_without_email_send(monkeypatch):
    connection = Connection()
    from types import SimpleNamespace
    connection.getresponse = lambda: SimpleNamespace(status=204,
        getheader=lambda name, default: default, read=lambda limit: b"")
    monkeypatch.setattr(b, "HTTPSConnection", Mock(return_value=connection))
    result = b.BrevoHTTPS().unblock(KEY, "a+b@example.invalid")
    assert result.outcome == "provider_accepted"
    request = next(value for phase, value in connection.calls if phase == "request")
    assert request[0][0:2] == ("DELETE", "/v3/smtp/blockedContacts/a%2Bb%40example.invalid")
