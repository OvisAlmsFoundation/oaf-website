"""Deterministic artifact and PostgreSQL catalog checks for exact reviewed states.

No queries run at import. Extending the managed inventory requires a separately
reviewed validator and manifest; a version marker alone never proves correctness.
"""

import ast
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from sqlalchemy import text

from .migration_config import IDENTITIES, Failure, MigrationError
from .state_request_schema import STATE_REQUESTS, REQUEST_OBJECTS, REQUEST_GRANTS, REQUEST_EDGES
from .notification_schema import NOTIFICATIONS, NOTIFICATION_OBJECTS, NOTIFICATION_GRANTS, NOTIFICATION_EDGES
from .notification_delivery_schema import DELIVERY, TABLES as DELIVERY_TABLES, OBJECTS as DELIVERY_OBJECTS, GRANTS as DELIVERY_GRANTS, EDGES as DELIVERY_EDGES

from .confirmation_outbox_schema import OUTBOX, TABLES as OUTBOX_TABLES, OBJECTS as OUTBOX_OBJECTS, GRANTS as OUTBOX_GRANTS, EDGES as OUTBOX_EDGES
from .notification_management_schema import MANAGEMENT, TABLES as MANAGEMENT_TABLES, ADDED_OBJECTS as MANAGEMENT_OBJECTS, GRANTS as MANAGEMENT_GRANTS, EDGES as MANAGEMENT_EDGES

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "0001_migration_baseline"
BASE = "base"
FRAMEWORK_FILES = frozenset({
    "requirements-migrations.txt", "alembic.ini", "migrations/env.py",
    "migrations/script.py.mako", "oaf_website/migration_config.py",
    "oaf_website/migrate.py", "oaf_website/migration_validation.py",
    "oaf_website/database_config.py", "oaf_website/__init__.py",
    "oaf_website/migration_authority.py",
    "requirements.txt", "oaf_website/confirmation_outbox_schema.py",
    "oaf_website/state_request_schema.py", "oaf_website/state_request_validation.py",
    "oaf_website/notification_schema.py", "oaf_website/notification_validation.py",
    "oaf_website/notification_delivery_schema.py", "oaf_website/notification_delivery_validation.py",
    "oaf_website/notification_dispatch.py",
    "oaf_website/notification_management_schema.py",
})
REVISION_FILE = f"migrations/versions/{BASELINE}.py"
REQUEST_REVISION_FILE = f"migrations/versions/{STATE_REQUESTS}.py"
NOTIFICATION_REVISION_FILE = f"migrations/versions/{NOTIFICATIONS}.py"
DELIVERY_REVISION_FILE = f"migrations/versions/{DELIVERY}.py"
OUTBOX_REVISION_FILE = f"migrations/versions/{OUTBOX}.py"
MANAGEMENT_REVISION_FILE = f"migrations/versions/{MANAGEMENT}.py"
REVISION_FILES = frozenset({REVISION_FILE, REQUEST_REVISION_FILE, NOTIFICATION_REVISION_FILE, DELIVERY_REVISION_FILE, OUTBOX_REVISION_FILE, MANAGEMENT_REVISION_FILE})
HASH_MODE = "sha256-utf8-lf"
STATE_CONTRACT = {
    "base": {"revision": None, "managed_objects": []},
    BASELINE: {
        "revision": BASELINE,
        "managed_objects": [
            {"kind": "table", "name": "alembic_version"},
            {"kind": "index", "name": "alembic_version_pkc"},
            {"kind": "row_type", "name": "alembic_version"},
            {"kind": "array_type", "name": "_alembic_version"},
            {"kind": "primary_key", "name": "alembic_version_pkc"},
        ],
    },
}
STATE_CONTRACT[STATE_REQUESTS] = {
    "revision": STATE_REQUESTS,
    "managed_objects": STATE_CONTRACT[BASELINE]["managed_objects"] + REQUEST_OBJECTS,
}
STATE_CONTRACT[NOTIFICATIONS] = {
    "revision": NOTIFICATIONS,
    "managed_objects": STATE_CONTRACT[STATE_REQUESTS]["managed_objects"] + NOTIFICATION_OBJECTS,
}
STATE_CONTRACT[DELIVERY] = {"revision": DELIVERY, "managed_objects": STATE_CONTRACT[NOTIFICATIONS]["managed_objects"] + DELIVERY_OBJECTS}
STATE_CONTRACT[OUTBOX] = {"revision": OUTBOX, "managed_objects": STATE_CONTRACT[DELIVERY]["managed_objects"] + OUTBOX_OBJECTS}
STATE_CONTRACT[MANAGEMENT] = {"revision": MANAGEMENT, "managed_objects": STATE_CONTRACT[OUTBOX]["managed_objects"] + MANAGEMENT_OBJECTS}
SECURITY_CONTRACT = {
    "schema": "oaf_website",
    "owners": {name: i.owner for name, i in IDENTITIES.items()},
    "schema_runtime_privileges": ["USAGE"],
    "runtime_object_grants": [],
    "public_privileges": {
        "schema": [], "tables_and_columns": [], "ordinary_types": [],
        "generated_types": "exact_generated_type_exception",
    },
    "default_privileges": "owner_only_tables_sequences_routines_types",
    "generated_type_exception": {
        "objects": ["oaf_website.alembic_version", "oaf_website._alembic_version"],
        "relationships": ["row_type_internal_to_version_table", "array_type_internal_to_row_type"],
        "acl": "null_with_owner_and_public_usage_no_nonowner_grant_options",
        "data_access": "no_public_or_runtime_metadata_privileges",
        "ordinary_types": "no_public_usage_and_restrictive_owner_defaults",
    },
    "dependencies": {
        "baseline_edges": [
            ["table", 0, "schema", 0, "n"],
            ["row_type", 0, "table", 0, "i"],
            ["array_type", 0, "row_type", 0, "i"],
            ["primary_key", 0, "table", 1, "a"],
            ["index", 0, "primary_key", 0, "i"],
        ],
        "schema_defaults": "matching_owner_r_S_f_T_auto_dependency_on_application_schema",
        "global_defaults": "matching_owner_r_S_f_T_n_without_local_dependencies",
        "builtin_dependencies": "pinned_objects_omitted_by_postgresql_17",
        "other_inbound_outbound_edges": "prohibited_including_extension_membership",
    },
    "version_table": "oaf_website.alembic_version",
    "postconditions": [
        "exact_catalog_inventory", "matching_object_owners",
        "exact_version_table_definition", "one_exact_revision_row",
        "no_runtime_metadata_privileges", "no_public_data_or_schema_exposure",
        "exact_generated_type_usage_exception", "exact_dependency_relationships",
        "no_nonowner_grant_options", "restrictive_global_and_schema_defaults",
    ],
}
SECURITY_CONTRACT["runtime_object_grants"] = REQUEST_GRANTS + NOTIFICATION_GRANTS + DELIVERY_GRANTS + OUTBOX_GRANTS
SECURITY_CONTRACT["state_request_types"] = "private_row_type_array_uses_element_acl_no_public_or_runtime_usage"
SECURITY_CONTRACT["dependencies"]["state_request_edges"] = REQUEST_EDGES
SECURITY_CONTRACT["postconditions"] += ["exact_state_request_definition", "exact_state_request_runtime_grants"]
SECURITY_CONTRACT["notification_types"] = "private_row_type_array_uses_element_acl_no_public_or_runtime_usage"
SECURITY_CONTRACT["dependencies"]["notification_edges"] = NOTIFICATION_EDGES
SECURITY_CONTRACT["postconditions"] += ["exact_notification_definition", "exact_notification_runtime_grants"]
SECURITY_CONTRACT["dependencies"]["notification_delivery_edges"] = DELIVERY_EDGES
SECURITY_CONTRACT["postconditions"] += ["exact_notification_delivery_definition", "exact_notification_delivery_runtime_grants"]

SECURITY_CONTRACT["dependencies"]["confirmation_outbox_edges"] = OUTBOX_EDGES
SECURITY_CONTRACT["postconditions"] += ["exact_confirmation_outbox_definition", "exact_confirmation_outbox_runtime_grants"]
SECURITY_CONTRACT["runtime_object_grants"] += MANAGEMENT_GRANTS
SECURITY_CONTRACT["dependencies"]["notification_management_edges"] = MANAGEMENT_EDGES
SECURITY_CONTRACT["postconditions"] += ["exact_notification_management_definition", "exact_notification_management_runtime_grants"]


def digest(data: bytes) -> str:
    """Hash UTF-8 text with Git checkout CRLF normalized to LF; no BOM/lone CR."""
    value = data.decode("utf-8").replace("\r\n", "\n")
    if "\r" in value or value.startswith("\ufeff"):
        raise MigrationError(Failure.ARTIFACT_HASH)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MigrationError(Failure.ARTIFACT_HASH)
        result[key] = value
    return result


@dataclass(frozen=True)
class VerifiedArtifacts:
    manifest_hash: str
    revision_hash: str
    expected_start: str
    target: str


@dataclass(frozen=True)
class _RunnerContext:
    """Runner-local lifecycle binding, not a credential-holder security sandbox."""
    connection: object
    identity: object
    artifacts: VerifiedArtifacts
    transaction: object
    evidence: object
    sink: object
    authority: object
    session_lock_backend: int


_ACTIVE_RUNNERS = {}


@contextmanager
def _runner_execution(connection, identity, artifacts, transaction, evidence,
                      sink, authority, session_lock_backend):
    """Private runner composition seam; no public context constructor/flag.

    All Python code in this process is trusted. Modifying private state or using
    valid PostgreSQL credentials for arbitrary SQL is outside this boundary.
    The live runner's closed operational gate precedes issuance.
    """
    runner = _RunnerContext(connection, identity, artifacts, transaction,
                            evidence, sink, authority, session_lock_backend)
    _ACTIVE_RUNNERS[id(runner)] = (runner, False)
    try:
        yield runner
    finally:
        _ACTIVE_RUNNERS.pop(id(runner), None)


def consume_runner_context(runner):
    entry = _ACTIVE_RUNNERS.get(id(runner))
    if (type(runner) is not _RunnerContext or entry is None
            or entry[0] is not runner or entry[1]):
        raise MigrationError(Failure.OPERATIONAL_GATE)
    e, a = runner.evidence, runner.artifacts
    if (runner.authority is None or runner.sink is None
            or runner.authority is not e.operational_authority
            or runner.sink is not e.audit_sink
            or runner.connection is not e.verified_connection
            or runner.transaction is not e.verified_transaction
            or runner.session_lock_backend != e.session_lock_backend
            or not e.authorized or not e.audit_acknowledged
            or not e.verified or not e.session_lock_verified
            or e.phase != "revision" or e.validation != "preflight_passed"
            or e.commit != "not_invoked" or e.request.action != "upgrade"
            or e.request.environment != runner.identity.environment
            or e.observed_start != a.expected_start
            or (e.request.expected_start, e.request.target,
                e.request.manifest_hash, e.request.revision_hash) !=
               (a.expected_start, a.target, a.manifest_hash, a.revision_hash)
            or e.identity != runner.identity):
        raise MigrationError(Failure.OPERATIONAL_GATE)
    _ACTIVE_RUNNERS[id(runner)] = (runner, True)
    return runner


def verify_session_lock(connection, backend, lock_id):
    """Catalog identity plus runner proof of survival across setup rollback.

    pg_locks does not expose session vs transaction lock ownership. A catalog
    row alone is insufficient; backend is recorded only after the runner's
    session acquisition survives the end of its setup transaction.
    """
    if type(backend) is not int or scalar(connection, "SELECT pg_catalog.pg_backend_pid()") != backend:
        raise MigrationError(Failure.LOCK_BUSY)
    if not scalar(connection, """
        SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_locks
            WHERE locktype='advisory' AND pid=:backend
              AND database=(SELECT oid FROM pg_catalog.pg_database
                            WHERE datname=pg_catalog.current_database())
              AND classid=:namespace AND objid=:resource AND objsubid=2
              AND mode='ExclusiveLock' AND granted)
    """, backend=backend, namespace=lock_id[0], resource=lock_id[1]):
        raise MigrationError(Failure.LOCK_BUSY)


def validate_artifacts(
    *, expected_start: str, target: str, manifest_hash: str,
    revision_hash: str,
) -> VerifiedArtifacts:
    """Never import revision code. Digests must come from independent review.

    Hash matching is integrity, not run authorization. The runner's separate
    authority adapter must attest approval of this exact manifest for live use.
    """
    try:
        return _validate_artifacts(expected_start, target, manifest_hash, revision_hash)
    except MigrationError:
        raise
    except Exception:
        raise MigrationError(Failure.ARTIFACT_HASH) from None


def _validate_artifacts(start, target, manifest_hash, revision_hash):
    if (start, target) not in {(BASE, BASELINE), (BASELINE, BASELINE),
                               (BASELINE, STATE_REQUESTS), (STATE_REQUESTS, STATE_REQUESTS),
                               (STATE_REQUESTS, NOTIFICATIONS), (NOTIFICATIONS, NOTIFICATIONS),
                               (NOTIFICATIONS, DELIVERY), (DELIVERY, DELIVERY),
                               (DELIVERY, OUTBOX), (OUTBOX, OUTBOX),
                               (OUTBOX, MANAGEMENT), (MANAGEMENT, MANAGEMENT)}:
        raise MigrationError(Failure.STARTING_REVISION)
    if any(not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h)
           for h in (manifest_hash, revision_hash)):
        raise MigrationError(Failure.ARTIFACT_HASH)
    payload = (ROOT / "migrations/manifest.json").read_bytes()
    if digest(payload) != manifest_hash:
        raise MigrationError(Failure.ARTIFACT_HASH)
    document = json.loads(payload, object_pairs_hook=_unique_object)
    if set(document) != {"format", "hash_mode", "approval_status", "framework",
                         "revisions", "states", "security"}:
        raise MigrationError(Failure.ARTIFACT_HASH)
    if (type(document["format"]) is not int or document["format"] != 1
            or document["hash_mode"] != HASH_MODE
            or document["approval_status"] != "pending_independent_review"
            or document["states"] != STATE_CONTRACT
            or document["security"] != SECURITY_CONTRACT):
        raise MigrationError(Failure.ARTIFACT_HASH)
    framework = document["framework"]
    if set(framework) != FRAMEWORK_FILES:
        raise MigrationError(Failure.ARTIFACT_HASH)
    revisions = document["revisions"]
    if not isinstance(revisions, list) or len(revisions) != 6:
        raise MigrationError(Failure.ARTIFACT_HASH)
    if revisions[0] != {
        "id": BASELINE, "parent": None, "file": REVISION_FILE,
        "sha256": revisions[0].get("sha256"), "starting_state": BASE,
        "target_state": BASELINE, "grants": [],
    } or revisions[1] != {
        "id": STATE_REQUESTS, "parent": BASELINE, "file": REQUEST_REVISION_FILE,
        "sha256": revisions[1].get("sha256"), "starting_state": BASELINE,
        "target_state": STATE_REQUESTS, "grants": REQUEST_GRANTS,
    } or revisions[2] != {
        "id": NOTIFICATIONS, "parent": STATE_REQUESTS, "file": NOTIFICATION_REVISION_FILE,
        "sha256": revisions[2].get("sha256"), "starting_state": STATE_REQUESTS,
        "target_state": NOTIFICATIONS, "grants": NOTIFICATION_GRANTS,
    } or revisions[3] != {
        "id": DELIVERY, "parent": NOTIFICATIONS, "file": DELIVERY_REVISION_FILE,
        "sha256": revisions[3].get("sha256"), "starting_state": NOTIFICATIONS,
        "target_state": DELIVERY, "grants": DELIVERY_GRANTS,
    } or revisions[4] != {
        "id": OUTBOX, "parent": DELIVERY, "file": OUTBOX_REVISION_FILE,
        "sha256": revisions[4].get("sha256"), "starting_state": DELIVERY,
        "target_state": OUTBOX, "grants": OUTBOX_GRANTS,
    } or revisions[5] != {
        "id": MANAGEMENT, "parent": OUTBOX, "file": MANAGEMENT_REVISION_FILE,
        "sha256": revisions[5].get("sha256"), "starting_state": OUTBOX,
        "target_state": MANAGEMENT, "grants": MANAGEMENT_GRANTS,
    } or revision_hash != next(r["sha256"] for r in revisions if r["id"] == target):
        raise MigrationError(Failure.ARTIFACT_HASH)
    # Explicit single linear root, no missing ancestors/branches/second heads.
    migration_files = {
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "migrations").rglob("*") if p.is_file()
    }
    if migration_files != {
        "migrations/env.py", "migrations/script.py.mako",
        "migrations/manifest.json", *REVISION_FILES,
    }:
        raise MigrationError(Failure.ARTIFACT_HASH)
    for name, expected in {**framework, **{r["file"]: r["sha256"] for r in revisions}}.items():
        path = ROOT / name
        if path.is_symlink() or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise MigrationError(Failure.ARTIFACT_HASH)
        if digest(path.read_bytes()) != expected:
            raise MigrationError(Failure.ARTIFACT_HASH)
    tree = ast.parse((ROOT / REVISION_FILE).read_text(encoding="utf-8"))
    assignments = {}
    functions = {}
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            if key in assignments:
                raise MigrationError(Failure.ARTIFACT_HASH)
            assignments[key] = ast.literal_eval(node.value)
        elif isinstance(node, ast.FunctionDef) and node.name not in functions:
            functions[node.name] = node
        else:
            raise MigrationError(Failure.ARTIFACT_HASH)
    if assignments != {"revision": BASELINE, "down_revision": None,
                       "branch_labels": None, "depends_on": None} or set(functions) != {"upgrade", "downgrade"}:
        raise MigrationError(Failure.ARTIFACT_HASH)
    upgrade = functions["upgrade"]
    for function in functions.values():
        if (function.decorator_list or function.returns or function.args.args
                or function.args.posonlyargs or function.args.defaults
                or function.args.kwonlyargs or function.args.kw_defaults
                or function.args.vararg or function.args.kwarg):
            raise MigrationError(Failure.ARTIFACT_HASH)
    if (upgrade.decorator_list or upgrade.args.args or upgrade.args.defaults
            or upgrade.args.kwonlyargs or upgrade.args.vararg or upgrade.args.kwarg
            or len(upgrade.body) != 1 or not isinstance(upgrade.body[0], ast.Pass)):
        raise MigrationError(Failure.ARTIFACT_HASH)
    downgrade = functions["downgrade"]
    if (len(downgrade.body) != 1 or not isinstance(downgrade.body[0], ast.Raise)
            or ast.dump(downgrade.body[0]) != ast.dump(ast.parse(
                'raise RuntimeError("Ordinary migration downgrade is prohibited.")'
            ).body[0])):
        raise MigrationError(Failure.ARTIFACT_HASH)
    # Exact AST keeps revision 0002 declarative, without imports/commits/DDL
    # outside its one hashed schema helper. Never import revision code here.
    expected_request_revision = '''
from alembic import op
from oaf_website.state_request_schema import upgrade_state_requests
revision = "0002_state_requests"
down_revision = "0001_migration_baseline"
branch_labels = None
depends_on = None
def upgrade():
    upgrade_state_requests(op.get_bind())
def downgrade():
    raise RuntimeError("Ordinary migration downgrade is prohibited.")
'''
    request_tree = ast.parse((ROOT / REQUEST_REVISION_FILE).read_text(encoding="utf-8"))
    if (request_tree.body and isinstance(request_tree.body[0], ast.Expr)
            and isinstance(request_tree.body[0].value, ast.Constant)
            and isinstance(request_tree.body[0].value.value, str)):
        request_tree.body.pop(0)
    if ast.dump(request_tree) != ast.dump(ast.parse(expected_request_revision)):
        raise MigrationError(Failure.ARTIFACT_HASH)
    expected_notification_revision = expected_request_revision.replace(
        "state_request_schema", "notification_schema").replace(
        "upgrade_state_requests", "upgrade_notifications").replace(
        'revision = "0002_state_requests"', 'revision = "0003_notifications"').replace(
        'down_revision = "0001_migration_baseline"', 'down_revision = "0002_state_requests"')
    notification_tree = ast.parse((ROOT / NOTIFICATION_REVISION_FILE).read_text(encoding="utf-8"))
    if (notification_tree.body and isinstance(notification_tree.body[0], ast.Expr)
            and isinstance(notification_tree.body[0].value, ast.Constant)
            and isinstance(notification_tree.body[0].value.value, str)):
        notification_tree.body.pop(0)
    if ast.dump(notification_tree) != ast.dump(ast.parse(expected_notification_revision)):
        raise MigrationError(Failure.ARTIFACT_HASH)
    expected_delivery_revision = expected_notification_revision.replace(
        "notification_schema", "notification_delivery_schema").replace(
        "upgrade_notifications", "upgrade_notification_delivery").replace(
        'revision = "0003_notifications"', 'revision = "0004_notification_delivery"').replace(
        'down_revision = "0002_state_requests"', 'down_revision = "0003_notifications"')
    delivery_tree = ast.parse((ROOT / DELIVERY_REVISION_FILE).read_text(encoding="utf-8"))
    if (delivery_tree.body and isinstance(delivery_tree.body[0], ast.Expr)
            and isinstance(delivery_tree.body[0].value, ast.Constant)
            and isinstance(delivery_tree.body[0].value.value, str)):
        delivery_tree.body.pop(0)
    if ast.dump(delivery_tree) != ast.dump(ast.parse(expected_delivery_revision)):
        raise MigrationError(Failure.ARTIFACT_HASH)
    expected_outbox_revision = expected_delivery_revision.replace(
        "notification_delivery_schema", "confirmation_outbox_schema").replace(
        "upgrade_notification_delivery", "upgrade_confirmation_outbox").replace(
        'revision = "0004_notification_delivery"', 'revision = "0005_confirmation_outbox"').replace(
        'down_revision = "0003_notifications"', 'down_revision = "0004_notification_delivery"')
    outbox_tree = ast.parse((ROOT / OUTBOX_REVISION_FILE).read_text(encoding="utf-8"))
    if (outbox_tree.body and isinstance(outbox_tree.body[0], ast.Expr)
            and isinstance(outbox_tree.body[0].value, ast.Constant)
            and isinstance(outbox_tree.body[0].value.value, str)):
        outbox_tree.body.pop(0)
    if ast.dump(outbox_tree) != ast.dump(ast.parse(expected_outbox_revision)):
        raise MigrationError(Failure.ARTIFACT_HASH)
    expected_management_revision = expected_outbox_revision.replace(
        "confirmation_outbox_schema", "notification_management_schema").replace(
        "upgrade_confirmation_outbox", "upgrade_notification_management").replace(
        'revision = "0005_confirmation_outbox"', 'revision = "0006_notification_management"').replace(
        'down_revision = "0004_notification_delivery"', 'down_revision = "0005_confirmation_outbox"')
    management_tree = ast.parse((ROOT / MANAGEMENT_REVISION_FILE).read_text(encoding="utf-8"))
    if (management_tree.body and isinstance(management_tree.body[0], ast.Expr)
            and isinstance(management_tree.body[0].value, ast.Constant)
            and isinstance(management_tree.body[0].value.value, str)):
        management_tree.body.pop(0)
    if ast.dump(management_tree) != ast.dump(ast.parse(expected_management_revision)):
        raise MigrationError(Failure.ARTIFACT_HASH)
    return VerifiedArtifacts(manifest_hash, revision_hash, start, target)


def rows(connection, sql, **parameters):
    return [dict(r) for r in connection.execute(text(sql), parameters).mappings()]


def scalar(connection, sql, **parameters):
    return connection.execute(text(sql), parameters).scalar_one()


def verify_identity(connection, identity, *, assumed=False):
    found = rows(connection, """
        SELECT pg_catalog.current_database() AS database,
               session_user AS authenticated, current_user AS effective,
               pg_catalog.host(pg_catalog.inet_server_addr()) AS host,
               pg_catalog.inet_server_port() AS port,
               pg_catalog.current_setting('server_version_num')::int / 10000 AS major
    """)[0]
    if found != {
        "database": identity.database, "authenticated": identity.migrator,
        "effective": identity.owner if assumed else identity.migrator,
        "host": identity.host, "port": identity.port, "major": identity.postgres_major,
    }:
        raise MigrationError(Failure.WRONG_IDENTITY)


def verify_authority(connection, identity):
    """All six ordinary identities; exceptional administrators stay separate.

    Incoming exceptional paths must already possess superuser authority or the
    ability to SET the preserved shared database owner. CREATEDB/CREATEROLE alone
    does not qualify. Authorizing/provisioning administrators is never done here.
    """
    if identity != IDENTITIES.get(identity.environment):
        raise MigrationError(Failure.WRONG_IDENTITY)
    registered = {name for i in IDENTITIES.values()
                  for name in (i.runtime, i.migrator, i.owner)}
    owners = {i.owner for i in IDENTITIES.values()}
    allowed = {(i.migrator, i.owner, False, True, False) for i in IDENTITIES.values()}
    roles = rows(connection, """
        SELECT oid, rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication,
               rolbypassrls, rolinherit, rolcanlogin,
               (rolsuper OR pg_catalog.pg_has_role(oid, 'oaf_website_owner', 'SET'))
                   AS exceptional
        FROM pg_catalog.pg_roles ORDER BY rolname
    """)
    rolemap = {r["rolname"]: r for r in roles}
    if not registered.issubset(rolemap):
        raise MigrationError(Failure.UNAUTHORIZED_MEMBERSHIP)
    for name in sorted(registered):
        role = rolemap[name]
        if (any(role[k] for k in ("rolsuper", "rolcreatedb", "rolcreaterole",
                                  "rolreplication", "rolbypassrls", "exceptional"))
                or role["rolcanlogin"] != (name not in owners)
                or (name in owners or name.endswith("_migrator")) and role["rolinherit"]):
            raise MigrationError(Failure.UNAUTHORIZED_MEMBERSHIP)
    memberships = rows(connection, """
        SELECT member.rolname AS member, parent.rolname AS parent,
               m.inherit_option, m.set_option, m.admin_option
        FROM pg_catalog.pg_auth_members m
        JOIN pg_catalog.pg_roles member ON member.oid=m.member
        JOIN pg_catalog.pg_roles parent ON parent.oid=m.roleid
        ORDER BY member.rolname, parent.rolname, m.grantor
    """)
    edges = [(m["member"], m["parent"], m["inherit_option"],
              m["set_option"], m["admin_option"]) for m in memberships]
    # Outbound traversal rejects every unapproved parent, independent of edge
    # options. This includes indirect shared-owner and cross-environment paths.
    outbound = set()
    for root in sorted(registered):
        pending, visited = [root], set()
        while pending:
            role = pending.pop()
            if role in visited:
                continue
            visited.add(role)
            for edge in edges:
                if edge[0] == role:
                    if edge not in allowed:
                        raise MigrationError(Failure.UNAUTHORIZED_MEMBERSHIP)
                    outbound.add(edge)
                    pending.append(edge[1])
    if outbound != allowed or any(edges.count(edge) != 1 for edge in allowed):
        raise MigrationError(Failure.UNAUTHORIZED_MEMBERSHIP)
    # Incoming traversal covers all ancestors, even a testing member entering a
    # development owner or an ordinary external member entering through another
    # ordinary role. Only the preserved exceptional administration boundary is
    # exempt; it is not migration authority and has no runner execution path.
    for root in sorted(registered):
        pending, visited = [root], set()
        while pending:
            role = pending.pop()
            if role in visited:
                continue
            visited.add(role)
            for edge in edges:
                if edge[1] == role:
                    if edge not in allowed and (edge[0] in registered
                                                 or not rolemap[edge[0]]["exceptional"]):
                        raise MigrationError(Failure.UNAUTHORIZED_MEMBERSHIP)
                    pending.append(edge[0])
    for i in IDENTITIES.values():
        for name in (i.runtime, i.migrator, i.owner):
            for db in (j.database for j in IDENTITIES.values()):
                # Runtime and migrator CONNECT only to their own database;
                # NOLOGIN schema owners need no database privilege grant.
                expected_connect = db == i.database and name != i.owner
                if bool(scalar(connection,
                        "SELECT pg_catalog.has_database_privilege(:name, :db, 'CONNECT')",
                        name=name, db=db)) != expected_connect:
                    raise MigrationError(Failure.UNAUTHORIZED_MEMBERSHIP)
                for privilege in ("CREATE", "TEMPORARY", "CONNECT WITH GRANT OPTION",
                                  "CREATE WITH GRANT OPTION", "TEMPORARY WITH GRANT OPTION"):
                    if scalar(connection,
                            "SELECT pg_catalog.has_database_privilege(:name, :db, :privilege)",
                            name=name, db=db, privilege=privilege):
                        raise MigrationError(Failure.UNAUTHORIZED_MEMBERSHIP)
            # Scan permanent schemas, including pg_catalog/information_schema and
            # non-public extension/user schemas. Temp namespaces are not managed.
            if scalar(connection, """
                SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace n
                    WHERE n.nspname !~ '^pg_(temp|toast_temp)_[0-9]+$'
                      AND pg_catalog.has_schema_privilege(:name, n.oid, 'CREATE')
                      AND NOT (n.nspname='oaf_website' AND :name=:owner))
            """, name=name, owner=identity.owner):
                raise MigrationError(Failure.UNAUTHORIZED_MEMBERSHIP)
    if scalar(connection, """
        SELECT pg_catalog.pg_get_userbyid(datdba) <> 'oaf_website_owner'
        FROM pg_catalog.pg_database WHERE datname=:db
    """, db=identity.database):
        raise MigrationError(Failure.UNAUTHORIZED_MEMBERSHIP)
    # pg_shdepend is the general ownership inventory, covering collations,
    # operators, extensions, languages, large objects, foreign servers/wrappers,
    # event triggers, publications/subscriptions, statistics and future catalogs.
    # Only selected-owner schema, baseline objects and restrictive defaults may
    # have ownership dependencies here. No six-role shared-object ownership.
    for i in IDENTITIES.values():
        for name in (i.runtime, i.migrator, i.owner):
            if scalar(connection, """
                SELECT EXISTS (
                    SELECT 1 FROM pg_catalog.pg_shdepend d
                    JOIN pg_catalog.pg_roles r ON r.oid=d.refobjid
                    WHERE d.refclassid='pg_catalog.pg_authid'::pg_catalog.regclass
                      AND d.deptype='o' AND r.rolname=:name
                      AND (d.dbid=0 OR
                        (d.dbid=(SELECT oid FROM pg_catalog.pg_database WHERE datname=:db)
                         AND NOT (:name=:owner AND (
                          (d.classid='pg_catalog.pg_namespace'::pg_catalog.regclass AND
                           d.objid=(SELECT oid FROM pg_catalog.pg_namespace WHERE nspname='oaf_website'))
                          OR (d.classid='pg_catalog.pg_class'::pg_catalog.regclass AND
                           d.objid IN (SELECT c.oid FROM pg_catalog.pg_class c
                              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                              WHERE n.nspname='oaf_website'))
                          OR (d.classid='pg_catalog.pg_type'::pg_catalog.regclass AND
                           d.objid IN (SELECT t.oid FROM pg_catalog.pg_type t
                              JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace
                              WHERE n.nspname='oaf_website'))
                          OR (d.classid='pg_catalog.pg_default_acl'::pg_catalog.regclass AND
                           d.objid IN (SELECT a.oid FROM pg_catalog.pg_default_acl a
                              WHERE a.defaclrole=r.oid AND (a.defaclnamespace=0 OR
                                a.defaclnamespace=(SELECT oid FROM pg_catalog.pg_namespace
                                                   WHERE nspname='oaf_website'))))
                         ))))
                )
            """, name=name, owner=identity.owner, db=identity.database):
                raise MigrationError(Failure.UNAUTHORIZED_MEMBERSHIP)
            # Cluster catalogs also reveal unexpected ownership outside the
            # role's registered database without opening another connection.
            if scalar(connection, """
                SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_shdepend d
                    JOIN pg_catalog.pg_roles r ON r.oid=d.refobjid
                    WHERE d.refclassid='pg_catalog.pg_authid'::pg_catalog.regclass
                      AND d.deptype='o' AND r.rolname=:name AND d.dbid<>0
                      AND d.dbid<>(SELECT oid FROM pg_catalog.pg_database WHERE datname=:db))
            """, name=name, db=i.database):
                raise MigrationError(Failure.UNAUTHORIZED_MEMBERSHIP)


def verify_schema(connection, identity):
    found = rows(connection, """
        SELECT pg_catalog.pg_get_userbyid(nspowner) AS owner
        FROM pg_catalog.pg_namespace WHERE nspname='oaf_website'
    """)
    if found != [{"owner": identity.owner}]:
        raise MigrationError(Failure.SCHEMA_OWNERSHIP)
    acl = rows(connection, """
        SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(a.grantee) END AS grantee,
               pg_catalog.pg_get_userbyid(a.grantor) AS grantor, a.privilege_type AS privilege,
               a.is_grantable AS grantable
        FROM pg_catalog.pg_namespace n CROSS JOIN LATERAL
             pg_catalog.aclexplode(COALESCE(n.nspacl, pg_catalog.acldefault('n', n.nspowner))) a
        WHERE n.nspname='oaf_website'
    """)
    actual = {(a["grantee"], a["grantor"], a["privilege"], a["grantable"]) for a in acl}
    expected = {(identity.owner, identity.owner, p, False) for p in ("USAGE", "CREATE")}
    expected.add((identity.runtime, identity.owner, "USAGE", False))
    if actual != expected:
        raise MigrationError(Failure.DRIFT)
    for name in (identity.runtime, identity.migrator):
        if scalar(connection, "SELECT pg_catalog.has_schema_privilege(:name, 'oaf_website', 'CREATE')", name=name):
            raise MigrationError(Failure.DRIFT)
    if not scalar(connection, "SELECT pg_catalog.has_schema_privilege(:name, 'oaf_website', 'USAGE')", name=identity.runtime):
        raise MigrationError(Failure.DRIFT)


def verify_defaults(connection, identity):
    """Check global built-in defaults AND every schema-specific additive default."""
    defaults = rows(connection, """
        SELECT d.defaclobjtype AS kind, d.defaclnamespace AS namespace,
               n.nspname AS schema,
               d.defaclacl AS acl
        FROM pg_catalog.pg_default_acl d JOIN pg_catalog.pg_roles r ON r.oid=d.defaclrole
        LEFT JOIN pg_catalog.pg_namespace n ON n.oid=d.defaclnamespace
        WHERE r.rolname=:owner
    """, owner=identity.owner)
    # Global routine/type revocations must exist. Absence retains PUBLIC defaults.
    global_kinds = {d["kind"] for d in defaults if d["namespace"] == 0}
    if not {"f", "T"}.issubset(global_kinds):
        raise MigrationError(Failure.DRIFT)
    if any(d["kind"] not in {"r", "S", "f", "T", "n"} for d in defaults):
        raise MigrationError(Failure.DRIFT)
    if any(d["namespace"] != 0 and (d["schema"] != "oaf_website" or d["kind"] == "n")
           for d in defaults):
        raise MigrationError(Failure.DRIFT)
    if scalar(connection, """
        SELECT EXISTS (
            SELECT 1 FROM pg_catalog.pg_default_acl d
            JOIN pg_catalog.pg_roles r ON r.oid=d.defaclrole
            CROSS JOIN LATERAL pg_catalog.aclexplode(d.defaclacl) a
            WHERE r.rolname=:owner AND
              (a.grantee <> d.defaclrole OR a.grantor <> d.defaclrole OR a.is_grantable)
        )
    """, owner=identity.owner):
        raise MigrationError(Failure.DRIFT)


def catalog_state(connection, identity) -> str:
    """Exact baseline inventory, definition, ACL and marker validation under lock."""
    verify_schema(connection, identity)
    verify_defaults(connection, identity)
    relations = rows(connection, """
        SELECT c.relname AS name, c.relkind AS kind,
               pg_catalog.pg_get_userbyid(c.relowner) AS owner,
               c.relpersistence AS persistence, c.relrowsecurity AS rls,
               c.relforcerowsecurity AS force_rls, c.relhasrules AS rules,
               c.relhastriggers AS triggers, c.reloptions AS options
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='oaf_website' ORDER BY c.relname
    """)
    state = (BASE if not relations else MANAGEMENT
             if any(r["name"] == "notification_preference_changes" for r in relations) else OUTBOX
             if any(r["name"] == "notification_confirmation_intents" for r in relations) else DELIVERY
             if any(r["name"] == "notification_release_events" for r in relations) else NOTIFICATIONS
             if any(r["name"] == "notifications" for r in relations) else STATE_REQUESTS
             if any(r["name"] == "state_requests" for r in relations) else BASELINE)
    names = [(r["name"], r["kind"]) for r in relations]
    expected_relations = [] if state == BASE else [("alembic_version", "r"), ("alembic_version_pkc", "i")]
    if state in {STATE_REQUESTS, NOTIFICATIONS, DELIVERY, OUTBOX, MANAGEMENT}:
        expected_relations += [("state_requests", "r"), ("state_requests_pk", "i")]
    if state in {NOTIFICATIONS, DELIVERY, OUTBOX, MANAGEMENT}:
        expected_relations += [("notifications", "r"), ("notifications_pk", "i"), ("notifications_active_email", "i")]
    if state in {DELIVERY, OUTBOX, MANAGEMENT}:
        expected_relations += [(o["name"], "r" if o["kind"] == "table" else "i")
                               for o in DELIVERY_OBJECTS if o["kind"] in {"table", "index"}]
    if state in {OUTBOX, MANAGEMENT}:
        expected_relations += [(o["name"], "r" if o["kind"] == "table" else "i")
                               for o in OUTBOX_OBJECTS if o["kind"] in {"table", "index"}]
    if state == MANAGEMENT:
        expected_relations += [(o["name"], "r" if o["kind"] == "table" else "i")
                               for o in MANAGEMENT_OBJECTS if o["kind"] in {"table", "index"}]
    if names != sorted(expected_relations):
        raise MigrationError(Failure.DRIFT)
    trigger_tables = set()
    if state in {DELIVERY, OUTBOX, MANAGEMENT}:
        from .notification_delivery_schema import FK_TRIGGERS
        trigger_tables |= {t["relation"] for t in FK_TRIGGERS}
    if state in {OUTBOX, MANAGEMENT}:
        from .confirmation_outbox_schema import FK_TRIGGERS
        trigger_tables |= {t["relation"] for t in FK_TRIGGERS}
    if state == MANAGEMENT:
        from .notification_management_schema import FK_TRIGGERS
        trigger_tables |= {t["relation"] for t in FK_TRIGGERS}
    if any(r["owner"] != identity.owner or r["persistence"] != "p"
           or r["rls"] or r["force_rls"] or r["rules"] or r["triggers"] != (r["name"] in trigger_tables) or r["options"]
           for r in relations):
        raise MigrationError(Failure.DRIFT)
    types = rows(connection, """
        SELECT t.typname AS name, t.typtype AS kind,
               pg_catalog.pg_get_userbyid(t.typowner) AS owner,
               t.typrelid::bigint AS relation, t.typelem::bigint AS element
        FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace
        WHERE n.nspname='oaf_website' ORDER BY t.typname
    """)
    if state == BASE and types:
        raise MigrationError(Failure.DRIFT)
    if state != BASE:
        expected_types = [("_alembic_version", "b", identity.owner), ("alembic_version", "c", identity.owner)]
        if state in {STATE_REQUESTS, NOTIFICATIONS, DELIVERY, OUTBOX, MANAGEMENT}:
            expected_types += [("_state_requests", "b", identity.owner), ("state_requests", "c", identity.owner)]
        if state in {NOTIFICATIONS, DELIVERY, OUTBOX, MANAGEMENT}:
            expected_types += [("_notifications", "b", identity.owner), ("notifications", "c", identity.owner)]
        if state in {DELIVERY, OUTBOX, MANAGEMENT}:
            expected_types += [(name, kind, identity.owner) for item in DELIVERY_TABLES
                               for name, kind in [(item.name, "c"), ("_" + item.name, "b")]]
        if state in {OUTBOX, MANAGEMENT}:
            expected_types += [(name, kind, identity.owner) for item in OUTBOX_TABLES
                               for name, kind in [(item.name, "c"), ("_" + item.name, "b")]]
        if state == MANAGEMENT:
            expected_types += [(name, kind, identity.owner) for item in MANAGEMENT_TABLES
                               for name, kind in [(item.name, "c"), ("_" + item.name, "b")]]
        if ([(t["name"], t["kind"], t["owner"]) for t in types] != sorted(expected_types)
                or any(not t["element"] if t["kind"] == "b" else not t["relation"] for t in types)):
            raise MigrationError(Failure.DRIFT)
        if not scalar(connection, """
            SELECT t.typrelid='oaf_website.alembic_version'::pg_catalog.regclass
                   AND a.typelem=t.oid AND t.typarray=a.oid
                   AND t.typisdefined AND a.typisdefined AND a.typrelid=0
                   AND t.typelem=0 AND a.typarray=0
                   AND t.typcategory='C' AND a.typcategory='A'
                   AND a.typsubscript='pg_catalog.array_subscript_handler'::pg_catalog.regproc
                   AND t.typacl IS NULL AND a.typacl IS NULL
            FROM pg_catalog.pg_type t JOIN pg_catalog.pg_type a ON a.oid=t.typarray
            WHERE t.oid=(SELECT reltype FROM pg_catalog.pg_class
                         WHERE oid='oaf_website.alembic_version'::pg_catalog.regclass)
        """):
            raise MigrationError(Failure.DRIFT)
        verify_generated_type_privileges(connection, identity)
        if state in {STATE_REQUESTS, NOTIFICATIONS, DELIVERY, OUTBOX, MANAGEMENT}:
            from .state_request_validation import verify_state_requests
            verify_state_requests(connection, identity)
        if state in {NOTIFICATIONS, DELIVERY, OUTBOX, MANAGEMENT}:
            from .notification_validation import verify_notifications
            if state == MANAGEMENT:
                verify_notifications(connection, identity, management=True)
            else:
                verify_notifications(connection, identity)
    if state in {DELIVERY, OUTBOX, MANAGEMENT}:
        from .notification_delivery_validation import verify_delivery
        if state in {OUTBOX, MANAGEMENT}:
            from .notification_delivery_schema import MUTABLE, FK_TRIGGERS
            from .confirmation_outbox_schema import MUTABLE as outbox_mutable, FK_TRIGGERS as outbox_triggers
            tables = DELIVERY_TABLES + OUTBOX_TABLES
            mutable = {**MUTABLE, **outbox_mutable}
            triggers = FK_TRIGGERS + outbox_triggers
            if state == MANAGEMENT:
                from .notification_management_schema import intents, FK_TRIGGERS as management_triggers
                tables = DELIVERY_TABLES + (intents, OUTBOX_TABLES[1]) + MANAGEMENT_TABLES
                mutable.update({t.name: () for t in MANAGEMENT_TABLES})
                triggers = triggers + management_triggers
            verify_delivery(connection, identity, tables=tables, mutable=mutable, expected_triggers=triggers)
        else:
            verify_delivery(connection, identity)
    verify_dependencies(connection, identity, state)
    if state == BASE:
        if scalar(connection, """
            SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint c
                JOIN pg_catalog.pg_namespace n ON n.oid=c.connamespace
                WHERE n.nspname='oaf_website')
        """):
            raise MigrationError(Failure.DRIFT)
        return BASE
    verify_version_table(connection, identity)
    marker = rows(connection, "SELECT version_num FROM oaf_website.alembic_version")
    if marker != [{"version_num": state}]:
        raise MigrationError(Failure.DRIFT)
    return state


def verify_generated_type_privileges(connection, identity):
    """The sole generated exception is the exact verified baseline row/array pair.

    NULL ACLs mean built-in defaults, not no access. PostgreSQL array checks use
    the element type's ACL. Effective PUBLIC USAGE never grants table-row access.
    Exact type identity/owner/schema and internal dependencies are checked by
    catalog_state and verify_dependencies. No ordinary managed type is approved.
    """
    acl = rows(connection, """
        SELECT t.typname AS name,
               CASE WHEN a.grantee=0 THEN 'PUBLIC'
                    ELSE pg_catalog.pg_get_userbyid(a.grantee) END AS grantee,
               pg_catalog.pg_get_userbyid(a.grantor) AS grantor,
               a.privilege_type AS privilege, a.is_grantable AS grantable
        FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(t.typacl, pg_catalog.acldefault('T',t.typowner))) a
        WHERE n.nspname='oaf_website'
          AND t.typname IN ('alembic_version', '_alembic_version')
    """)
    expected = {(name, grantee, identity.owner, 'USAGE', False)
                for name in ('alembic_version', '_alembic_version')
                for grantee in (identity.owner, 'PUBLIC')}
    actual = {(a['name'], a['grantee'], a['grantor'], a['privilege'], a['grantable']) for a in acl}
    if actual != expected or len(acl) != len(expected):
        raise MigrationError(Failure.DRIFT)
    for name in ('oaf_website.alembic_version', 'oaf_website._alembic_version'):
        for i in IDENTITIES.values():
            for role in (i.owner, i.runtime, i.migrator):
                if not scalar(connection,
                        "SELECT pg_catalog.has_type_privilege(:role, :name, 'USAGE')",
                        role=role, name=name):
                    raise MigrationError(Failure.DRIFT)
                if role != identity.owner and scalar(connection,
                        "SELECT pg_catalog.has_type_privilege(:role, :name, 'USAGE WITH GRANT OPTION')",
                        role=role, name=name):
                    raise MigrationError(Failure.DRIFT)


def verify_dependencies(connection, identity, state):
    """Exact inbound/outbound pg_depend edges, including remote extensions.

    No wildcard acceptance of dependency flavors or arbitrary pg_catalog objects.
    PostgreSQL 17 pinned builtins have no pg_depend rows; column/type/collation
    and index/opclass identities are separately verified in verify_version_table.
    Owner-specific default ACL objects are included, not mistaken for drift.
    """
    objects = rows(connection, """
        SELECT 'schema' AS label, 'pg_catalog.pg_namespace'::pg_catalog.regclass::bigint AS classid,
               oid::bigint AS objid FROM pg_catalog.pg_namespace WHERE nspname='oaf_website'
        UNION ALL
        SELECT CASE WHEN left(c.relname,13)='notification_' THEN 'delivery_' || CASE c.relkind WHEN 'r' THEN 'table_' ELSE 'index_' END || c.relname
                    WHEN c.relname='state_requests' THEN 'request_table'
                    WHEN c.relname='state_requests_pk' THEN 'request_index'
                    WHEN c.relname='notifications' THEN 'notification_table'
                    WHEN c.relname='notifications_pk' THEN 'notification_index'
                    WHEN c.relname='notifications_active_email' THEN 'notification_active_index'
                    ELSE CASE c.relkind WHEN 'r' THEN 'table' WHEN 'i' THEN 'index' ELSE 'unexpected' END END,
               'pg_catalog.pg_class'::pg_catalog.regclass::bigint, c.oid::bigint
          FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
         WHERE n.nspname='oaf_website'
        UNION ALL
        SELECT CASE WHEN left(t.typname,13)='notification_' OR left(t.typname,14)='_notification_' THEN 'delivery_type_' || t.typname
                    WHEN t.typname='state_requests' THEN 'request_row_type'
                    WHEN t.typname='_state_requests' THEN 'request_array_type'
                    WHEN t.typname='notifications' THEN 'notification_row_type'
                    WHEN t.typname='_notifications' THEN 'notification_array_type'
                    ELSE CASE t.typtype WHEN 'c' THEN 'row_type' ELSE 'array_type' END END,
               'pg_catalog.pg_type'::pg_catalog.regclass::bigint, t.oid::bigint
          FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace
         WHERE n.nspname='oaf_website'
        UNION ALL
        SELECT CASE WHEN left(c.conname,13)='notification_' THEN 'delivery_constraint_' || c.conname
                    WHEN c.conname='state_requests_pk' THEN 'request_primary_key'
                    WHEN c.conname='state_requests_state_check' THEN 'request_check'
                    WHEN c.conname='notifications_pk' THEN 'notification_primary_key'
                    WHEN c.conname LIKE 'notifications_%' THEN 'notification_' || c.conname
                    ELSE 'primary_key' END,
               'pg_catalog.pg_constraint'::pg_catalog.regclass::bigint, c.oid::bigint
          FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_namespace n ON n.oid=c.connamespace
         WHERE n.nspname='oaf_website'
        UNION ALL
        SELECT CASE WHEN c.relname='notifications' AND a.attname='created_at' THEN 'notification_default'
                    WHEN c.relname='state_requests' THEN 'request_default'
                    ELSE 'management_default_' || c.relname || '_' || a.attname END,
               'pg_catalog.pg_attrdef'::pg_catalog.regclass::bigint, d.oid::bigint
          FROM pg_catalog.pg_attrdef d JOIN pg_catalog.pg_class c ON c.oid=d.adrelid
          JOIN pg_catalog.pg_attribute a ON a.attrelid=d.adrelid AND a.attnum=d.adnum
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
         WHERE n.nspname='oaf_website'
        UNION ALL
        SELECT 'delivery_trigger_' || c.conname || '_' || r.relname || '_' || t.tgtype::text,
               'pg_catalog.pg_trigger'::pg_catalog.regclass::bigint, t.oid::bigint
          FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_constraint c ON c.oid=t.tgconstraint
          JOIN pg_catalog.pg_class r ON r.oid=t.tgrelid
          JOIN pg_catalog.pg_namespace n ON n.oid=c.connamespace
         WHERE n.nspname='oaf_website' AND left(c.conname,13)='notification_'
        UNION ALL
        SELECT 'default_' || d.defaclnamespace::text || '_' || d.defaclobjtype::text,
               'pg_catalog.pg_default_acl'::pg_catalog.regclass::bigint, d.oid::bigint
          FROM pg_catalog.pg_default_acl d JOIN pg_catalog.pg_roles r ON r.oid=d.defaclrole
         WHERE r.rolname=:owner
    """, owner=identity.owner)
    addresses = {(o['classid'], o['objid']): o['label'] for o in objects}
    labels = [o['label'] for o in objects]
    expected_labels = {'schema'} if state == BASE else {
        'schema', 'table', 'index', 'row_type', 'array_type', 'primary_key'}
    if state in {STATE_REQUESTS, NOTIFICATIONS, DELIVERY, OUTBOX, MANAGEMENT}:
        expected_labels |= {'request_table', 'request_index', 'request_row_type',
                            'request_array_type', 'request_primary_key', 'request_check', 'request_default'}
    if state in {NOTIFICATIONS, DELIVERY, OUTBOX, MANAGEMENT}:
        expected_labels |= {edge[0] for edge in NOTIFICATION_EDGES}
    if state in {DELIVERY, OUTBOX, MANAGEMENT}:
        expected_labels |= {edge[0] for edge in DELIVERY_EDGES}
    if state in {OUTBOX, MANAGEMENT}:
        expected_labels |= {edge[0] for edge in OUTBOX_EDGES}
    if state == MANAGEMENT:
        expected_labels |= {edge[0] for edge in MANAGEMENT_EDGES}
    if (len(set(labels)) != len(labels) or
            {v for v in labels if not v.startswith('default_')} != expected_labels):
        raise MigrationError(Failure.DRIFT)
    # Each address is a verified numeric catalog value, bound as SQL parameters.
    # One query covers both endpoints without restricting extension namespaces.
    parameters = {}
    clauses = []
    for index, (catalog, oid) in enumerate(sorted(addresses)):
        parameters[f'c{index}'], parameters[f'o{index}'] = catalog, oid
        clauses.append(f'(classid=:c{index} AND objid=:o{index})')
        clauses.append(f'(refclassid=:c{index} AND refobjid=:o{index})')
    dependencies = rows(connection,
        "SELECT classid::bigint, objid::bigint, objsubid, refclassid::bigint, "
        "refobjid::bigint, refobjsubid, deptype FROM pg_catalog.pg_depend WHERE "
        + ' OR '.join(clauses), **parameters)
    actual = []
    generated_toast = {}
    for d in dependencies:
        source = addresses.get((d['classid'], d['objid']))
        target = addresses.get((d['refclassid'], d['refobjid']))
        if (source is None and target is not None
                and d['classid'] == d['refclassid']
                and (d['objsubid'], d['refobjsubid'], d['deptype']) == (0, 0, 'i')):
            # Only the exact whole-relation internal edge to a managed parent.
            # TOAST names are not identity; bind both OIDs through reltoastrelid.
            toast = rows(connection, """
                SELECT 'pg_catalog.pg_class'::pg_catalog.regclass::bigint AS classid,
                       t.oid::bigint AS objid, t.relkind AS kind, n.nspname AS schema,
                       pg_catalog.pg_get_userbyid(t.relowner) AS owner,
                       t.relpersistence AS persistence, t.relacl AS acl,
                       t.reltoastrelid::bigint AS toast, p.oid::bigint AS parent,
                       p.reltoastrelid::bigint AS parent_toast, p.relkind AS parent_kind,
                       pn.nspname AS parent_schema,
                       pg_catalog.pg_get_userbyid(p.relowner) AS parent_owner,
                       p.relpersistence AS parent_persistence
                FROM pg_catalog.pg_class p
                JOIN pg_catalog.pg_class t ON t.oid=p.reltoastrelid
                JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
                JOIN pg_catalog.pg_namespace pn ON pn.oid=p.relnamespace
                WHERE p.oid=:parent AND t.oid=:source
            """, parent=d['refobjid'], source=d['objid'])
            if toast != [dict(classid=d['classid'], objid=d['objid'], kind='t', schema='pg_toast',
                              owner=identity.owner, persistence='p', acl=None, toast=0,
                              parent=d['refobjid'], parent_toast=d['objid'], parent_kind='r',
                              parent_schema='oaf_website', parent_owner=identity.owner,
                              parent_persistence='p')]:
                raise MigrationError(Failure.DRIFT)
            source = f"toast_{d['objid']}"
            generated_toast[source] = (source, 0, target, 0, 'i')
        if source is None or target is None:
            raise MigrationError(Failure.DRIFT)
        actual.append((source, d['objsubid'], target, d['refobjsubid'], d['deptype']))
    expected = set() if state == BASE else {
        tuple(edge) for edge in SECURITY_CONTRACT['dependencies']['baseline_edges']}
    expected |= set(generated_toast.values())
    if state in {STATE_REQUESTS, NOTIFICATIONS, DELIVERY, OUTBOX, MANAGEMENT}:
        expected |= {tuple(edge) for edge in REQUEST_EDGES}
    if state in {NOTIFICATIONS, DELIVERY, OUTBOX, MANAGEMENT}:
        expected |= {tuple(edge) for edge in NOTIFICATION_EDGES}
    if state in {DELIVERY, OUTBOX, MANAGEMENT}:
        expected |= {tuple(edge) for edge in DELIVERY_EDGES}
    if state in {OUTBOX, MANAGEMENT}:
        expected |= {tuple(edge) for edge in OUTBOX_EDGES}
    if state == MANAGEMENT:
        expected |= {tuple(edge) for edge in MANAGEMENT_EDGES}
    for label in labels:
        if label.startswith('default_'):
            _, namespace, kind = label.split('_')
            if namespace != '0':
                if kind not in {'r', 'S', 'f', 'T'}:
                    raise MigrationError(Failure.DRIFT)
                expected.add((label, 0, 'schema', 0, 'a'))
    if set(actual) != expected or len(actual) != len(expected):
        raise MigrationError(Failure.DRIFT)


def verify_version_table(connection, identity):
    columns = rows(connection, """
        SELECT a.attname AS name, pg_catalog.format_type(a.atttypid,a.atttypmod) AS type,
               a.attnotnull AS required, a.atthasdef AS has_default,
               a.attidentity AS identity, a.attgenerated AS generated, a.attisdropped AS dropped,
               a.attnum AS position, a.attndims AS dimensions,
               a.attcollation='pg_catalog."default"'::pg_catalog.regcollation AS default_collation
        FROM pg_catalog.pg_attribute a
        WHERE a.attrelid='oaf_website.alembic_version'::pg_catalog.regclass AND a.attnum>0
        ORDER BY a.attnum
    """)
    if columns != [{"name": "version_num", "type": "character varying(32)",
                    "required": True, "has_default": False, "identity": "",
                    "generated": "", "dropped": False, "position": 1,
                    "dimensions": 0, "default_collation": True}]:
        raise MigrationError(Failure.DRIFT)
    constraints = rows(connection, """
        SELECT c.conname AS name, c.contype AS kind, c.convalidated AS validated,
               c.condeferrable AS deferrable, c.condeferred AS deferred,
               pg_catalog.pg_get_constraintdef(c.oid) AS definition
        FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_namespace n ON n.oid=c.connamespace
        WHERE n.nspname='oaf_website'
          AND c.conrelid='oaf_website.alembic_version'::pg_catalog.regclass
    """)
    if constraints != [{"name": "alembic_version_pkc", "kind": "p", "validated": True,
                        "deferrable": False, "deferred": False, "definition": "PRIMARY KEY (version_num)"}]:
        raise MigrationError(Failure.DRIFT)
    if not scalar(connection, """
        SELECT i.indisunique AND i.indisprimary AND i.indisvalid AND i.indisready
               AND i.indislive AND i.indexprs IS NULL AND i.indpred IS NULL
               AND i.indnatts=1 AND i.indnkeyatts=1 AND am.amname='btree'
               AND i.indkey[0]=1 AND i.indoption[0]=0
               AND i.indcollation[0]='pg_catalog."default"'::pg_catalog.regcollation
               AND op.opcname='text_ops' AND ns.nspname='pg_catalog'
        FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid
        JOIN pg_catalog.pg_am am ON am.oid=c.relam
        JOIN pg_catalog.pg_opclass op ON op.oid=i.indclass[0]
        JOIN pg_catalog.pg_namespace ns ON ns.oid=op.opcnamespace
        WHERE i.indexrelid='oaf_website.alembic_version_pkc'::pg_catalog.regclass
          AND i.indrelid='oaf_website.alembic_version'::pg_catalog.regclass
    """):
        raise MigrationError(Failure.DRIFT)
    if scalar(connection, """
        SELECT EXISTS (
            SELECT 1 FROM pg_catalog.pg_class c CROSS JOIN LATERAL
                 pg_catalog.aclexplode(COALESCE(c.relacl, pg_catalog.acldefault('r', c.relowner))) a
            WHERE c.oid='oaf_website.alembic_version'::pg_catalog.regclass
              AND (a.grantee<>c.relowner OR a.grantor<>c.relowner OR a.is_grantable)
            UNION ALL
            SELECT 1 FROM pg_catalog.pg_attribute c CROSS JOIN LATERAL
                 pg_catalog.aclexplode(c.attacl) a
            WHERE c.attrelid='oaf_website.alembic_version'::pg_catalog.regclass
              AND (a.grantee<>(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=:owner)
                   OR a.grantor<>(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=:owner)
                   OR a.is_grantable)
            UNION ALL
            SELECT 1 FROM pg_catalog.pg_policy WHERE polrelid='oaf_website.alembic_version'::pg_catalog.regclass
            UNION ALL
            SELECT 1 FROM pg_catalog.pg_rewrite WHERE ev_class='oaf_website.alembic_version'::pg_catalog.regclass
            UNION ALL
            SELECT 1 FROM pg_catalog.pg_inherits WHERE
                 inhrelid='oaf_website.alembic_version'::pg_catalog.regclass
                 OR inhparent='oaf_website.alembic_version'::pg_catalog.regclass
            UNION ALL
            SELECT 1 FROM pg_catalog.pg_trigger WHERE tgrelid='oaf_website.alembic_version'::pg_catalog.regclass
        )
    """, owner=identity.owner):
        raise MigrationError(Failure.DRIFT)
    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN"):
        if not scalar(connection, "SELECT pg_catalog.has_table_privilege(:name, 'oaf_website.alembic_version', :privilege)",
                      name=identity.owner, privilege=privilege):
            raise MigrationError(Failure.DRIFT)
        for i in IDENTITIES.values():
            for name in (i.runtime, i.migrator, i.owner):
                if name != identity.owner and scalar(connection,
                        "SELECT pg_catalog.has_table_privilege(:name, 'oaf_website.alembic_version', :privilege)",
                        name=name, privilege=privilege):
                    raise MigrationError(Failure.DRIFT)
    for i in IDENTITIES.values():
        for name in (i.runtime, i.migrator, i.owner):
            if name != identity.owner and scalar(connection,
                    "SELECT pg_catalog.has_any_column_privilege(:name, 'oaf_website.alembic_version', 'SELECT, INSERT, UPDATE, REFERENCES')",
                    name=name):
                raise MigrationError(Failure.DRIFT)
    # No sequences or routines are approved. Their presence already fails exact
    # inventory; future grants require dedicated server-enforced validators.
