"""Disabled Windows task definition and finite, sanitized one-shot invocation.

No registration, credential access or processing occurs on import or in plan mode.
The task must be separately registered and enabled by the authorized owner.
"""

import argparse
import base64
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from io import StringIO
import json
import os
from pathlib import Path
import re
import stat
import sys
import xml.etree.ElementTree as ET

from . import confirmation_processor as processor
from .brevo import TestingRecipientScope
from .database_config import _validate_environment
from .notification_messages import secure_confirmation_page
from .notification_dispatch import validate_failure, safe_failure, diagnostic_error

ROOT = Path(__file__).resolve().parents[1]
TASK_NAME = "OAF Website Confirmation Processor"
TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"


def _arguments(profile, enabled, account, page, recipient, management_enabled=False):
    _validate_environment({"OAF_ENV": profile}, profile)
    if profile == "production" or type(enabled) is not bool or type(management_enabled) is not bool:
        raise diagnostic_error(ValueError("Unsupported scheduling configuration."), "arguments", "schedule_configuration", stage="schedule")
    arguments = ["--environment", profile]
    if enabled:
        if profile == "testing":
            recipient = TestingRecipientScope(profile, recipient).mailbox
        elif recipient is not None:
            raise ValueError("Controlled recipients require TESTING.")
        page = secure_confirmation_page(page)
        if type(account) is not str or re.fullmatch(r"[A-Za-z0-9@._/-]{1,128}", account, re.ASCII) is None:
            raise diagnostic_error(ValueError("Existing protected credential metadata is required."), "arguments", "schedule_credential_metadata", stage="schedule")
        arguments += ["--enable-processing", "--brevo-account", account, "--confirmation-page", page]
        if recipient is not None:
            arguments += ["--testing-recipient", recipient]
        if management_enabled:
            arguments += ["--enable-management"]
    return arguments


def task_xml(*, profile, windows_user, enabled=False, account=None, page=None, recipient=None, management_enabled=False):
    """Return a deterministic DISABLED definition; never contact Task Scheduler.

    One canonical task across both environments. InteractiveToken deliberately
    requires the approved credential/DPAPI account to be logged on; no password
    registration or changed credential arrangement is implied.
    """
    arguments = _arguments(profile, enabled, account, page, recipient, management_enabled)
    if type(windows_user) is not str or re.fullmatch(r"S-1-5-21(?:-[0-9]{1,10}){4}", windows_user) is None:
        raise ValueError("An explicit approved local account SID is required.")
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        "Set-Location -LiteralPath " + quote(ROOT),
        # A conflicting inherited profile is left intact so runtime validation
        # rejects it. Never silently switch TESTING to DEVELOPMENT or vice versa.
        "if (-not $env:OAF_ENV) { $env:OAF_ENV = " + quote(profile) + " }",
        "& " + quote(ROOT / ".venv/Scripts/python.exe")
        + " -u -B -m oaf_website.confirmation_schedule run "
        + " ".join(quote(value) for value in arguments),
        "exit $LASTEXITCODE",
    ])
    encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
    ET.register_namespace("", TASK_NAMESPACE)
    task = ET.Element("{" + TASK_NAMESPACE + "}Task", version="1.3")

    def child(parent, name, value=None):
        node = ET.SubElement(parent, "{" + TASK_NAMESPACE + "}" + name)
        node.text = value
        return node

    info = child(task, "RegistrationInfo")
    child(info, "URI", "\\" + TASK_NAME)
    trigger = child(child(task, "Triggers"), "TimeTrigger")
    child(trigger, "Enabled", "true")
    child(trigger, "StartBoundary", "2026-01-01T00:00:00")
    repetition = child(trigger, "Repetition")
    child(repetition, "Interval", "PT1M")
    child(repetition, "StopAtDurationEnd", "false")
    principal = child(child(task, "Principals"), "Principal")
    principal.set("id", "Owner")
    child(principal, "UserId", windows_user)
    child(principal, "LogonType", "InteractiveToken")
    child(principal, "RunLevel", "LeastPrivilege")
    settings = child(task, "Settings")
    for name, value in (
        ("MultipleInstancesPolicy", "IgnoreNew"),
        ("DisallowStartIfOnBatteries", "false"), ("StopIfGoingOnBatteries", "false"),
        ("StartWhenAvailable", "true"), ("RunOnlyIfNetworkAvailable", "false"),
        ("AllowStartOnDemand", "false"), ("Enabled", "false"),
        ("WakeToRun", "false"), ("ExecutionTimeLimit", "PT4M"),
    ):
        child(settings, name, value)
    actions = child(task, "Actions")
    actions.set("Context", "Owner")
    action = child(actions, "Exec")
    child(action, "Command", str(Path(os.environ.get("SystemRoot", "C:/Windows")) /
                                "System32/WindowsPowerShell/v1.0/powershell.exe"))
    child(action, "Arguments", "-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand " + encoded)
    child(action, "WorkingDirectory", str(ROOT))
    return ET.tostring(task, encoding="unicode", xml_declaration=False)


class _Overlap(Exception):
    pass


def _file_lock(lock, *, release=False):
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK if release else msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN if release else fcntl.LOCK_EX | fcntl.LOCK_NB)


@contextmanager
def _local_run_lock():
    # This OS-released file lock prevents conflicting local wrapper instances,
    # including differently named tasks/environments. It is NOT outbox authority.
    directory = ROOT / "instance"
    for path in (ROOT, directory, directory / "confirmation-processor.lock",
                 directory / "confirmation-processor.jsonl"):
        if path.is_symlink() or (path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError("Redirected invocation files are prohibited.")
    directory.mkdir(exist_ok=True)
    with (directory / "confirmation-processor.lock").open("a+b") as lock:
        if lock.seek(0, 2) == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            _file_lock(lock)
        except OSError:
            raise _Overlap from None
        try:
            yield
        finally:
            lock.seek(0)
            _file_lock(lock, release=True)


def _append(record):
    with (ROOT / "instance/confirmation-processor.jsonl").open("a", encoding="utf-8", newline="\n") as log:
        log.write(json.dumps(record, sort_keys=True) + "\n")
        log.flush()
        os.fsync(log.fileno())


def run_scheduled(*, profile, enabled=False, account=None, page=None, recipient=None, management_enabled=False,
                  management_intent_fingerprint=None, management_identity_fingerprint=None, management_deadline=None):
    """Call the existing one-shot CLI once. No catch-up loop or wrapper retry."""
    record = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "environment": profile if profile in {"testing", "development"} else "invalid",
              "status": "unavailable", "processed": 0, "exit_code": 1}
    try:
        with _local_run_lock():
            # Fail closed BEFORE any processor/credential access if logging fails.
            try:
                _append(dict(record, status="started", exit_code=None))
            except Exception as exc:
                record["first_failure"] = safe_failure("schedule", "terminal_publication", exc)
                record["status"] = "reporting_failed"
            else:
                try:
                    _validate_environment(dict(os.environ), profile)
                    arguments = _arguments(profile, enabled, account, page, recipient, management_enabled)
                    scope = (management_intent_fingerprint, management_identity_fingerprint, management_deadline)
                    if any(value is not None for value in scope):
                        if not all(type(value) is str for value in scope) or profile != "testing" or not enabled or not management_enabled:
                            raise ValueError("Complete controlled intent scope required.")
                        for name, value in zip(("management-intent-fingerprint", "management-identity-fingerprint", "management-deadline"), scope):
                            arguments += ["--" + name, value]
                except Exception as exc:
                    record.setdefault("first_failure", safe_failure("schedule", "configuration", exc))
                    record.update(status="invalid_configuration", exit_code=2)
                else:
                    try:
                        output = StringIO()
                        with redirect_stdout(output), redirect_stderr(StringIO()):
                            code = processor.main(arguments)
                        result = json.loads(output.getvalue())
                        if (set(result) not in ({"status", "processed"}, {"status", "processed", "first_failure"})
                                or result["status"] not in {"processed", "disabled", "unavailable"}
                                or type(result["processed"]) is not int or not 0 <= result["processed"] <= 20
                                or type(code) is not int or code not in {0, 1, 2, 130}):
                            raise ValueError("Invalid processor result.")
                        record.update(status=result["status"], processed=result["processed"], exit_code=code)
                        if "first_failure" in result:
                            record["first_failure"] = validate_failure(result["first_failure"])
                        if code == 130:
                            record["status"] = "interrupted"
                    except KeyboardInterrupt:
                        record.update(status="interrupted", exit_code=130)
                    except Exception as exc:
                        record.update(status="unavailable", exit_code=1)
                        record.setdefault("first_failure", safe_failure("schedule", "processor_result", exc,
                            side_effects="submission_possible", predicate="invalid_result"))
                try:
                    _append(dict(record, timestamp_utc=datetime.now(timezone.utc).isoformat()))
                except Exception as exc:
                    record.update(status="reporting_failed", exit_code=1)
                    record.setdefault("first_failure", safe_failure("schedule", "terminal_publication", exc,
                        side_effects="acknowledged_outcomes_retained"))
    except _Overlap as exc:
        record.setdefault("first_failure", safe_failure("schedule", "advisory_lock", exc, predicate="schedule_overlap"))
        record.update(status="overlap", exit_code=2)
    except KeyboardInterrupt as exc:
        record.setdefault("first_failure", safe_failure("schedule", "processor_result", exc, side_effects="submission_possible"))
        record.update(status="interrupted", exit_code=130)
    except Exception as exc:
        record.setdefault("first_failure", safe_failure("schedule", "processor_result", exc, side_effects="submission_possible"))
        record.update(status="unavailable", exit_code=1)
    print(json.dumps(record, sort_keys=True), flush=True)
    return record["exit_code"]


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise diagnostic_error(ValueError("Invalid schedule arguments."), "arguments", "schedule_arguments", stage="schedule")


class _Once(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            raise diagnostic_error(ValueError("Repeated scheduling option."), "arguments", "schedule_option_once", stage="schedule")
        setattr(namespace, self.dest, values)


def main(argv=None):
    parser = _Parser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("plan", "run"):
        command = commands.add_parser(action, allow_abbrev=False)
        command.add_argument("--environment", dest="profile", required=True, action=_Once)
        command.add_argument("--enable-processing", dest="enabled", action="store_true")
        command.add_argument("--enable-management", dest="management_enabled", action="store_true")
        command.add_argument("--brevo-account", dest="account", action=_Once)
        command.add_argument("--confirmation-page", dest="page", action=_Once)
        command.add_argument("--testing-recipient", dest="recipient", action=_Once)
        if action == "plan":
            command.add_argument("--windows-user", required=True, action=_Once)
        else:
            for name in ("management-intent-fingerprint", "management-identity-fingerprint", "management-deadline"):
                command.add_argument("--" + name, action=_Once)
    try:
        options = vars(parser.parse_args(argv))
        action = options.pop("action")
        if action == "plan":
            print(task_xml(**options), flush=True)
            return 0
        return run_scheduled(**options)
    except Exception as exc:
        print(json.dumps({"status": "invalid_configuration", "processed": 0, "exit_code": 2,
            "first_failure": safe_failure("schedule", "arguments", exc)}), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
