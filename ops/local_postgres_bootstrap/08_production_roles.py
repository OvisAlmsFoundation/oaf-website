"""Owner-only production preparation; source approval is not execution approval.

Separate explicit role-provisioning and PUBLIC TEMPORARY correction operations;
neither invokes the other. No retry/rotation/bootstrap mode. Reuses Step 06's
pinned Windows clients and exclusive flushed evidence. Render manages server
monitoring, preload libraries and logging; OAF protects credentials locally.
Import performs no credential, configuration, network, RNG or audit access.
"""
from __future__ import annotations

import getpass
import hashlib
import importlib.util
import logging
import os
from pathlib import Path
import re
import secrets
import sys
from datetime import datetime, timezone
from uuid import UUID, uuid4
import warnings


HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("oaf_step06_primitives", HERE / "06_activate_test.py")
legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(legacy)
Stop, require, save_json = legacy.Stop, legacy.require, legacy.save_json
REPOSITORY, AUDIT_ROOT = legacy.REPOSITORY, legacy.AUDIT_ROOT
DATABASE = "oaf_website_prod"
ADMINISTRATOR = "oaf_website_prod_user"
APP = "oaf_website_prod_app"
MIGRATOR = "oaf_website_prod_migrator"
SERVICES = {APP: "OAF Website/production/PostgreSQL",
            MIGRATOR: "OAF Website/production/PostgreSQL/Migrations"}
CLAIM_NAME = "Step08-production-roles.claim.json"
TEMPORARY_CLAIM_NAME = "Step08-production-public-temporary.claim.json"
REVOKE_TEMPORARY = "REVOKE TEMPORARY ON DATABASE oaf_website_prod FROM PUBLIC"


def environment():
    require(sys.platform == "win32" and sys.version_info[:2] == (3, 11), "windows_python_required")
    require(Path.cwd().resolve() == REPOSITORY
            and HERE == REPOSITORY / "ops/local_postgres_bootstrap"
            and Path(sys.executable).resolve() == REPOSITORY / ".venv/Scripts/python.exe",
            "approved_workspace_and_interpreter_required")
    require(sys.flags.isolated and sys.dont_write_bytecode
            and sys.argv[1:] in (["--provision-production"], ["--revoke-public-temporary"]),
            "explicit_invocation_required")
    require(sys.stdin is sys.__stdin__ and sys.stdin.isatty()
            and sys.stdout is sys.__stdout__ and sys.stdout.isatty()
            and sys.stderr is sys.__stderr__ and sys.stderr.isatty(), "interactive_console_required")
    require(not any(name.upper().startswith(("PG", "DB_", "DATABASE_"))
                    or (name.upper().startswith("OAF_") and name.upper() != "OAF_ENV")
                    or "KEYRING_PROPERTY_" in name.upper()
                    or name.upper() in {"SQLALCHEMY_DATABASE_URI", "PSYCOPG_IMPL",
                                        "SSL_CERT_FILE", "SSL_CERT_DIR", "SSLKEYLOGFILE"}
                    for name in os.environ), "environment_override_refused")
    require(os.environ.get("OAF_ENV", "production") == "production"
            and os.environ.get("PYTHON_KEYRING_BACKEND", legacy.BACKEND) == legacy.BACKEND,
            "environment_selection_refused")


def metadata():
    # -I excludes the working directory. Add only the already checked repository.
    if str(REPOSITORY) not in sys.path:
        sys.path.insert(0, str(REPOSITORY))
    from oaf_website.migration_config import production_metadata
    document = production_metadata()
    require(document["database_owner"] == ADMINISTRATOR, "provider_owner_mismatch")
    return document


def source_hashes():
    # Bind the procedure, reused security primitives and fixed metadata loader.
    return {str(path.relative_to(REPOSITORY)).replace("\\", "/"):
            hashlib.sha256(path.read_bytes()).hexdigest() for path in (
                Path(__file__).resolve(), HERE / "06_activate_test.py",
                REPOSITORY / "oaf_website/migration_config.py",
                REPOSITORY / "oaf_website/production_config.py")}


class Audit:
    def __init__(self, *, public_temporary=False):
        require(AUDIT_ROOT.is_dir() and AUDIT_ROOT.resolve() == AUDIT_ROOT,
                "audit_destination_mismatch")
        self.execution_id = uuid4().hex
        prefix = "Step08-public-temporary-" if public_temporary else "Step08-"
        self.directory = AUDIT_ROOT / (prefix + self.execution_id)
        self.directory.mkdir()
        self.sequence = 0
        self.state = dict(execution_id=self.execution_id, database=DATABASE,
                          administrator=ADMINISTRATOR,
                          operation="revoke_public_temporary" if public_temporary else "provision_production_roles",
                          roles=[] if public_temporary else list(SERVICES),
                          phase="prelaunch", authorization="not_acknowledged",
                          credentials={} if public_temporary else {role: "not_attempted" for role in SERVICES},
                          commit="not_attempted", verification="not_attempted",
                          migration_revision="not_applicable", advisory_lock="not_applicable",
                          source_hashes=source_hashes())

    def record(self, phase, **changes):
        self.state.update(changes, phase=phase)
        self.sequence += 1
        save_json(self.directory / f"{self.sequence:02d}-{phase}.json",
                  {**self.state, "utc": datetime.now(timezone.utc).isoformat()})


def owner_approval(audit, document):
    # An existing, separate owner approval is referenced, never issued here.
    correction = audit.state["operation"] == "revoke_public_temporary"
    if correction:
        print(REVOKE_TEMPORARY + ";")
        print("PUBLIC TEMPORARY only; preserve all other database and public-schema privileges.")
    else:
        print("Production roles only; schema bootstrap, migrations and deployment require separate authority.")
    print(f"Endpoint={document['database_host']}:5432; database={DATABASE}; administrator={ADMINISTRATOR}")
    print("Reviewed source SHA-256:", audit.state["source_hashes"])
    scope = "PUBLIC TEMPORARY correction" if correction else "role-provisioning"
    reference = input(f"Existing owner {scope} approval reference (UUID): ")
    try:
        require(str(UUID(reference)) == reference, "owner_approval_required")
    except ValueError:
        raise Stop("owner_approval_required") from None
    action = "REVOKE TEMPORARY" if correction else "ROLES"
    confirmation = f"AUTHORIZE {action} {document['database_host']} {DATABASE} {ADMINISTRATOR}"
    require(input(f"Confirm reviewed sources, audit retention and this separate approval; type {confirmation}: ")
            == confirmation, "owner_approval_required")
    audit.record("owner_authorization", authorization="owner_acknowledged",
                 approval_reference=reference, endpoint=document["database_host"] + ":5432")


def targets_absent(vault):
    for role, service in SERVICES.items():
        require(vault._read_credential(service) is None
                and vault._read_credential(role + "@" + service) is None,
                "credential_target_already_exists")


def stored_password(vault, role, expected):
    service = SERVICES[role]
    record = vault._read_credential(service)
    require(record is not None and record.get("TargetName") == service
            and record.get("UserName") == role and record.get("Type") == 1
            and record.get("Persist") == 2, "stored_credential_metadata_mismatch")
    blob = record.get("CredentialBlob")
    # Strict native UTF-16LE readback; do not invoke keyring's UTF-8 fallback.
    require(type(blob) is bytes and len(blob) == 128, "stored_credential_encoding_mismatch")
    password = blob.decode("utf-16-le", errors="strict")
    require(re.fullmatch(r"[0-9a-f]{64}", password) is not None
            and secrets.compare_digest(password, expected), "stored_credential_secret_mismatch")
    require(vault._read_credential(role + "@" + service) is None, "compound_target_collision")
    return password


def connect(psycopg, document, username, password):
    return psycopg.connect(host=document["database_host"], port=5432, dbname=DATABASE,
                          user=username, password=password, passfile="NUL", connect_timeout=10,
                          require_auth="scram-sha-256", sslmode="require",
                          ssl_min_protocol_version="TLSv1.2", sslsni="1", gssencmode="disable",
                          application_name="OAF-Website-Step08", client_encoding="UTF8",
                          options="-c search_path=pg_catalog,pg_temp -c statement_timeout=60000 -c lock_timeout=5000",
                          autocommit=True, prepare_threshold=None)


def identity(connection, document):
    require((connection.pgconn.host, connection.pgconn.port, connection.pgconn.db, connection.pgconn.user)
            == (document["database_host"].encode("ascii"), b"5432", DATABASE.encode("ascii"),
                ADMINISTRATOR.encode("ascii")) and connection.pgconn.used_password,
            "endpoint_or_authentication_mismatch")
    require(connection.execute("""
        SELECT session_user::text, current_user::text, current_database(),
               current_setting('server_version_num'), inet_server_port(),
               pg_get_userbyid(datdba), datallowconn, datistemplate
        FROM pg_catalog.pg_database WHERE datname=current_database()
    """).fetchone() == (ADMINISTRATOR, ADMINISTRATOR, DATABASE, "170011", 5432,
                         ADMINISTRATOR, True, False), "server_identity_mismatch")
    require(connection.execute("""
        SELECT rolcanlogin AND rolcreaterole AND NOT rolsuper
        FROM pg_catalog.pg_roles WHERE rolname=session_user
    """).fetchone() == (True,), "provider_administrator_authority_mismatch")
    require(connection.execute("""
        SELECT ssl AND version IN ('TLSv1.2','TLSv1.3')
        FROM pg_catalog.pg_stat_ssl WHERE pid=pg_backend_pid()
    """).fetchone() == (True,), "tls_required")


def starting_state(connection, document):
    identity(connection, document)
    require(connection.execute("""
        SELECT NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname=ANY(%s))
           AND NOT EXISTS (SELECT FROM pg_catalog.pg_namespace WHERE nspname='oaf_website')
           AND EXISTS (SELECT FROM pg_catalog.pg_namespace WHERE nspname='public')
    """, (list(SERVICES),)).fetchone() == (True,), "initial_role_or_schema_collision")
    # Do not reproduce 07's ACL changes. Unsafe inherited PUBLIC privileges
    # require a separate owner decision; role provisioning never repairs them.
    require(connection.execute("""
        SELECT NOT EXISTS (
          SELECT FROM pg_catalog.pg_database d,
            pg_catalog.aclexplode(coalesce(d.datacl,pg_catalog.acldefault('d',d.datdba))) a
          WHERE d.datname=current_database() AND a.grantee=0
            AND (a.privilege_type IN ('CREATE','TEMPORARY') OR a.is_grantable))
          AND NOT EXISTS (
          SELECT FROM pg_catalog.pg_namespace n,
            pg_catalog.aclexplode(coalesce(n.nspacl,pg_catalog.acldefault('n',n.nspowner))) a
          WHERE n.nspname !~ '^pg_(temp|toast_temp)_[0-9]+$'
            AND a.grantee=0 AND (a.privilege_type='CREATE' OR a.is_grantable))
    """).fetchone() == (True,), "unsafe_public_structural_authority")


def restricted_roles(connection):
    rows = connection.execute("""
        SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
               rolreplication, rolbypassrls, rolinherit, rolconnlimit,
               rolvaliduntil IS NULL, rolconfig IS NULL
        FROM pg_catalog.pg_roles WHERE rolname=ANY(%s)
    """, (list(SERVICES),)).fetchall()
    require(len(rows) == 2 and set(rows) == {
        (role, True, False, False, False, False, False, False, -1, True, True)
        for role in SERVICES}, "restricted_role_attributes_mismatch")
    edges = connection.execute("""
        SELECT parent.rolname, member.rolname, grantor.rolname,
               m.admin_option, m.inherit_option, m.set_option
        FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles parent ON parent.oid=m.roleid
        JOIN pg_catalog.pg_roles member ON member.oid=m.member
        JOIN pg_catalog.pg_roles grantor ON grantor.oid=m.grantor
        WHERE parent.rolname=ANY(%s) OR member.rolname=ANY(%s)
    """, (list(SERVICES), list(SERVICES))).fetchall()
    bootstrap = connection.execute("SELECT rolname FROM pg_catalog.pg_roles WHERE oid=10 AND rolsuper").fetchone()
    require(bootstrap is not None and len(edges) == 3 and set(edges) == {
        (APP, ADMINISTRATOR, bootstrap[0], True, False, False),
        (MIGRATOR, ADMINISTRATOR, bootstrap[0], True, False, False),
        (MIGRATOR, ADMINISTRATOR, ADMINISTRATOR, False, False, True)}, "restricted_role_membership_mismatch")
    require(connection.execute("""
        SELECT NOT EXISTS (
          SELECT FROM pg_catalog.pg_shdepend d JOIN pg_catalog.pg_roles r ON r.oid=d.refobjid
          WHERE d.refclassid='pg_catalog.pg_authid'::pg_catalog.regclass AND d.deptype='o'
            AND r.rolname=ANY(%s))
          AND NOT EXISTS (
          SELECT FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_database d
          WHERE r.rolname=ANY(%s) AND d.datname=current_database()
            AND (pg_catalog.has_database_privilege(r.oid,d.oid,'CREATE')
                 OR pg_catalog.has_database_privilege(r.oid,d.oid,'TEMP')))
          AND NOT EXISTS (
          SELECT FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_namespace n
          WHERE r.rolname=ANY(%s) AND n.nspname !~ '^pg_(temp|toast_temp)_[0-9]+$'
            AND pg_catalog.has_schema_privilege(r.oid,n.oid,'CREATE'))
          AND NOT EXISTS (
          SELECT FROM pg_catalog.pg_db_role_setting s JOIN pg_catalog.pg_roles r ON r.oid=s.setrole
          WHERE r.rolname=ANY(%s))
          AND NOT EXISTS (
          SELECT FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_parameter_acl p
          WHERE r.rolname=ANY(%s) AND pg_catalog.has_parameter_privilege(r.oid,p.parname,'ALTER SYSTEM'))
          AND NOT EXISTS (
          SELECT FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_settings p
          WHERE r.rolname=ANY(%s) AND p.context IN ('superuser','superuser-backend')
            AND pg_catalog.has_parameter_privilege(r.oid,p.name,'SET'))
    """, tuple(list(SERVICES) for _ in range(6))).fetchone() == (True,), "restricted_role_authority_mismatch")


def public_acl(connection, *, temporary):
    # Expand NULL database ACLs using PostgreSQL defaults. Include every grantor,
    # grantee, grant option and owner so only the authorized entry may change.
    database = connection.execute("""
        SELECT d.oid, d.datdba, a.grantor, a.grantee, a.privilege_type, a.is_grantable
        FROM pg_catalog.pg_database d
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          coalesce(d.datacl,pg_catalog.acldefault('d',d.datdba))) a
        WHERE d.datname=current_database()
        ORDER BY a.grantor, a.grantee, a.privilege_type, a.is_grantable
    """).fetchall()
    schema = connection.execute("""
        SELECT n.oid, n.nspowner, a.grantor, a.grantee, a.privilege_type, a.is_grantable
        FROM pg_catalog.pg_namespace n
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          coalesce(n.nspacl,pg_catalog.acldefault('n',n.nspowner))) a
        WHERE n.nspname='public'
        ORDER BY a.grantor, a.grantee, a.privilege_type, a.is_grantable
    """).fetchall()
    require(database and schema, "database_or_public_schema_acl_missing")
    require({row[4] for row in database if row[3] == 0}
            == ({"CONNECT", "TEMPORARY"} if temporary else {"CONNECT"})
            and {row[4] for row in schema if row[3] == 0} == {"USAGE"},
            "public_acl_mismatch")
    return {"database": database, "public_schema": schema}


def revoke_public_temporary(psycopg, audit, document):
    administrator = None
    administrator_password = None
    try:
        require(audit.state["authorization"] == "owner_acknowledged"
                and audit.state["operation"] == "revoke_public_temporary", "owner_approval_required")
        require(not (AUDIT_ROOT / TEMPORARY_CLAIM_NAME).exists(), "prior_claim_refuses_retry")
        audit.record("administrator_prompt")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            administrator_password = getpass.getpass("Render provider administrator password: ")
        require(bool(administrator_password), "empty_administrator_password")
        administrator = connect(psycopg, document, ADMINISTRATOR, administrator_password)
        administrator_password = None
        audit.record("public_temporary_transaction")
        administrator.execute("BEGIN")
        identity(administrator, document)
        before = public_acl(administrator, temporary=True)
        expected = {"database": [row for row in before["database"]
                                 if not (row[3] == 0 and row[4] == "TEMPORARY")],
                    "public_schema": before["public_schema"]}
        audit.record("prior_state_verified", public_acl_before=before)
        save_json(AUDIT_ROOT / TEMPORARY_CLAIM_NAME, dict(execution_id=audit.execution_id,
                  database=DATABASE, operation="revoke_public_temporary",
                  status="owner_reconciliation_required_before_any_retry"))
        audit.record("public_temporary_revoke")
        administrator.execute(REVOKE_TEMPORARY)
        after = public_acl(administrator, temporary=False)
        require(after == expected, "unapproved_acl_or_owner_change")
        identity(administrator, document)
        require(metadata() == document and source_hashes() == audit.state["source_hashes"], "reviewed_inputs_changed")
        audit.record("public_acl_verified", public_acl_after=after)
        audit.record("commit", commit="outcome_uncertain")
        require(administrator.execute("COMMIT").statusmessage == "COMMIT", "commit_not_acknowledged")
        audit.record("commit_acknowledged", commit="acknowledged")
        administrator.execute("BEGIN READ ONLY")
        identity(administrator, document)
        require(public_acl(administrator, temporary=False) == expected, "postcommit_acl_mismatch")
        administrator.execute("ROLLBACK")
        audit.record("verified", verification="PASS")
    finally:
        administrator_password = None
        if administrator is not None:
            # Closing aborts any uncommitted transaction, as in provisioning.
            # Never retry COMMIT, undo a commit, remove a claim or repair ACLs.
            administrator.close()


def provision(psycopg, vault, audit, document):
    administrator = None
    administrator_password = verifier = command = None
    passwords = {}
    try:
        require(audit.state["authorization"] == "owner_acknowledged"
                and audit.state["operation"] == "provision_production_roles", "owner_approval_required")
        audit.record("credential_absence_preflight")
        targets_absent(vault)
        audit.record("administrator_prompt")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            administrator_password = getpass.getpass("Render provider administrator password: ")
        require(bool(administrator_password), "empty_administrator_password")
        administrator = connect(psycopg, document, ADMINISTRATOR, administrator_password)
        administrator_password = None
        audit.record("database_preflight")
        starting_state(administrator, document)
        # Render owns server monitoring/logging. Do not inspect or reconfigure
        # provider internals; retain local credential and verifier protections.
        targets_absent(vault)
        audit.record("prior_state_verified")
        save_json(AUDIT_ROOT / CLAIM_NAME, dict(execution_id=audit.execution_id,
                  database=DATABASE, roles=list(SERVICES), status="owner_reconciliation_required_before_any_retry"))
        audit.record("password_generation")
        passwords = {role: secrets.token_hex(32) for role in SERVICES}
        require(all(re.fullmatch(r"[0-9a-f]{64}", value) for value in passwords.values())
                and not secrets.compare_digest(*passwords.values()), "independent_password_generation_failed")
        targets_absent(vault)
        for role, service in SERVICES.items():
            audit.record("credential_write", credentials={**audit.state["credentials"], role: "outcome_uncertain"})
            vault._set_password(service, role, passwords[role])
            stored_password(vault, role, passwords[role])
            audit.record("credential_verified", credentials={**audit.state["credentials"], role: "verified_machine_local"})
        audit.record("role_transaction")
        administrator.execute("BEGIN")
        administrator.execute("SET LOCAL createrole_self_grant = ''")
        starting_state(administrator, document)
        for role in SERVICES:
            # PG17 retains the implicit bootstrap-superuser ADMIN edge, and
            # self-grants a separate creator-granted SET edge for the migrator.
            administrator.execute("SELECT pg_catalog.set_config('createrole_self_grant',%s,true)",
                                  ("set" if role == MIGRATOR else "",))
            verifier = administrator.pgconn.encrypt_password(passwords[role].encode("ascii"), role.encode("ascii"), b"scram-sha-256")
            require(type(verifier) is bytes and re.fullmatch(
                rb"SCRAM-SHA-256\$[1-9][0-9]*:[A-Za-z0-9+/]+=*\$[A-Za-z0-9+/]+=*:[A-Za-z0-9+/]+=*", verifier),
                "scram_verifier_api_result_invalid")
            command = psycopg.sql.SQL("CREATE ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                                      "NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT -1 PASSWORD {}").format(
                psycopg.sql.Identifier(role), psycopg.sql.Literal(verifier.decode("ascii")))
            audit.record("role_creation")
            administrator.execute(command)
            command = verifier = None
        restricted_roles(administrator)
        identity(administrator, document)
        require(metadata() == document and source_hashes() == audit.state["source_hashes"], "reviewed_inputs_changed")
        audit.record("commit", commit="outcome_uncertain")
        administrator.execute("COMMIT")
        audit.record("commit_acknowledged", commit="acknowledged")
        # Fresh read-only catalog transaction: no additional login probes or
        # schema bootstrap. 07 alone establishes database CONNECT/schema grants.
        administrator.execute("BEGIN READ ONLY")
        identity(administrator, document)
        restricted_roles(administrator)
        for role in SERVICES:
            stored_password(vault, role, passwords[role])
        administrator.execute("ROLLBACK")
        audit.record("verified", verification="PASS")
    finally:
        administrator_password = verifier = command = None
        passwords.clear()
        if administrator is not None:
            administrator.close()


def main():
    audit = None
    logging.disable(sys.maxsize)
    try:
        environment()
        correction = sys.argv[1:] == ["--revoke-public-temporary"]
        audit = Audit(public_temporary=correction)
        audit.record("prelaunch")
        claim_name = TEMPORARY_CLAIM_NAME if correction else CLAIM_NAME
        require(not (AUDIT_ROOT / claim_name).exists(), "prior_claim_refuses_retry")
        document = metadata()
        owner_approval(audit, document)
        psycopg, vault = legacy.installed_clients()
        if correction:
            revoke_public_temporary(psycopg, audit, document)
        else:
            provision(psycopg, vault, audit, document)
    except BaseException as error:
        # Only internal literal codes are printable. Never serialize a provider
        # exception, SQL command, verifier, credential, traceback or environment.
        code = str(error) if type(error) is Stop else "operation_failed_or_interrupted"
        saved = False
        if audit is not None:
            try:
                commit = audit.state["commit"]
                audit.record("stopped", failed_phase=audit.state["phase"], failure_code=code,
                             outcome=("uncertain" if commit == "outcome_uncertain" else
                                      "acknowledged_commit_requires_review" if commit == "acknowledged" else "rejected_before_commit"),
                             verification="STOP_REQUIRES_OWNER_REVIEW")
                saved = True
            except BaseException:
                pass
        print(f"STOP: code={code}; outcome_evidence_saved={saved}.")
        print("Preserve all evidence, credentials and claims. No retry or cleanup; owner reconciliation required.")
        return 1
    result = ("PUBLIC TEMPORARY correction acknowledged and ACL verified" if correction else
              "production role provisioning acknowledged and catalog/vault verified")
    print(f"PASS: {result}; execution_id={audit.execution_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
