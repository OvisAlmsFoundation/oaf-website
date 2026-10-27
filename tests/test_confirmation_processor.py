"""R39 one-shot invocation with guarded synthetic runtime/provider dependencies."""
import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import ctypes
import importlib
import json
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.engine import URL

from oaf_website import brevo, confirmation_processor as processor, database_config as database
from oaf_website import confirmation_outbox as outbox, local_testing
from oaf_website.confirmation_outbox_schema import intents, confirmation_attempts
from oaf_website.notification_delivery_schema import verification, limits
from oaf_website.notification_dispatch import BatchResult
from oaf_website.notifications import SubscriptionStore
from test_brevo import KEY, PAGE, response
from test_notification_delivery import Model, SECRET, subscribe
from test_public_confirmation import build, signup, token, CONFIRM
from test_notifications import post


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    model = Model()
    model.dispose = Mock()
    settings = tmp_path / "database.toml"
    settings.write_bytes((Path(__file__).resolve().parents[1] /
                          "config/database.example.toml").read_bytes())
    provider_credential = Mock(return_value=KEY)
    db_credential = Mock(return_value="synthetic-database-private")
    provider_loader = Mock(side_effect=lambda profile, **kw: brevo.load_brevo_config(
        profile, credential_loader=provider_credential, **kw))
    testing_loader = Mock(side_effect=lambda **kw: database.load_testing_database_config(
        local_config_path=settings, credential_loader=db_credential, **kw))
    development_loader = Mock(side_effect=lambda **kw: database.load_database_config(
        local_config_path=settings, credential_loader=db_credential, **kw))
    secret_loader = Mock(return_value=SECRET)
    creator, listener = Mock(return_value=model), Mock()
    transport = Mock(return_value=response())
    monkeypatch.setattr(processor, "load_brevo_config", provider_loader)
    monkeypatch.setattr(processor, "load_testing_database_config", testing_loader)
    monkeypatch.setattr(processor, "load_database_config", development_loader)
    monkeypatch.setattr(processor, "recognition_secret", secret_loader)
    monkeypatch.setattr(processor, "create_engine", creator)
    monkeypatch.setattr(processor.event, "listen", listener)
    monkeypatch.setattr(brevo, "BrevoHTTPS", lambda: transport)
    monkeypatch.setattr(processor.os, "environ", {"OAF_ENV": "testing"})
    return SimpleNamespace(model=model, transport=transport, provider_loader=provider_loader,
        provider_credential=provider_credential, db_credential=db_credential,
        testing_loader=testing_loader, development_loader=development_loader,
        secret_loader=secret_loader, creator=creator, listener=listener)


def invoke(profile="testing", **changes):
    options = dict(expected_profile=profile, enabled=True, credential_account="synthetic-account",
                   confirmation_page=PAGE, environ={"OAF_ENV": profile})
    if profile == "testing":
        options["testing_recipient"] = "subscriber1@example.invalid"
    options.update(changes)
    return processor.process_confirmations(**options)


def reserve(runtime, number=1, profile="testing"):
    store = outbox.ConfirmationOutboxStore(runtime.model, SECRET, profile)
    subscription = subscribe(runtime.model, number)
    bearer = store.request_confirmation(f"subscriber{number}@example.invalid")
    record = next(r for r in runtime.model.rows(intents) if r["subscription"] == subscription)
    return store, subscription, bearer, record["intent"]


def assert_no_runtime(runtime):
    for mock in (runtime.provider_loader, runtime.testing_loader, runtime.development_loader,
                 runtime.secret_loader, runtime.creator, runtime.listener, runtime.transport):
        mock.assert_not_called()
    assert not runtime.model.statements


def test_default_off_never_loads_configuration_or_starts_processing(runtime):
    assert processor.process_confirmations(expected_profile="testing") == BatchResult("disabled")
    assert_no_runtime(runtime)


def test_import_has_no_runtime_side_effects(runtime, monkeypatch):
    forbidden = Mock(side_effect=AssertionError("Import cannot process"))
    monkeypatch.setattr(outbox.ConfirmationDispatcher, "process", forbidden)
    importlib.reload(processor)
    forbidden.assert_not_called()
    assert_no_runtime(runtime)


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("profile,environment", [
    ("testing", {}), ("testing", {"OAF_ENV": "development"}),
    ("development", {"OAF_ENV": "testing"}), ("production", {"OAF_ENV": "production"}),
    ("Testing", {"OAF_ENV": "Testing"}),
    *[("testing", {"OAF_ENV": "testing", name: "synthetic-private"}) for name in
      ("OAF_CONFIRMATION_ENABLED", "PGHOST", "DATABASE_URL", "DB_PASSWORD", "SQLALCHEMY_DATABASE_URI")],
])
def test_environment_rejection_precedes_all_runtime_access(runtime, profile, environment, enabled):
    assert invoke(profile, enabled=enabled, environ=environment) == BatchResult("unavailable")
    assert_no_runtime(runtime)


@pytest.mark.parametrize("enabled", [None, 1, 0, "true", [], {}])
def test_activation_requires_exact_boolean(runtime, enabled):
    assert invoke(enabled=enabled) == BatchResult("unavailable")
    assert_no_runtime(runtime)


@pytest.mark.parametrize("page", [None, "http://website.invalid/gramanna.html",
    "https://website.invalid/", "https://website.invalid/gramanna.html#synthetic-private"])
def test_bad_page_rejected_before_secrets(runtime, page):
    assert invoke(confirmation_page=page) == BatchResult("unavailable")
    assert_no_runtime(runtime)


@pytest.mark.parametrize("account", [None, "", "bad\naccount", "x" * 129])
def test_bad_provider_metadata_never_reads_a_credential(runtime, account):
    assert invoke(credential_account=account) == BatchResult("unavailable")
    runtime.provider_credential.assert_not_called()
    runtime.testing_loader.assert_not_called()
    runtime.secret_loader.assert_not_called()
    runtime.creator.assert_not_called()


@pytest.mark.parametrize("profile", ["testing", "development"])
def test_empty_enabled_invocation_uses_existing_identity_and_exact_target(runtime, profile):
    assert invoke(profile) == BatchResult("processed", 0)
    runtime.provider_credential.assert_called_once_with(
        f"OAF Website/{profile}/Brevo/ApiKey", "synthetic-account", {"OAF_ENV": profile}, exact_target=True)
    (runtime.testing_loader if profile == "testing" else runtime.development_loader).assert_called_once()
    (runtime.development_loader if profile == "testing" else runtime.testing_loader).assert_not_called()
    runtime.secret_loader.assert_called_once_with(require_existing=True)
    options = runtime.creator.call_args.kwargs
    assert options == dict(echo=False, hide_parameters=True, pool_pre_ping=True, connect_args={
        "connect_timeout": 5, "require_auth": "scram-sha-256",
        "application_name": "oaf_website_confirmation_processor",
        "options": "-c statement_timeout=10000 -c lock_timeout=5000"})
    assert runtime.listener.call_args.args[:2] == (runtime.model, "checkout")
    runtime.model.dispose.assert_called_once_with()
    runtime.transport.assert_not_called()
    assert sum("LIMIT" in sql for sql in runtime.model.statements) == 2


@pytest.mark.parametrize("values,valid", [
    (("oaf_website_test", "oaf_website_test_app", "oaf_website_test_app", "127.0.0.1", 5432, 17), True),
    (("oaf_website_dev", "oaf_website_test_app", "oaf_website_test_app", "127.0.0.1", 5432, 17), False),
    (("oaf_website_test", "postgres", "oaf_website_test_app", "127.0.0.1", 5432, 17), False),
    (("oaf_website_test", "oaf_website_test_app", "postgres", "127.0.0.1", 5432, 17), False),
    (("oaf_website_test", "oaf_website_test_app", "oaf_website_test_app", "localhost", 5432, 17), False),
    (("oaf_website_test", "oaf_website_test_app", "oaf_website_test_app", "127.0.0.1", 5433, 17), False),
    (("oaf_website_test", "oaf_website_test_app", "oaf_website_test_app", "127.0.0.1", 5432, 16), False),
])
def test_registered_checkout_verifies_every_identity_component(runtime, values, valid):
    assert invoke().status == "processed"
    query, rollback = Mock(), Mock()
    @contextmanager
    def cursor():
        yield SimpleNamespace(execute=query, fetchone=lambda: values)
    dbapi = SimpleNamespace(cursor=cursor, rollback=rollback)
    callback = runtime.listener.call_args.args[2]
    if valid:
        callback(dbapi, None, None)
    else:
        with pytest.raises(database.DatabaseConfigurationError):
            callback(dbapi, None, None)
    rollback.assert_called_once()
    assert "session_user" in query.call_args.args[0]
    runtime.transport.assert_not_called()


@pytest.mark.parametrize("config", [None, database.DatabaseConfig("development", URL.create(
    "postgresql+psycopg", username="oaf_website_app", password="synthetic", host="127.0.0.1",
    port=5432, database="oaf_website_dev"))])
def test_returned_config_must_match_selected_environment(runtime, config):
    runtime.testing_loader.side_effect = None
    runtime.testing_loader.return_value = config
    assert invoke() == BatchResult("unavailable")
    runtime.secret_loader.assert_not_called()
    runtime.creator.assert_not_called()


@pytest.mark.parametrize('page_path', ['/gramanna.html', '/confirm-email.html'])
def test_new_invocation_recovers_pending_and_acceptance_never_verifies(runtime, page_path):
    _, _, bearer, _ = reserve(runtime)
    before = deepcopy(runtime.model.rows(limits))
    assert invoke(confirmation_page=PAGE.replace('/gramanna.html', page_path)) == BatchResult("processed", 1)
    body = json.loads(runtime.transport.call_args.args[1])
    assert PAGE.replace('/gramanna.html', '/confirm-email.html') + "#confirm-email=" + bearer in body["textContent"]
    assert runtime.model.rows(intents)[0]["status"] == "accepted"
    assert runtime.model.rows(verification)[0]["verified_at"] is None
    assert runtime.model.rows(limits) == before
    assert invoke() == BatchResult("processed", 0)
    assert runtime.transport.call_count == 1
    assert runtime.model.dispose.call_count == 2


@pytest.mark.parametrize("submitting", [False, True])
def test_invocation_bounds_recovery_and_selection_independently(runtime, submitting):
    for number in range(1, 47):
        store, _, _, intent = reserve(runtime, number, profile="development")
        if number <= 23:
            claim = store.claim_confirmation(intent)
            if submitting:
                assert store.prepare_confirmation(intent, claim, PAGE)
    runtime.model.elapse(minutes=5)
    runtime.model.statements.clear()
    assert invoke("development") == BatchResult("processed", 20)
    records = runtime.model.rows(intents)
    recovery_status = "uncertain" if submitting else "failed"
    assert sum(r["status"] == recovery_status for r in records) == 20
    assert sum(r["status"] == ("submitting" if submitting else "claimed") for r in records) == 3
    assert sum(r["status"] == "pending" for r in records) == 3
    assert sum(r["status"] == "accepted" for r in records) == 20
    assert runtime.transport.call_count == 20
    assert "LIMIT" in runtime.model.statements[2] and "ORDER BY" in runtime.model.statements[2]
    assert invoke("development") == BatchResult("processed", 3)
    assert sum(r["status"] == recovery_status for r in runtime.model.rows(intents)) == 23


@pytest.mark.parametrize("outcome", ["not_submitted", "retryable_rejection"])
def test_retry_timing_exhaustion_and_original_expiry_across_invocations(runtime, outcome):
    _, _, bearer, _ = reserve(runtime)
    expiry = runtime.model.rows(verification)[0]["expires_at"]
    runtime.transport.return_value = brevo.ProviderOutcome(outcome)
    assert invoke() == BatchResult("processed", 1)
    for delay in (60, 300):
        runtime.model.elapse(seconds=delay - 1)
        assert invoke() == BatchResult("processed", 0)
        runtime.model.elapse(seconds=1)
        assert invoke() == BatchResult("processed", 1)
    record = runtime.model.rows(intents)[0]
    assert (record["attempts"], record["status"], record["next_attempt_at"]) == (3, "failed", None)
    assert len(runtime.model.rows(confirmation_attempts)) == 3
    assert runtime.model.rows(verification)[0]["expires_at"] == expiry
    assert all(bearer in json.loads(call.args[1])["textContent"] for call in runtime.transport.call_args_list)
    runtime.model.elapse(days=2)
    assert invoke() == BatchResult("processed", 0)
    assert runtime.transport.call_count == 3


@pytest.mark.parametrize("submitting", [False, True])
def test_interruption_recovery_uses_lease_then_retry_or_uncertainty(runtime, submitting):
    store, _, _, intent = reserve(runtime)
    claim = store.claim_confirmation(intent)
    if submitting:
        assert store.prepare_confirmation(intent, claim, PAGE)
    assert invoke() == BatchResult("processed", 0)
    runtime.model.elapse(seconds=299)
    assert invoke() == BatchResult("processed", 0)
    runtime.model.elapse(seconds=1)
    assert invoke() == BatchResult("processed", 0)
    assert runtime.model.rows(intents)[0]["status"] == ("uncertain" if submitting else "failed")
    runtime.model.elapse(seconds=59)
    assert invoke().processed == 0
    runtime.model.elapse(seconds=1)
    assert invoke().processed == int(not submitting)
    assert runtime.transport.call_count == int(not submitting)


@pytest.mark.parametrize("phase", ["candidates", "claim_confirmation", "prepare_confirmation", "confirmation_outcome"])
@pytest.mark.parametrize("failure", ["commit", "uncertain"])
def test_failed_and_unacknowledged_commits_never_cause_blind_resend(runtime, monkeypatch, phase, failure):
    reserve(runtime)
    original = getattr(outbox.ConfirmationOutboxStore, phase)
    def fail(store, *args):
        runtime.model.failure = failure
        return original(store, *args)
    monkeypatch.setattr(outbox.ConfirmationOutboxStore, phase, fail)
    assert invoke() == BatchResult("unavailable", 0)
    assert runtime.transport.call_count == int(phase == "confirmation_outcome")
    runtime.model.failure = None
    monkeypatch.setattr(outbox.ConfirmationOutboxStore, phase, original)
    runtime.model.elapse(minutes=5)
    assert invoke().status == "processed"
    runtime.model.elapse(seconds=60)
    assert invoke().status == "processed"
    if phase == "prepare_confirmation" and failure == "uncertain":
        assert runtime.model.rows(intents)[0]["status"] == "uncertain"
        runtime.transport.assert_not_called()
    elif phase == "confirmation_outcome":
        assert runtime.transport.call_count == 1
        assert runtime.model.rows(intents)[0]["status"] == ("uncertain" if failure == "commit" else "accepted")
    else:
        assert runtime.transport.call_count == 1


def test_concurrent_invocations_compete_for_one_database_claim(runtime, monkeypatch):
    reserve(runtime)
    barrier = Barrier(8)
    original = outbox.ConfirmationOutboxStore.candidates
    def select_together(store, limit):
        candidates = original(store, limit)
        barrier.wait(timeout=10)
        return candidates
    monkeypatch.setattr(outbox.ConfirmationOutboxStore, "candidates", select_together)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: invoke(), range(8)))
    assert all(r.status == "processed" for r in results)
    assert sum(r.processed for r in results) == runtime.transport.call_count == 1
    assert len(runtime.model.rows(confirmation_attempts)) == 1


@pytest.mark.parametrize("when", ["claim_confirmation", "prepare_confirmation"])
@pytest.mark.parametrize("reason", ["withdrawn", "suppressed", "verified", "expired", "superseded"])
def test_lifecycle_recheck_prevents_dispatch(runtime, monkeypatch, when, reason):
    store, subscription, bearer, _ = reserve(runtime)
    original = getattr(outbox.ConfirmationOutboxStore, when)
    def change_then_continue(current, *args):
        if reason == "withdrawn": SubscriptionStore(runtime.model).unsubscribe(subscription)
        if reason == "suppressed": store.suppress("subscriber1@example.invalid", "complaint")
        if reason == "verified": assert store.confirm(bearer) == "verified"
        if reason == "expired": runtime.model.elapse(days=1)
        if reason == "superseded":
            runtime.model.elapse(seconds=60)
            # Model a committed newer confirmation, not a pending resend.
            runtime.model.rows(verification)[0].update(token_digest="f"*64,
                issued_at=runtime.model.now)
        return original(current, *args)
    monkeypatch.setattr(outbox.ConfirmationOutboxStore, when, change_then_continue)
    assert invoke() == BatchResult("processed", 0)
    runtime.transport.assert_not_called()


@pytest.mark.parametrize("outcome", [brevo.ProviderOutcome("submission_unknown"),
    brevo.ProviderOutcome("provider_rejected"), TimeoutError("synthetic-private")])
def test_uncertainty_and_terminal_rejection_never_resend(runtime, outcome):
    reserve(runtime)
    if isinstance(outcome, Exception): runtime.transport.side_effect = outcome
    else: runtime.transport.return_value = outcome
    assert invoke() == BatchResult("processed", 1)
    for elapsed in (60, 300, 86400):
        runtime.model.elapse(seconds=elapsed)
        assert invoke() == BatchResult("processed", 0)
    assert runtime.transport.call_count == 1


@pytest.mark.parametrize("phase", ["provider_loader", "testing_loader", "secret_loader", "creator", "listener"])
def test_dependency_failures_are_sanitized_and_cleanup_is_attempted(runtime, phase, capsys, caplog):
    secret = "synthetic-private-email@example.invalid/bearer/claim/key/database-password"
    getattr(runtime, phase).side_effect = RuntimeError(secret)
    assert processor.main(["--environment", "testing", "--enable-processing", "--brevo-account",
                           "synthetic-account", "--confirmation-page", PAGE,
                           "--testing-recipient", "subscriber1@example.invalid"]) == 1
    observed = json.loads(capsys.readouterr().out)
    assert observed["status"] == "unavailable" and observed["processed"] == 0
    assert processor.validate_failure(observed["first_failure"])["stage"] == "processor"
    assert secret not in caplog.text
    assert runtime.model.dispose.call_count == int(phase == "listener")
    runtime.transport.assert_not_called()


def test_cleanup_failure_retains_acknowledged_progress(runtime):
    reserve(runtime)
    runtime.model.dispose.side_effect = RuntimeError("synthetic-private")
    assert invoke() == BatchResult("unavailable", 1)
    runtime.model.dispose.side_effect = None
    assert invoke() == BatchResult("processed", 0)
    assert runtime.transport.call_count == 1


@pytest.mark.parametrize("arguments", [[], ["--environment", "synthetic-private"],
    ["--environment", "testing", "--unknown", "synthetic-private"],
    ["--environment", "testing", "--enable-process"], ["--environment"]])
def test_cli_argument_errors_are_sanitized_nonzero(runtime, capsys, arguments):
    assert processor.main(arguments) == 2
    captured = capsys.readouterr()
    observed = json.loads(captured.out)
    first = processor.validate_failure(observed.pop("first_failure"))
    assert observed == {"status": "unavailable", "processed": 0}
    assert first["predicate"] == "processor_arguments" and first["stage"] == "processor"
    assert "synthetic-private" not in captured.out
    assert not captured.err
    assert_no_runtime(runtime)


def test_cli_disabled_and_empty_completed_results(runtime, capsys):
    assert processor.main(["--environment", "testing"]) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "disabled", "processed": 0}
    assert_no_runtime(runtime)
    assert processor.main(["--environment", "testing", "--enable-processing", "--brevo-account",
                           "synthetic-account", "--confirmation-page", PAGE,
                           "--testing-recipient", "subscriber1@example.invalid"]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "processed", "processed": 0}


def test_interrupt_exits_safely_without_exception_or_secret(runtime, monkeypatch, capsys):
    monkeypatch.setattr(outbox.ConfirmationDispatcher, "process", Mock(side_effect=KeyboardInterrupt("private")))
    assert processor.main(["--environment", "testing", "--enable-processing", "--brevo-account",
                           "synthetic-account", "--confirmation-page", PAGE,
                           "--testing-recipient", "subscriber1@example.invalid"]) == 130
    observed = json.loads(capsys.readouterr().out)
    assert observed["status"] == "unavailable" and observed["processed"] == 0
    assert processor.validate_failure(observed["first_failure"])["exception_class"] == "KeyboardInterrupt"
    runtime.model.dispose.assert_called_once()


def test_r38_public_signup_dispatch_and_explicit_consumption_remain_compatible(runtime):
    setup = (runtime.model, *build(runtime.model))
    assert signup(setup, email="subscriber1@example.invalid").status_code == 200
    bearer = token(runtime.model, setup[1])
    runtime.transport.assert_not_called()
    assert invoke() == BatchResult("processed", 1)
    assert runtime.model.rows(verification)[0]["verified_at"] is None
    assert post(setup[-2], setup[-1], {"token": bearer}, CONFIRM).json["status"] == "confirmed"
    assert invoke() == BatchResult("processed", 0)
    assert runtime.transport.call_count == 1


def test_required_existing_key_is_read_only_and_uses_current_user_dpapi(monkeypatch, tmp_path):
    path = tmp_path / "config" / "recognition.dpapi"
    path.parent.mkdir()
    path.write_bytes(b"synthetic-protected-file")
    monkeypatch.setattr(local_testing, "ROOT", tmp_path)
    monkeypatch.setattr(local_testing, "SECRET_PATH", path)
    buffer = ctypes.create_string_buffer(b"s" * 32)
    def decrypt(source, description, entropy, reserved, prompt, flags, target):
        assert flags == 1  # UI forbidden, current-user scope inherited from existing file.
        target._obj.size = 32
        target._obj.data = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        return True
    crypt = SimpleNamespace(CryptProtectData=Mock(), CryptUnprotectData=Mock(side_effect=decrypt))
    kernel = SimpleNamespace(LocalFree=Mock())
    native = Mock(side_effect=[crypt, kernel])
    monkeypatch.setattr(local_testing.ctypes, "WinDLL", native, raising=False)
    monkeypatch.setattr(local_testing.sys, "platform", "win32")
    assert local_testing.recognition_secret(require_existing=True) == b"s" * 32
    crypt.CryptProtectData.assert_not_called()
    assert path.read_bytes() == b"synthetic-protected-file"
    kernel.LocalFree.assert_called_once()


@pytest.mark.parametrize("policy", [True, None, 1, "true"])
def test_missing_key_and_invalid_policy_never_create_or_access_native_secrets(monkeypatch, tmp_path, policy):
    path = tmp_path / "missing.dpapi"
    monkeypatch.setattr(local_testing, "ROOT", tmp_path)
    monkeypatch.setattr(local_testing, "SECRET_PATH", path)
    native = Mock(side_effect=AssertionError("No native secret access"))
    monkeypatch.setattr(local_testing.ctypes, "WinDLL", native, raising=False)
    with pytest.raises((RuntimeError, ValueError)):
        local_testing.recognition_secret(require_existing=policy)
    native.assert_not_called()
    assert not path.exists()



def approved_mobile_events(runtime):
    from test_notification_delivery import payload
    from oaf_website.notification_delivery import NotificationDeliveryStore
    store = NotificationDeliveryStore(runtime.model, SECRET, "testing", management_enabled=True, releases_enabled=True)
    digest = subscribe(runtime.model)
    bearer = store.request_confirmation("subscriber1@example.invalid")
    assert store.confirm(bearer) == "verified"
    store.accept_event(payload())
    store.accept_event(payload("ios", event_id="00000000-0000-0000-0000-000000000009"))
    return store, digest


def test_three_launch_types_have_independent_three_submission_budgets_and_ten_confirmations(runtime):
    from collections import Counter
    from test_notification_delivery import payload, web_payload, WEB_URL
    from oaf_website.notification_delivery import NotificationDeliveryStore
    from oaf_website.notification_delivery_schema import events, deliveries, attempts
    # DEVELOPMENT model permits multiple synthetic recipients without widening TESTING scope.
    store = NotificationDeliveryStore(runtime.model, SECRET, "development", management_enabled=True,
                                      releases_enabled=True, web_launch_url=WEB_URL)
    for number in range(1, 6):
        subscribe(runtime.model, number, web_launch=True)
        assert store.confirm(store.request_confirmation(f"subscriber{number}@example.invalid")) == "verified"
    outbox_store = outbox.ConfirmationOutboxStore(runtime.model, SECRET, "development")
    assert outbox.ConfirmationDispatcher(outbox_store, brevo.BrevoConfig("development", KEY), PAGE).process().processed == 0
    runtime.transport.assert_not_called()
    for number in range(101, 113):
        subscribe(runtime.model, number)
        outbox_store.request_confirmation(f"subscriber{number}@example.invalid")
    for values in (payload(event_id="00000000-0000-0000-0000-000000000010"),
                   payload("ios", event_id="00000000-0000-0000-0000-000000000011"), web_payload()):
        store.accept_event(dict(values, environment="development"))
    result = invoke(profile="development", management_enabled=True, releases_enabled=True,
                    environ={"OAF_ENV":"development", "GRAMANNA_WEB_LAUNCH_URL":WEB_URL})
    assert result == BatchResult("processed", 19)
    bodies = [json.loads(call.args[1]) for call in runtime.transport.call_args_list]
    counts = Counter(body["subject"] for body in bodies)
    assert counts["GraManna is now available on the web"] == 3
    assert counts["GraManna is available for Android"] == 3
    assert counts["GraManna is available for Apple iOS"] == 3
    assert sum(counts.values()) == 19 and len(runtime.model.rows(attempts)) == 9
    assert len([r for r in runtime.model.rows(deliveries) if r["status"] == "pending"]) == 6


def test_web_processor_configuration_is_required_and_restart_does_not_resend(runtime):
    from test_notification_delivery import web_payload, WEB_URL, web_store
    from oaf_website.notification_delivery_schema import deliveries
    store = web_store(runtime.model)
    subscribe(runtime.model, web_launch=True)
    assert store.confirm(store.request_confirmation("subscriber1@example.invalid")) == "verified"
    store.accept_event(web_payload())
    # Missing destination fails at rendering before a provider submission.
    assert invoke(management_enabled=True, releases_enabled=True).status == "unavailable"
    runtime.transport.assert_not_called()
    runtime.model.elapse(minutes=6)
    options = dict(management_enabled=True, releases_enabled=True,
        environ={"OAF_ENV":"testing", "GRAMANNA_WEB_LAUNCH_URL":WEB_URL})
    invoke(**options)
    runtime.model.elapse(seconds=60)
    assert invoke(**options) == BatchResult("processed", 1)
    assert invoke(**options) == BatchResult("processed", 0)
    assert runtime.transport.call_count == 1 and runtime.model.rows(deliveries)[0]["status"] == "accepted"


def test_web_configuration_does_not_weaken_existing_environment_override_guard(runtime):
    from test_notification_delivery import WEB_URL
    assert invoke(management_enabled=True, releases_enabled=True,
        environ={"OAF_ENV":"testing", "OAF_GRAMANNA_WEB_LAUNCH_URL":WEB_URL}).status == "unavailable"
    assert_no_runtime(runtime)


def test_existing_processor_drives_both_platforms_and_restart_does_not_repeat(runtime):
    from oaf_website.notification_delivery_schema import deliveries, attempts
    approved_mobile_events(runtime)
    assert invoke(management_enabled=True, releases_enabled=True).status == "processed"
    assert runtime.transport.call_count == 2
    assert {r["status"] for r in runtime.model.rows(deliveries)} == {"accepted"}
    assert len(runtime.model.rows(attempts)) == 2
    assert invoke(management_enabled=True, releases_enabled=True).processed == 0
    assert runtime.transport.call_count == 2


@pytest.mark.parametrize("mode", ["default", "disabled", "invalid", "no_management", "intent_scope"])
def test_release_processing_default_off_and_scope_is_not_widened(runtime, mode):
    store, _ = approved_mobile_events(runtime)
    options = dict(management_enabled=True)
    if mode == "disabled": options.update(enabled=False, releases_enabled=True)
    if mode == "invalid": options.update(releases_enabled=1)
    if mode == "no_management": options.update(releases_enabled=True, management_enabled=False)
    if mode == "intent_scope": options.update(releases_enabled=True,
        intent_scope=outbox.ManagementIntentScope("A"*64, "B"*64, runtime.model.now))
    result = invoke(**options)
    assert runtime.transport.call_count == 0
    if mode != "default": assert result.status in {"disabled", "unavailable"}
    assert store.pending_release_events()


def test_mobile_processor_cli_uses_existing_finite_batch(runtime, capsys):
    approved_mobile_events(runtime)
    code = processor.main(["--environment", "testing", "--enable-processing", "--enable-management", "--enable-releases",
        "--brevo-account", "synthetic-account", "--confirmation-page", PAGE, "--testing-recipient", "subscriber1@example.invalid"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["processed"] == 2
    assert runtime.transport.call_count == 2


def test_mobile_processing_holds_uncertain_provider_results(runtime):
    from oaf_website.notification_delivery_schema import deliveries, attempts
    approved_mobile_events(runtime)
    runtime.transport.side_effect = TimeoutError("synthetic private provider uncertainty")
    invoke(management_enabled=True, releases_enabled=True)
    assert {r["status"] for r in runtime.model.rows(deliveries)} == {"uncertain"}
    assert len(runtime.model.rows(attempts)) == 2
    runtime.model.elapse(minutes=10)
    invoke(management_enabled=True, releases_enabled=True)
    assert runtime.transport.call_count == 2



@pytest.mark.parametrize("phase", ["pending_release_events", "begin_submission", "record_outcome"])
def test_release_transaction_uncertainty_cannot_trigger_a_blind_resend(runtime, monkeypatch, phase):
    from oaf_website.notification_delivery import NotificationDeliveryStore
    approved_mobile_events(runtime)
    original=getattr(NotificationDeliveryStore,phase)
    def fail(store,*args,**kwargs):
        runtime.model.failure="uncertain"
        return original(store,*args,**kwargs)
    monkeypatch.setattr(NotificationDeliveryStore,phase,fail)
    assert invoke(management_enabled=True,releases_enabled=True).status=="unavailable"
    assert runtime.transport.call_count==int(phase=="record_outcome")
    runtime.model.failure=None
    monkeypatch.setattr(NotificationDeliveryStore,phase,original)
    runtime.model.elapse(minutes=6)
    invoke(management_enabled=True,releases_enabled=True)
    runtime.model.elapse(seconds=60)
    invoke(management_enabled=True,releases_enabled=True)
    bodies=[json.loads(call.args[1])["subject"] for call in runtime.transport.call_args_list]
    assert len(bodies)==len(set(bodies))
