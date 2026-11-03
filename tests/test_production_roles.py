"""Production provisioning: synthetic vault, server, approval and RNG only."""
import migration_offline as isolation
isolation.require_early_registration()

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import psycopg.sql
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("production_roles_under_test",
                                             ROOT / "ops/local_postgres_bootstrap/08_production_roles.py")
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)
DOCUMENT = dict(database_host="dpg-synthetic.oregon-postgres.render.com", database_owner=p.ADMINISTRATOR)
APP_PASSWORD, MIGRATOR_PASSWORD = "a1" * 32, "b2" * 32
ADMIN_PASSWORD = "synthetic-private-administrator"
VERIFIER = b"SCRAM-SHA-256$4096:c3ludGhldGlj$c3ludGhldGlj:c3ludGhldGlj"
PRIVATE_ERROR = "synthetic-private-provider-error"


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return self.rows


class Vault:
    def __init__(self):
        self.records = {}
        self.writes = []
        self.reads = []
        self.fail_write = None

    def _read_credential(self, target):
        self.reads.append(target)
        return self.records.get(target)

    def _set_password(self, target, account, password):
        assert target not in self.records
        self.writes.append(target)
        self.records[target] = dict(TargetName=target, UserName=account, Type=1,
                                    Persist=2, CredentialBlob=password.encode("utf-16-le"))
        if self.fail_write == target:
            raise RuntimeError(PRIVATE_ERROR)


class Database:
    def __init__(self):
        self.commands = []
        self.created = []
        self.closed = False
        self.commits = 0
        self.fail = None
        self.collision = False
        self.public_safe = True
        self.authority_safe = True
        self.attributes = [(role, True, False, False, False, False, False, False, -1, True, True)
                           for role in p.SERVICES]
        self.edges = [(p.APP, p.ADMINISTRATOR, "postgres", True, False, False),
                      (p.MIGRATOR, p.ADMINISTRATOR, "postgres", True, False, False),
                      (p.MIGRATOR, p.ADMINISTRATOR, p.ADMINISTRATOR, False, False, True)]
        self.identity_row = (p.ADMINISTRATOR, p.ADMINISTRATOR, p.DATABASE, "170011", 5432,
                             p.ADMINISTRATOR, True, False)
        self.admin_safe = self.tls_safe = True
        self.pgconn = SimpleNamespace(host=DOCUMENT["database_host"].encode(), port=b"5432",
            db=p.DATABASE.encode(), user=p.ADMINISTRATOR.encode(), used_password=True,
            encrypt_password=Mock(return_value=VERIFIER))

    def execute(self, command, parameters=None):
        text = command.as_string() if isinstance(command, psycopg.sql.Composable) else command
        self.commands.append(text)
        if self.fail and self.fail in text:
            raise RuntimeError(PRIVATE_ERROR)
        if text.startswith("CREATE ROLE"):
            self.created.append(text)
        if text == "COMMIT":
            self.commits += 1
        if "datallowconn" in text:
            rows = [self.identity_row]
        elif "rolcanlogin AND rolcreaterole" in text:
            rows = [(self.admin_safe,)]
        elif "pg_stat_ssl" in text:
            rows = [(self.tls_safe,)]
        elif "SELECT NOT EXISTS (SELECT FROM pg_catalog.pg_roles" in text:
            rows = [(not self.collision,)]
        elif "aclexplode" in text:
            rows = [(self.public_safe,)]
        elif "set_config('createrole_self_grant'" in text:
            rows = [(parameters[0],)]
        elif "rolconnlimit" in text:
            rows = self.attributes
        elif "pg_auth_members" in text:
            rows = self.edges
        elif "WHERE oid=10 AND rolsuper" in text:
            rows = [("postgres",)]
        elif "pg_shdepend" in text:
            rows = [(self.authority_safe,)]
        else:
            rows = [(True,)]
        return Result(rows)

    def close(self):
        self.closed = True


@pytest.fixture
def scenario(monkeypatch, tmp_path):
    # Production code can only see these explicit fakes. Token generation never
    # reaches the OS RNG, even on failure paths. No real owner records are read.
    # Bind source hashing to this checkout, including non-Windows CI paths.
    monkeypatch.setattr(p, "REPOSITORY", ROOT)
    monkeypatch.setattr(p, "AUDIT_ROOT", tmp_path)
    monkeypatch.setattr(p, "environment", Mock())
    monkeypatch.setattr(p, "metadata", Mock(return_value=dict(DOCUMENT)))
    monkeypatch.setattr(p.getpass, "getpass", Mock(return_value=ADMIN_PASSWORD))
    generator = Mock(side_effect=[APP_PASSWORD, MIGRATOR_PASSWORD])
    monkeypatch.setattr(p.secrets, "token_hex", generator)
    vault, database = Vault(), Database()
    connection = Mock(return_value=database)
    clients = SimpleNamespace(connect=connection, sql=psycopg.sql)
    monkeypatch.setattr(p.legacy, "installed_clients", Mock(return_value=(clients, vault)))
    answers = iter(["11111111-1111-4111-8111-111111111111",
                    f"AUTHORIZE ROLES {DOCUMENT['database_host']} {p.DATABASE} {p.ADMINISTRATOR}"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    return SimpleNamespace(vault=vault, db=database, connect=connection, generator=generator, root=tmp_path)


def evidence(scenario):
    return [json.loads(path.read_text()) for path in sorted(scenario.root.glob("Step08-*/*.json"))]


def assert_confidential(scenario, capsys):
    captured = capsys.readouterr()
    text = captured.out + captured.err
    text += "".join(path.read_text() for path in scenario.root.rglob("*.json"))
    assert all(value not in text for value in
               (APP_PASSWORD, MIGRATOR_PASSWORD, ADMIN_PASSWORD, VERIFIER.decode(), PRIVATE_ERROR))
    return text


def test_success_has_only_two_restricted_roles_and_separate_vault_targets(scenario, capsys):
    assert p.main() == 0
    assert scenario.generator.call_args_list == [((32,),), ((32,),)]
    assert scenario.vault.writes == list(p.SERVICES.values())
    assert len(scenario.db.created) == 2
    assert scenario.db.pgconn.encrypt_password.call_args_list == [
        ((password.encode("ascii"), role.encode("ascii"), b"scram-sha-256"),)
        for role, password in ((p.APP, APP_PASSWORD), (p.MIGRATOR, MIGRATOR_PASSWORD))]
    for command in scenario.db.created:
        for clause in ("LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE", "NOREPLICATION NOBYPASSRLS NOINHERIT",
                       "CONNECTION LIMIT -1", VERIFIER.decode()):
            assert clause in command
    assert all(APP_PASSWORD not in command and MIGRATOR_PASSWORD not in command
               and ADMIN_PASSWORD not in command for command in scenario.db.commands)
    assert not any(c.startswith(("CREATE SCHEMA", "ALTER SYSTEM")) or "ON DATABASE" in c
                   for c in scenario.db.commands)
    assert scenario.db.commits == 1 and scenario.db.closed
    assert evidence(scenario)[-1]["commit"] == "acknowledged"
    assert evidence(scenario)[-1]["verification"] == "PASS"
    assert evidence(scenario)[-1]["authorization"] == "owner_acknowledged"
    assert_confidential(scenario, capsys)


@pytest.mark.parametrize("answer", ["", "not-a-uuid", "00000000-0000-0000-0000-000000000000"])
def test_missing_or_unconfirmed_separate_authority_denies_before_clients(scenario, monkeypatch, answer, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt: answer)
    assert p.main() == 1
    p.legacy.installed_clients.assert_not_called()
    scenario.connect.assert_not_called()
    scenario.generator.assert_not_called()
    assert not scenario.vault.writes
    assert_confidential(scenario, capsys)


def test_provision_cannot_bypass_owner_authorization(scenario):
    audit = p.Audit()
    with pytest.raises(p.Stop, match="owner_approval_required"):
        p.provision(None, scenario.vault, audit, DOCUMENT)
    assert not scenario.vault.reads


@pytest.mark.parametrize("failure", ["identity", "endpoint", "database", "administrator", "tls", "password_auth",
                                      "collision", "public"])
def test_preflight_denials_never_generate_or_write_passwords(scenario, failure, capsys):
    d = scenario.db
    if failure == "identity":
        d.identity_row = ("wrong",) + d.identity_row[1:]
    elif failure == "endpoint":
        d.pgconn.host = b"another.example"
    elif failure == "database":
        d.pgconn.db = b"postgres"
    elif failure == "administrator":
        d.admin_safe = False
    elif failure == "tls":
        d.tls_safe = False
    elif failure == "password_auth":
        d.pgconn.used_password = False
    elif failure == "collision":
        d.collision = True
    elif failure == "public":
        d.public_safe = False
    assert p.main() == 1
    scenario.generator.assert_not_called()
    assert not scenario.vault.writes and not d.created and d.commits == 0
    assert not (scenario.root / p.CLAIM_NAME).exists()
    assert_confidential(scenario, capsys)


def test_provider_internals_are_not_inspected_or_reconfigured(scenario, monkeypatch, capsys):
    # Simulate a managed provider that refuses internal inspection/configuration.
    # Restricted-role parameter privilege checks remain required and available.
    original = scenario.db.execute
    attempts = []

    def execute(command, parameters=None):
        text = command.as_string() if isinstance(command, psycopg.sql.Composable) else command
        if (text == "SELECT current_setting(%s) = ''" or any(marker in text for marker in (
                "preload_libraries", "pg_extension", "SELECT name, setting",
                "has_parameter_privilege(current_user", "set_config(%s,%s,false)"))):
            attempts.append(text)
            raise PermissionError(PRIVATE_ERROR)
        return original(command, parameters)

    monkeypatch.setattr(scenario.db, "execute", execute)
    assert p.main() == 0
    assert attempts == []
    assert len(scenario.db.created) == 2 and scenario.db.commits == 1
    assert evidence(scenario)[-1]["verification"] == "PASS"
    assert_confidential(scenario, capsys)


@pytest.mark.parametrize("operation", ["encrypt_password", "CREATE ROLE"])
@pytest.mark.parametrize("failure_type", [RuntimeError, KeyboardInterrupt])
def test_secret_bearing_failures_and_interruptions_are_sanitized(
        scenario, monkeypatch, capsys, operation, failure_type):
    private_error = " ".join((PRIVATE_ERROR, ADMIN_PASSWORD, APP_PASSWORD,
                              MIGRATOR_PASSWORD, VERIFIER.decode()))
    if operation == "encrypt_password":
        scenario.db.pgconn.encrypt_password.side_effect = failure_type(private_error)
    else:
        original = scenario.db.execute

        def execute(command, parameters=None):
            if isinstance(command, psycopg.sql.Composable):
                raise failure_type(private_error)
            return original(command, parameters)

        monkeypatch.setattr(scenario.db, "execute", execute)
    assert p.main() == 1
    stopped = evidence(scenario)[-1]
    assert stopped["failure_code"] == "operation_failed_or_interrupted"
    assert stopped["outcome"] == "rejected_before_commit"
    assert len(scenario.vault.records) == 2
    assert (scenario.root / p.CLAIM_NAME).exists()
    assert not scenario.db.created and scenario.db.commits == 0 and scenario.db.closed
    assert_confidential(scenario, capsys)


@pytest.mark.parametrize("target", [p.SERVICES[p.APP], p.SERVICES[p.MIGRATOR],
                                     p.APP + "@" + p.SERVICES[p.APP],
                                     p.MIGRATOR + "@" + p.SERVICES[p.MIGRATOR]])
def test_existing_vault_target_rejects_without_overwrite(scenario, target):
    scenario.vault.records[target] = {"UserName": "another-account"}
    assert p.main() == 1
    scenario.generator.assert_not_called()
    assert scenario.vault.records[target] == {"UserName": "another-account"}
    scenario.connect.assert_not_called()


@pytest.mark.parametrize("role", [p.APP, p.MIGRATOR])
def test_uncertain_vault_write_preserves_records_claim_and_no_sql(scenario, role, capsys):
    scenario.vault.fail_write = p.SERVICES[role]
    assert p.main() == 1
    assert p.SERVICES[role] in scenario.vault.records
    assert not scenario.db.created
    assert (scenario.root / p.CLAIM_NAME).exists()
    assert evidence(scenario)[-1]["credentials"][role] == "outcome_uncertain"
    assert_confidential(scenario, capsys)


@pytest.mark.parametrize("field,value", [("UserName", "wrong"), ("TargetName", "wrong"), ("Type", 2),
                                          ("Persist", 3), ("CredentialBlob", b"a" * 64),
                                          ("CredentialBlob", ("A1" * 32).encode("utf-16-le"))])
def test_strict_vault_readback_rejects_incompatible_metadata_or_encoding(scenario, field, value):
    scenario.vault._set_password(p.SERVICES[p.APP], p.APP, APP_PASSWORD)
    scenario.vault.records[p.SERVICES[p.APP]][field] = value
    with pytest.raises((p.Stop, UnicodeError)):
        p.stored_password(scenario.vault, p.APP, APP_PASSWORD)


@pytest.mark.parametrize("index", range(1, 11))
def test_every_restricted_role_attribute_is_enforced(scenario, index):
    row = list(scenario.db.attributes[0])
    row[index] = 5 if index == 8 else not row[index]
    scenario.db.attributes[0] = tuple(row)
    with pytest.raises(p.Stop, match="restricted_role_attributes_mismatch"):
        p.restricted_roles(scenario.db)


@pytest.mark.parametrize("drift", ["outbound", "extra_inbound", "inherit", "runtime_set", "migrator_set", "ownership_or_acl"])
def test_membership_and_effective_authority_denials(scenario, drift):
    if drift == "outbound":
        scenario.db.edges.append(("elevated", p.APP, "postgres", True, True, True))
    elif drift == "extra_inbound":
        scenario.db.edges.append((p.APP, "unapproved", "postgres", False, False, True))
    elif drift == "inherit":
        scenario.db.edges[0] = (p.APP, p.ADMINISTRATOR, "postgres", True, True, False)
    elif drift == "runtime_set":
        scenario.db.edges[0] = (p.APP, p.ADMINISTRATOR, "postgres", True, False, True)
    elif drift == "migrator_set":
        scenario.db.edges[2] = (p.MIGRATOR, p.ADMINISTRATOR, p.ADMINISTRATOR, False, False, False)
    else:
        scenario.db.authority_safe = False
    with pytest.raises(p.Stop):
        p.restricted_roles(scenario.db)


@pytest.mark.parametrize("failure,expected", [("CREATE ROLE", "rejected_before_commit"),
                                              ("COMMIT", "uncertain"),
                                              ("BEGIN READ ONLY", "acknowledged_commit_requires_review")])
def test_rejection_uncertain_commit_and_postcommit_failure_are_distinct(scenario, failure, expected, capsys):
    scenario.db.fail = failure
    assert p.main() == 1
    assert evidence(scenario)[-1]["outcome"] == expected
    assert len(scenario.vault.records) == 2
    assert (scenario.root / p.CLAIM_NAME).exists()
    assert scenario.db.closed
    assert scenario.db.commands.count("COMMIT") <= 1
    assert not any("DROP" in command or "ALTER ROLE" in command for command in scenario.db.commands)
    assert_confidential(scenario, capsys)


def test_durable_audit_failure_before_claim_prevents_generation(scenario, monkeypatch):
    original = p.save_json
    def fail(path, record):
        if record.get("phase") == "prior_state_verified":
            raise OSError(PRIVATE_ERROR)
        original(path, record)
    monkeypatch.setattr(p, "save_json", fail)
    assert p.main() == 1
    scenario.generator.assert_not_called()
    assert not scenario.vault.writes and not scenario.db.created


def test_postcommit_audit_failure_does_not_reclassify_acknowledged_commit(scenario, monkeypatch, capsys):
    original = p.save_json
    def fail(path, record):
        if record.get("phase") == "commit_acknowledged":
            raise OSError(PRIVATE_ERROR)
        original(path, record)
    monkeypatch.setattr(p, "save_json", fail)
    assert p.main() == 1
    assert scenario.db.commits == 1
    assert evidence(scenario)[-1]["commit"] == "acknowledged"
    assert evidence(scenario)[-1]["outcome"] == "acknowledged_commit_requires_review"
    assert_confidential(scenario, capsys)


def test_existing_claim_permanently_refuses_automatic_retry(scenario):
    (scenario.root / p.CLAIM_NAME).write_text("existing partial claim")
    assert p.main() == 1
    scenario.connect.assert_not_called()
    scenario.generator.assert_not_called()
    assert (scenario.root / p.CLAIM_NAME).read_text() == "existing partial claim"


def test_same_generated_passwords_rejected_before_vault_write(scenario):
    scenario.generator.side_effect = [APP_PASSWORD, APP_PASSWORD]
    assert p.main() == 1
    assert not scenario.vault.writes and not scenario.db.created


def test_source_or_metadata_change_prevents_commit(scenario, monkeypatch):
    original = p.source_hashes
    calls = 0
    def changed():
        nonlocal calls
        calls += 1
        return original() if calls == 1 else {"changed": "artifact"}
    monkeypatch.setattr(p, "source_hashes", changed)
    assert p.main() == 1
    assert scenario.db.commits == 0
    assert len(scenario.vault.records) == 2


def test_second_absence_check_rejects_a_racing_role_before_ddl(scenario, monkeypatch):
    original = scenario.vault._set_password
    def write(*args):
        original(*args)
        scenario.db.collision = True
    monkeypatch.setattr(scenario.vault, "_set_password", write)
    assert p.main() == 1
    assert len(scenario.vault.records) == 2
    assert not scenario.db.created and not scenario.db.commits


def test_invalid_local_scram_result_never_enters_sql(scenario):
    scenario.db.pgconn.encrypt_password.return_value = b"invalid-private-verifier"
    assert p.main() == 1
    assert not scenario.db.created
    assert len(scenario.vault.records) == 2


def test_commit_reply_loss_remains_uncertain_even_if_server_committed(scenario, monkeypatch):
    original = scenario.db.execute
    def execute(command, parameters=None):
        result = original(command, parameters)
        if command == "COMMIT":
            raise ConnectionError(PRIVATE_ERROR)
        return result
    monkeypatch.setattr(scenario.db, "execute", execute)
    assert p.main() == 1
    assert scenario.db.commits == 1
    assert evidence(scenario)[-1]["commit"] == "outcome_uncertain"
    assert evidence(scenario)[-1]["outcome"] == "uncertain"


def test_credential_echo_fallback_is_denied_before_generation(scenario, monkeypatch, capsys):
    def prompt(*args):
        p.warnings.warn("synthetic warning", p.getpass.GetPassWarning)
        return ADMIN_PASSWORD
    monkeypatch.setattr(p.getpass, "getpass", prompt)
    assert p.main() == 1
    scenario.connect.assert_not_called()
    scenario.generator.assert_not_called()
    assert_confidential(scenario, capsys)


def test_failed_claim_persistence_never_generates_credentials(scenario, monkeypatch):
    original = p.save_json
    def save(path, record):
        original(path, record)
        if path.name == p.CLAIM_NAME:
            raise OSError(PRIVATE_ERROR)
    monkeypatch.setattr(p, "save_json", save)
    assert p.main() == 1
    scenario.generator.assert_not_called()
    assert (scenario.root / p.CLAIM_NAME).exists()
    assert not scenario.vault.writes


def test_unavailable_audit_is_visible_without_secret_output(scenario, monkeypatch, capsys):
    monkeypatch.setattr(p, "save_json", Mock(side_effect=OSError(PRIVATE_ERROR)))
    assert p.main() == 1
    scenario.generator.assert_not_called()
    scenario.connect.assert_not_called()
    captured = capsys.readouterr()
    assert "outcome_evidence_saved=False" in captured.out
    assert PRIVATE_ERROR not in captured.out + captured.err


def test_durable_json_never_replaces_an_existing_record(scenario):
    path = scenario.root / "existing.json"
    p.save_json(path, {"first": True})
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        p.save_json(path, {"second": True})
    assert path.read_bytes() == before


def test_connection_parameters_preserve_tls_dns_and_scram(scenario):
    assert p.main() == 0
    args = scenario.connect.call_args.kwargs
    assert args["host"] == DOCUMENT["database_host"]
    assert args["dbname"] == p.DATABASE and args["user"] == p.ADMINISTRATOR
    assert args["sslmode"] == "require" and args["ssl_min_protocol_version"] == "TLSv1.2"
    assert args["sslsni"] == "1" and args["require_auth"] == "scram-sha-256"
    assert args["passfile"] == "NUL" and args["prepare_threshold"] is None
    assert "hostaddr" not in args


REAL_ENVIRONMENT = p.environment


@pytest.mark.parametrize("override", [{"PGPASSWORD": "private"}, {"OAF_ENV": "testing"},
                                     {"PYTHON_KEYRING_BACKEND": "other"}, {"OAF_DATABASE_URL": "private"},
                                     {"SSL_CERT_FILE": "private"}, {"SSL_CERT_DIR": "private"},
                                     {"SSLKEYLOGFILE": "private"},
                                     {"KEYRING_PROPERTY_X": "private"}])
def test_environment_overrides_are_denied(monkeypatch, override):
    console = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(p, "sys", SimpleNamespace(platform="win32", version_info=(3, 11),
        executable=str(ROOT / ".venv/Scripts/python.exe"), flags=SimpleNamespace(isolated=True),
        dont_write_bytecode=True, argv=["helper", "--provision-production"],
        stdin=console, __stdin__=console, stdout=console, __stdout__=console, stderr=console, __stderr__=console))
    monkeypatch.setattr(p, "os", SimpleNamespace(environ=override))
    with pytest.raises(p.Stop):
        REAL_ENVIRONMENT()


@pytest.mark.parametrize("change", ["missing_operation", "not_isolated", "bytecode", "redirected_input", "redirected_output"])
def test_explicit_isolated_console_is_required(monkeypatch, change):
    console = SimpleNamespace(isatty=lambda: True)
    settings = dict(platform="win32", version_info=(3, 11),
        executable=str(ROOT / ".venv/Scripts/python.exe"), flags=SimpleNamespace(isolated=True),
        dont_write_bytecode=True, argv=["helper", "--provision-production"],
        stdin=console, __stdin__=console, stdout=console, __stdout__=console, stderr=console, __stderr__=console)
    if change == "missing_operation":
        settings["argv"] = ["helper"]
    elif change == "not_isolated":
        settings["flags"] = SimpleNamespace(isolated=False)
    elif change == "bytecode":
        settings["dont_write_bytecode"] = False
    else:
        settings["stdin" if change == "redirected_input" else "stdout"] = SimpleNamespace(isatty=lambda: False)
    monkeypatch.setattr(p, "sys", SimpleNamespace(**settings))
    monkeypatch.setattr(p, "os", SimpleNamespace(environ={}))
    with pytest.raises(p.Stop):
        REAL_ENVIRONMENT()


class TemporaryDatabase(Database):
    """Transactional ACL model: close/rollback discard pending catalog changes."""
    def __init__(self):
        super().__init__()
        self.catalog = {
            "database": sorted([
                (9001, 9000, 9000, 0, "CONNECT", False),
                (9001, 9000, 9000, 0, "TEMPORARY", False),
                *((9001, 9000, 9000, 9000, privilege, True)
                  for privilege in ("CONNECT", "CREATE", "TEMPORARY")),
                (9001, 9000, 9000, 9090, "CREATE", True),
                (9001, 9000, 9000, 9090, "TEMPORARY", False),
            ]),
            "public_schema": sorted([
                (2200, 6171, 6171, 0, "USAGE", False),
                (2200, 6171, 6171, 6171, "USAGE", True),
                (2200, 6171, 6171, 6171, "CREATE", True),
                (2200, 6171, 6171, 9090, "USAGE", False),
            ]),
        }
        self.pending = None
        self.after_revoke = lambda catalog: None

    def execute(self, command, parameters=None):
        result = super().execute(command, parameters)
        if command in {"BEGIN", "BEGIN READ ONLY"}:
            assert self.pending is None
            self.pending = deepcopy(self.catalog)
        elif "SELECT d.oid, d.datdba" in command:
            return Result(deepcopy(self.pending["database"]))
        elif "SELECT n.oid, n.nspowner" in command:
            return Result(deepcopy(self.pending["public_schema"]))
        elif command == p.REVOKE_TEMPORARY:
            assert self.pending is not None
            self.pending["database"] = [row for row in self.pending["database"]
                                        if not (row[3] == 0 and row[4] == "TEMPORARY")]
            self.after_revoke(self.pending)
        elif command == "COMMIT":
            assert self.pending is not None
            self.catalog = self.pending
            self.pending = None
            return SimpleNamespace(statusmessage="COMMIT")
        elif command == "ROLLBACK":
            self.pending = None
        return result

    def close(self):
        self.pending = None
        super().close()


@pytest.fixture
def correction(scenario, monkeypatch):
    scenario.db = TemporaryDatabase()
    scenario.before = deepcopy(scenario.db.catalog)
    scenario.connect.return_value = scenario.db
    monkeypatch.setattr(p.sys, "argv", ["helper", "--revoke-public-temporary"])
    answers = iter(["11111111-1111-4111-8111-111111111111",
                    f"AUTHORIZE REVOKE TEMPORARY {DOCUMENT['database_host']} {p.DATABASE} {p.ADMINISTRATOR}"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    return scenario


def test_public_temporary_correction_changes_only_authorized_acl_and_audits_before_commit(correction, capsys):
    assert p.main() == 0
    d = correction.db
    assert d.catalog == {
        "database": [row for row in correction.before["database"]
                     if not (row[3] == 0 and row[4] == "TEMPORARY")],
        "public_schema": correction.before["public_schema"],
    }
    assert d.commands.count("BEGIN") == d.commands.count("COMMIT") == 1
    assert d.commands.count(p.REVOKE_TEMPORARY) == 1
    assert d.commands.index("BEGIN") < d.commands.index(p.REVOKE_TEMPORARY) < d.commands.index("COMMIT")
    revoke_at = d.commands.index(p.REVOKE_TEMPORARY)
    commit_at = d.commands.index("COMMIT")
    assert any("SELECT d.oid, d.datdba" in sql for sql in d.commands[revoke_at + 1:commit_at])
    assert any("datallowconn" in sql for sql in d.commands[:revoke_at])
    assert any("datallowconn" in sql for sql in d.commands[revoke_at + 1:commit_at])
    assert not any(sql.startswith(("CREATE", "GRANT", "ALTER", "SET")) for sql in d.commands)
    assert [sql for sql in d.commands if sql.startswith("REVOKE")] == [
        "REVOKE TEMPORARY ON DATABASE oaf_website_prod FROM PUBLIC"]
    correction.generator.assert_not_called()
    assert not correction.vault.reads and not correction.vault.writes and not d.created
    records = evidence(correction)
    phases = [record["phase"] for record in records]
    assert phases.index("public_acl_verified") < phases.index("commit") < phases.index("commit_acknowledged")
    assert records[-1]["commit"] == "acknowledged" and records[-1]["verification"] == "PASS"
    assert records[-1]["operation"] == "revoke_public_temporary"
    assert records[-1]["roles"] == [] and records[-1]["credentials"] == {}
    assert records[-1]["public_acl_before"] == json.loads(json.dumps(correction.before))
    assert records[-1]["public_acl_after"] == json.loads(json.dumps(d.catalog))
    assert (correction.root / p.TEMPORARY_CLAIM_NAME).is_file()
    assert not (correction.root / p.CLAIM_NAME).exists()
    assert d.closed
    assert_confidential(correction, capsys)


@pytest.mark.parametrize("failure", ["host", "database", "user", "session_user", "current_user", "owner",
                                      "version", "port", "administrator", "tls", "password_auth"])
def test_correction_identity_denials_precede_revoke(correction, failure):
    d = correction.db
    if failure in {"host", "database", "user"}:
        setattr(d.pgconn, "db" if failure == "database" else failure, b"wrong")
    elif failure in {"session_user", "current_user", "owner", "version", "port"}:
        index = {"session_user": 0, "current_user": 1, "owner": 5, "version": 3, "port": 4}[failure]
        row = list(d.identity_row)
        row[index] = "wrong"
        d.identity_row = tuple(row)
    elif failure == "administrator":
        d.admin_safe = False
    elif failure == "tls":
        d.tls_safe = False
    else:
        d.pgconn.used_password = False
    assert p.main() == 1
    assert p.REVOKE_TEMPORARY not in d.commands and d.commits == 0
    assert d.catalog == correction.before and d.closed
    assert not (correction.root / p.TEMPORARY_CLAIM_NAME).exists()


@pytest.mark.parametrize("drift", ["connect", "create", "temporary", "schema_usage", "schema_create", "schema_absent"])
def test_correction_requires_accepted_public_starting_permissions(correction, drift):
    catalog = correction.db.catalog
    if drift in {"connect", "temporary"}:
        catalog["database"] = [row for row in catalog["database"]
                               if not (row[3] == 0 and row[4] == drift.upper())]
    elif drift == "create":
        catalog["database"].append((9001, 9000, 9000, 0, "CREATE", False))
    elif drift == "schema_usage":
        catalog["public_schema"] = [row for row in catalog["public_schema"] if row[3] != 0]
    elif drift == "schema_create":
        catalog["public_schema"].append((2200, 6171, 6171, 0, "CREATE", False))
    else:
        catalog["public_schema"] = []
    before = deepcopy(catalog)
    assert p.main() == 1
    assert p.REVOKE_TEMPORARY not in correction.db.commands and correction.db.commits == 0
    assert correction.db.catalog == before


@pytest.mark.parametrize("drift", ["temporary_retained", "connect_removed", "create_added", "explicit_grant",
                                      "grant_option", "grantor", "database_owner", "public_schema", "schema_owner"])
def test_correction_rejects_unapproved_post_revoke_acl_changes_before_commit(correction, drift):
    def change(catalog):
        if drift == "temporary_retained":
            catalog["database"].append((9001, 9000, 9000, 0, "TEMPORARY", False))
        elif drift == "connect_removed":
            catalog["database"] = [row for row in catalog["database"] if row[3] != 0]
        elif drift == "create_added":
            catalog["database"].append((9001, 9000, 9000, 0, "CREATE", False))
        elif drift == "explicit_grant":
            catalog["database"] = [row for row in catalog["database"] if row[3] != 9090]
        else:
            key = "public_schema" if drift in {"public_schema", "schema_owner"} else "database"
            row = list(catalog[key][-1])
            index = {"grant_option": 5, "grantor": 2, "database_owner": 1,
                     "public_schema": 5, "schema_owner": 1}[drift]
            row[index] = not row[index] if index == 5 else 9999
            catalog[key][-1] = tuple(row)
    correction.db.after_revoke = change
    assert p.main() == 1
    assert correction.db.commits == 0 and "COMMIT" not in correction.db.commands
    assert correction.db.catalog == correction.before and correction.db.closed
    assert (correction.root / p.TEMPORARY_CLAIM_NAME).is_file()
    assert evidence(correction)[-1]["outcome"] == "rejected_before_commit"


@pytest.mark.parametrize("failure,expected", [(p.REVOKE_TEMPORARY, "rejected_before_commit"),
                                              ("COMMIT", "uncertain"),
                                              ("BEGIN READ ONLY", "acknowledged_commit_requires_review")])
def test_correction_distinguishes_rejection_uncertainty_and_postcommit_failure(correction, failure, expected, capsys):
    correction.db.fail = failure
    assert p.main() == 1
    assert evidence(correction)[-1]["outcome"] == expected
    assert correction.db.commands.count("COMMIT") <= 1
    assert correction.db.closed and (correction.root / p.TEMPORARY_CLAIM_NAME).is_file()
    if correction.db.commits == 0:
        assert correction.db.catalog == correction.before
    assert_confidential(correction, capsys)


def test_correction_lost_commit_reply_preserves_uncertainty_and_refuses_retry(correction, monkeypatch):
    original = correction.db.execute
    def execute(command, parameters=None):
        result = original(command, parameters)
        if command == "COMMIT":
            raise ConnectionError(PRIVATE_ERROR)
        return result
    monkeypatch.setattr(correction.db, "execute", execute)
    assert p.main() == 1
    assert correction.db.commits == 1
    assert evidence(correction)[-1]["commit"] == "outcome_uncertain"
    assert evidence(correction)[-1]["outcome"] == "uncertain"
    assert p.main() == 1
    assert correction.connect.call_count == 1
    assert correction.db.commands.count(p.REVOKE_TEMPORARY) == 1


def test_correction_requires_explicit_commit_command_acknowledgement(correction, monkeypatch):
    original = correction.db.execute
    def execute(command, parameters=None):
        result = original(command, parameters)
        return SimpleNamespace(statusmessage="ROLLBACK") if command == "COMMIT" else result
    monkeypatch.setattr(correction.db, "execute", execute)
    assert p.main() == 1
    assert evidence(correction)[-1]["commit"] == "outcome_uncertain"
    assert "BEGIN READ ONLY" not in correction.db.commands


@pytest.mark.parametrize("phase", ["prior_state_verified", "public_temporary_revoke", "public_acl_verified", "commit",
                                   "commit_acknowledged", "verified"])
def test_correction_audit_failures_stop_and_preserve_commit_certainty(correction, monkeypatch, phase, capsys):
    original = p.save_json
    def save(path, record):
        if record.get("phase") == phase:
            raise OSError(PRIVATE_ERROR)
        original(path, record)
    monkeypatch.setattr(p, "save_json", save)
    assert p.main() == 1
    expected_commits = int(phase in {"commit_acknowledged", "verified"})
    assert correction.db.commits == expected_commits
    assert evidence(correction)[-1]["commit"] == (
        "acknowledged" if expected_commits else "outcome_uncertain" if phase == "commit" else "not_attempted")
    if not expected_commits:
        assert correction.db.catalog == correction.before
    assert_confidential(correction, capsys)


def test_correction_permanent_claim_is_independent_of_role_provisioning(correction):
    (correction.root / p.CLAIM_NAME).write_text("preserved role claim")
    assert p.main() == 0
    assert (correction.root / p.CLAIM_NAME).read_text() == "preserved role claim"
    assert p.main() == 1
    assert correction.connect.call_count == 1


def test_correction_failed_exclusive_claim_write_prevents_revoke(correction, monkeypatch):
    original = p.save_json
    def save(path, record):
        original(path, record)
        if path.name == p.TEMPORARY_CLAIM_NAME:
            raise OSError(PRIVATE_ERROR)
    monkeypatch.setattr(p, "save_json", save)
    assert p.main() == 1
    assert (correction.root / p.TEMPORARY_CLAIM_NAME).exists()
    assert p.REVOKE_TEMPORARY not in correction.db.commands
    assert correction.db.commits == 0


@pytest.mark.parametrize("drift", ["source", "metadata"])
def test_correction_changed_reviewed_inputs_prevent_commit(correction, monkeypatch, drift):
    def change(catalog):
        if drift == "source":
            monkeypatch.setattr(p, "source_hashes", lambda: {"changed": "artifact"})
        else:
            p.metadata.return_value = {**DOCUMENT, "database_host": "changed.invalid"}
    correction.db.after_revoke = change
    assert p.main() == 1
    assert correction.db.commits == 0 and correction.db.catalog == correction.before


@pytest.mark.parametrize("answer", ["", "not-a-uuid",
    f"AUTHORIZE ROLES {DOCUMENT['database_host']} {p.DATABASE} {p.ADMINISTRATOR}"])
def test_correction_cannot_use_role_provisioning_acknowledgement(correction, monkeypatch, answer):
    monkeypatch.setattr("builtins.input", lambda prompt: answer)
    assert p.main() == 1
    p.legacy.installed_clients.assert_not_called()
    correction.connect.assert_not_called()


def test_correction_cannot_bypass_operation_authorization(correction):
    audit = p.Audit()
    audit.state["authorization"] = "owner_acknowledged"
    with pytest.raises(p.Stop, match="owner_approval_required"):
        p.revoke_public_temporary(None, audit, DOCUMENT)
    correction.connect.assert_not_called()


def test_correction_authority_cannot_provision_roles_or_credentials(correction):
    audit = p.Audit(public_temporary=True)
    audit.state["authorization"] = "owner_acknowledged"
    with pytest.raises(p.Stop, match="owner_approval_required"):
        p.provision(None, correction.vault, audit, DOCUMENT)
    assert not correction.vault.reads and not correction.vault.writes
    correction.generator.assert_not_called()
    correction.connect.assert_not_called()


@pytest.mark.parametrize("arguments,allowed", [(["--revoke-public-temporary"], True),
    (["--revoke-public-temporary", "--provision-production"], False),
    (["--revoke-public-temporary", "--retry"], False)])
def test_correction_requires_exact_isolated_invocation(monkeypatch, arguments, allowed):
    # Satisfy the workspace prerequisite on every checkout before testing argv.
    monkeypatch.setattr(p, "REPOSITORY", ROOT)
    console = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(p, "sys", SimpleNamespace(platform="win32", version_info=(3, 11),
        executable=str(ROOT / ".venv/Scripts/python.exe"), flags=SimpleNamespace(isolated=True),
        dont_write_bytecode=True, argv=["helper", *arguments],
        stdin=console, __stdin__=console, stdout=console, __stdout__=console, stderr=console, __stderr__=console))
    monkeypatch.setattr(p, "os", SimpleNamespace(environ={}))
    if allowed:
        REAL_ENVIRONMENT()
    else:
        with pytest.raises(p.Stop, match="explicit_invocation_required"):
            REAL_ENVIRONMENT()
