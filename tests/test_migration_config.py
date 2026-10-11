"""Explicit migration registry, synthetic credentials, redaction, import safety."""

import migration_offline as isolation
isolation.require_early_registration()

from dataclasses import replace
from pathlib import Path
import socket
import sqlite3
import sys
import traceback
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import psycopg
import pytest
from sqlalchemy.engine import URL
from sqlalchemy.engine import Engine

from migration_offline import SECRET
from oaf_website import database_config as db, migration_config as c


@pytest.mark.parametrize("environment", c.IDENTITIES)
def test_explicit_registry_and_selected_credential(monkeypatch, environment):
    provider = Mock(return_value=SECRET)
    monkeypatch.setattr(c, "_windows_password", provider)
    config = c.load_migration_config(environment=environment, environ={"OAF_ENV": environment})
    identity = c.IDENTITIES[environment]
    provider.assert_called_once_with(identity.credential_service, identity.migrator,
                                     {"OAF_ENV": environment}, exact_target=True)
    assert config.url.database == identity.database
    assert config.url.username == identity.migrator
    assert config.url.password == SECRET
    assert SECRET not in repr(config) + str(config.url)
    with pytest.raises(db.DatabaseConfigurationError):
        db.DatabaseConfig(environment, config.url)


@pytest.mark.parametrize("environment,environ", [
    ("testing", {}), ("testing", {"OAF_ENV": "development"}),
    ("testing", {"OAF_ENV": "Testing"}), ("Testing", {"OAF_ENV": "Testing"}),
    ("production", {"OAF_ENV": "production"}), ("unknown", {"OAF_ENV": "unknown"}),
    (None, {}), ("testing", {"OAF_ENV": " testing"}),
])
def test_invalid_environment_precedes_credentials(monkeypatch, environment, environ):
    provider = Mock()
    monkeypatch.setattr(c, "_windows_password", provider)
    with pytest.raises(c.MigrationError, match=c.Failure.INVALID_CONFIGURATION):
        c.load_migration_config(environment=environment, environ=environ)
    provider.assert_not_called()


@pytest.mark.parametrize("key", ["DATABASE_URL", "database_url", "DB_HOST", "PGHOST", "PGPASSFILE",
    "PGPASSWORD", "PGSERVICE", "SQLALCHEMY_DATABASE_URI", "SQLALCHEMY_URL", "OAF_DATABASE",
    "OTHER_KEYRING_PROPERTY_GET_CREDENTIAL", "PYTHON_KEYRING_BACKEND"])
def test_conflicting_environment_is_sanitized(monkeypatch, key):
    provider = Mock()
    monkeypatch.setattr(c, "_windows_password", provider)
    with pytest.raises(c.MigrationError) as caught:
        c.load_migration_config(environment="testing", environ={"OAF_ENV": "testing", key: SECRET})
    assert SECRET not in str(caught.value)
    provider.assert_not_called()


@pytest.mark.parametrize("settings", [{"database": "wrong"}, {"username": "wrong"},
    {"credential_service": "wrong"}, {"credential_account": "wrong"}, {"url": SECRET}, ["wrong"]])
def test_no_settings_override(monkeypatch, settings):
    provider = Mock()
    monkeypatch.setattr(c, "_windows_password", provider)
    with pytest.raises(c.MigrationError):
        c.load_migration_config(environment="testing", environ={"OAF_ENV": "testing"}, settings=settings)
    provider.assert_not_called()


@pytest.mark.parametrize("change", [{"database": "wrong"}, {"username": "wrong"}, {"host": "localhost"},
    {"port": 5433}, {"drivername": "sqlite"}, {"query": {"url": SECRET}}, {"password": ""}, {"password": None}])
def test_url_identity_is_fixed(change):
    i = c.IDENTITIES["testing"]
    values = dict(drivername="postgresql+psycopg", username=i.migrator, host=i.host,
                  port=i.port, database=i.database, password=SECRET)
    values.update(change)
    with pytest.raises(c.MigrationError):
        c.MigrationConfig(i, URL.create(**values))


@pytest.mark.parametrize("change", [{"database": "wrong"}, {"migrator": "wrong"},
    {"credential_service": "wrong"}, {"owner": "postgres"}, {"schema": "public"}])
def test_fabricated_registry_entry_rejected(change):
    i = c.IDENTITIES["testing"]
    with pytest.raises(c.MigrationError):
        c.MigrationConfig(replace(i, **change), URL.create("postgresql+psycopg"))


@pytest.mark.parametrize("value", [None, "", 123, b"synthetic"])
def test_missing_credentials(monkeypatch, value):
    monkeypatch.setattr(c, "_windows_password", Mock(return_value=value))
    with pytest.raises(c.MigrationError, match=c.Failure.CREDENTIAL_UNAVAILABLE):
        c.load_migration_config(environment="testing", environ={"OAF_ENV": "testing"})


def test_provider_exception_redacted(monkeypatch):
    monkeypatch.setattr(c, "_windows_password", Mock(side_effect=RuntimeError(SECRET)))
    with pytest.raises(c.MigrationError) as caught:
        c.load_migration_config(environment="testing", environ={"OAF_ENV": "testing"})
    assert SECRET not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("account", ["wrong", "oaf_website_test_migrator"])
def test_exact_windows_adapter_reference_with_synthetic_backend(stage5_vault, account):
    service = "OAF Website/testing/PostgreSQL/Migrations"
    stage5_vault.entries[service] = stage5_vault.credential(service, account)
    if account == "wrong":
        with pytest.raises(c.MigrationError, match=c.Failure.CREDENTIAL_UNAVAILABLE):
            c.load_migration_config(environment="testing", environ={"OAF_ENV": "testing"})
    else:
        assert c.load_migration_config(environment="testing", environ={"OAF_ENV": "testing"}).url.password == SECRET
    stage5_vault.read.assert_called_once_with(service)


def test_isolation_guards_fail_closed():
    # Isolate expected probe evidence without disabling denial accounting.
    with pytest.MonkeyPatch.context() as probe:
        attempts = []
        probe.setattr(isolation, "ATTEMPTS", attempts)
        for obj, name in isolation.GUARDED_APIS:
            action = getattr(obj, name)
            assert action is isolation.denied  # Verify before invoking any API.
            before = len(attempts)
            with pytest.raises(isolation.OfflineAccess):
                action("synthetic-only")
            assert len(attempts) == before + 1
        for name in ("PGconn", "PGcancel", "PGcancelConn"):
            assert getattr(psycopg.pq, name) is isolation._DeniedNativeConnection
        for module_name in ("psycopg.pq", "psycopg_binary.pq"):
            for method in ("connect", "connect_start", "reset", "reset_start", "ping"):
                before = len(attempts)
                with pytest.raises(isolation.OfflineAccess):
                    getattr(sys.modules[module_name].PGconn, method)(b"synthetic-only")
                assert len(attempts) == before + 1
        for module_name in ("keyring", "keyring.backends.Windows", "win32cred",
                            "win32crypt", "win32vault", "win32ctypes.pywin32.win32cred"):
            for method in isolation.CREDENTIAL_METHODS:
                action = getattr(sys.modules[module_name], method)
                assert action is isolation.denied
                before = len(attempts)
                with pytest.raises(isolation.OfflineAccess):
                    action("synthetic-only")
                assert len(attempts) == before + 1
        before = len(attempts)
        with pytest.raises(isolation.OfflineAccess):
            (isolation.ROOT / "config/local/STAGE3-SYNTHETIC-DENIED").read_bytes()
        assert len(attempts) == before + 1
    assert not isolation.ATTEMPTS


def test_early_registration_and_missing_or_late_plugin_fail_closed(monkeypatch):
    assert isolation.EARLY_REGISTERED
    assert {"oaf_website", "oaf_website.migrate", "oaf_website.migration_config",
            "oaf_website.migration_validation", "oaf_website.database_config"} <= set(isolation.PRODUCTION_IMPORTS)
    # Missing and late registration share a fail-closed collection prerequisite.
    with monkeypatch.context() as state:
        state.setattr(isolation, "EARLY_REGISTERED", False)
        with pytest.raises(pytest.UsageError, match="before collection"):
            isolation.require_early_registration()
        with pytest.raises(pytest.UsageError):
            isolation._ImportGuard().find_spec("oaf_website.synthetic_late_import")
    isolation.require_early_registration()


def test_startup_rejects_unsafe_configuration_before_collection(monkeypatch):
    # Exercise the actual startup hook with synthetic pytest state; never start
    # an unguarded child pytest process or import another production module.
    manager = SimpleNamespace(get_plugin=lambda name: isolation)
    namespace = SimpleNamespace(file_or_dir=[str(isolation.ROOT / "tests/test_migration_config.py")])
    config = SimpleNamespace(pluginmanager=manager, known_args_namespace=namespace)
    safe_environment = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    for case in ("autoload", "plugins", "addopts", "missing_plugin", "interpreter",
                 "implicit_scope", "unapproved_scope", "missing_guard", "missing_native_guard",
                 "missing_credential_guard"):
        with monkeypatch.context() as state:
            state.setattr(isolation.os, "environ", dict(safe_environment))
            if case == "autoload":
                isolation.os.environ.clear()
            elif case in {"plugins", "addopts"}:
                isolation.os.environ["PYTEST_" + case.upper()] = "synthetic-uncontrolled"
            elif case == "missing_plugin":
                state.setattr(manager, "get_plugin", lambda name: None)
            elif case == "interpreter":
                state.setattr(sys, "prefix", str(isolation.ROOT))
            elif case in {"implicit_scope", "unapproved_scope"}:
                state.setattr(namespace, "file_or_dir", [] if case == "implicit_scope" else ["tests"])
            elif case == "missing_guard":
                state.setattr(psycopg.AsyncConnection, "connect", Mock())
            elif case == "missing_native_guard":
                state.setattr(psycopg.pq, "PGconn", object())
            else:
                state.setattr(sys.modules["win32cred"], "CredRead", Mock())
            with pytest.raises(pytest.UsageError):
                isolation.pytest_load_initial_conftests(config, None, [])
    assert not isolation.ATTEMPTS


def test_caught_guard_violation_still_fails_session(monkeypatch, capsys):
    with monkeypatch.context() as state:
        attempts = []
        state.setattr(isolation, "ATTEMPTS", attempts)
        try:
            psycopg.AsyncConnection.connect("synthetic-only")
        except isolation.OfflineAccess:
            pass  # Catching the operation cannot turn the session into PASS.
        assert attempts == ["external access denied"]
        for initial in (0, 1, 2, 3, 4, 5):
            session = SimpleNamespace(exitstatus=initial)
            isolation.pytest_sessionfinish(session, initial)
            assert session.exitstatus == (1 if initial == 0 else initial)
        assert "UNEXPECTED OFFLINE ACCESS ATTEMPTS: 1" in capsys.readouterr().out
    assert not isolation.ATTEMPTS


def test_audit_and_unsupported_native_routes_are_counted(monkeypatch):
    with monkeypatch.context() as state:
        attempts = []
        state.setattr(isolation, "ATTEMPTS", attempts)
        # Synthetic events never call native functions, spawn processes or send packets.
        for event in ("socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto",
                      "subprocess.Popen", "os.exec", "os.spawn", "os.startfile",
                      "sqlite3.connect", "ctypes.dlopen", "ctypes.dlsym"):
            before = len(attempts)
            with pytest.raises(isolation.OfflineAccess):
                isolation._audit_guard(event, ())
            assert len(attempts) == before + 1
        for name in ("psycopg.pq.pq_ctypes", "psycopg.pq._pq_ctypes",
                     "psycopg_c.pq", "win32ctypes.core.ctypes._win32cred", "cffi"):
            before = len(attempts)
            with pytest.raises(isolation.OfflineAccess):
                isolation._ImportGuard().find_spec(name)
            assert len(attempts) == before + 1
    assert not isolation.ATTEMPTS


def test_imports_have_no_resource_or_credential_access(monkeypatch, capsys):
    # Fresh source execution avoids replacing live module classes used elsewhere.
    monkeypatch.setattr(db, "_windows_password", isolation.denied)
    monkeypatch.setattr(db, "_read_settings", isolation.denied)
    for name in ("__init__", "database_config", "migration_config", "migration_validation", "migrate"):
        module = ModuleType("oaf_website._stage3_import_" + name)
        module.__package__ = "oaf_website"
        module.__file__ = str(isolation.ROOT / "oaf_website" / (name + ".py"))
        monkeypatch.setitem(sys.modules, module.__name__, module)
        exec(compile(Path(module.__file__).read_bytes(), module.__file__, "exec"), module.__dict__)
    assert capsys.readouterr() == ("", "")
    assert not isolation.ATTEMPTS


@pytest.fixture
def stage5_vault(monkeypatch):
    """Model the installed WinVault service/compound lookup without native code."""
    entries = {}
    read = Mock(side_effect=lambda target: entries.get(target))

    class Credential(dict):
        def __init__(self, service, account, password=SECRET):
            super().__init__(TargetName=service, UserName=account, Type=1, Persist=2)
            self.password = password

        @property
        def value(self):
            if isinstance(self.password, Exception):
                raise self.password
            return self.password

    class SyntheticVault:
        priority = 5
        _read_credential = staticmethod(read)

        def get_credential(self, service, username):
            # keyring 25.7.0's compatibility fallback must not select migration
            # credentials when the Stage 4C canonical target is absent/swapped.
            found = self._read_credential(service)
            if found is None or found['UserName'] != username:
                found = self._read_credential(f'{username}@{service}')
            return None if found is None else SimpleNamespace(
                username=found['UserName'], password=found.value)

    module = ModuleType('keyring.backends.Windows')
    module.WinVaultKeyring = SyntheticVault
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(db.sys, 'platform', 'win32')
    return SimpleNamespace(entries=entries, read=read, credential=Credential)


@pytest.mark.parametrize('environment', c.IDENTITIES)
@pytest.mark.parametrize('case', [
    'valid', 'missing', 'runtime', 'administrator', 'other_migrator',
    'target', 'type', 'persistence', 'empty', 'nonstring', 'decode_error', 'provider_error',
])
def test_stage5_exact_activated_target_only(stage5_vault, environment, case, capsys, caplog):
    vault = stage5_vault
    i = c.IDENTITIES[environment]
    other = next(j for j in c.IDENTITIES.values() if j != i)
    selected = vault.credential(i.credential_service, i.migrator)
    vault.entries[i.credential_service] = selected
    # Valid alternate entries exist: no failed lookup may try any of them.
    for service, account in (
        (f'{i.migrator}@{i.credential_service}', i.migrator),
        (i.credential_service.removesuffix('/Migrations'), i.runtime),
        (other.credential_service, other.migrator), ('postgres', 'postgres'),
    ):
        vault.entries[service] = vault.credential(service, account)
    if case == 'missing':
        del vault.entries[i.credential_service]
    elif case in {'runtime', 'administrator', 'other_migrator'}:
        selected['UserName'] = {
            'runtime': i.runtime, 'administrator': 'postgres',
            'other_migrator': other.migrator,
        }[case]
    elif case in {'target', 'type', 'persistence'}:
        field, value = {'target': ('TargetName', other.credential_service),
                        'type': ('Type', 2), 'persistence': ('Persist', 3)}[case]
        selected[field] = value
    elif case in {'empty', 'nonstring', 'decode_error'}:
        selected.password = {'empty': '', 'nonstring': b'synthetic',
                             'decode_error': RuntimeError(SECRET)}[case]
    elif case == 'provider_error':
        vault.read.side_effect = RuntimeError(SECRET)
    if case == 'valid':
        config = c.load_migration_config(environment=environment, environ={'OAF_ENV': environment})
        assert (config.url.database, config.url.username, config.url.password) == (
            i.database, i.migrator, SECRET)
        assert SECRET not in repr(config) + str(config.url)
    else:
        with pytest.raises(c.MigrationError, match=c.Failure.CREDENTIAL_UNAVAILABLE) as caught:
            c.load_migration_config(environment=environment, environ={'OAF_ENV': environment})
        assert SECRET not in ''.join(traceback.format_exception(caught.value))
    vault.read.assert_called_once_with(i.credential_service)
    assert capsys.readouterr() == ('', '')
    assert SECRET not in caplog.text


@pytest.mark.parametrize('environment', c.IDENTITIES)
def test_stage5_other_environment_rejected_before_vault(stage5_vault, environment):
    other = next(name for name in c.IDENTITIES if name != environment)
    with pytest.raises(c.MigrationError, match=c.Failure.INVALID_CONFIGURATION):
        c.load_migration_config(environment=environment, environ={'OAF_ENV': other})
    stage5_vault.read.assert_not_called()


@pytest.mark.parametrize('environment', c.IDENTITIES)
@pytest.mark.parametrize('case', ['database', 'admin_database', 'runtime', 'other_runtime',
                                  'other_migrator', 'owner', 'administrator'])
def test_stage5_database_and_login_substitutions_rejected(environment, case):
    i = c.IDENTITIES[environment]
    other = next(j for j in c.IDENTITIES.values() if j != i)
    url = URL.create('postgresql+psycopg', username=i.migrator, password=SECRET,
                     host=i.host, port=i.port, database=i.database)
    changes = {
        'database': {'database': other.database}, 'admin_database': {'database': 'postgres'},
        'runtime': {'username': i.runtime}, 'other_runtime': {'username': other.runtime},
        'other_migrator': {'username': other.migrator}, 'owner': {'username': i.owner},
        'administrator': {'username': 'postgres'},
    }
    with pytest.raises(c.MigrationError, match=c.Failure.INVALID_CONFIGURATION):
        c.MigrationConfig(i, url.set(**changes[case]))


@pytest.mark.parametrize('environment', c.IDENTITIES)
def test_stage5_selected_vault_to_runner_isolation(runner, stage5_vault, monkeypatch,
                                                 environment, capsys, caplog):
    i = c.IDENTITIES[environment]
    for j in c.IDENTITIES.values():
        stage5_vault.entries[j.credential_service] = stage5_vault.credential(
            j.credential_service, j.migrator)
    monkeypatch.setattr(c.os, 'environ', {'OAF_ENV': environment})
    monkeypatch.setattr(runner.m, 'load_migration_config', c.load_migration_config)
    request = replace(runner.request, environment=environment)
    result = runner.m.run(request, authority=runner.authority)
    assert result['outcome'] == 'applied_and_verified'  # Synthetic runner only.
    stage5_vault.read.assert_called_once_with(i.credential_service)
    runner.m.create_engine.assert_called_once()
    url = runner.m.create_engine.call_args.args[0]
    assert (url.database, url.username, url.password) == (i.database, i.migrator, SECRET)
    assert url.host == '127.0.0.1' and url.port == 5432 and not url.query
    role_commands = [q for q in runner.connection.calls if q.startswith('SET LOCAL ROLE')]
    assert role_commands == [f'SET LOCAL ROLE "{i.owner}"'] * 2
    assert not any('public' in q.lower() for q in runner.connection.calls)
    assert SECRET not in repr(result) + repr(runner.sink.events) + repr(runner.sink.final_events)
    assert capsys.readouterr() == ('', '') and SECRET not in caplog.text
