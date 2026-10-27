"""R44 synthetic task definitions and repeated finite CLI runs; no scheduler calls."""
import migration_offline as isolation
isolation.require_early_registration()

import base64
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import xml.etree.ElementTree as ET

import pytest

from oaf_website import brevo, confirmation_schedule as schedule
from oaf_website.confirmation_outbox_schema import intents, confirmation_attempts
from oaf_website.notification_delivery_schema import verification
from oaf_website.notifications import SubscriptionStore
from test_brevo import PAGE
from test_confirmation_processor import runtime, reserve, assert_no_runtime

SID = "S-1-5-21-111-222-333-1001"
MAILBOX = "subscriber1@example.invalid"
NS = {"t": schedule.TASK_NAMESPACE}


@pytest.fixture
def scheduled(runtime, monkeypatch, tmp_path):
    monkeypatch.setattr(schedule, "ROOT", tmp_path)
    return runtime


def run(profile="testing", **changes):
    options = dict(profile=profile, enabled=True, account="synthetic-account", page=PAGE)
    if profile == "testing":
        options["recipient"] = MAILBOX
    options.update(changes)
    return schedule.run_scheduled(**options)


def records():
    return [json.loads(line) for line in (schedule.ROOT / "instance/confirmation-processor.jsonl").read_text().splitlines()]


def output(capsys):
    result = json.loads(capsys.readouterr().out)
    required = {"timestamp_utc", "environment", "status", "processed", "exit_code"}
    assert set(result) in (required, required | {"first_failure"})
    if "first_failure" in result:
        assert schedule.validate_failure(result["first_failure"]) == result["first_failure"]
    assert result["timestamp_utc"].endswith("+00:00")
    return result


@pytest.mark.parametrize('complete', [False, True])
def test_legacy_management_scope_is_validated_and_forwarded(scheduled, monkeypatch, capsys, complete):
    call = Mock(return_value=0)
    def processed(arguments):
        print(json.dumps(dict(status='processed', processed=0)))
        return call(arguments)
    monkeypatch.setattr(schedule.processor, 'main', processed)
    options = dict(management_enabled=True, management_intent_fingerprint='a'*64)
    if complete:
        options.update(management_identity_fingerprint='b'*64, management_deadline='2026-10-16T12:00:00+00:00')
    assert run(**options) == (0 if complete else 2)
    result = output(capsys)
    if complete:
        arguments = call.call_args.args[0]
        assert arguments[-6:] == ['--management-intent-fingerprint', 'a'*64,
            '--management-identity-fingerprint', 'b'*64, '--management-deadline', options['management_deadline']]
    else:
        call.assert_not_called()
        assert result['first_failure']['operation']=='configuration'


@pytest.mark.parametrize('boundary', ['processor', 'initial_append'])
def test_schedule_interrupt_retains_finite_exit_and_no_retry(scheduled, monkeypatch, capsys, boundary):
    target = schedule.processor if boundary == 'processor' else schedule
    monkeypatch.setattr(target, 'main' if boundary == 'processor' else '_append', Mock(side_effect=KeyboardInterrupt()))
    assert run() == 130
    result = output(capsys)
    assert result['status']=='interrupted' and result['processed']==0


@pytest.mark.parametrize("profile", ["testing", "development"])
@pytest.mark.parametrize("enabled", [False, True])
def test_deterministic_disabled_task_with_explicit_finite_action(scheduled, profile, enabled):
    options = dict(profile=profile, windows_user=SID, enabled=enabled,
                   account="synthetic-account", page=PAGE,
                   recipient=MAILBOX if profile == "testing" else None)
    xml = schedule.task_xml(**options)
    assert xml == schedule.task_xml(**options)
    assert xml.startswith("<Task ")
    assert "<?xml" not in xml
    task = ET.fromstring(xml)
    assert task.tag == "{" + schedule.TASK_NAMESPACE + "}Task"
    assert task.attrib == {"version": "1.3"}
    assert [node.tag.split("}")[-1] for node in task.find("t:Triggers/t:TimeTrigger", NS)] == [
        "Enabled", "StartBoundary", "Repetition"]
    find = lambda path: task.find("t:" + path.replace("/", "/t:"), NS).text
    assert find("RegistrationInfo/URI") == "\\" + schedule.TASK_NAME
    assert find("Settings/Enabled") == "false"
    assert find("Settings/MultipleInstancesPolicy") == "IgnoreNew"
    assert find("Settings/StartWhenAvailable") == "true"
    assert find("Settings/AllowStartOnDemand") == "false"
    assert find("Settings/WakeToRun") == "false"
    assert find("Settings/ExecutionTimeLimit") == "PT4M"
    assert find("Triggers/TimeTrigger/Repetition/Interval") == "PT1M"
    assert find("Triggers/TimeTrigger/StartBoundary") == "2026-01-01T00:00:00"
    assert find("Principals/Principal/UserId") == SID
    assert find("Principals/Principal/LogonType") == "InteractiveToken"
    assert find("Principals/Principal/RunLevel") == "LeastPrivilege"
    assert task.find("t:Principals/t:Principal", NS).attrib == {"id": "Owner"}
    assert task.find("t:Actions", NS).attrib == {"Context": "Owner"}
    assert find("Actions/Exec/Command") == str(Path(schedule.os.environ.get("SystemRoot", "C:/Windows")) /
        "System32/WindowsPowerShell/v1.0/powershell.exe")
    assert find("Actions/Exec/WorkingDirectory") == str(schedule.ROOT)
    action = find("Actions/Exec/Arguments")
    assert action.startswith("-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand ")
    script = base64.b64decode(action.split()[-1]).decode("utf-16-le")
    assert "-u -B -m oaf_website.confirmation_schedule run" in script
    assert "if (-not $env:OAF_ENV)" in script
    assert "'--environment' '" + profile + "'" in script
    assert ("'--enable-processing'" in script) == enabled
    assert ("'--testing-recipient'" in script) == (enabled and profile == "testing")
    assert script.endswith("exit $LASTEXITCODE")
    assert len(task.findall("t:Triggers/*", NS)) == len(task.findall("t:Actions/*", NS)) == 1
    assert task.find(".//t:RestartOnFailure", NS) is None
    assert_no_runtime(scheduled)
    assert not (schedule.ROOT / "instance").exists()


@pytest.mark.parametrize("profile", ["testing", "development"])
@pytest.mark.parametrize("enabled", [False, True])
def test_plan_and_import_never_start_processor_or_scheduler(scheduled, monkeypatch, capsys, profile, enabled):
    forbidden = Mock(side_effect=AssertionError("No runtime or scheduler"))
    monkeypatch.setattr(schedule.processor, "main", forbidden)
    actual_root = schedule.ROOT
    importlib.reload(schedule)
    monkeypatch.setattr(schedule, "ROOT", actual_root)
    arguments = ["plan", "--environment", profile, "--windows-user", SID]
    if enabled:
        arguments += ["--enable-processing", "--brevo-account", "synthetic-account", "--confirmation-page", PAGE]
        if profile == "testing":
            arguments += ["--testing-recipient", MAILBOX]
    assert schedule.main(arguments) == 0
    xml = capsys.readouterr().out
    assert xml.startswith("<Task ")
    assert "<?xml" not in xml
    assert ET.fromstring(xml).find("t:Settings/t:Enabled", NS).text == "false"
    forbidden.assert_not_called()
    assert_no_runtime(scheduled)


@pytest.mark.parametrize("options", [
    {"profile": "production"}, {"profile": "Testing"}, {"enabled": 1},
    {"windows_user": ""}, {"windows_user": "unapproved-account"},
    {"recipient": None}, {"recipient": "bad"}, {"account": None},
    {"account": "bad\nprivate"}, {"page": "http://website.invalid/confirm-email.html"},
    {"profile": "development", "recipient": MAILBOX},
])
def test_invalid_plan_rejects_before_runtime_access(scheduled, options):
    values = dict(profile="testing", windows_user=SID, enabled=True,
                  account="synthetic-account", page=PAGE, recipient=MAILBOX)
    values.update(options)
    with pytest.raises(ValueError):
        schedule.task_xml(**values)
    assert_no_runtime(scheduled)


def test_default_off_is_observable_without_processor_runtime(scheduled, capsys):
    assert schedule.run_scheduled(profile="testing") == 2
    assert output(capsys)["status"] == "disabled"
    assert [r["status"] for r in records()] == ["started", "disabled"]
    assert_no_runtime(scheduled)


@pytest.mark.parametrize("environment", [{}, {"OAF_ENV": "development"},
    {"OAF_ENV": "testing", "PGHOST": "private"},
    {"OAF_ENV": "testing", "OAF_CONFIRMATION_ENABLED": "true"}])
def test_scheduled_environment_has_no_fallback(scheduled, monkeypatch, capsys, environment):
    monkeypatch.setattr(schedule.os, "environ", environment)
    assert run() == 2
    assert output(capsys)["status"] == "invalid_configuration"
    assert records()[-1]["status"] == "invalid_configuration"
    assert_no_runtime(scheduled)


@pytest.mark.parametrize("profile,options", [
    ("production", {}), ("testing", {"recipient": None}),
    ("testing", {"recipient": "bad"}), ("development", {"recipient": MAILBOX}),
])
def test_activation_rejections_have_safe_persistent_classification(scheduled, monkeypatch, capsys, profile, options):
    monkeypatch.setenv("OAF_ENV", profile)
    assert run(profile, **options) == 2
    assert output(capsys)["status"] == "invalid_configuration"
    assert_no_runtime(scheduled)


def test_testing_scope_and_repeated_schedule_starts(scheduled, capsys):
    reserve(scheduled)
    reserve(scheduled, 2)
    original = deepcopy(scheduled.model.rows(intents)[1])
    assert run(recipient=" Subscriber1@Example.Invalid ") == 0
    assert output(capsys)["processed"] == 1
    for _ in range(3):
        scheduled.model.elapse(minutes=1)
        assert run() == 0
        assert output(capsys)["processed"] == 0
    assert scheduled.model.rows(intents)[1] == original
    assert scheduled.transport.call_count == 1
    assert scheduled.model.dispose.call_count == 4
    assert len(records()) == 8
    assert scheduled.model.rows(verification)[0]["verified_at"] is None
    assert records()[-1]["status"] == "processed"


def test_ordinary_development_scope_and_twenty_item_bound(scheduled, monkeypatch, capsys):
    monkeypatch.setenv("OAF_ENV", "development")
    for number in range(1, 24):
        reserve(scheduled, number, profile="development")
    assert run("development") == 0
    assert output(capsys)["processed"] == 20
    assert run("development") == 0
    assert output(capsys)["processed"] == 3
    assert scheduled.transport.call_count == 23
    assert scheduled.provider_credential.call_args.args[0] == "OAF Website/development/Brevo/ApiKey"
    scheduled.testing_loader.assert_not_called()


@pytest.mark.parametrize("outcome", ["not_submitted", "retryable_rejection"])
def test_minute_ticks_honor_safe_retry_due_times_and_attempt_exhaustion(scheduled, capsys, outcome):
    reserve(scheduled)
    scheduled.transport.return_value = brevo.ProviderOutcome(outcome)
    expiry = scheduled.model.rows(verification)[0]["expires_at"]
    expected = [1, 1, 0, 0, 0, 0, 1, 0]
    for processed in expected:
        assert run() == 0
        assert output(capsys)["processed"] == processed
        scheduled.model.elapse(seconds=60)
    assert scheduled.transport.call_count == 3
    assert scheduled.model.rows(intents)[0]["attempts"] == 3
    assert scheduled.model.rows(intents)[0]["next_attempt_at"] is None
    assert len(scheduled.model.rows(confirmation_attempts)) == 3
    assert scheduled.model.rows(verification)[0]["expires_at"] == expiry


@pytest.mark.parametrize("submitting", [False, True])
def test_missed_runs_and_restart_recover_expired_claims_conservatively(scheduled, capsys, submitting):
    store, _, _, intent = reserve(scheduled)
    claim = store.claim_confirmation(intent)
    if submitting:
        assert store.prepare_confirmation(intent, claim, PAGE)
    scheduled.model.elapse(minutes=12)
    assert run() == 0
    assert output(capsys)["processed"] == 0
    assert scheduled.model.rows(intents)[0]["status"] == ("uncertain" if submitting else "failed")
    scheduled.model.elapse(minutes=1)
    assert run() == 0
    assert output(capsys)["processed"] == int(not submitting)
    assert scheduled.transport.call_count == int(not submitting)


@pytest.mark.parametrize("reason", ["expired", "superseded", "withdrawn", "verified", "suppressed"])
def test_lifecycle_changes_during_missed_runs_remain_authoritative(scheduled, capsys, reason):
    store, subscription, bearer, intent = reserve(scheduled)
    if reason == "expired": scheduled.model.elapse(days=1)
    if reason == "superseded":
        # The accepted lifecycle repair coalesces unexpired pending work. A new
        # request after original expiry creates the real replacement boundary.
        scheduled.model.elapse(days=1, seconds=60)
        assert store.request_confirmation(MAILBOX) != bearer
    if reason == "withdrawn": SubscriptionStore(scheduled.model).unsubscribe(subscription)
    if reason == "verified": assert store.confirm(bearer) == "verified"
    if reason == "suppressed": store.suppress(MAILBOX, "complaint")
    assert run() == 0
    assert output(capsys)["processed"] == int(reason == "superseded")
    old = next(row for row in scheduled.model.rows(intents) if row["intent"] == intent)
    assert old["status"] == "suppressed"
    assert scheduled.transport.call_count == int(reason == "superseded")


@pytest.mark.parametrize("outcome", ["provider_accepted", "provider_rejected", "submission_unknown"])
def test_no_scheduled_resend_after_terminal_or_uncertain_outcome(scheduled, capsys, outcome):
    reserve(scheduled)
    scheduled.transport.return_value = brevo.ProviderOutcome(outcome)
    assert run() == 0
    assert output(capsys)["processed"] == 1
    scheduled.model.elapse(minutes=20)
    assert run() == 0
    assert output(capsys)["processed"] == 0
    assert scheduled.transport.call_count == 1


def test_local_lock_prevents_conflicting_environment_or_task_alias_and_releases(scheduled, capsys):
    reserve(scheduled)
    with schedule._local_run_lock():
        assert run() == 2
        assert output(capsys)["status"] == "overlap"
        assert_no_runtime_after_reservation(scheduled)
    assert run() == 0
    assert output(capsys)["processed"] == 1


def assert_no_runtime_after_reservation(runtime):
    runtime.transport.assert_not_called()
    runtime.provider_loader.assert_not_called()
    runtime.creator.assert_not_called()


def test_exception_releases_local_lock(scheduled):
    with pytest.raises(RuntimeError):
        with schedule._local_run_lock():
            raise RuntimeError("synthetic interruption")
    with schedule._local_run_lock():
        pass


@pytest.fixture(params=["win32", "linux"])
def lock_backend(request, monkeypatch):
    # Exercise both dispatch paths with REAL host kernel locks. On the other
    # platform, adapt only the unavailable API signature; never fake a lock.
    if sys.platform == "win32" and request.param == "linux":
        import msvcrt
        def flock(fd, operation):
            msvcrt.locking(fd, msvcrt.LK_UNLCK if operation == 0 else msvcrt.LK_NBLCK, 1)
        monkeypatch.setitem(sys.modules, "fcntl",
                            SimpleNamespace(flock=flock, LOCK_UN=0, LOCK_EX=2, LOCK_NB=4))
    elif sys.platform != "win32" and request.param == "win32":
        import fcntl
        def locking(fd, operation, length):
            assert length == 1
            fcntl.flock(fd, fcntl.LOCK_UN if operation == 0 else fcntl.LOCK_EX | fcntl.LOCK_NB)
        monkeypatch.setitem(sys.modules, "msvcrt",
                            SimpleNamespace(locking=locking, LK_UNLCK=0, LK_NBLCK=2))
    monkeypatch.setattr(schedule, "sys", SimpleNamespace(platform=request.param))


def test_kernel_lock_excludes_concurrent_thread_and_releases(scheduled, lock_backend):
    from concurrent.futures import ThreadPoolExecutor
    def contender():
        with pytest.raises(schedule._Overlap):
            with schedule._local_run_lock():
                pytest.fail("Concurrent owner entered the locked section")
    with ThreadPoolExecutor(max_workers=1) as worker:
        with schedule._local_run_lock():
            worker.submit(contender).result(timeout=5)
        with schedule._local_run_lock():
            pass


@pytest.mark.parametrize("boundary", ["acquire", "release"])
def test_lock_errors_fail_closed_and_file_close_releases(scheduled, lock_backend, monkeypatch, capsys, boundary):
    original = schedule._file_lock
    def fail(lock, *, release=False):
        if release == (boundary == "release"):
            raise OSError("synthetic lock failure")
        original(lock, release=release)
    monkeypatch.setattr(schedule, "_file_lock", fail)
    assert schedule.run_scheduled(profile="testing") == (2 if boundary == "acquire" else 1)
    result = output(capsys)
    assert result["status"] == ("overlap" if boundary == "acquire" else "unavailable")
    assert_no_runtime(scheduled)
    # Even a failed explicit unlock must close its handle and release the lock.
    monkeypatch.setattr(schedule, "_file_lock", original)
    with schedule._local_run_lock():
        pass


@pytest.mark.parametrize("name", ["instance", "confirmation-processor.lock", "confirmation-processor.jsonl"])
def test_redirected_runtime_files_fail_before_processor_access(scheduled, monkeypatch, capsys, name):
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path.name == name or original(path))
    assert run() == 1
    assert output(capsys)["status"] == "unavailable"
    assert_no_runtime(scheduled)


@pytest.mark.parametrize("result", [
    {"status": "private-provider-response", "processed": 0},
    {"status": "processed", "processed": True},
    {"status": "processed", "processed": 21},
    {"status": "processed", "processed": 1, "email": MAILBOX},
])
def test_only_allowlisted_processor_results_reach_invocation_log(scheduled, monkeypatch, capsys, result):
    def invalid_main(arguments):
        print(json.dumps(result))
        return 0
    monkeypatch.setattr(schedule.processor, "main", invalid_main)
    assert run() == 1
    record = output(capsys)
    assert record["status"] == "unavailable" and record["processed"] == 0
    assert MAILBOX not in json.dumps(records())
    assert "private-provider-response" not in json.dumps(records())
    assert_no_runtime(scheduled)


@pytest.mark.parametrize("after_processing", [False, True])
def test_reporting_failure_blocks_start_or_preserves_acknowledged_progress(scheduled, monkeypatch, capsys, after_processing):
    reserve(scheduled)
    original = schedule._append
    def fail(record):
        if (record["status"] != "started") == after_processing:
            raise OSError("private-mailbox@example.invalid/token/credentials")
        original(record)
    monkeypatch.setattr(schedule, "_append", fail)
    assert run() == 1
    result = output(capsys)
    assert result["status"] == "reporting_failed"
    assert result["processed"] == int(after_processing)
    assert scheduled.transport.call_count == int(after_processing)
    if not after_processing: assert_no_runtime_after_reservation(scheduled)


def test_dependency_failure_is_persistent_sanitized_and_retry_is_next_tick(scheduled, capsys, caplog):
    private = "private-mailbox@example.invalid/token/credential/raw-provider-response"
    scheduled.provider_loader.side_effect = RuntimeError(private)
    assert run() == 1
    result = output(capsys)
    assert result["status"] == records()[-1]["status"] == "unavailable"
    assert private not in json.dumps(records()) + json.dumps(result) + caplog.text
    assert scheduled.provider_loader.call_count == 1
    scheduled.transport.assert_not_called()


def test_interruption_is_classified_without_resend(scheduled, monkeypatch, capsys):
    reserve(scheduled)
    scheduled.transport.side_effect = KeyboardInterrupt("private")
    assert run() == 130
    assert output(capsys)["status"] == records()[-1]["status"] == "interrupted"
    scheduled.transport.side_effect = None
    scheduled.model.elapse(minutes=7)
    assert run() == 0
    assert output(capsys)["processed"] == 0
    assert scheduled.transport.call_count == 1
    assert scheduled.model.rows(intents)[0]["status"] == "uncertain"


def test_safe_deactivation_and_reactivation_preserve_pending_work(scheduled, capsys):
    reserve(scheduled)
    before = deepcopy(scheduled.model.records)
    assert run(enabled=False) == 2
    assert output(capsys)["status"] == "disabled"
    assert scheduled.model.records == before
    scheduled.transport.assert_not_called()
    assert run() == 0
    assert output(capsys)["processed"] == 1


@pytest.mark.parametrize("arguments", [[], ["run"], ["run", "--environment", "testing", "--unknown", "private"],
    ["run", "--environment", "testing", "--environment", "development"],
    ["run", "--environment", "testing", "--testing-recipient", MAILBOX, "--testing-recipient", MAILBOX]])
def test_cli_argument_failure_never_echoes_supplied_data_or_starts_processor(scheduled, capsys, arguments):
    assert schedule.main(arguments) == 2
    captured = capsys.readouterr()
    observed = json.loads(captured.out)
    first = schedule.validate_failure(observed.pop("first_failure"))
    assert observed == {"status": "invalid_configuration", "processed": 0, "exit_code": 2}
    assert first["operation"] == "arguments" and first["stage"] == "schedule"
    assert "private" not in captured.out and MAILBOX not in captured.out
    assert not captured.err
    assert_no_runtime(scheduled)


def test_scheduled_cli_delegates_existing_one_shot_and_records_only_safe_fields(scheduled, capsys):
    reserve(scheduled)
    assert schedule.main(["run", "--environment", "testing", "--enable-processing", "--brevo-account",
        "synthetic-account", "--confirmation-page", PAGE, "--testing-recipient", MAILBOX]) == 0
    result = output(capsys)
    assert result["status"] == "processed" and result["processed"] == 1
    for record in records():
        assert set(record) == set(result)
        assert MAILBOX not in json.dumps(record) and PAGE not in json.dumps(record)
        assert "synthetic-account" not in json.dumps(record)


def test_export_synthetic_action_for_powershell_parser_only(scheduled, monkeypatch, tmp_path):
    # No task is registered or run. Retain the exact synthetic definition so the
    # visible PowerShell harness can independently parse its decoded action.
    monkeypatch.setattr(schedule, "ROOT", tmp_path / "synthetic OAF's Website")
    xml = schedule.task_xml(profile="testing", windows_user=SID, enabled=True,
        account="synthetic-account", page=PAGE, recipient=MAILBOX)
    evidence = tmp_path / "synthetic-task.xml"
    evidence.write_text(xml, encoding="utf-8")
    assert evidence.read_text(encoding="utf-8") == xml
    task = ET.fromstring(xml)
    action = task.find("t:Actions/t:Exec/t:Arguments", NS).text
    script = base64.b64decode(action.split()[-1]).decode("utf-16-le")
    assert str(schedule.ROOT).replace("'", "''") in script
    assert script.endswith("exit $LASTEXITCODE")
    assert_no_runtime(scheduled)



def test_release_task_flag_uses_same_disabled_task_and_bounded_invocation(scheduled, capsys):
    from test_confirmation_processor import approved_mobile_events
    approved_mobile_events(scheduled)
    xml = schedule.task_xml(profile="testing", windows_user=SID, enabled=True, account="synthetic-account",
        page=PAGE, recipient=MAILBOX, management_enabled=True, releases_enabled=True)
    task = ET.fromstring(xml)
    assert task.find("t:Settings/t:Enabled", NS).text == "false"
    command = base64.b64decode(task.find("t:Actions/t:Exec/t:Arguments", NS).text.split()[-1]).decode("utf-16-le")
    assert "--enable-releases" in command
    assert run(management_enabled=True, releases_enabled=True) == 0
    assert output(capsys)["processed"] == 2
    assert run(management_enabled=True, releases_enabled=True) == 0
    assert output(capsys)["processed"] == 0
    assert scheduled.transport.call_count == 2


@pytest.mark.parametrize("options", [dict(releases_enabled=1), dict(releases_enabled=True),
    dict(releases_enabled=True, management_enabled=True, management_intent_fingerprint="a"*64,
         management_identity_fingerprint="b"*64, management_deadline="2026-10-16T12:00:00+00:00")])
def test_release_scheduler_rejects_invalid_or_exceptional_scope(scheduled, capsys, options):
    assert run(**options) == 2
    assert output(capsys)["status"] == "invalid_configuration"
    assert_no_runtime(scheduled)



@pytest.mark.parametrize("platform", ["android", "ios"])
def test_one_authenticated_approval_drives_existing_schedule_without_another_send_action(scheduled, capsys, platform):
    from test_integrations import CONFIG, RELEASE_KEY, RELEASE_PATH, service
    from dataclasses import replace
    from oaf_website import state_requests
    from oaf_website.notification_delivery import NotificationDeliveryStore
    from oaf_website.notification_delivery_schema import events, deliveries, attempts
    from test_notification_delivery import SECRET, subscribe, payload
    from test_state_requests import ORIGIN
    store=NotificationDeliveryStore(scheduled.model,SECRET,"testing",releases_enabled=True,management_enabled=True)
    subscribe(scheduled.model)
    assert store.confirm(store.request_confirmation(MAILBOX))=="verified"
    app=state_requests._build_app(None,state_requests.BrowserRecognition(SECRET),ORIGIN,
        integration_config=replace(CONFIG,release_credential=RELEASE_KEY),environment="testing",release_store=store)
    client=app.test_client(use_cookies=False)
    assert service(client,RELEASE_PATH,credential=RELEASE_KEY,data=payload(platform)).status_code==200
    assert len(scheduled.model.rows(events))==1
    scheduled.transport.assert_not_called()
    assert run(management_enabled=True,releases_enabled=True)==0
    assert output(capsys)["processed"]==1
    assert {row["status"] for row in scheduled.model.rows(deliveries)}=={"accepted"}
    assert len(scheduled.model.rows(attempts))==1
    assert service(client,RELEASE_PATH,credential=RELEASE_KEY,data=payload(platform)).status_code==200
    assert run(management_enabled=True,releases_enabled=True)==0
    assert output(capsys)["processed"]==0
    assert scheduled.transport.call_count==1
