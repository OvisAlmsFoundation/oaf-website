"""Synthetic, serialized transactions and fake provider only; no credentials/network."""
import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import hmac
import json
from unittest.mock import Mock

import pytest

from oaf_website import confirmation_outbox as o
from oaf_website.confirmation_outbox_schema import intents, confirmation_attempts
from oaf_website.notification_delivery_schema import verification, limits
from oaf_website.notifications import SubscriptionStore
from oaf_website.notification_dispatch import BatchResult
from oaf_website.brevo import ProviderOutcome, BrevoConfigurationError
from test_notification_delivery import Model, NOW, SECRET, subscribe
from test_brevo import CONFIG, KEY, PAGE, response


@pytest.fixture
def setup():
    model = Model()
    store = o.ConfirmationOutboxStore(model, SECRET, "testing")
    transport = Mock(return_value=response())
    dispatcher = o.ConfirmationDispatcher(store, CONFIG, PAGE, transport=transport)
    return model, store, transport, dispatcher


def reserve(model, store):
    subscription = subscribe(model)
    token = store.request_confirmation("subscriber1@example.invalid")
    return subscription, token, model.rows(intents)[-1]["intent"]


@pytest.mark.parametrize('page_path', ['/gramanna.html', '/confirm-email.html'])
def test_restart_recovers_original_capability_and_authoritative_recipient(setup, page_path):
    model, store, transport, _ = setup
    subscription, token, intent = reserve(model, store)
    assert token not in repr(model.records) and intent != token
    assert model.rows(intents)[0]["token_digest"] == model.rows(verification)[0]["token_digest"]
    restarted = o.ConfirmationOutboxStore(model, SECRET, "testing")
    def send(key, body):
        assert model.rows(intents)[0]["status"] == "submitting"
        assert model.rows(confirmation_attempts)[0]["submitting_at"] == model.now
        data = json.loads(body)
        assert data["to"] == [{"email": "subscriber1@example.invalid"}]
        assert data["sender"] == {"name":"Ovis Alms Foundation", "email":"communications@updates.ovisalmsfoundation.org"}
        assert data["replyTo"] == {"email":"contact@ovisalmsfoundation.org"}
        assert PAGE.replace('/gramanna.html', '/confirm-email.html') + "#confirm-email=" + token in data["textContent"]
        assert token in data["htmlContent"]
        return response()
    transport.side_effect = send
    dispatcher = o.ConfirmationDispatcher(restarted, CONFIG, PAGE.replace('/gramanna.html', page_path), transport=transport)
    assert dispatcher.process() == BatchResult("processed", 1)
    assert model.rows(intents)[0]["status"] == "accepted"
    assert model.rows(verification)[0]["verified_at"] is None
    assert dispatcher.process() == BatchResult("processed", 0)
    assert store.confirm(token) == "verified"
    assert store.confirm(token) == "verified"
    assert transport.call_count == 1
    assert token not in repr(model.records) and KEY not in repr(model.records)


def test_derivation_explicit_domain_environment_lifecycle_and_version_binding(setup):
    model, store, _, _ = setup
    subscription, token, intent = reserve(model, store)
    expected = hmac.new(SECRET, ("oaf-notification-confirmation-recovery-v1:testing:" + subscription + ":" + intent).encode(), hashlib.sha256).hexdigest()
    assert token == expected
    assert o.capability(store, "f"*64, intent) != token
    assert o.capability(store, subscription, "e"*64) != token
    other = o.ConfirmationOutboxStore(model, SECRET, "development")
    assert o.capability(other, subscription, intent) != token
    assert token != store._digest("confirmation", intent)


@pytest.mark.parametrize("failure", ["execute", "commit", "uncertain"])
def test_atomic_reservation_interruption_and_commit_acknowledgement(setup, failure):
    model, store, transport, dispatcher = setup
    subscribe(model)
    model.failure = failure
    with pytest.raises(RuntimeError): store.request_confirmation("subscriber1@example.invalid")
    if failure == "uncertain":
        assert len(model.rows(verification)) == len(model.rows(intents)) == 1
        assert len(model.rows(limits)) == 2
    else:
        assert not model.rows(verification) and not model.rows(intents) and not model.rows(limits)
    model.failure = None
    assert dispatcher.process().processed == int(failure == "uncertain")
    assert transport.call_count == int(failure == "uncertain")


def test_outbox_insert_failure_rolls_back_reservation_and_quota(setup, monkeypatch):
    model, store, _, _ = setup
    subscribe(model)
    original = o.insert
    def fail(item):
        if item is intents: raise RuntimeError("synthetic outbox insert failure")
        return original(item)
    monkeypatch.setattr(o, "insert", fail)
    with pytest.raises(RuntimeError): store.request_confirmation("subscriber1@example.invalid")
    assert not model.rows(intents) and not model.rows(verification) and not model.rows(limits)


@pytest.mark.parametrize("state", ["pending", "claimed", "failed", "submitting", "uncertain", "accepted"])
def test_resend_replaces_version_and_preserves_attempt_evidence(setup, state):
    model, store, transport, dispatcher = setup
    subscription, token, old = reserve(model, store)
    claim = None
    if state != "pending": claim = store.claim_confirmation(old)
    if state in {"failed", "submitting", "uncertain", "accepted"}:
        assert store.prepare_confirmation(old, claim, PAGE)
    if state in {"failed", "uncertain", "accepted"}:
        store.confirmation_outcome(old, claim, {"failed":"not_submitted", "uncertain":"submission_unknown", "accepted":"provider_accepted"}[state])
    evidence = [dict(r) for r in model.rows(confirmation_attempts)]
    model.elapse(seconds=60)
    replacement = store.request_confirmation("subscriber1@example.invalid")
    assert replacement != token and store.confirm(token) == "unavailable"
    assert model.rows(intents)[0]["status"] == ("suppressed" if state in {"pending", "claimed", "failed"} else state)
    if state != "claimed": assert model.rows(confirmation_attempts) == evidence
    assert store.prepare_confirmation(old, claim, PAGE) is None
    assert dispatcher.process().processed == 1
    assert replacement in json.loads(transport.call_args.args[1])["textContent"]
    assert store.confirm(replacement) == "verified"


@pytest.mark.parametrize("when", ["claim_confirmation", "prepare_confirmation"])
@pytest.mark.parametrize("reason", ["withdrawn", "suppressed", "expired", "future", "verified", "superseded", "resubscribed", "missing_verification", "missing_subscriber"])
def test_last_eligibility_boundary_prevents_revoked_or_expired_dispatch(setup, monkeypatch, when, reason):
    model, store, transport, dispatcher = setup
    subscription, token, intent = reserve(model, store)
    original = getattr(store, when)
    def intervene(*args):
        if reason in {"withdrawn", "resubscribed"}: SubscriptionStore(model).unsubscribe(subscription)
        if reason == "resubscribed": subscribe(model, 2, email="subscriber1@example.invalid")
        if reason == "suppressed": store.suppress("subscriber1@example.invalid", "complaint")
        if reason == "expired": model.elapse(days=1)
        if reason == "future": model.rows(verification)[0]["issued_at"] += timedelta(seconds=1)
        if reason == "verified": assert store.confirm(token) == "verified"
        if reason == "superseded": model.rows(verification)[0]["token_digest"] = "f"*64
        if reason == "missing_verification": model.rows(verification).clear()
        if reason == "missing_subscriber": model.rows(o.notifications).clear()
        return original(*args)
    monkeypatch.setattr(store, when, intervene)
    assert dispatcher.process().processed == 0
    transport.assert_not_called()
    # Expiring a claim during the intervention leaves it for safe lease recovery.
    assert model.rows(intents)[0]["status"] in {"suppressed", "claimed"}


@pytest.mark.parametrize("outcome, status", [("not_submitted", "failed"), ("retryable_rejection", "failed"),
    ("provider_rejected", "rejected"), ("submission_unknown", "uncertain")])
def test_provider_retry_budget_and_uncertain_outcomes(setup, outcome, status):
    model, store, transport, dispatcher = setup
    reserve(model, store)
    transport.return_value = ProviderOutcome(outcome)
    assert dispatcher.process().processed == 1
    assert model.rows(intents)[0]["status"] == status
    if status == "failed":
        for seconds in (60, 300):
            model.elapse(seconds=seconds-1)
            assert dispatcher.process().processed == 0
            model.elapse(seconds=1)
            assert dispatcher.process().processed == 1
        assert len(model.rows(confirmation_attempts)) == 3
        assert model.rows(intents)[0]["next_attempt_at"] is None
    model.elapse(days=2)
    assert dispatcher.process().processed == 0
    assert transport.call_count == (3 if status == "failed" else 1)
    assert model.rows(verification)[0]["verified_at"] is None


@pytest.mark.parametrize("submitting", [False, True])
def test_durable_claim_crash_recovery_does_not_retry_uncertain_submission(setup, submitting):
    model, store, transport, dispatcher = setup
    _, _, intent = reserve(model, store)
    claim = store.claim_confirmation(intent)
    if submitting: assert store.prepare_confirmation(intent, claim, PAGE)
    assert dispatcher.process().processed == 0
    model.elapse(minutes=5)
    assert dispatcher.process().processed == 0
    assert model.rows(intents)[0]["status"] == ("uncertain" if submitting else "failed")
    assert model.rows(confirmation_attempts)[0]["outcome"] == ("submission_unknown" if submitting else "claim_expired")
    assert store.confirmation_outcome(intent, claim, "provider_accepted") is False
    model.elapse(seconds=60)
    assert dispatcher.process().processed == int(not submitting)
    assert transport.call_count == int(not submitting)


def test_preparation_failure_audited_and_safe_retry_recovers_same_link(setup, monkeypatch):
    model, store, transport, dispatcher = setup
    _, token, _ = reserve(model, store)
    original = o.verification_message
    monkeypatch.setattr(o, "verification_message", Mock(side_effect=RuntimeError(token)))
    assert dispatcher.process() == BatchResult("processed", 0)
    assert model.rows(intents)[0]["status"] == "failed"
    assert model.rows(confirmation_attempts)[0]["outcome"] == "not_submitted"
    transport.assert_not_called()
    monkeypatch.setattr(o, "verification_message", original)
    model.elapse(seconds=60)
    assert dispatcher.process().processed == 1
    assert token in json.loads(transport.call_args.args[1])["textContent"]


@pytest.mark.parametrize("method", ["candidates", "claim_confirmation", "prepare_confirmation", "confirmation_outcome"])
@pytest.mark.parametrize("failure", ["commit", "uncertain"])
def test_failed_commit_at_every_boundary_never_blindly_submits(setup, monkeypatch, method, failure):
    model, store, transport, dispatcher = setup
    reserve(model, store)
    original = getattr(store, method)
    def fail(*args):
        model.failure = failure
        return original(*args)
    monkeypatch.setattr(store, method, fail)
    assert dispatcher.process() == BatchResult("unavailable", 0)
    assert transport.call_count == int(method == "confirmation_outcome")
    model.failure = None
    monkeypatch.setattr(store, method, original)
    model.elapse(minutes=6)
    dispatcher.process()
    if method == "confirmation_outcome": assert transport.call_count == 1
    if method == "prepare_confirmation" and failure == "uncertain":
        assert model.rows(intents)[0]["status"] == "uncertain"
        transport.assert_not_called()


def test_simultaneous_reservations_and_workers_remain_deduplicated(setup):
    model, store, transport, dispatcher = setup
    subscribe(model)
    with ThreadPoolExecutor(max_workers=8) as pool:
        tokens = list(pool.map(lambda _:store.request_confirmation("subscriber1@example.invalid"), range(8)))
    assert sum(t is not None for t in tokens) == 1 and len(model.rows(intents)) == 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _:dispatcher.process(), range(8)))
    assert sum(r.processed for r in results) == transport.call_count == 1
    assert len(model.rows(confirmation_attempts)) == 1


def test_resend_race_after_candidate_selection_cancels_obsolete_intent(setup, monkeypatch):
    model, store, transport, dispatcher = setup
    _, old_token, intent = reserve(model, store)
    original = store.claim_confirmation
    def race(identity):
        model.elapse(seconds=60)
        store.request_confirmation("subscriber1@example.invalid")
        return original(identity)
    monkeypatch.setattr(store, "claim_confirmation", race)
    assert dispatcher.process().processed == 0
    transport.assert_not_called()
    assert store.confirm(old_token) == "unavailable"
    assert model.rows(intents)[0]["status"] == "suppressed"


def test_legacy_irreversible_digest_never_fabricates_recovery(setup):
    model, store, transport, dispatcher = setup
    subscription = subscribe(model)
    token = "e"*64
    model.rows(verification).append(dict(subscription=subscription,
        token_digest=store._digest("confirmation", token), issued_at=NOW,
        expires_at=NOW+timedelta(hours=24), verified_at=None))
    assert dispatcher.process().processed == 0
    transport.assert_not_called()
    assert not model.rows(intents)
    replacement = store.request_confirmation("subscriber1@example.invalid")
    assert replacement != token and store.confirm(token) == "unavailable"
    assert dispatcher.process().processed == 1


@pytest.mark.parametrize("secret", [None, b"short", "not-bytes"])
def test_unavailable_recovery_key_fails_before_persistence(setup, secret):
    model, _, transport, _ = setup
    with pytest.raises(ValueError): o.ConfirmationOutboxStore(model, secret, "testing")
    transport.assert_not_called()
    assert not model.statements


def test_wrong_key_or_environment_cannot_send_and_restored_key_recovers(setup):
    model, store, transport, dispatcher = setup
    reserve(model, store)
    wrong = o.ConfirmationOutboxStore(model, b"wrong-key-but-long-enough-for-protected-requirement", "testing")
    other = o.ConfirmationDispatcher(wrong, CONFIG, PAGE, transport=transport)
    assert other.process() == BatchResult("unavailable", 0)
    assert model.rows(intents)[0]["status"] == "pending"
    transport.assert_not_called()
    assert dispatcher.process().processed == 1


@pytest.mark.parametrize("limit", [True, 0, -1, 21, 1.5, None])
def test_invalid_batch_limit_precedes_database_or_provider_access(setup, limit):
    model, _, transport, dispatcher = setup
    with pytest.raises(ValueError): dispatcher.process(limit=limit)
    assert not model.statements
    transport.assert_not_called()


def test_invalid_config_environment_or_page_precedes_provider_access(setup):
    _, store, transport, _ = setup
    with pytest.raises(BrevoConfigurationError): o.ConfirmationDispatcher(store, None, PAGE, transport=transport)
    other = o.ConfirmationOutboxStore(store.engine, SECRET, "development")
    with pytest.raises(BrevoConfigurationError): o.ConfirmationDispatcher(other, CONFIG, PAGE, transport=transport)
    with pytest.raises(ValueError): o.ConfirmationDispatcher(store, CONFIG, "https://evil.invalid/", transport=transport)
    transport.assert_not_called()


@pytest.mark.parametrize("claim", [None, "", "f"*64, "F"*64, 42])
def test_invalid_or_replayed_claim_cannot_prepare_or_finish(setup, claim):
    model, store, transport, _ = setup
    _, _, intent = reserve(model, store)
    assert store.prepare_confirmation("unknown", claim, PAGE) is None
    assert store.claim_confirmation("unknown") is None
    assert store.prepare_confirmation(intent, claim, PAGE) is None
    assert store.confirmation_outcome(intent, claim, "provider_accepted") is False
    real = store.claim_confirmation(intent)
    assert store.prepare_confirmation(intent, claim, PAGE) is None
    assert store.prepare_confirmation(intent, real, PAGE)
    assert store.prepare_confirmation(intent, real, PAGE) is None
    assert store.confirmation_outcome(intent, claim, "provider_accepted") is False
    transport.assert_not_called()


@pytest.mark.parametrize("outcome, message", [("bad",None), ("provider_accepted",42),
    ("provider_accepted", "private error\n"), ("provider_accepted","x"*201)])
def test_private_or_unrecognized_outcome_rejected(setup, outcome, message):
    model, store, _, _ = setup
    with pytest.raises(ValueError): store.confirmation_outcome("unknown",None,outcome,message)
    assert not model.statements


def test_adapter_exception_is_uncertain_and_failed_outcome_write_does_not_repeat(setup, monkeypatch):
    model, store, _, dispatcher = setup
    reserve(model, store)
    monkeypatch.setattr(dispatcher.adapter,"submit", Mock(side_effect=RuntimeError("private bearer")))
    assert dispatcher.process().processed == 1
    assert model.rows(intents)[0]["status"] == "uncertain"
    assert dispatcher.process().processed == 0
    model.elapse(seconds=60)
    store.request_confirmation("subscriber1@example.invalid")
    monkeypatch.setattr(store,"confirmation_outcome",lambda *args:False)
    assert dispatcher.process() == BatchResult("unavailable",0)


def test_batch_bounds_and_due_claim_boundaries(setup):
    model, store, transport, dispatcher = setup
    for n in range(1, 23):
        subscribe(model,n)
        store.request_confirmation(f"subscriber{n}@example.invalid")
    assert dispatcher.process().processed == 20
    assert dispatcher.process(limit=1).processed == 1
    assert dispatcher.process().processed == 1
    assert transport.call_count == 22
    assert store.claim_confirmation(model.rows(intents)[0]["intent"]) is None


def test_expired_claim_cannot_prepare_and_failed_work_waits_for_due_time(setup):
    model, store, _, dispatcher = setup
    _, _, intent = reserve(model, store)
    claim = store.claim_confirmation(intent)
    model.elapse(minutes=5)
    assert store.prepare_confirmation(intent,claim,PAGE) is None
    store.candidates(20)
    assert store.claim_confirmation(intent) is None
    model.rows(intents)[0]["next_attempt_at"] = None
    assert store.claim_confirmation(intent) is None
    model.rows(intents)[0]["attempts"] = 3
    assert store.claim_confirmation(intent) is None


@pytest.mark.parametrize("identifier", ["bearer", "embedded", "safe", "none"])
def test_provider_identifier_cannot_persist_confirmation_bearer(setup, identifier):
    model, store, transport, dispatcher = setup
    _, token, _ = reserve(model, store)
    message_id = {"bearer":token,"embedded":"<"+token+"@provider.invalid>","safe":"<synthetic-id@provider.invalid>","none":None}[identifier]
    transport.return_value = (response(data={"messageId":message_id}) if identifier == "bearer"
                              else ProviderOutcome("provider_accepted",message_id))
    assert dispatcher.process().processed == 1
    assert model.rows(intents)[0]["status"] == ("uncertain" if identifier == "bearer" else "accepted")
    expected = message_id if identifier in {"safe","none"} else None
    assert model.rows(intents)[0]["provider_message_id"] == expected
    assert model.rows(confirmation_attempts)[0]["provider_message_id"] == expected
    assert token not in repr(model.records)


def test_random_context_collision_cannot_commit_digest_or_budget_without_new_intent(setup, monkeypatch):
    from copy import deepcopy
    model, store, _, _ = setup
    _, token, intent = reserve(model, store)
    before = deepcopy(model.records)
    model.elapse(seconds=60)
    monkeypatch.setattr(o.secrets,"token_hex",lambda size:intent)
    with pytest.raises(RuntimeError,match="unique constraint"):
        store.request_confirmation("subscriber1@example.invalid")
    assert model.records == before
    assert store.confirm(token) == "verified"


def test_wrong_environment_preserves_pending_intent_and_context_is_not_a_bearer(setup):
    from dataclasses import replace
    model, store, transport, dispatcher = setup
    _, token, intent = reserve(model, store)
    wrong = o.ConfirmationOutboxStore(model, SECRET, "development")
    other = o.ConfirmationDispatcher(wrong, replace(CONFIG,environment="development"), PAGE, transport=transport)
    assert other.process() == BatchResult("unavailable",0)
    assert model.rows(intents)[0]["status"] == "pending"
    assert store.confirm(intent) == "unavailable"
    claim = store.claim_confirmation(intent)
    assert store.confirm(claim) == "unavailable"
    assert model.rows(verification)[0]["verified_at"] is None
    transport.assert_not_called()
    assert store.prepare_confirmation(intent,claim,PAGE)


def test_repeated_claim_crashes_exhaust_three_attempts_without_submission(setup):
    model, store, transport, dispatcher = setup
    _, _, intent = reserve(model, store)
    for delay in (60,300,0):
        claim = store.claim_confirmation(intent)
        assert claim
        model.elapse(minutes=5)
        assert dispatcher.process().processed == 0
        model.elapse(seconds=delay)
    assert len(model.rows(confirmation_attempts)) == 3
    assert model.rows(intents)[0]["status"] == "failed"
    assert model.rows(intents)[0]["next_attempt_at"] is None
    assert dispatcher.process().processed == 0
    transport.assert_not_called()



def test_verification_unique_conflict_cannot_commit_an_orphaned_intent_or_quota(setup, monkeypatch):
    from copy import deepcopy
    model, store, _, _ = setup
    reserve(model, store)
    subscribe(model,2)
    existing_digest = model.rows(verification)[0]["token_digest"]
    original = store._digest
    monkeypatch.setattr(store,"_digest",lambda domain,value: existing_digest if domain == "confirmation" else original(domain,value))
    before = deepcopy(model.records)
    with pytest.raises(RuntimeError,match="unique constraint"):
        store.request_confirmation("subscriber2@example.invalid")
    assert model.records == before
    assert len(model.rows(intents)) == len(model.rows(verification)) == 1
