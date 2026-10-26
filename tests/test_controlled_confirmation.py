"""Controlled TESTING processing: synthetic model, mailboxes and transport only."""
import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from threading import Barrier
from unittest.mock import Mock

import pytest

from oaf_website import brevo, confirmation_outbox as outbox, confirmation_processor as processor
from oaf_website.confirmation_outbox_schema import intents, confirmation_attempts
from oaf_website.notification_schema import notifications
from oaf_website.notification_delivery_schema import verification
from oaf_website.notification_dispatch import BatchResult
from oaf_website.notifications import SubscriptionStore
from test_brevo import CONFIG, PAGE, response
from test_confirmation_processor import runtime, invoke, reserve, assert_no_runtime
from test_notification_delivery import SECRET

MAILBOX = "subscriber1@example.invalid"


def controlled(runtime):
    return outbox.ConfirmationOutboxStore(runtime.model, SECRET, "testing",
        recipient_scope=brevo.TestingRecipientScope("testing", MAILBOX))


@pytest.mark.parametrize("value", [None, "", "bad", "a@b", "a@example.invalid,b@example.invalid",
    [MAILBOX], {"mailbox": MAILBOX}, 1, "a\r\nb@example.invalid", "a@example.invalid\n"])
def test_missing_or_malformed_scope_fails_before_any_runtime_access(runtime, value):
    assert invoke(testing_recipient=value) == BatchResult("unavailable")
    assert_no_runtime(runtime)


@pytest.mark.parametrize("profile", ["development", "production"])
def test_non_testing_scope_fails_before_runtime_access(runtime, profile):
    assert invoke(profile, testing_recipient=MAILBOX) == BatchResult("unavailable")
    assert_no_runtime(runtime)
    with pytest.raises(ValueError):
        brevo.TestingRecipientScope(profile, MAILBOX)


def test_disabled_scope_is_inert(runtime):
    assert invoke(enabled=False, testing_recipient="invalid") == BatchResult("disabled")
    assert_no_runtime(runtime)


def test_scope_is_normalized_private_and_immutable(runtime):
    scope = brevo.TestingRecipientScope("testing", " Subscriber1@Example.Invalid ")
    assert scope.mailbox == MAILBOX and MAILBOX not in repr(scope)
    with pytest.raises(AttributeError):
        scope.mailbox = "other@example.invalid"
    reserve(runtime)
    assert invoke(testing_recipient=" Subscriber1@Example.Invalid ") == BatchResult("processed", 1)
    assert json.loads(runtime.transport.call_args.args[1])["to"] == [{"email": MAILBOX}]


@pytest.mark.parametrize("scope", [MAILBOX, {}, Mock()])
def test_invalid_scope_object_rejected_at_store_and_adapter(runtime, scope):
    with pytest.raises(ValueError):
        outbox.ConfirmationOutboxStore(runtime.model, SECRET, "testing", recipient_scope=scope)
    with pytest.raises(ValueError):
        brevo.BrevoAdapter(CONFIG, recipient_scope=scope)
    assert_no_runtime(runtime)


def test_environment_mismatch_cannot_construct_controlled_store_or_adapter(runtime):
    scope = brevo.TestingRecipientScope("testing", MAILBOX)
    with pytest.raises(ValueError):
        outbox.ConfirmationOutboxStore(runtime.model, SECRET, "development", recipient_scope=scope)
    with pytest.raises(ValueError):
        brevo.BrevoAdapter(brevo.BrevoConfig("development", CONFIG.api_key), recipient_scope=scope)
    assert_no_runtime(runtime)


def test_exact_mailbox_filter_is_in_both_ordered_limited_queries(runtime):
    for number in (2, 1, 3): reserve(runtime, number)
    before = deepcopy(runtime.model.records)
    store = controlled(runtime)
    wanted = next(r["intent"] for r in runtime.model.rows(intents)
                  if r["subscription"] == runtime.model.rows(notifications)[1]["unsubscribe_digest"])
    runtime.model.statements.clear()
    assert store.candidates(20) == [wanted]
    statements = [s for s in runtime.model.statements if "LIMIT" in s]
    assert len(statements) == 2
    for statement in statements:
        assert "IN (SELECT oaf_website.notifications.unsubscribe_digest" in statement
        assert "WHERE oaf_website.notifications.email =" in statement
        assert "ORDER BY oaf_website.notification_confirmation_intents.intent" in statement
        assert MAILBOX not in statement  # Bound parameters, never inline identities.
    assert invoke() == BatchResult("processed", 1)
    assert runtime.transport.call_count == 1
    for name, rows in before.items():
        if name == intents.name:
            assert [r for r in runtime.model.records[name] if r["intent"] != wanted] == [
                r for r in rows if r["intent"] != wanted]
        elif name != confirmation_attempts.name:
            assert runtime.model.records[name] == rows
    assert len(runtime.model.rows(confirmation_attempts)) == 1
    assert runtime.model.rows(confirmation_attempts)[0]["intent"] == wanted


def test_absent_approved_mailbox_leaves_all_foreign_pending_and_expired_work_untouched(runtime):
    ordinary, _, _, intent = reserve(runtime, 2)
    ordinary.claim_confirmation(intent)
    reserve(runtime, 3)
    runtime.model.elapse(minutes=5)
    before = deepcopy(runtime.model.records)
    assert invoke() == BatchResult("processed", 0)
    assert runtime.model.records == before
    runtime.transport.assert_not_called()


@pytest.mark.parametrize("submitting", [False, True])
def test_other_expired_claims_and_attempts_are_untouched(runtime, submitting):
    ours, _, _, own = reserve(runtime)
    other, _, _, foreign = reserve(runtime, 2)
    for store, intent in ((ours, own), (other, foreign)):
        claim = store.claim_confirmation(intent)
        if submitting: assert store.prepare_confirmation(intent, claim, PAGE)
    original = deepcopy(runtime.model.records)
    runtime.model.elapse(minutes=5)
    assert invoke() == BatchResult("processed", 0)
    assert next(r for r in runtime.model.rows(intents) if r["intent"] == foreign) == next(
        r for r in original[intents.name] if r["intent"] == foreign)
    assert next(r for r in runtime.model.rows(confirmation_attempts) if r["intent"] == foreign) == next(
        r for r in original[confirmation_attempts.name] if r["intent"] == foreign)
    assert next(r for r in runtime.model.rows(intents) if r["intent"] == own)["status"] == (
        "uncertain" if submitting else "failed")
    runtime.model.elapse(seconds=60)
    assert invoke().processed == int(not submitting)
    assert runtime.transport.call_count == int(not submitting)


def test_selection_bypass_cannot_claim_or_mutate_another_subscriber(runtime, monkeypatch):
    _, _, _, foreign = reserve(runtime, 2)
    before = deepcopy(runtime.model.records)
    monkeypatch.setattr(outbox.ConfirmationOutboxStore, "candidates", lambda *_: [foreign])
    assert invoke() == BatchResult("unavailable")
    assert runtime.model.records == before
    runtime.transport.assert_not_called()


@pytest.mark.parametrize("phase", ["prepare", "outcome"])
def test_foreign_owned_claim_cannot_cross_controlled_persistence_boundary(runtime, phase):
    ordinary, _, _, foreign = reserve(runtime, 2)
    claim = ordinary.claim_confirmation(foreign)
    if phase == "outcome": ordinary.prepare_confirmation(foreign, claim, PAGE)
    before = deepcopy(runtime.model.records)
    store = controlled(runtime)
    with pytest.raises(ValueError):
        if phase == "prepare": store.prepare_confirmation(foreign, claim, PAGE)
        else: store.confirmation_outcome(foreign, claim, "not_submitted")
    assert runtime.model.records == before
    runtime.transport.assert_not_called()


def test_authoritative_mailbox_rechecked_at_last_precommit_boundary(runtime, monkeypatch):
    _, _, _, intent = reserve(runtime)
    store = controlled(runtime)
    claim = store.claim_confirmation(intent)
    before = deepcopy(runtime.model.records)
    original = store._get
    reads = 0
    def authoritative(connection, table, **keys):
        nonlocal reads
        row = original(connection, table, **keys)
        if table is notifications:
            reads += 1
            if reads == 3:
                from sqlalchemy.engine.result import IteratorResult, SimpleResultMetaData
                row = next(IteratorResult(SimpleResultMetaData(list(row)), iter([
                    tuple("other@example.invalid" if key == "email" else row[key] for key in row)
                ])).mappings())
        return row
    monkeypatch.setattr(store, "_get", authoritative)
    with pytest.raises(ValueError): store.prepare_confirmation(intent, claim, PAGE)
    assert reads == 3 and runtime.model.records == before
    runtime.transport.assert_not_called()


def test_adapter_prevents_foreign_recipient_even_if_preparation_is_bypassed(runtime, monkeypatch):
    reserve(runtime)
    original = outbox.ConfirmationOutboxStore.prepare_confirmation
    def corrupted(store, *args):
        _, message = original(store, *args)
        return "other@example.invalid", message
    monkeypatch.setattr(outbox.ConfirmationOutboxStore, "prepare_confirmation", corrupted)
    assert invoke() == BatchResult("unavailable")
    runtime.transport.assert_not_called()
    runtime.model.elapse(minutes=5)
    assert invoke() == BatchResult("processed", 0)
    assert runtime.model.rows(intents)[0]["status"] == "uncertain"
    runtime.transport.assert_not_called()


@pytest.mark.parametrize("email", ["other@example.invalid", "Subscriber1@Example.Invalid", None])
def test_adapter_own_guard_prevents_transport_and_does_not_redirect(runtime, email):
    from oaf_website.notification_messages import verification_message
    adapter = brevo.BrevoAdapter(CONFIG, transport=runtime.transport,
                                recipient_scope=brevo.TestingRecipientScope("testing", MAILBOX))
    with pytest.raises(ValueError): adapter.submit(email, verification_message("a" * 64, PAGE))
    runtime.transport.assert_not_called()


def test_competing_scoped_invocations_preserve_foreign_state(runtime, monkeypatch):
    reserve(runtime)
    _, _, _, foreign = reserve(runtime, 2)
    before = deepcopy(next(r for r in runtime.model.rows(intents) if r["intent"] == foreign))
    barrier = Barrier(8)
    original = outbox.ConfirmationOutboxStore.candidates
    def together(store, limit):
        candidates = original(store, limit)
        barrier.wait(timeout=10)
        return candidates
    monkeypatch.setattr(outbox.ConfirmationOutboxStore, "candidates", together)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: invoke(), range(8)))
    assert all(r.status == "processed" for r in results)
    assert sum(r.processed for r in results) == runtime.transport.call_count == 1
    assert next(r for r in runtime.model.rows(intents) if r["intent"] == foreign) == before
    assert len(runtime.model.rows(confirmation_attempts)) == 1


def test_cli_missing_and_duplicate_scope_are_private_failures(runtime, capsys):
    args = ["--environment", "testing", "--enable-processing", "--brevo-account",
            "synthetic-account", "--confirmation-page", PAGE]
    assert processor.main(args) == 1
    observed = json.loads(capsys.readouterr().out)
    assert observed["status"] == "unavailable" and observed["processed"] == 0
    assert processor.validate_failure(observed["first_failure"])["stage"] == "processor"
    assert processor.main(args + ["--testing-recipient", MAILBOX, "--testing-recipient", MAILBOX]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "unavailable", "processed": 0}
    assert not captured.err
    assert_no_runtime(runtime)
