"""J1 single-use runner context and Alembic environment's independent gates."""

import migration_offline as isolation
isolation.require_early_registration()

from contextlib import nullcontext
from dataclasses import replace
import runpy
import traceback
from types import SimpleNamespace
from unittest.mock import Mock

from alembic import context, command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError
from sqlalchemy.schema import CreateTable

from migration_offline import ROOT, SECRET, FakeConnection, DriverError, artifacts
from oaf_website import migrate as m, migration_validation as v, migration_config as c


@pytest.fixture
def context_setup(monkeypatch, request):
    a = artifacts()
    i = c.IDENTITIES[getattr(request, "param", "testing")]
    conn = FakeConnection()
    transaction = conn.begin()
    conn.lock = True
    authority, sink = object(), object()
    request = m.Request("upgrade", i.environment, a.expected_start, a.target, a.manifest_hash, a.revision_hash)
    evidence = m._Evidence(request, i, "synthetic-run")
    for key, value in dict(authorized=True, audit_acknowledged=True, verified=True,
        session_lock_verified=True, phase="revision", validation="preflight_passed",
        observed_start=a.expected_start, operational_authority=authority, audit_sink=sink,
        verified_connection=conn, verified_transaction=transaction, session_lock_backend=701).items():
        setattr(evidence, key, value)
    config = Config()
    monkeypatch.setattr(context, "config", config, raising=False)
    for key, value in {"is_offline_mode": False, "get_x_argument": [], "get_tag_argument": None,
                       "get_revision_argument": a.target}.items():
        monkeypatch.setattr(context, key, Mock(return_value=value))
    configure, execute = Mock(), Mock()
    monkeypatch.setattr(context, "configure", configure)
    monkeypatch.setattr(context, "begin_transaction", lambda: nullcontext())
    monkeypatch.setattr(context, "run_migrations", execute)
    monkeypatch.setattr(m, "_require_operational_adapter", Mock())
    monkeypatch.setattr(v, "verify_identity", Mock())
    monkeypatch.setattr(v, "verify_authority", Mock())
    monkeypatch.setattr(v, "catalog_state", Mock(return_value=v.BASE))
    return SimpleNamespace(a=a, i=i, conn=conn, transaction=transaction, e=evidence,
                           authority=authority, sink=sink, config=config, configure=configure,
                           execute=execute,
                           issue=lambda: v._runner_execution(conn, i, a, transaction, evidence, sink, authority, 701),
                           env=lambda: runpy.run_path(str(ROOT / "migrations/env.py")))


def test_valid_single_use_context_rejected_after_consumption_and_scope(context_setup):
    s = context_setup
    with s.issue() as runner:
        assert v.consume_runner_context(runner) is runner
        with pytest.raises(c.MigrationError, match=c.Failure.OPERATIONAL_GATE):
            v.consume_runner_context(runner)
    with pytest.raises(c.MigrationError, match=c.Failure.OPERATIONAL_GATE):
        v.consume_runner_context(runner)
    assert not v._ACTIVE_RUNNERS


@pytest.mark.parametrize("value", [None, {}, object(), SimpleNamespace(authorized=True)])
def test_missing_fabricated_context_rejected(value):
    with pytest.raises(c.MigrationError, match=c.Failure.OPERATIONAL_GATE):
        v.consume_runner_context(value)


@pytest.mark.parametrize("field,value", [
    ("authorized", False), ("audit_acknowledged", False), ("verified", False),
    ("session_lock_verified", False), ("session_lock_backend", 702),
    ("audit_sink", None), ("operational_authority", None), ("verified_connection", object()),
    ("verified_transaction", object()), ("phase", "precommit"), ("validation", "failed"),
    ("commit", "confirmed"), ("observed_start", "wrong"), ("identity", c.IDENTITIES["development"]),
])
def test_context_evidence_binding_rejects_mismatch(context_setup, field, value):
    s = context_setup
    setattr(s.e, field, value)
    with s.issue() as runner:
        with pytest.raises(c.MigrationError, match=c.Failure.OPERATIONAL_GATE):
            v.consume_runner_context(runner)


@pytest.mark.parametrize("field,value", [("environment", "development"), ("action", "verify"),
    ("target", "head"), ("expected_start", "wrong"), ("manifest_hash", "0"*64), ("revision_hash", "0"*64)])
def test_context_binds_request_to_exact_artifact_and_transition(context_setup, field, value):
    s = context_setup
    s.e.request = replace(s.e.request, **{field: value})
    with s.issue() as runner:
        with pytest.raises(c.MigrationError, match=c.Failure.OPERATIONAL_GATE):
            v.consume_runner_context(runner)


def test_alembic_env_positive_uses_existing_transaction(context_setup):
    s = context_setup
    with s.issue() as runner:
        s.config.attributes["oaf_runner"] = runner
        s.env()
    s.execute.assert_called_once()
    kwargs = s.configure.call_args.kwargs
    assert kwargs["connection"] is s.conn
    assert kwargs["version_table_schema"] == "oaf_website"
    assert kwargs["version_table"] == "alembic_version" and kwargs["version_table_pk"]
    assert kwargs["transactional_ddl"] is True
    assert kwargs["transaction_per_migration"] is False
    assert s.conn.get_transaction() is s.transaction
    assert s.conn.commits == 0


@pytest.mark.parametrize("context_setup", c.IDENTITIES, indirect=True)
def test_stage5_installed_alembic_schema_transaction_and_history(context_setup):
    """Compile only: real Alembic/SQLAlchemy, synthetic session, no SQL dispatch."""
    s = context_setup
    with s.issue() as runner:
        s.config.attributes["oaf_runner"] = runner
        s.env()
    options = dict(s.configure.call_args.kwargs)
    assert options.pop("connection") is s.conn
    assert options["target_metadata"] is None  # Explicit revisions; no autogeneration.
    s.conn.dialect = postgresql.dialect()
    migration = MigrationContext.configure(connection=s.conn, opts=options)
    before = list(s.conn.calls)
    with migration.begin_transaction():
        assert s.conn.get_transaction() is s.transaction
    assert s.conn.calls == before  # Alembic does not begin/commit the owner's transaction.
    assert s.transaction.is_active and s.conn.commits == 0
    # Compile the installed implementation's version table, never execute it.
    ddl = str(CreateTable(migration._version).compile(dialect=s.conn.dialect))
    assert ' '.join(ddl.split()) == (
        'CREATE TABLE oaf_website.alembic_version ( version_num VARCHAR(32) NOT NULL, '
        'CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num) )')
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert script.get_bases() == [v.BASELINE]
    assert script.get_heads() == [v.NOTIFICATIONS]
    assert [(r.revision, r.down_revision) for r in script.walk_revisions()] == [
        (v.NOTIFICATIONS, v.STATE_REQUESTS),
        (v.STATE_REQUESTS, v.BASELINE), (v.BASELINE, None)]


@pytest.mark.parametrize("case", ["offline", "missing", "fabricated", "transaction", "inactive", "nested",
    "url", "cmd_opts", "x", "tag", "target", "start", "lock", "owner", "artifact", "environment"])
def test_alembic_env_rejects_unsupported_context_before_execution(context_setup, monkeypatch, case):
    s = context_setup
    with s.issue() as runner:
        s.config.attributes["oaf_runner"] = runner
        if case == "offline":
            context.is_offline_mode.return_value = True
        elif case == "missing":
            s.config.attributes.clear()
        elif case == "fabricated":
            s.config.attributes["oaf_runner"] = SimpleNamespace(**runner.__dict__)
        elif case == "transaction":
            s.conn.transaction = object()
        elif case == "inactive":
            s.transaction.is_active = False
        elif case == "nested":
            monkeypatch.setattr(s.conn, "in_nested_transaction", lambda: True)
        elif case == "url":
            s.config.set_main_option("sqlalchemy.url", "synthetic-only")
        elif case == "cmd_opts":
            s.config.cmd_opts = object()
        elif case in {"x", "tag", "target"}:
            getattr(context, {"x": "get_x_argument", "tag": "get_tag_argument", "target": "get_revision_argument"}[case]).return_value = "wrong"
        elif case == "start":
            v.catalog_state.return_value = v.BASELINE
        elif case == "lock":
            s.conn.lock = False
        elif case == "owner":
            v.verify_identity.side_effect = c.MigrationError(c.Failure.WRONG_IDENTITY)
        elif case == "artifact":
            monkeypatch.setattr(v, "validate_artifacts", Mock(side_effect=c.MigrationError(c.Failure.ARTIFACT_HASH)))
        else:
            s.e.request = replace(s.e.request, environment="development")
        with pytest.raises(c.MigrationError):
            s.env()
    s.execute.assert_not_called()


@pytest.mark.parametrize("code,expected", [("57014", c.Failure.STATEMENT_TIMEOUT),
    ("40P01", c.Failure.DEADLOCK), ("40001", c.Failure.SERIALIZATION),
    ("08006", c.Failure.CONNECTION), (None, c.Failure.TRANSACTION)])
def test_alembic_env_driver_failure_classification(context_setup, code, expected):
    s = context_setup
    s.execute.side_effect = DriverError(code)
    with s.issue() as runner:
        s.config.attributes["oaf_runner"] = runner
        with pytest.raises(c.MigrationError, match=expected) as caught:
            s.env()
        assert SECRET not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("code,expected", [
    ("55P03", c.Failure.LOCK_BUSY), ("57014", c.Failure.STATEMENT_TIMEOUT),
    ("40P01", c.Failure.DEADLOCK), ("40001", c.Failure.SERIALIZATION),
    ("08001", c.Failure.CONNECTION), ("08006", c.Failure.CONNECTION),
    ("ZZ999", c.Failure.DATABASE),
])
def test_j7_sqlalchemy_wrapped_error_through_alembic_and_runner(
        runner, context_setup, monkeypatch, capsys, caplog, code, expected):
    import json
    from dataclasses import asdict
    from test_migration_runner import failed

    s = context_setup
    raw_sql = "SELECT STAGE3_SENSITIVE_RAW_SQL"
    driver = DriverError(code)
    wrapped = DBAPIError(raw_sql, {"private_parameter": SECRET}, driver,
                        connection_invalidated=code.startswith("08"))
    assert wrapped.orig is driver and wrapped.orig.sqlstate == code
    s.execute.side_effect = wrapped
    observed = []

    def alembic_upgrade(config, target):
        assert target == v.BASELINE
        # The real runner's _execute_revision issues the single-use context;
        # the actual env.py consumes it and classifies the SQLAlchemy exception.
        monkeypatch.setattr(context, "config", config)
        try:
            s.env()
        except c.MigrationError as error:
            observed.append(error.classification)
            assert SECRET not in "".join(traceback.format_exception(error))
            assert raw_sql not in "".join(traceback.format_exception(error))
            raise

    upgrade = Mock(side_effect=alembic_upgrade)
    monkeypatch.setattr(command, "upgrade", upgrade)
    monkeypatch.setattr(m, "_execute_revision", runner.real_execute_revision)
    result = failed(runner, expected)
    assert observed == [expected]  # Category survives both real boundaries.
    assert result["classification"] == expected and result["failed_phase"] == "revision"
    assert wrapped.orig.sqlstate == code
    upgrade.assert_called_once()
    s.execute.assert_called_once()  # No automatic retry at Alembic or runner.
    assert "commit" not in runner.connection.calls
    assert result["commit_certainty"] == "not_invoked"
    assert result["transaction_outcome"] == "rollback_confirmed"
    assert result["cleanup_attempts"]["rollback"] == ["confirmed_successful"] * 3
    assert result["lock_outcome"] == "release_confirmed"
    assert not result["database_commit_confirmed"]
    assert not result["secondary_failures"]
    evidence = json.dumps({"result": result,
        "audit": [asdict(e) for e in runner.sink.write_attempts],
        "terminal": [asdict(e) for e in runner.sink.final_attempts]})
    assert SECRET not in evidence and raw_sql not in evidence
    assert "private_parameter" not in evidence
    assert runner.sink.final_events[0].failure == expected
    assert capsys.readouterr() == ("", "")
    assert not caplog.records
    assert not v._ACTIVE_RUNNERS


def test_env_requires_transaction_survive_revision(context_setup):
    s = context_setup
    s.execute.side_effect = lambda: setattr(s.transaction, "is_active", False)
    with s.issue() as runner:
        s.config.attributes["oaf_runner"] = runner
        with pytest.raises(c.MigrationError, match=c.Failure.TRANSACTION):
            s.env()


def test_runner_calls_only_exact_upgrade_and_revokes_context(context_setup, monkeypatch):
    s = context_setup
    seen = []
    def upgrade(config, target):
        seen.append(config)
        assert target == v.BASELINE
        assert v.consume_runner_context(config.attributes["oaf_runner"])
        raise DriverError("40P01")
    monkeypatch.setattr(command, "upgrade", upgrade)
    with pytest.raises(DriverError):
        m._execute_revision(s.conn, s.i, s.a, s.transaction, s.e, s.sink, s.authority, 701)
    assert "oaf_runner" not in seen[0].attributes
    assert not v._ACTIVE_RUNNERS


def test_direct_alembic_invocation_without_runner_denied(context_setup):
    with pytest.raises(c.MigrationError, match=c.Failure.OPERATIONAL_GATE):
        context_setup.env()


def test_exact_class_fabricated_context_not_registered(context_setup):
    s = context_setup
    with s.issue() as runner:
        fabricated = replace(runner)
        with pytest.raises(c.MigrationError, match=c.Failure.OPERATIONAL_GATE):
            v.consume_runner_context(fabricated)


def test_unregistered_owner_identity_rejected_by_env(context_setup):
    s = context_setup
    wrong = replace(s.i, owner="postgres")
    s.e.identity = wrong
    with v._runner_execution(s.conn, wrong, s.a, s.transaction, s.e, s.sink, s.authority, 701) as runner:
        s.config.attributes["oaf_runner"] = runner
        with pytest.raises(c.MigrationError, match=c.Failure.INVALID_CONFIGURATION):
            s.env()


@pytest.mark.parametrize("backend,lock", [(None, True), (True, True), (702, True), (701, False)])
def test_session_lock_requires_valid_backend_and_catalog_evidence(context_setup, backend, lock):
    s = context_setup
    s.conn.lock = lock
    with pytest.raises(c.MigrationError, match=c.Failure.LOCK_BUSY):
        v.verify_session_lock(s.conn, backend, m.LOCK_ID)


@pytest.mark.parametrize("needle,wrong", [("current_setting('search_path')", "public"),
    ("name='lock_timeout'", 0), ("name='statement_timeout'", 0)])
def test_env_independently_checks_limits(context_setup, monkeypatch, needle, wrong):
    s = context_setup
    original = v.scalar
    monkeypatch.setattr(v, "scalar", lambda conn, sql, **kw: wrong if needle in sql else original(conn, sql, **kw))
    with s.issue() as runner:
        s.config.attributes["oaf_runner"] = runner
        with pytest.raises(c.MigrationError, match=c.Failure.INVALID_CONFIGURATION):
            s.env()
    s.execute.assert_not_called()


@pytest.mark.parametrize("environment", c.IDENTITIES)
@pytest.mark.parametrize("action", ["verify", "upgrade"])
@pytest.mark.parametrize("entrypoint", ["cli", "runner", "supplied_authority"])
def test_stage5_unpatched_operational_gate_at_entry_points(
        monkeypatch, capsys, caplog, environment, action, entrypoint):
    """Valid artifact integrity and a working caller sink confer no approval."""
    import json
    from uuid import UUID

    monkeypatch.setattr(c.os, "environ", {"OAF_ENV": environment})
    a = artifacts()
    request = m.Request(action, environment, a.expected_start, a.target,
                        a.manifest_hash, a.revision_hash)
    sink = SimpleNamespace(write=Mock(), finalize=Mock())
    authority = SimpleNamespace(authorize=Mock(return_value=sink))
    provider = Mock(side_effect=AssertionError(SECRET))
    engine = Mock(side_effect=AssertionError(SECRET))
    monkeypatch.setattr(m, "load_migration_config", provider)
    monkeypatch.setattr(m, "create_engine", engine)

    if entrypoint == "cli":
        assert m.main([
            action, "--environment", environment,
            "--expected-start", a.expected_start, "--target", a.target,
            "--manifest-sha256", a.manifest_hash,
            "--revision-sha256", a.revision_hash,
        ]) == 1
        captured = capsys.readouterr()
        assert captured.err == "" and SECRET not in captured.out
        result = json.loads(captured.out)
    else:
        with pytest.raises(c.MigrationError, match=c.Failure.OPERATIONAL_GATE) as caught:
            m.run(request, authority=authority if entrypoint == "supplied_authority" else None)
        assert SECRET not in "".join(traceback.format_exception(caught.value))
        result = caught.value.operational_result
        assert capsys.readouterr() == ("", "")

    assert result["classification"] == c.Failure.OPERATIONAL_GATE
    assert result["outcome"] == "failed" and result["failed_phase"] == "authorization"
    assert str(UUID(result["run_id"])) == result["run_id"]
    assert result["commit_certainty"] == "not_invoked"
    assert result["transaction_outcome"] == "not_started"
    assert not result["mutation_started"] and not result["database_commit_confirmed"]
    # This case intentionally removes LOCALAPPDATA: persistence must fail closed.
    assert result["audit_write_outcome"] == "failed"
    assert all(value == "not_attempted" for value in result["cleanup"].values())
    assert not result["secondary_failures"]
    authority.authorize.assert_not_called()
    sink.write.assert_not_called()
    sink.finalize.assert_not_called()
    provider.assert_not_called()
    engine.assert_not_called()
    assert not caplog.records
    assert m._OPERATIONAL_ADAPTER_TYPES == (m.FileOperationalAuthority,)


@pytest.mark.parametrize("environment", c.IDENTITIES)
def test_stage5_internal_execution_and_real_alembic_cannot_bypass_gate(environment):
    """Even a private, active runner context cannot unlock the real env.py gate.

    Alembic loads env.py, but the unpatched gate rejects before SQL dispatch,
    context configuration, version-table creation or revision execution.
    """
    a = artifacts()
    identity = c.IDENTITIES[environment]
    connection = FakeConnection()
    transaction = connection.begin()
    connection.lock = True
    sink = SimpleNamespace(write=Mock(), finalize=Mock())
    authority = SimpleNamespace(authorize=Mock(return_value=sink))
    request = m.Request("upgrade", environment, a.expected_start, a.target,
                        a.manifest_hash, a.revision_hash)
    evidence = m._Evidence(request, identity, "synthetic-run")
    for key, value in dict(
        authorized=True, audit_acknowledged=True, verified=True,
        session_lock_verified=True, phase="revision", validation="preflight_passed",
        observed_start=a.expected_start, operational_authority=authority,
        audit_sink=sink, verified_connection=connection,
        verified_transaction=transaction, session_lock_backend=701,
    ).items():
        setattr(evidence, key, value)
    before = list(connection.calls)
    with pytest.raises(c.MigrationError, match=c.Failure.OPERATIONAL_GATE):
        m._execute_revision(connection, identity, a, transaction,
                            evidence, sink, authority, 701)
    assert connection.calls == before
    assert transaction.is_active and connection.commits == 0
    assert not v._ACTIVE_RUNNERS
    authority.authorize.assert_not_called()
    sink.write.assert_not_called()
    sink.finalize.assert_not_called()
    assert m._OPERATIONAL_ADAPTER_TYPES == (m.FileOperationalAuthority,)
