"""Owner-operated Step 05. Source approval is NOT execution approval.

Run only after separate owner approval, in a fresh Windows PowerShell console
with transcription/recording disabled, using the website Python with -I -B.
There is no dry-run mode: offline tests must replace all external interfaces.

--activate-development changes only the development migrator.
--verify-development only verifies the approved prior activation; it cannot
retry activation. It reads the existing credential and uses read-only sessions.
Current HBA file integrity is mandatory for PASS, using the approved path/hash.
Active-file identity and ten-rule effective order rely on the owner's prior
administrative inspection; a matching hash is not proof of loaded server rules.
Verification performs no fresh administrative HBA catalog inspection.
The testing database receives one
deliberately rejected startup probe, with no SQL, to verify its HBA exclusion.
No runtime credential service is accessed. Secrets stay in process memory and
the approved vault; Python cannot guarantee erasure of immutable secret copies.
The Windows user, database superusers, and OS administrators remain trusted.

Audit: existing LOCALAPPDATA/OAF Website/BootstrapAudit/Step05-<execution_id>.
Exclusive, flushed JSON phase records contain only fixed, sanitized evidence.
A permanent exclusive claim file prevents concurrent/repeated activation after
any credential-write attempt. Never delete it or a credential to retry blindly.
There is no atomic transaction spanning WinVault and PostgreSQL. Any failure
requires owner reconciliation; a lost COMMIT reply is explicitly uncertain.
"""

from __future__ import annotations

import getpass
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import re
import secrets
import stat
import string
import sys
from datetime import datetime, timezone
from uuid import uuid4
import warnings


REPOSITORY = Path(r"C:\Users\ovisa\Documents\OAF_App\Development\OAF Website")
AUDIT_ROOT = Path(r"C:\Users\ovisa\AppData\Local\OAF Website\BootstrapAudit")
CLAIM_NAME = "Step05-development-activation.claim.json"
PRIOR_EXECUTION = "2b90b0c986de4d37af2738f04aca5404"
PRIOR_SOURCE_SHA256 = "690647015e6e3083f0eb3eb0ebac2012c999745c37a04c1e9d743dd3c5906708"
DATABASE = "oaf_website_dev"
ACCOUNT = "oaf_website_dev_migrator"
OWNER = "oaf_website_dev_schema_owner"
TEST_ACCOUNT = "oaf_website_test_migrator"
TEST_OWNER = "oaf_website_test_schema_owner"
SERVICE = "OAF Website/development/PostgreSQL/Migrations"
COMPOUND_TARGET = ACCOUNT + "@" + SERVICE
BOOTSTRAP_ROLES = (ACCOUNT, TEST_ACCOUNT, OWNER, TEST_OWNER)
ORDINARY_ROLES = BOOTSTRAP_ROLES + ("oaf_website_app", "oaf_website_test_app")
BACKEND = "keyring.backends.Windows.WinVaultKeyring"

# Owner's prior PostgreSQL 17.11 inspection: approved active file, ten valid
# rules in effective order, zero invalid rules. The separately owner-verified
# file hash pins that approval's exact contents, not fresh server-loaded state.
APPROVED_HBA_PATH = Path(r"C:\Program Files\PostgreSQL\17\data\pg_hba.conf")
APPROVED_HBA_SHA256 = "3344ed79726f9b82004bdf20559c5f7dc4ef48e8b788f0b03098db68a1c0618f"
# Each tuple is (type, databases, users, address, netmask, auth_method), using
# pg_hba_file_rules representations and rule_number order: CIDRs are split
# into address/netmask, local rules use None for both, and "all" has no mask.
# Activation checks these tuples through the catalog; verification pins the
# approved file bytes. Neither mode adopts a new rule set or changes approval.
APPROVED_HBA = (
    ("host", ("oaf_website_dev",), ("oaf_website_dev_migrator",),
     "127.0.0.1", "255.255.255.255", "scram-sha-256"),
    ("host", ("oaf_website_test",), ("oaf_website_test_migrator",),
     "127.0.0.1", "255.255.255.255", "scram-sha-256"),
    ("host", ("all", "replication"),
     ("oaf_website_dev_migrator", "oaf_website_test_migrator"), "all", None, "reject"),
    ("local", ("all", "replication"),
     ("oaf_website_dev_migrator", "oaf_website_test_migrator"), None, None, "reject"),
    ("local", ("all",), ("all",), None, None, "scram-sha-256"),
    ("host", ("all",), ("all",), "127.0.0.1", "255.255.255.255", "scram-sha-256"),
    ("host", ("all",), ("all",), "::1", "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff", "scram-sha-256"),
    ("local", ("replication",), ("all",), None, None, "scram-sha-256"),
    ("host", ("replication",), ("all",), "127.0.0.1", "255.255.255.255", "scram-sha-256"),
    ("host", ("replication",), ("all",), "::1", "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff", "scram-sha-256"),
)

# SESSION settings, outside the activation transaction: rollback must not turn
# query/error logging back on while a verifier-bearing command is in memory.
CONFIDENTIALITY = {
    "track_activities": "off", "log_statement": "none", "log_duration": "off",
    "log_min_duration_statement": "-1", "log_min_duration_sample": "-1",
    "log_statement_sample_rate": "0", "log_transaction_sample_rate": "0",
    "log_min_error_statement": "panic", "log_min_messages": "panic",
    "log_parameter_max_length": "0", "log_parameter_max_length_on_error": "0",
    "debug_print_parse": "off", "debug_print_rewritten": "off",
    "debug_print_plan": "off", "log_parser_stats": "off",
    "log_planner_stats": "off", "log_executor_stats": "off",
    "log_statement_stats": "off",
}


class Stop(Exception):
    """An internal fixed code, never a provider exception or supplied value."""


def require(condition, code):
    if not condition:
        raise Stop(code)


def save_json(path, record):
    # Exclusive creation preserves even an incomplete record after interruption.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def initial_audit_state(execution_id, source_hash):
    return {
        "execution_id": execution_id, "account": ACCOUNT,
        "database": DATABASE, "administrator": "postgres",
        "endpoint": "127.0.0.1:5432", "server_version": "17.11",
        "service": SERVICE, "prior_state": "not_verified",
        "credential_storage": "not_attempted", "commit": "not_attempted",
        "scram_authentication": "not_attempted", "hba_rejection": "not_attempted",
        "final_verification": "not_verified", "phase": "prelaunch",
        "helper_sha256": source_hash,
    }


class Audit:
    def __init__(self, *, verification=False):
        require(AUDIT_ROOT.is_dir() and AUDIT_ROOT.resolve() == AUDIT_ROOT,
                "audit_destination_mismatch")
        self.execution_id = uuid4().hex
        prefix = "Step05-verify-" if verification else "Step05-"
        self.directory = AUDIT_ROOT / (prefix + self.execution_id)
        self.directory.mkdir()
        self.sequence = 0
        self.state = initial_audit_state(
            self.execution_id, hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        if verification:
            self.state.update(mode="verification_only", administrator="not_used",
                              hba_rule_set="owner_previously_verified_ten_ordered_rules",
                              hba_active_file_identity="owner_previously_verified",
                              hba_catalog_verification="not_performed",
                              hba_file_integrity="not_verified")

    def record(self, phase, **changes):
        self.state.update(changes, phase=phase)
        self.sequence += 1
        save_json(self.directory / f"{self.sequence:02d}-{phase}.json", {
            **self.state, "utc": datetime.now(timezone.utc).isoformat(),
        })


def verify_predecessor():
    """Replay only the approved stopped execution; never infer a retry grant."""
    def read_record(path):
        try:
            require(path.resolve() == path, "activation_evidence_path_mismatch")
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise Stop("activation_evidence_missing_or_malformed") from None
        require(isinstance(record, dict), "activation_evidence_missing_or_malformed")
        return record

    require(read_record(AUDIT_ROOT / CLAIM_NAME) == {
        "execution_id": PRIOR_EXECUTION, "account": ACCOUNT, "database": DATABASE,
        "status": "owner_reconciliation_required_before_any_retry",
    }, "approved_activation_claim_mismatch")
    directory = AUDIT_ROOT / ("Step05-" + PRIOR_EXECUTION)
    phases = (
        "prelaunch hba_approval_preflight client_preflight credential_absence_preflight "
        "administrator_prompt administrator_connection confidentiality_preflight database_preflight "
        "prior_state_verified activation_claim password_generation credential_write credential_readback "
        "credential_verified activation_transaction role_activation commit commit_acknowledged "
        "scram_authentication scram_verified migrator_authority_checks cross_environment_probe stopped"
    ).split()
    changes = {
        "prior_state_verified": {"prior_state": "verified"},
        "credential_write": {"credential_storage": "write_outcome_uncertain"},
        "credential_readback": {"credential_storage": "write_returned"},
        "credential_verified": {"credential_storage": "verified_machine_local"},
        "commit": {"commit": "outcome_uncertain"},
        "commit_acknowledged": {"commit": "acknowledged"},
        "scram_authentication": {"scram_authentication": "pending"},
        "scram_verified": {"scram_authentication": "verified"},
        "cross_environment_probe": {"hba_rejection": "pending"},
        "stopped": {"failed_phase": "cross_environment_probe",
                    "failure_code": "cross_environment_rejection_unverified",
                    "final_verification": "FAILED_REQUIRES_OWNER_REVIEW"},
    }
    expected = initial_audit_state(PRIOR_EXECUTION, PRIOR_SOURCE_SHA256)
    previous_time = datetime.min.replace(tzinfo=timezone.utc)
    names = {f"{number:02d}-{phase}.json" for number, phase in enumerate(phases, 1)}
    require(directory.is_dir() and directory.resolve() == directory
            and {path.name for path in directory.iterdir()} == names,
            "activation_predecessor_inventory_mismatch")
    for number, phase in enumerate(phases, 1):
        record = read_record(directory / f"{number:02d}-{phase}.json")
        try:
            timestamp = datetime.fromisoformat(record.pop("utc"))
            require(timestamp.utcoffset() == timezone.utc.utcoffset(None)
                    and timestamp >= previous_time, "activation_predecessor_time_mismatch")
        except (KeyError, TypeError, ValueError):
            raise Stop("activation_predecessor_time_mismatch") from None
        previous_time = timestamp
        expected.update(changes.get(phase, {}), phase=phase)
        require(record == expected, "activation_predecessor_state_mismatch")


def environment():
    require(sys.platform == "win32" and sys.version_info[:2] == (3, 11),
            "windows_python_required")
    require(Path.cwd().resolve() == REPOSITORY
            and Path(__file__).resolve() == REPOSITORY / "ops/local_postgres_bootstrap/05_activate_dev.py"
            and Path(sys.executable).resolve() == REPOSITORY / ".venv/Scripts/python.exe",
            "approved_workspace_and_interpreter_required")
    require(sys.flags.isolated and sys.dont_write_bytecode
            and sys.argv[1:] in (["--activate-development"], ["--verify-development"]),
            "explicit_invocation_required")
    require(sys.stdin is sys.__stdin__ and sys.stdin.isatty() and sys.stdout.isatty(),
            "interactive_console_required")
    names = [name.upper() for name in os.environ]
    require(not any(name.startswith(("PG", "DB_", "DATABASE_"))
                    or (name.startswith("OAF_") and name != "OAF_ENV")
                    or "KEYRING_PROPERTY_" in name
                    or name in ("SQLALCHEMY_DATABASE_URI", "PSYCOPG_IMPL") for name in names),
            "environment_override_refused")
    require(os.environ.get("OAF_ENV", "development") == "development"
            and os.environ.get("PYTHON_KEYRING_BACKEND", BACKEND) == BACKEND,
            "environment_selection_refused")


def installed_clients():
    for package, version in (("psycopg", "3.3.6"), ("psycopg-binary", "3.3.6"),
                             ("keyring", "25.7.0"), ("pywin32-ctypes", "0.2.3")):
        require(importlib.metadata.version(package) == version, "unreviewed_client_version")
    import psycopg
    from keyring.backends.Windows import WinVaultKeyring, win32cred

    require(psycopg.pq.__impl__ == "binary" and psycopg.pq.version() == 180004
            and psycopg.capabilities.has_encrypt_password()
            and any(item.keyword == b"require_auth" for item in psycopg.pq.Conninfo.get_defaults()),
            "reviewed_libpq_required")
    vault = WinVaultKeyring()
    require(type(vault) is WinVaultKeyring and vault.priority > 0
            and win32cred.__name__ == "win32ctypes.pywin32.win32cred"
            and vault._compound_name(ACCOUNT, SERVICE) == COMPOUND_TARGET,
            "reviewed_winvault_required")
    vault.persist = win32cred.CRED_PERSIST_LOCAL_MACHINE
    require(vault.persist == 2, "machine_local_persistence_required")
    return psycopg, vault


def connect(psycopg, username, password, *, rejection_probe=False, read_only=False):
    # One numeric endpoint, no TLS/GSS fallback, service lookup, or passfile.
    # The explicit require_auth also rejects trust/SSPI/MD5 authentication.
    return psycopg.connect(
        host="127.0.0.1", hostaddr="127.0.0.1", port=5432,
        dbname="oaf_website_test" if rejection_probe else DATABASE,
        user=username, password=password, passfile="NUL", connect_timeout=10,
        require_auth="scram-sha-256", sslmode="disable", gssencmode="disable",
        application_name="OAF-Website-Step05", client_encoding="UTF8",
        options=("-c search_path=pg_catalog,pg_temp -c statement_timeout=60000 -c lock_timeout=5000"
                 + (" -c default_transaction_read_only=on" if read_only or rejection_probe else "")),
        autocommit=True, prepare_threshold=None,
    )


def identity(connection, username):
    row = connection.execute("""
        SELECT session_user::text, current_user::text, current_database(),
               host(inet_server_addr()), inet_server_port(),
               current_setting('server_version_num')
    """).fetchone()
    require(row == (username, username, DATABASE, "127.0.0.1", 5432, "170011")
            and connection.pgconn.used_password, "server_identity_or_scram_mismatch")
    if username == "postgres":
        require(connection.execute("""
            SELECT EXISTS (SELECT FROM pg_roles WHERE oid=10 AND rolname='postgres'
                           AND rolsuper AND rolcanlogin)
        """).fetchone() == (True,), "administrator_mismatch")
        locations = connection.execute(
            "SELECT current_setting('data_directory'), current_setting('hba_file')"
        ).fetchone()
        require(tuple(Path(value) for value in locations) == (
            Path(r"C:\Program Files\PostgreSQL\17\data"),
            Path(r"C:\Program Files\PostgreSQL\17\data\pg_hba.conf"),
        ), "approved_cluster_location_mismatch")


def confidentiality(connection):
    # Unknown preload/audit hooks cannot be proven confidential by core GUCs.
    require(connection.execute("""
        SELECT current_setting('shared_preload_libraries') = ''
           AND current_setting('session_preload_libraries') = ''
           AND current_setting('local_preload_libraries') = ''
           AND NOT EXISTS (SELECT FROM pg_extension WHERE extname <> 'plpgsql')
    """).fetchone() == (True,), "unreviewed_server_logging_hooks")
    for name, value in CONFIDENTIALITY.items():
        connection.execute("SELECT set_config(%s, %s, false)", (name, value))
    rows = connection.execute(
        "SELECT name, setting FROM pg_settings WHERE name = ANY(%s)",
        (list(CONFIDENTIALITY),),
    ).fetchall()
    require(dict(rows) == CONFIDENTIALITY, "confidentiality_controls_mismatch")


def verify_hba(connection):
    require(len(APPROVED_HBA) == 10, "approved_hba_baseline_missing")
    rows = connection.execute("""
        SELECT rule_number, type, database, user_name, address, netmask,
               auth_method, options, error, file_name = current_setting('hba_file')
        FROM pg_hba_file_rules ORDER BY rule_number NULLS LAST, line_number
    """).fetchall()
    actual = []
    for number, kind, databases, users, address, mask, method, options, error, same_file in rows:
        require(number == len(actual) + 1 and error is None and not options and same_file,
                "hba_parse_order_or_include_mismatch")
        actual.append((kind, tuple(databases), tuple(users), address, mask, method))
    require(tuple(actual) == APPROVED_HBA, "approved_hba_mismatch")


def verify_hba_file():
    """Current file integrity only; no claim of fresh server/catalog evidence."""
    path = APPROVED_HBA_PATH
    try:
        require(path.resolve(strict=True) == path, "approved_hba_path_mismatch")
        before = path.stat()
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            require(stat.S_ISREG(opened.st_mode) and os.path.samestat(before, opened),
                    "approved_hba_file_changed")
            digest = hashlib.sha256(stream.read()).hexdigest()
            after = os.fstat(stream.fileno())
        require(path.resolve(strict=True) == path, "approved_hba_path_mismatch")
        current = path.stat()
    except (OSError, RuntimeError):
        raise Stop("approved_hba_file_unavailable") from None
    require(all(os.path.samestat(before, item)
                and (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                == (item.st_size, item.st_mtime_ns, item.st_ctime_ns)
                for item in (opened, after, current)), "approved_hba_file_changed")
    require(digest == APPROVED_HBA_SHA256, "approved_hba_file_hash_mismatch")


def authority(connection, *, active, check_passwords=True):
    """Restricted verification omits the administrator-only pg_authid check."""
    rows = connection.execute("""
        SELECT rolname, rolcanlogin, rolsuper OR rolcreatedb OR rolcreaterole
               OR rolreplication OR rolbypassrls, rolinherit, rolconnlimit,
               rolvaliduntil IS NULL, rolconfig IS NULL
        FROM pg_roles WHERE rolname = ANY(%s)
    """, (list(ORDINARY_ROLES),)).fetchall()
    require({row[0] for row in rows} == set(ORDINARY_ROLES), "required_role_missing")
    for name, login, elevated, inherit, limit, no_expiry, no_config in rows:
        require(not elevated, "elevated_role_privileges")
        if name in BOOTSTRAP_ROLES:
            require(login == (active and name == ACCOUNT) and not inherit
                    and limit == -1 and no_expiry and no_config, "bootstrap_role_drift")
        else:
            require(login, "runtime_role_drift")
    if check_passwords:
        # Only boolean password properties leave pg_authid, never verifiers.
        passwords = connection.execute("""
            SELECT rolname, rolpassword IS NULL,
                   coalesce(rolpassword LIKE 'SCRAM-SHA-256$%%', false)
            FROM pg_authid WHERE rolname = ANY(%s)
        """, (list(BOOTSTRAP_ROLES),)).fetchall()
        expected = {(name, not (active and name == ACCOUNT), active and name == ACCOUNT)
                    for name in BOOTSTRAP_ROLES}
        require(set(passwords) == expected, "password_state_mismatch")
    edges = connection.execute("""
        SELECT member.rolname, parent.rolname, m.inherit_option, m.set_option,
               m.admin_option, m.grantor
        FROM pg_auth_members m JOIN pg_roles member ON member.oid=m.member
        JOIN pg_roles parent ON parent.oid=m.roleid
        WHERE member.rolname=ANY(%s) OR parent.rolname=ANY(%s)
    """, (list(ORDINARY_ROLES), list(ORDINARY_ROLES))).fetchall()
    require(len(edges) == 2 and set(edges) == {
        (ACCOUNT, OWNER, False, True, False, 10),
        (TEST_ACCOUNT, TEST_OWNER, False, True, False, 10),
    }, "restricted_membership_mismatch")
    require(connection.execute("""
        SELECT NOT EXISTS (SELECT FROM pg_db_role_setting s JOIN pg_roles r ON r.oid=s.setrole
                           WHERE r.rolname=ANY(%s))
          AND NOT EXISTS (SELECT FROM pg_roles r CROSS JOIN pg_parameter_acl p
                          WHERE r.rolname=ANY(%s) AND has_parameter_privilege(r.oid,p.parname,'ALTER SYSTEM'))
          AND NOT EXISTS (SELECT FROM pg_roles r CROSS JOIN pg_settings p
                          WHERE r.rolname=ANY(%s) AND p.context IN ('superuser','superuser-backend')
                            AND has_parameter_privilege(r.oid,p.name,'SET'))
    """, (list(BOOTSTRAP_ROLES), list(ORDINARY_ROLES), list(ORDINARY_ROLES))).fetchone()
            == (True,), "unexpected_settings_or_parameter_authority")
    databases = connection.execute("""
        SELECT d.datname, r.rolname, r.rolcanlogin, d.datallowconn, d.datistemplate,
               EXISTS (SELECT FROM aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a
                       WHERE a.grantee=0)
        FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba
        WHERE d.datname IN ('oaf_website_dev','oaf_website_test')
    """).fetchall()
    require(set(databases) == {
        (name, "oaf_website_owner", False, True, False, False)
        for name in (DATABASE, "oaf_website_test")
    }, "database_owner_or_public_authority_mismatch")
    privileges = connection.execute("""
        SELECT r.rolname, d.datname, has_database_privilege(r.oid,d.oid,'CONNECT'),
               has_database_privilege(r.oid,d.oid,
                 'CREATE,TEMPORARY,CONNECT WITH GRANT OPTION,CREATE WITH GRANT OPTION,TEMPORARY WITH GRANT OPTION')
        FROM pg_roles r CROSS JOIN pg_database d WHERE r.rolname=ANY(%s)
          AND d.datname IN ('oaf_website_dev','oaf_website_test')
    """, (list(ORDINARY_ROLES),)).fetchall()
    matching = {ACCOUNT: DATABASE, "oaf_website_app": DATABASE,
                TEST_ACCOUNT: "oaf_website_test", "oaf_website_test_app": "oaf_website_test"}
    require(len(privileges) == 12 and all(
        allowed == (matching.get(name) == database) and not elevated
        for name, database, allowed, elevated in privileges), "database_authority_mismatch")
    require(connection.execute("""
        SELECT n.nspowner=(SELECT oid FROM pg_roles WHERE rolname=%s),
               NOT EXISTS (SELECT FROM pg_roles r CROSS JOIN pg_namespace other
                   WHERE r.rolname=ANY(%s) AND other.nspname !~ '^pg_(temp|toast_temp)_[0-9]+$'
                     AND has_schema_privilege(r.oid,other.oid,'CREATE')
                     AND NOT (other.oid=n.oid AND r.oid=n.nspowner)),
               NOT EXISTS (SELECT FROM pg_shdepend d JOIN pg_roles r ON r.oid=d.refobjid
                   WHERE d.refclassid='pg_authid'::regclass AND d.deptype='o'
                     AND r.rolname=ANY(%s) AND NOT (
                       r.rolname IN ('oaf_website_dev_schema_owner','oaf_website_test_schema_owner')
                       AND d.dbid=(SELECT oid FROM pg_database WHERE datname=CASE r.rolname
                         WHEN 'oaf_website_dev_schema_owner' THEN 'oaf_website_dev' ELSE 'oaf_website_test' END)))
        FROM pg_namespace n WHERE n.nspname='oaf_website'
    """, (OWNER, list(ORDINARY_ROLES), list(ORDINARY_ROLES))).fetchone()
            == (True, True, True), "schema_or_object_authority_mismatch")


def targets_absent(vault):
    # Read the exact names even if another account occupies the service target.
    first = vault._read_credential(SERVICE)
    second = vault._read_credential(COMPOUND_TARGET)
    require(first is None and second is None, "credential_target_already_exists")


def stored_password(vault, expected=None):
    credential = vault._read_credential(SERVICE)
    require(credential is not None and credential.get("UserName") == ACCOUNT
            and credential.get("TargetName") == SERVICE and credential.get("Type") == 1
            and credential.get("Persist") == 2, "stored_credential_metadata_mismatch")
    password = credential.value
    require(isinstance(password, str) and re.fullmatch(r"[A-Za-z0-9]{48}", password) is not None,
            "stored_credential_secret_invalid")
    require(expected is None or secrets.compare_digest(password, expected),
            "stored_credential_secret_mismatch")
    require(vault._read_credential(COMPOUND_TARGET) is None, "compound_target_collision")
    return password


def verify_migrator(connection):
    identity(connection, ACCOUNT)
    require(connection.execute("""
        SELECT rolname FROM pg_roles WHERE oid <> (SELECT oid FROM pg_roles WHERE rolname=current_user)
          AND pg_has_role(current_user, oid, 'SET') ORDER BY rolname
    """).fetchall() == [(OWNER,)], "unexpected_set_role_authority")
    # This separate read-only transaction makes SET LOCAL ROLE self-resetting.
    with connection.transaction():
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL ROLE oaf_website_dev_schema_owner")
        require(connection.execute("SELECT session_user::text,current_user::text").fetchone()
                == (ACCOUNT, OWNER), "set_role_verification_failed")
        require(connection.execute("""
            SELECT NOT has_database_privilege(current_user,'oaf_website_test','CONNECT,CREATE,TEMPORARY')
        """).fetchone() == (True,), "schema_owner_cross_environment_authority")
    identity(connection, ACCOUNT)


def verify_rejection(psycopg, password):
    # Psycopg 3.3.6 (including the installed binary generator) saves a
    # FinishedPGconn on poll failure; timeout errors may have no pgconn.
    # Startup errors expose no structured PGresult/SQLSTATE. SQLSTATE 28000
    # alone would also cover unrelated authentication failures.
    # libpq prefixes error_message with endpoint text, potentially on the SAME
    # line as FATAL. Match the explicit reject diagnostic and identities, not
    # the whole formatted line, severity spacing, or encryption translation.
    # English primary text remains necessary with this API: localized or
    # unfamiliar text fails closed. Never print/persist the raw diagnostic.
    # require_auth stays SCRAM: libpq handles an ErrorResponse before its
    # AuthenticationRequest checks, so a pre-authentication reject survives.
    try:
        unexpected = connect(psycopg, ACCOUNT, password, rejection_probe=True)
    except psycopg.OperationalError as error:
        pgconn = error.pgconn
        message = getattr(pgconn, "error_message", None)
        require(isinstance(message, bytes) and bool(message),
                "cross_environment_rejection_evidence_missing")
        require(getattr(pgconn, "status", None) == psycopg.pq.ConnStatus.BAD
                and tuple(getattr(pgconn, name, None) for name in ("host", "hostaddr", "port", "user", "db")) == (
                    b"127.0.0.1", b"127.0.0.1", b"5432", ACCOUNT.encode("ascii"), b"oaf_website_test")
                and getattr(pgconn, "used_password", None) is False
                and error.sqlstate in (None, "28000"),
                "cross_environment_rejection_context_mismatch")
        diagnostic = (rb'\bpg_hba\.conf rejects connection for host "127\.0\.0\.1",\s+user "'
                      + ACCOUNT.encode("ascii") + rb'",\s+database "oaf_website_test", [^\r\n]+')
        require(re.search(diagnostic, message) is not None,
                "cross_environment_rejection_unverified")
    else:
        unexpected.close()
        raise Stop("cross_environment_connection_unexpectedly_accepted")


def verify_development(psycopg, vault, audit):
    """No administrative login, password generation, credential write, or DDL."""
    migrator = password = None
    try:
        audit.record("existing_credential_read")
        password = stored_password(vault)
        audit.record("existing_credential_verified", credential_storage="existing_machine_local")
        migrator = connect(psycopg, ACCOUNT, password, read_only=True)
        identity(migrator, ACCOUNT)
        require(migrator.execute("SHOW default_transaction_read_only").fetchone() == ("on",),
                "read_only_session_required")
        audit.record("scram_verified", scram_authentication="verified")
        audit.record("migrator_authority_checks")
        authority(migrator, active=True, check_passwords=False)
        verify_migrator(migrator)
        audit.record("cross_environment_probe", hba_rejection="pending")
        verify_rejection(psycopg, password)
        identity(migrator, ACCOUNT)
        audit.record("hba_rejection_observed", hba_rejection="verified_explicit_reject")
        audit.record("current_hba_checks")
        verify_hba_file()
        audit.record("current_hba_file_verified", hba_file_integrity="verified_approved_sha256",
                     hba_file_path=str(APPROVED_HBA_PATH), hba_file_sha256=APPROVED_HBA_SHA256)
        stored_password(vault, password)
        verify_predecessor()
        audit.record("verified", final_verification="PASS")
    finally:
        password = None
        if migrator is not None:
            migrator.close()


def activate(psycopg, vault, audit):
    administrator = migrator = None
    administrator_password = password = verifier = None
    try:
        audit.record("credential_absence_preflight")
        targets_absent(vault)
        audit.record("administrator_prompt")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            administrator_password = getpass.getpass("PostgreSQL postgres administrator password: ")
        require(bool(administrator_password), "empty_administrator_password")
        audit.record("administrator_connection")
        administrator = connect(psycopg, "postgres", administrator_password)
        administrator_password = None
        identity(administrator, "postgres")
        audit.record("confidentiality_preflight")
        confidentiality(administrator)
        audit.record("database_preflight")
        authority(administrator, active=False)
        verify_hba(administrator)
        targets_absent(vault)
        audit.record("prior_state_verified", prior_state="verified")

        # This durable, exclusive write is the concurrency and retry boundary.
        # WinVault itself has no atomic create-only primitive. The owner must
        # keep other credential/database administration idle during this run.
        audit.record("activation_claim")
        save_json(AUDIT_ROOT / CLAIM_NAME, {"execution_id": audit.execution_id,
                  "account": ACCOUNT, "database": DATABASE, "status": "owner_reconciliation_required_before_any_retry"})
        audit.record("password_generation")
        password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(48))
        verifier = administrator.pgconn.encrypt_password(
            password.encode("ascii"), ACCOUNT.encode("ascii"), b"scram-sha-256")
        require(re.fullmatch(rb"SCRAM-SHA-256\$[1-9][0-9]*:[A-Za-z0-9+/]+=*\$[A-Za-z0-9+/]+=*:[A-Za-z0-9+/]+=*",
                             verifier) is not None, "scram_verifier_api_result_invalid")
        targets_absent(vault)
        audit.record("credential_write", credential_storage="write_outcome_uncertain")
        # Reviewed keyring 25.7.0 primitive: exactly one CredWrite. The public
        # set_password may move an existing credential and is intentionally unused.
        vault._set_password(SERVICE, ACCOUNT, password)
        audit.record("credential_readback", credential_storage="write_returned")
        stored_password(vault, password)
        audit.record("credential_verified", credential_storage="verified_machine_local")

        audit.record("activation_transaction")
        administrator.execute("BEGIN")
        authority(administrator, active=False)
        verify_hba(administrator)
        audit.record("role_activation")
        # The verifier alone is a SQL literal. No plaintext password enters SQL.
        command = psycopg.sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
            psycopg.sql.Identifier(ACCOUNT), psycopg.sql.Literal(verifier.decode("ascii")))
        administrator.execute(command)
        del command
        verifier = None
        authority(administrator, active=True)
        verify_hba(administrator)
        audit.record("commit", commit="outcome_uncertain")
        administrator.execute("COMMIT")
        audit.record("commit_acknowledged", commit="acknowledged")

        audit.record("scram_authentication", scram_authentication="pending")
        # Authenticate with the password retrieved from WinVault, not merely
        # the generated copy. This proves matching working credentials.
        migrator = connect(psycopg, ACCOUNT, stored_password(vault, password))
        identity(migrator, ACCOUNT)
        audit.record("scram_verified", scram_authentication="verified")
        audit.record("migrator_authority_checks")
        verify_migrator(migrator)
        audit.record("cross_environment_probe", hba_rejection="pending")
        verify_rejection(psycopg, password)
        audit.record("hba_rejection_verified", hba_rejection="verified_explicit_reject")
        audit.record("final_checks")
        identity(administrator, "postgres")
        authority(administrator, active=True)
        verify_hba(administrator)
        stored_password(vault, password)
        audit.record("verified", final_verification="PASS")
    finally:
        # Close implicitly aborts an open, uncommitted transaction. No COMMIT
        # retry, explicit recovery SQL, credential deletion, or password rotation.
        administrator_password = password = verifier = None
        for connection in (migrator, administrator):
            if connection is not None:
                connection.close()


def main():
    audit = None
    phase = "environment"
    # No provider logger or Python traceback may serialize an exception/secret.
    logging.disable(sys.maxsize)
    try:
        environment()
        verification = sys.argv[1:] == ["--verify-development"]
        phase = "audit_prelaunch"
        audit = Audit(verification=verification)
        audit.record("prelaunch")
        if verification:
            audit.record("activation_predecessor_checks")
            verify_predecessor()
            audit.record("activation_predecessor_verified", prior_state="verified",
                         prior_execution_id=PRIOR_EXECUTION, prior_activation_commit="acknowledged")
        else:
            require(not (AUDIT_ROOT / CLAIM_NAME).exists(), "prior_activation_claim_refuses_retry")
        audit.record("hba_approval_preflight")
        require(len(APPROVED_HBA) == 10, "approved_hba_baseline_missing")
        audit.record("client_preflight")
        psycopg, vault = installed_clients()
        if verification:
            verify_development(psycopg, vault, audit)
        else:
            activate(psycopg, vault, audit)
    except BaseException as error:
        code = str(error) if type(error) is Stop else "operation_failed_or_interrupted"
        phase = audit.state["phase"] if audit is not None else phase
        evidence_saved = False
        if audit is not None:
            try:
                audit.record("stopped", failed_phase=phase, failure_code=code,
                             final_verification="FAILED_REQUIRES_OWNER_REVIEW")
                evidence_saved = True
            except BaseException:
                pass
        print(f"STOP: phase={phase}; code={code}; outcome_evidence_saved={evidence_saved}.")
        print("Do not retry or remove credentials/claim files. Owner reconciliation is required.")
        return 1
    operation = "verification only" if verification else "activation"
    print(f"PASS: development {operation} verified; execution_id={audit.execution_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
