"""Offline transaction, SQLSTATE, audit, interrupt and cleanup evidence."""

import migration_offline as isolation
isolation.require_early_registration()

from dataclasses import asdict, replace
import json
import traceback
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from migration_offline import SECRET, DriverError, artifacts
from oaf_website import migrate as m, migration_config as c


def failed(runner, classification=None):
    with pytest.raises(c.MigrationError) as caught:
        runner.run()
    if classification:
        assert caught.value.classification == classification
    assert SECRET not in "".join(traceback.format_exception(caught.value))
    return caught.value.operational_result


def test_success_one_revision_one_mutating_transaction(runner):
    result = runner.run()
    conn = runner.connection
    assert result["outcome"] == "applied_and_verified"
    assert result["commit_certainty"] == "confirmed"
    assert result["transaction_outcome"] == "committed_confirmed"
    assert result["database_commit_confirmed"]
    assert result["lock_outcome"] == "release_confirmed"
    assert conn.calls.count("revision") == 1
    assert conn.commits == 1
    assert conn.calls.count("commit") == 1
    assert conn.calls.index("audit_commit_ready") < conn.calls.index("commit") < conn.calls.index("audit_postcommit")
    # Setup, revision, postcommit and advisory cleanup transactions are distinct.
    assert conn.begins == 4
    assert conn.rollbacks == 3
    assert conn.closed
    assert all(result["cleanup"][key] == "confirmed_successful" for key in result["cleanup"])
    assert runner.m._OPERATIONAL_ADAPTER_TYPES == (m.FileOperationalAuthority,)
    kwargs = runner.m.create_engine.call_args.kwargs
    assert kwargs["hide_parameters"] is True and kwargs["echo"] is False
    assert kwargs["connect_args"]["connect_timeout"] == 5


@pytest.mark.parametrize("action,target,outcome", [("verify", False, "verified_start"),
    ("verify", True, "verified_target"), ("upgrade", True, "verified_noop")])
def test_verified_repeat_and_verify_are_nonmutating(runner, action, target, outcome):
    runner.request = replace(runner.request, action=action,
                             expected_start=runner.a.target if target else runner.a.expected_start)
    runner.connection.target = target
    result = runner.m.run(runner.request, authority=runner.authority)
    assert result["outcome"] == outcome
    assert not result["mutation_started"]
    assert result["commit_certainty"] == "not_invoked"
    assert not result["database_commit_confirmed"]
    assert runner.connection.commits == 0
    assert "revision" not in runner.connection.calls
    assert result["transaction_outcome"] == "rollback_confirmed"


@pytest.mark.parametrize("phase", ["authority", "catalog"])
def test_preflight_drift_rejects_even_already_applied(runner, phase):
    runner.connection.target = True
    runner.connection.hooks[phase] = c.MigrationError(c.Failure.DRIFT)
    result = failed(runner, c.Failure.DRIFT)
    assert not result["mutation_started"] and runner.connection.commits == 0
    assert result["validation_outcome"] == "failed"


@pytest.mark.parametrize("action", ["downgrade", "stamp", "reset", "repair", "heads", "startup"])
def test_unapproved_actions_rejected_before_resources(monkeypatch, action):
    provider = Mock()
    monkeypatch.setattr(m, "load_migration_config", provider)
    a = artifacts()
    with pytest.raises(c.MigrationError, match=c.Failure.INVALID_CONFIGURATION):
        m.run(m.Request(action, "testing", a.expected_start, a.target, a.manifest_hash, a.revision_hash))
    provider.assert_not_called()


@pytest.mark.parametrize("action", ["verify", "upgrade"])
@pytest.mark.parametrize("authority", [None, SimpleNamespace(authorize=lambda *a: object())])
def test_default_operational_gate_closed_before_credentials(monkeypatch, action, authority):
    monkeypatch.setattr(c.os, "environ", {"OAF_ENV": "testing"})
    provider = Mock()
    monkeypatch.setattr(m, "load_migration_config", provider)
    a = artifacts()
    with pytest.raises(c.MigrationError, match=c.Failure.OPERATIONAL_GATE):
        m.run(m.Request(action, "testing", a.expected_start, a.target, a.manifest_hash, a.revision_hash), authority=authority)
    provider.assert_not_called()
    assert m._OPERATIONAL_ADAPTER_TYPES == (m.FileOperationalAuthority,)


def test_plan_repository_only(monkeypatch):
    monkeypatch.setattr(c.os, "environ", {"OAF_ENV": "testing"})
    a = artifacts()
    result = m.run(m.Request("plan", "testing", a.expected_start, a.target, a.manifest_hash, a.revision_hash))
    assert result["outcome"] == "planned"
    assert result["live_execution"].startswith("blocked")


@pytest.mark.parametrize("sink", [None, object(), SimpleNamespace(write=lambda *a: None)])
def test_authorization_without_usable_sink_is_rejected(runner, sink):
    runner.authority.authorize.return_value = sink
    result = failed(runner, c.Failure.OPERATIONAL_GATE)
    assert result["commit_certainty"] == "not_invoked"
    runner.m.load_migration_config.assert_not_called()


def test_failed_authentication_has_no_credential_access(runner):
    runner.authority.authorize.side_effect = RuntimeError(SECRET)
    failed(runner, c.Failure.OPERATIONAL_GATE)
    runner.m.load_migration_config.assert_not_called()


@pytest.mark.parametrize("code,expected", [("57014", c.Failure.STATEMENT_TIMEOUT),
    ("40P01", c.Failure.DEADLOCK), ("40001", c.Failure.SERIALIZATION),
    ("55P03", c.Failure.LOCK_BUSY), ("08006", c.Failure.CONNECTION),
    ("57P01", c.Failure.CONNECTION), ("57P02", c.Failure.CONNECTION),
    ("57P03", c.Failure.CONNECTION), ("23505", c.Failure.DATABASE), (None, c.Failure.TRANSACTION)])
def test_sqlstate_through_outer_runner_and_wrapped_driver(runner, code, expected):
    driver = DriverError(code)
    wrapped = SimpleNamespace(orig=driver)
    assert c.database_failure(wrapped) == expected
    runner.connection.hooks["revision"] = driver
    result = failed(runner, expected)
    assert result["commit_certainty"] == "not_invoked"
    assert result["transaction_outcome"] == "rollback_confirmed"
    assert runner.connection.calls.count("revision") == 1  # No blind retry.


@pytest.mark.parametrize("code,certainty,expected", [("40001", "rejected", c.Failure.SERIALIZATION),
    ("40P01", "rejected", c.Failure.DEADLOCK), ("57014", "uncertain", c.Failure.UNCERTAIN_COMMIT),
    ("08006", "uncertain", c.Failure.UNCERTAIN_COMMIT), (None, "uncertain", c.Failure.UNCERTAIN_COMMIT)])
def test_commit_rejected_or_uncertain_never_reported_confirmed(runner, code, certainty, expected):
    runner.connection.hooks["commit"] = DriverError(code)
    result = failed(runner, expected)
    assert result["commit_certainty"] == certainty
    assert not result["database_commit_confirmed"]
    assert runner.connection.calls.count("revision") == 1
    assert runner.connection.calls.index("audit_commit_ready") < runner.connection.calls.index("commit")
    if certainty == "uncertain":
        assert result["transaction_outcome"] == "unknown"
        assert result["lock_outcome"] == "release_unconfirmed"
        assert runner.connection.rollbacks == 1  # Setup only.
        assert "unlock" not in runner.connection.calls
        assert result["cleanup_attempts"]["rollback"] == ["confirmed_successful"]
        assert result["secondary_failures"] == [
            {"component": "commit", "classification": c.database_failure(DriverError(code))}]
        assert "rollback" not in runner.connection.calls[runner.connection.calls.index("commit") + 1:]
    else:
        assert result["classification"] == expected
        assert result["transaction_outcome"] == "commit_rejected"
        assert result["cleanup"]["rollback"] == "confirmed_successful"
        assert result["cleanup_attempts"]["rollback"] == ["confirmed_successful"] * 3
        assert result["lock_outcome"] == "release_confirmed"
        assert result["secondary_failures"] == []
        assert runner.connection.calls.index("commit") < runner.connection.calls.index("rollback", runner.connection.calls.index("commit"))
    assert runner.connection.calls.count("commit") == 1


@pytest.mark.parametrize("phase", ["authorization", "lock", "preflight", "revision", "precommit", "commit_ready"])
def test_failed_audit_prevents_commit(runner, phase):
    runner.connection.hooks["audit_" + phase] = RuntimeError(SECRET)
    result = failed(runner, c.Failure.AUDIT_WRITE)
    assert runner.connection.commits == 0
    assert "commit" not in runner.connection.calls  # Invocation, not successful-return count.
    assert result["commit_certainty"] == "not_invoked"
    if phase == "authorization":
        runner.m.load_migration_config.assert_not_called()
        assert result["transaction_outcome"] == "not_started"
        assert result["cleanup"]["rollback"] == "not_attempted"
        assert runner.connection.calls == ["audit_authorization", "finalize"]
    else:
        assert result["transaction_outcome"] == "rollback_confirmed"
        assert result["cleanup"]["rollback"] == "confirmed_successful"
        assert result["cleanup_attempts"]["rollback"] == ["confirmed_successful"] * 3
        assert runner.connection.calls.index("audit_" + phase) < runner.connection.calls.index(
            "rollback", runner.connection.calls.index("audit_" + phase))
    assert result["audit_write_outcome"] == "failed"


def test_postcommit_failure_preserves_confirmed_database_commit(runner):
    runner.connection.hooks["catalog"] = [None, None, c.MigrationError(c.Failure.DRIFT)]
    result = failed(runner, c.Failure.DRIFT)
    assert result["commit_certainty"] == "postcommit_verification_failed"
    assert result["database_commit_confirmed"]
    assert result["transaction_outcome"] == "committed_confirmed"
    assert runner.connection.calls.count("commit") == 1
    assert runner.connection.calls.count("revision") == 1
    assert result["cleanup"]["rollback"] == "confirmed_successful"


def test_precommit_target_mismatch_rolls_back(runner):
    runner.connection.hooks["catalog"] = [None, lambda c: "base"]
    result = failed(runner, c.Failure.DRIFT)
    assert result["validation_outcome"] == "failed"
    assert runner.connection.commits == 0


@pytest.mark.parametrize("phase", ["audit_authorization", "revision", "catalog", "audit_precommit",
    "audit_commit_ready", "commit", "audit_postcommit", "unlock", "absence", "close", "dispose", "finalize"])
def test_interruptions_are_sanitized_and_certainty_preserved(runner, phase):
    if phase == "catalog":
        runner.connection.hooks[phase] = [None, KeyboardInterrupt()]
    else:
        runner.connection.hooks[phase] = KeyboardInterrupt()
    result = failed(runner, c.Failure.UNCERTAIN_COMMIT if phase == "commit" else c.Failure.INTERRUPTED)
    assert result["interruption_phase"]
    if phase == "commit":
        assert result["commit_certainty"] == "uncertain"
        assert not result["database_commit_confirmed"]
    elif phase in {"audit_postcommit", "unlock", "absence", "close", "dispose", "finalize"}:
        assert result["database_commit_confirmed"]
    else:
        assert result["commit_certainty"] == "not_invoked"
        assert not result["database_commit_confirmed"]


@pytest.mark.parametrize("component,hook", [("rollback", "rollback"), ("advisory_unlock", "unlock"),
    ("advisory_unlock", "absence"), ("connection_close", "close"),
    ("engine_dispose", "dispose"), ("audit_finalize", "finalize")])
@pytest.mark.parametrize("secondary", [RuntimeError(SECRET), KeyboardInterrupt()])
def test_primary_failure_authoritative_with_secondary_cleanup_evidence(runner, component, hook, secondary):
    runner.connection.hooks["revision"] = DriverError("40P01")
    runner.connection.hooks[hook] = [None, secondary] if hook == "rollback" else secondary
    result = failed(runner, c.Failure.DEADLOCK)
    assert result["commit_certainty"] == "not_invoked"
    assert not result["database_commit_confirmed"]
    assert result["cleanup"][component] == ("unconfirmed" if isinstance(secondary, KeyboardInterrupt) else "failed")
    assert any(f["component"] == component for f in result["secondary_failures"])
    assert result["failed_phase"] == "revision"
    if component == "rollback":
        # A later successful rollback does not erase the failed attempt.
        assert len(result["cleanup_attempts"]["rollback"]) >= 2


def test_final_audit_failure_after_commit_is_distinct(runner):
    runner.connection.hooks["finalize"] = RuntimeError(SECRET)
    result = failed(runner, c.Failure.AUDIT)
    assert result["database_commit_confirmed"]
    assert result["commit_certainty"] == "confirmed"
    assert result["transaction_outcome"] == "committed_confirmed"
    assert result["secondary_failures"] == [{"component": "audit_finalize", "classification": c.Failure.AUDIT}]
    assert result["cleanup"]["audit_finalize"] == "failed"


def test_j8_commit_hook_observes_actual_invocation_boundary(runner, monkeypatch):
    evidence = []
    original = m._Evidence
    def construct(*args, **kwargs):
        state = original(*args, **kwargs)
        evidence.append(state)
        return state
    monkeypatch.setattr(m, "_Evidence", construct)
    observed = []
    def commit_hook(conn):
        state = evidence[0]
        observed.append((state.phase, state.commit, state.transaction))
        assert conn.calls[-1] == "commit"
        assert not state.commit_confirmed
        assert conn.get_transaction().is_active
        assert runner.sink.events[-1].phase == "commit_ready"
        assert runner.sink.events[-1].commit_certainty == "not_invoked"
    runner.connection.hooks["commit"] = commit_hook
    result = runner.run()
    assert observed == [("commit", "invocation_begun", "mutation_possible")]
    assert evidence[0].commit == result["commit_certainty"] == "confirmed"
    assert result["transaction_outcome"] == "committed_confirmed"
    assert runner.connection.calls.count("commit") == 1
    assert runner.sink.final_events[0].database_commit_confirmed


def test_j8_ordinary_postcommit_audit_write_failure(runner):
    runner.connection.hooks["audit_postcommit"] = RuntimeError(SECRET)
    result = failed(runner, c.Failure.AUDIT_WRITE)
    assert result["failed_phase"] == "postcommit"
    assert result["commit_certainty"] == "postcommit_verification_failed"
    assert result["database_commit_confirmed"]
    assert result["transaction_outcome"] == "committed_confirmed"
    assert result["audit_write_outcome"] == "failed"
    assert result["lock_outcome"] == "release_confirmed"
    assert runner.connection.calls.count("commit") == runner.connection.calls.count("revision") == 1
    assert runner.connection.calls.index("commit") < runner.connection.calls.index("audit_postcommit")
    assert result["cleanup"]["rollback"] == "confirmed_successful"
    assert result["cleanup_attempts"]["rollback"] == ["confirmed_successful"] * 2
    assert runner.sink.final_events[0].failure == c.Failure.AUDIT_WRITE


@pytest.mark.parametrize("case,primary,certainty,transaction,confirmed", [
    ("precommit", c.Failure.AUDIT_WRITE, "not_invoked", "rollback_confirmed", False),
    ("rejected", c.Failure.SERIALIZATION, "rejected", "commit_rejected", False),
    ("uncertain", c.Failure.UNCERTAIN_COMMIT, "uncertain", "unknown", False),
    ("postcommit", c.Failure.DRIFT, "postcommit_verification_failed", "committed_confirmed", True),
])
def test_j8_final_audit_failure_preserves_prior_exact_certainty(
        runner, case, primary, certainty, transaction, confirmed):
    if case == "precommit":
        runner.connection.hooks["audit_commit_ready"] = RuntimeError(SECRET)
    elif case in {"rejected", "uncertain"}:
        runner.connection.hooks["commit"] = DriverError("40001" if case == "rejected" else "08006")
    else:
        runner.connection.hooks["catalog"] = [None, None, c.MigrationError(c.Failure.DRIFT)]
    runner.connection.hooks["finalize"] = RuntimeError(SECRET)
    result = failed(runner, primary)
    assert result["commit_certainty"] == certainty
    assert result["transaction_outcome"] == transaction
    assert result["database_commit_confirmed"] is confirmed
    assert result["cleanup"]["audit_finalize"] == "failed"
    assert result["secondary_failures"][-1] == {"component": "audit_finalize", "classification": c.Failure.AUDIT}
    assert runner.connection.calls.count("commit") == (0 if case == "precommit" else 1)
    terminal = asdict(runner.sink.final_attempts[0])
    assert terminal["commit_certainty"] == certainty
    assert terminal["transaction_outcome"] == transaction
    assert terminal["database_commit_confirmed"] is confirmed
    assert terminal["failure"] == primary
    assert SECRET not in json.dumps({"result": result, "terminal": terminal})


def test_audit_required_fields_and_sanitized_terminal_evidence(runner):
    result = runner.run()
    phases = {event.phase for event in runner.sink.events}
    assert {"authorization", "lock", "preflight", "revision", "precommit", "commit_ready", "postcommit"} <= phases
    terminal = asdict(runner.sink.final_events[0])
    assert terminal["run_id"] == result["run_id"]
    assert terminal["operational_authority_verified"] and terminal["verified_identity"]
    assert terminal["verified_authenticated"] == c.IDENTITIES["testing"].migrator
    assert terminal["database_commit_confirmed"]
    assert terminal["cleanup"]["audit_finalize"] == "unconfirmed"
    assert result["cleanup"]["audit_finalize"] == "confirmed_successful"
    assert SECRET not in json.dumps(terminal)


def test_bounded_lock_polling_and_reentrant_lock_rejected(runner, monkeypatch):
    connection = runner.connection
    monkeypatch.setattr(m, "scalar", Mock(return_value=False))
    monkeypatch.setattr(m.time, "monotonic", Mock(side_effect=[0, 1, 5]))
    sleep = Mock()
    monkeypatch.setattr(m.time, "sleep", sleep)
    with pytest.raises(c.MigrationError, match=c.Failure.LOCK_BUSY):
        m._lock(connection)
    assert sleep.call_count == 1
    assert sleep.call_args.args[0] <= .05


def test_cli_default_gate_and_secret_arguments_are_redacted(monkeypatch, capsys):
    monkeypatch.setattr(c.os, "environ", {"OAF_ENV": "testing"})
    a = artifacts()
    argv = ["upgrade", "--environment", "testing", "--expected-start", a.expected_start,
            "--target", a.target, "--manifest-sha256", a.manifest_hash, "--revision-sha256", a.revision_hash]
    assert m.main(argv) == 1
    assert json.loads(capsys.readouterr().out)["classification"] == c.Failure.OPERATIONAL_GATE
    assert m.main(argv + [SECRET]) == 1
    assert SECRET not in capsys.readouterr().out


def test_revision_transaction_violation_rejected(runner, monkeypatch):
    def illegal_revision(*args):
        runner.connection.transaction.is_active = False
    monkeypatch.setattr(m, "_execute_revision", illegal_revision)
    result = failed(runner, c.Failure.TRANSACTION)
    assert result["commit_certainty"] == "not_invoked"


@pytest.mark.parametrize("phase", ["credential", "connection", "begin", "identity", "acquire"])
def test_failures_before_mutation_release_available_resources(runner, phase):
    error = DriverError("08006")
    if phase == "credential":
        runner.m.load_migration_config.side_effect = error
    elif phase == "connection":
        runner.engine.connect.side_effect = error
    else:
        runner.connection.hooks[phase] = error
    result = failed(runner, c.Failure.CONNECTION)
    assert not result["mutation_started"]
    assert result["commit_certainty"] == "not_invoked"
    assert "revision" not in runner.connection.calls
    if phase != "credential":
        assert result["cleanup"]["engine_dispose"] == "confirmed_successful"


@pytest.mark.parametrize("error", [KeyboardInterrupt(), DriverError("08006")])
def test_setup_rollback_failure_preserves_failed_attempt(runner, error):
    runner.connection.hooks["rollback"] = [error]
    result = failed(runner, c.Failure.INTERRUPTED if isinstance(error, KeyboardInterrupt) else c.Failure.CONNECTION)
    assert not result["mutation_started"]
    assert result["cleanup"]["rollback"] == ("unconfirmed" if isinstance(error, KeyboardInterrupt) else "failed")
    assert result["lock_outcome"] == "release_confirmed"
    assert not result["database_commit_confirmed"]


def test_noop_requires_confirmed_rollback(runner):
    runner.connection.target = True
    request = replace(runner.request, expected_start=runner.a.target)
    runner.run = lambda: m.run(request, authority=runner.authority)
    runner.connection.hooks["rollback"] = [None, KeyboardInterrupt()]
    result = failed(runner, c.Failure.INTERRUPTED)
    assert result["outcome"] == "failed"
    assert not result["mutation_started"]
    assert result["cleanup"]["rollback"] == "unconfirmed"


def test_lock_busy_and_preexisting_session_lock(runner):
    runner.connection.lock = True
    result = failed(runner, c.Failure.LOCK_BUSY)
    assert result["lock_outcome"] == "busy"
    assert not result["mutation_started"]
    assert "acquire" not in runner.connection.calls
    assert "unlock" not in runner.connection.calls


def test_missing_target_postcommit_is_failure_after_confirmed_commit(runner):
    runner.connection.hooks["catalog"] = [None, None, lambda conn: "base"]
    result = failed(runner, c.Failure.POSTCOMMIT)
    assert result["database_commit_confirmed"]
    assert result["commit_certainty"] == "postcommit_verification_failed"


def test_unexpected_start_before_mutation(runner):
    runner.connection.hooks["catalog"] = lambda conn: "unknown"
    result = failed(runner, c.Failure.STARTING_REVISION)
    assert not result["mutation_started"]


@pytest.mark.parametrize("needle,wrong", [("current_setting('search_path')", "public"),
    ("name='lock_timeout'", 0), ("name='statement_timeout'", 0)])
def test_limits_verified_not_assumed(runner, monkeypatch, needle, wrong):
    original = m.scalar
    monkeypatch.setattr(m, "scalar", lambda conn, sql, **kw: wrong if needle in sql else original(conn, sql, **kw))
    result = failed(runner, c.Failure.INVALID_CONFIGURATION)
    assert not result["mutation_started"]


def test_secondary_failures_all_retained(runner):
    runner.connection.hooks.update(revision=DriverError("40P01"),
        unlock=KeyboardInterrupt(), close=RuntimeError(SECRET),
        dispose=KeyboardInterrupt(), finalize=RuntimeError(SECRET))
    result = failed(runner, c.Failure.DEADLOCK)
    assert {f["component"] for f in result["secondary_failures"]} == {
        "advisory_unlock", "connection_close", "engine_dispose", "audit_finalize"}
    assert not result["database_commit_confirmed"]


@pytest.mark.parametrize("classified", [c.Failure.DRIFT, c.Failure.AUDIT_WRITE])
def test_registered_classification_and_commit_conservatism(classified):
    error = c.MigrationError(classified)
    assert c.database_failure(error) == classified
    assert c.database_failure(error, committing=True) == c.Failure.UNCERTAIN_COMMIT
    assert str(c.MigrationError(SECRET)) == c.Failure.TRANSACTION


@pytest.mark.parametrize("case,exit_code", [("interrupt", 130), ("generic", 1), ("result", 0)])
def test_cli_terminal_outcomes_redacted(monkeypatch, capsys, case, exit_code):
    if case == "interrupt":
        operation = Mock(side_effect=KeyboardInterrupt())
    elif case == "generic":
        operation = Mock(side_effect=RuntimeError(SECRET))
    else:
        operation = Mock(return_value={"outcome": "planned"})
    monkeypatch.setattr(m, "run", operation)
    argv = ["plan", "--environment", "testing", "--expected-start", "base", "--target", "0001_migration_baseline",
            "--manifest-sha256", "0"*64, "--revision-sha256", "0"*64]
    assert m.main(argv) == exit_code
    assert SECRET not in capsys.readouterr().out
