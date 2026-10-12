"""Stage 3 test-only plugin, explicitly loaded BEFORE collection with -p.

Supported PowerShell invocation (from the website root):
  $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; $env:PYTHONPATH="$PWD;$PWD/tests"
  $env:PYTEST_ADDOPTS=''; $env:PYTEST_PLUGINS=''
  .venv/Scripts/python.exe -B -m pytest -p migration_offline -q <APPROVED_TESTS>
APPROVED_TESTS below is the exact bounded file inventory; --collect-only is safe.

Guards cover the declared Python APIs, exposed native Psycopg aliases, native
wrapper imports, ctypes loading/symbol lookup and private file opens. All
connections/credentials in these tests must be synthetic. Operational records
are confined to test temporary directories. This is NOT OS isolation: malicious native code, cached
native function pointers or arbitrary alternate FFI are outside this trusted
test scope. Never extend the scope to those interfaces without separate review.
"""

import os
import asyncio
import ctypes
import importlib.abc
from pathlib import Path
import socket
import sqlite3
import sqlite3.dbapi2
import _sqlite3
import ssl
import subprocess
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import psycopg
import pytest
import sqlalchemy
import sqlalchemy.engine.create
from sqlalchemy.engine import Engine

# pytest's trusted Windows console adapter resolves kernel32 symbols on import.
# Load it before denying new FFI access; it has no credential/database interface.
if sys.platform == "win32":
    import colorama
    # Flask's pinned Click console adapter also resolves kernel32 console
    # symbols on import. Preload this trusted UI dependency before the same
    # FFI denial; it has no credential/database interface.
    import click


ROOT = Path(__file__).resolve().parents[1]
SECRET = "STAGE3-SYNTHETIC-NOT-A-DATABASE-PASSWORD:@/é"
ATTEMPTS = []
EARLY_REGISTERED = False
PRODUCTION_IMPORTS = []
APPROVED_TESTS = frozenset({
    "tests/test_database_config.py", "tests/test_migration_config.py",
    "tests/test_migration_artifacts.py", "tests/test_migration_authorization.py",
    "tests/test_migration_catalog.py", "tests/test_migration_runner.py",
    "tests/test_migration_provenance.py",
    "tests/test_migration_operational.py",
    "tests/test_state_requests.py", "tests/test_state_request_migration.py",
    "tests/test_notifications.py", "tests/test_notification_migration.py",
})
_guard = pytest.MonkeyPatch()
_REAL_AUDIT = str(Path(os.environ.get('LOCALAPPDATA', 'C:/unavailable')) /
                  'OAF Website' / 'BootstrapAudit').replace('\\', '/').lower()


class OfflineAccess(BaseException):
    """Cannot be swallowed by production's ordinary exception classification."""


def denied(*args, **kwargs):
    ATTEMPTS.append("external access denied")
    raise OfflineAccess("Stage 3 offline isolation denied external access")


def _private(path):
    if not isinstance(path, (str, bytes, os.PathLike)):
        return False
    value = "/" + os.fsdecode(path).replace("\\", "/").lower()
    return ("/config/local/" in value or "/secrets/" in value
            or _REAL_AUDIT in value
            or "/.aws/" in value or "/.ssh/" in value
            or Path(value).name.startswith(".env")
            or Path(value).name in {"keyringrc.cfg", "credentials", "pgpass.conf", ".pgpass"})


def _audit_guard(event, args):
    if event in {"socket.connect", "socket.bind", "socket.getaddrinfo",
                 "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo",
                 "socket.sendto", "socket.sendmsg", "subprocess.Popen", "os.system",
                 "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty",
                 "os.startfile", "os.startfile/2", "sqlite3.connect",
                 "ctypes.dlopen", "ctypes.dlsym", "ctypes.dlsym/handle"}:
        denied()
    if event == "open" and _private(args[0]):
        denied()
    if event in {'os.listdir', 'os.scandir'} and args and _private(args[0]):
        denied()


if any(name == "oaf_website" or name.startswith("oaf_website.") for name in sys.modules):
    raise pytest.UsageError("Offline plugin loaded after production imports")


class _ImportGuard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "oaf_website" or fullname.startswith("oaf_website."):
            require_early_registration()
            PRODUCTION_IMPORTS.append(fullname)
        # Alternate libpq/credential wrappers are unsupported; deny BEFORE load.
        if fullname.startswith(("psycopg.pq.pq_ctypes", "psycopg.pq._pq_ctypes",
                                "psycopg_c", "win32ctypes.core", "cffi")):
            denied()
        return None


class _DeniedNativeConnection:
    def __new__(cls, *args, **kwargs):
        denied()
    connect = connect_start = connect_poll = reset = reset_start = reset_poll = ping = staticmethod(denied)


# Native types are immutable in the installed binary distribution. Replace
# every exposed alias instead of pretending setattr on the C type succeeded.
for native_name in ("PGconn", "PGcancel", "PGcancelConn"):
    native = getattr(psycopg.pq, native_name)
    for module in tuple(sys.modules.values()):
        if module is not None and getattr(module, "__name__", "").startswith("psycopg"):
            if vars(module).get(native_name) is native:
                _guard.setattr(module, native_name, _DeniedNativeConnection)
del native

GUARDED_APIS = [
    (psycopg, "connect"), (psycopg.Connection, "connect"),
    (psycopg.AsyncConnection, "connect"), (psycopg.pq, "import_from_libpq"),
    (psycopg.generators, "connect"), (psycopg.generators, "_connect"),
    (sqlalchemy, "create_engine"), (sqlalchemy.engine.create, "create_engine"),
    (Engine, "connect"), (Engine, "raw_connection"),
]
# The binary generator can call libpq directly, bypassing pq.PGconn's alias.
from psycopg._cmodule import _psycopg
if _psycopg is not None:
    GUARDED_APIS.append((_psycopg, "connect"))
for obj, names in (
    (socket, ("create_connection", "create_server", "getaddrinfo", "getnameinfo",
              "gethostbyname", "gethostbyname_ex", "gethostbyaddr")),
    (socket.socket, ("connect", "connect_ex", "bind", "listen", "accept", "send",
                     "_accept", "sendall", "sendto", "sendmsg", "sendfile", "recv",
                     "recv_into", "recvfrom", "recvfrom_into", "recvmsg", "recvmsg_into")),
    (ssl.SSLSocket, ("connect", "connect_ex", "send", "sendall", "sendto", "write",
                    "read", "recv", "recv_into", "recvfrom", "recvfrom_into")),
    (asyncio.BaseEventLoop, ("create_connection", "create_server", "create_datagram_endpoint",
                            "connect_accepted_socket", "subprocess_exec", "subprocess_shell")),
    (asyncio.SelectorEventLoop, ("sock_connect", "sock_sendall", "sock_sendto")),
    (subprocess, ("Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput")),
    (os, tuple(n for n in dir(os) if n.startswith(("spawn", "exec"))) +
         ("system", "popen", "startfile", "posix_spawn", "posix_spawnp", "fork", "forkpty")),
    (ctypes, ("CDLL", "PyDLL", "WinDLL", "OleDLL")),
    (ctypes.LibraryLoader, ("LoadLibrary", "__getattr__")),
    (sqlite3, ("connect", "Connection")),
    (sqlite3.dbapi2, ("connect", "Connection")),
    (_sqlite3, ("connect", "Connection")),
):
    GUARDED_APIS.extend((obj, name) for name in names if hasattr(obj, name))
if sys.platform == "win32":
    import _winapi
    GUARDED_APIS.append((_winapi, "CreateProcess"))
    # Proactor uses different asynchronous socket implementations on Windows.
    from asyncio.proactor_events import BaseProactorEventLoop
    GUARDED_APIS.extend((BaseProactorEventLoop, name) for name in
                        ("sock_connect", "sock_sendall", "sock_sendto")
                        if hasattr(BaseProactorEventLoop, name))
for obj, name in GUARDED_APIS:
    _guard.setattr(obj, name, denied)

CREDENTIAL_MODULES = ("keyring", "keyring.backends", "keyring.backends.Windows",
    "win32cred", "win32crypt", "win32vault", "win32ctypes.pywin32.win32cred")
CREDENTIAL_METHODS = ("get_keyring", "get_password", "get_credential", "set_password",
    "delete_password", "WinVaultKeyring", "CredRead", "CredReadA", "CredReadW",
    "CredEnumerate", "CredEnumerateA", "CredEnumerateW", "CredWrite", "CredDelete",
    "CredReadDomainCredentials", "CredReadDomainCredentialsW", "CryptUnprotectData",
    "VaultOpenVault", "VaultEnumerateVaults", "VaultEnumerateItems", "VaultGetItem")
for name in CREDENTIAL_MODULES:
    module = ModuleType(name)
    module.__path__ = []
    for method in CREDENTIAL_METHODS:
        setattr(module, method, denied)
    _guard.setitem(sys.modules, name, module)
sys.dont_write_bytecode = True
sys.addaudithook(_audit_guard)
sys.meta_path.insert(0, _ImportGuard())


def require_early_registration():
    if not EARLY_REGISTERED:
        raise pytest.UsageError("Use the supported -p migration_offline invocation before collection")


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(early_config, parser, args):
    global EARLY_REGISTERED
    if (os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") != "1"
            or os.environ.get("PYTEST_PLUGINS") or os.environ.get("PYTEST_ADDOPTS")
            or early_config.pluginmanager.get_plugin("migration_offline") is not sys.modules[__name__]
            or Path(sys.prefix).resolve() != (ROOT / ".venv").resolve()):
        raise pytest.UsageError("Offline startup requires website .venv, explicit plugin and disabled autoload")
    selected = early_config.known_args_namespace.file_or_dir
    if not selected or any(Path(arg.split("::")[0]).resolve() not in
                           {ROOT / name for name in APPROVED_TESTS} for arg in selected):
        raise pytest.UsageError("Offline collection requires explicit approved test files")
    if (any(getattr(obj, name) is not denied for obj, name in GUARDED_APIS)
            or any(getattr(sys.modules[module], name) is not denied
                   for module in CREDENTIAL_MODULES for name in CREDENTIAL_METHODS)
            or any(getattr(psycopg.pq, name) is not _DeniedNativeConnection
                   for name in ("PGconn", "PGcancel", "PGcancelConn"))):
        raise pytest.UsageError("Offline guards incomplete before collection")
    EARLY_REGISTERED = True
    print("Stage 3 isolation: plugin and guards verified before conftest/collection")


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if ATTEMPTS:
        if session.exitstatus == 0:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
        print("UNEXPECTED OFFLINE ACCESS ATTEMPTS:", len(ATTEMPTS))
    else:
        print("Stage 3 isolation: zero unexpected external-access attempts")


@pytest.fixture(autouse=True)
def offline_guard(monkeypatch, isolate_external_access, tmp_path):
    # Run after existing conftest, then retain non-swallowable, counted denials.
    require_early_registration()
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    (tmp_path / 'OAF Website' / 'BootstrapAudit').mkdir(parents=True, exist_ok=True)
    for obj, name in GUARDED_APIS:
        monkeypatch.setattr(obj, name, denied)
    for name in ("keyring", "keyring.backends", "keyring.backends.Windows"):
        for method in CREDENTIAL_METHODS:
            # Existing conftest creates smaller synthetic modules per test.
            monkeypatch.setattr(sys.modules[name], method, denied, raising=False)
    # Also replace copied production aliases.
    for name in ("oaf_website.migrate",):
        module = sys.modules.get(name)
        if module is not None:
            monkeypatch.setattr(module, "create_engine", denied)
    yield
    assert not ATTEMPTS, "Unexpected access attempt must fail the whole run"


def artifacts():
    from oaf_website import migration_validation as v
    import json
    document = json.loads((ROOT / "migrations/manifest.json").read_bytes())
    return v.validate_artifacts(expected_start=v.BASE, target=v.BASELINE,
                                manifest_hash=v.digest((ROOT / "migrations/manifest.json").read_bytes()),
                                revision_hash=document["revisions"][0]["sha256"])


class DriverError(Exception):
    def __init__(self, code=None):
        self.sqlstate = code
        super().__init__(SECRET)


class Result:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        assert isinstance(self.value, list)
        return self.value

    def scalar_one(self):
        return self.value


class FakeTransaction:
    def __init__(self, connection):
        self.connection = connection
        self.is_active = True

    def commit(self):
        c = self.connection
        c.hit("commit")
        c.commits += 1
        self.is_active = False
        c.transaction = None

    def rollback(self):
        self.connection.rollback()


class FakeConnection:
    """Deterministic physical-session model; never subclasses a real connection."""
    def __init__(self):
        self.driver = SimpleNamespace(closed=False, broken=False, pgconn=object(), advisory_lock=False,
                                      info=SimpleNamespace(backend_pid=701))
        self.proxy = SimpleNamespace(is_valid=True, dbapi_connection=self.driver,
                                     driver_connection=self.driver)
        self.closed = self.invalidated = False
        self.transaction = None
        self.commits = self.rollbacks = self.begins = 0
        self.calls = []
        self.physical_calls = []
        self.reconnect_attempts = 0
        self.reconnect_on_access = False
        self.retain_lock_on_unlock = False
        self.hooks = {}
        self.lock = False
        self.target = False
        self.owner = False

    def hit(self, phase):
        self.calls.append(phase)
        hook = self.hooks.get(phase)
        if isinstance(hook, list):
            hook = hook.pop(0) if hook else None
        if isinstance(hook, BaseException):
            raise hook
        if callable(hook):
            return hook(self)

    @property
    def connection(self):
        self.hit("physical_proxy")
        if self.reconnect_on_access and (self.invalidated or not self.proxy.is_valid):
            self.reconnect_attempts += 1
            self.replace_physical_session()
            self.invalidated = False
        return self.proxy

    def replace_physical_session(self, same_pid=True):
        self.driver = SimpleNamespace(closed=False, broken=False, pgconn=object(), advisory_lock=False,
            info=SimpleNamespace(backend_pid=701 if same_pid else 702))
        self.proxy = SimpleNamespace(is_valid=True, dbapi_connection=self.driver,
                                     driver_connection=self.driver)
        self.lock = False

    @property
    def lock(self):
        return self.driver.advisory_lock

    @lock.setter
    def lock(self, value):
        self.driver.advisory_lock = value

    def begin(self):
        self.hit("begin")
        assert not self.transaction
        self.begins += 1
        self.transaction = FakeTransaction(self)
        return self.transaction

    def get_transaction(self):
        return self.transaction

    def in_transaction(self):
        return self.transaction is not None

    def in_nested_transaction(self):
        return False

    def rollback(self):
        self.hit("rollback")
        self.rollbacks += 1
        if self.transaction:
            self.transaction.is_active = False
        self.transaction = None
        self.owner = False

    def close(self):
        self.hit("close")
        self.closed = True

    def execute(self, sql, parameters=None):
        sql = str(sql)
        self.calls.append(sql)
        self.physical_calls.append((sql, self.proxy, self.driver, self.driver.pgconn))
        if sql.startswith("SET "):
            if "ROLE" in sql:
                self.owner = True
            return Result(None)
        if not self.transaction:
            self.begin()  # Model SQLAlchemy autobegin without opening anything.
        if "current_setting('search_path')" in sql:
            return Result("pg_catalog, oaf_website, pg_temp")
        if "pg_settings" in sql:
            return Result(5000 if "lock_timeout" in sql else 60000)
        if "SELECT pg_catalog.pg_backend_pid()" == sql:
            return Result(self.driver.info.backend_pid)
        if "pg_try_advisory_lock" in sql:
            self.hit("acquire")
            self.lock = True
            return Result(True)
        if "pg_advisory_unlock" in sql:
            override = self.hit("unlock")
            released = self.lock if override is None else override
            if not self.retain_lock_on_unlock:
                self.lock = False
            return Result(released)
        if "pg_locks" in sql:
            self.hit("absence" if "AND granted" in sql and "pid=pg_catalog.pg_backend_pid()" in sql else "lock_check")
            return Result(self.lock)
        raise AssertionError("Unknown fake session query: " + sql)


class FakeSink:
    def __init__(self, connection):
        self.connection = connection
        self.events = []
        self.final_events = []
        self.write_attempts = []
        self.final_attempts = []

    def write(self, event):
        self.write_attempts.append(event)
        self.connection.hit("audit_" + event.phase)
        self.events.append(event)

    def finalize(self, event):
        self.final_attempts.append(event)
        self.connection.hit("finalize")
        self.final_events.append(event)


@pytest.fixture
def runner(monkeypatch):
    from oaf_website import migrate as m, migration_config as c
    real_execute_revision = m._execute_revision
    a = artifacts()
    connection = FakeConnection()
    sink = FakeSink(connection)
    engine = SimpleNamespace(connect=Mock(return_value=connection),
                             dispose=lambda: connection.hit("dispose"))
    authority = SimpleNamespace(authorize=Mock(return_value=sink))
    request = m.Request("upgrade", "testing", a.expected_start, a.target,
                        a.manifest_hash, a.revision_hash)
    monkeypatch.setattr(c.os, "environ", {"OAF_ENV": "testing"})
    # Private seam replacement is limited to this fixture, not an adapter registry.
    monkeypatch.setattr(m, "_require_operational_adapter", Mock())
    monkeypatch.setattr(m, "load_migration_config", Mock(return_value=SimpleNamespace(url="synthetic-only")))
    monkeypatch.setattr(m, "create_engine", Mock(return_value=engine))
    monkeypatch.setattr(m, "verify_identity", lambda *args, **kw: connection.hit("identity"))
    monkeypatch.setattr(m, "verify_authority", lambda *args: connection.hit("authority"))

    def catalog(*args):
        override = connection.hit("catalog")
        return override if override is not None else a.target if connection.target else a.expected_start

    def revision(*args):
        args[4].mutation_started = True
        args[4].transaction = 'mutation_possible'
        connection.hit("revision")
        assert args[3] is connection.transaction
        connection.target = True

    monkeypatch.setattr(m, "catalog_state", catalog)
    monkeypatch.setattr(m, "_execute_revision", revision)
    return SimpleNamespace(m=m, c=c, a=a, connection=connection, sink=sink,
                           real_execute_revision=real_execute_revision,
                           engine=engine, authority=authority, request=request,
                           run=lambda: m.run(request, authority=authority))
