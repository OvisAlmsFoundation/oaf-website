"""0004 source contract/catalog/authorization checks; all records synthetic."""
import migration_offline as isolation
isolation.require_early_registration()

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
import re
from types import SimpleNamespace
from unittest.mock import Mock
import runpy

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, PrimaryKeyConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from alembic import op as alembic_op

from migration_offline import ROOT, Result, DriverError
from oaf_website import migration_validation as v, migrate as m
from oaf_website import notification_delivery_schema as s, notification_delivery_validation as validator
from oaf_website.migration_config import Failure, MigrationError, IDENTITIES
from test_notification_migration import NotificationCatalog
from test_migration_artifacts import artifact_copy, write_manifest
from test_migration_operational import operational, records


# Independently specified PostgreSQL catalog identity, not validator output.
DELIVERY_FOREIGN_KEYS = {
    ("oaf_website.notification_verification", "notification_verification_subscription_fk"):
        ("notifications", ["subscription"], ["unsubscribe_digest"]),
    ("oaf_website.notification_deliveries", "notification_deliveries_event_fk"):
        ("notification_release_events", ["event_id"], ["event_id"]),
    ("oaf_website.notification_deliveries", "notification_deliveries_subscription_fk"):
        ("notifications", ["subscription"], ["unsubscribe_digest"]),
    ("oaf_website.notification_delivery_attempts", "notification_delivery_attempts_delivery_fk"):
        ("notification_deliveries", ["event_id", "subscription"], ["event_id", "subscription"]),
}


def foreign_key_snapshots(specifications):
    return {key: [dict(referenced_schema="oaf_website", referenced_table=table,
                      columns=list(columns), referenced_columns=list(referenced_columns),
                      on_update="a", on_delete="a", match="s")]
            for key, (table, columns, referenced_columns) in specifications.items()}


PG_CLAIM_CHECK = """CHECK (
    (((status)::text = ANY ((ARRAY['claimed'::character varying, 'submitting'::character varying])::text[]))
      AND (claim_digest IS NOT NULL) AND (lease_until IS NOT NULL))
    OR
    (((status)::text <> ALL ((ARRAY['claimed'::character varying, 'submitting'::character varying])::text[]))
      AND (claim_digest IS NULL) AND (lease_until IS NULL)))"""
PG_STATUS_CHECK = """CHECK (((status)::text = ANY ((ARRAY[
    'pending'::character varying, 'claimed'::character varying, 'submitting'::character varying,
    'accepted'::character varying, 'rejected'::character varying, 'failed'::character varying,
    'suppressed'::character varying, 'uncertain'::character varying])::text[])))"""


def artifacts(start=v.NOTIFICATIONS):
    payload = (v.ROOT/"migrations/manifest.json").read_bytes()
    return v.validate_artifacts(expected_start=start, target=v.DELIVERY,
        manifest_hash=v.digest(payload), revision_hash=json.loads(payload)["revisions"][3]["sha256"])


class DeliveryCatalog(NotificationCatalog):
    def __init__(self, environment="testing"):
        super().__init__(environment)
        self.marker = [dict(version_num=v.DELIVERY)]
        trigger_tables = {t["relation"] for t in s.FK_TRIGGERS}
        for row in self.relations:
            row["triggers"] = row["name"] in trigger_tables
        self.relations += [dict(name=o["name"], kind="r" if o["kind"]=="table" else "i", owner=self.i.owner,
            persistence="p", rls=False, force_rls=False, rules=False, triggers=o["name"] in trigger_tables, options=None)
            for o in s.OBJECTS if o["kind"] in {"table", "index"}]
        self.relations.sort(key=lambda r:r["name"])
        self.types += [dict(name=name, kind=kind, owner=self.i.owner, relation=700 if kind=="c" else 0,
            element=701 if kind=="b" else 0) for item in s.TABLES for name, kind in ((item.name,"c"),("_"+item.name,"b"))]
        self.types.sort(key=lambda r:r["name"])
        labels = sorted({edge[0] for edge in s.EDGES})
        self.objects += [dict(label=label,classid=9000+n,objid=10000+n) for n,label in enumerate(labels)]
        addresses = {o["label"]:(o["classid"],o["objid"]) for o in self.objects}
        self.dependencies += [dict(classid=addresses[a][0],objid=addresses[a][1],objsubid=b,
            refclassid=addresses[c][0],refobjid=addresses[c][1],refobjsubid=d,deptype=e) for a,b,c,d,e in s.EDGES]
        self.foreign_keys = foreign_key_snapshots(DELIVERY_FOREIGN_KEYS)
        self.snapshots = {}
        for item in s.TABLES:
            name = "oaf_website."+item.name
            constraints = []
            for c in sorted(item.constraints, key=lambda c:c.name):
                kind = "c" if isinstance(c,CheckConstraint) else "f" if isinstance(c,ForeignKeyConstraint) else "p" if isinstance(c,PrimaryKeyConstraint) else "u"
                constraints.append(dict(name=c.name,kind=kind,validated=True,deferrable=False,deferred=False,
                    local=True,inherited=0,definition=validator.constraint_definition(c)))
            self.snapshots[name] = dict(columns=validator.column_contract(item), constraints=constraints,
                indexes=validator.index_contract(item), inheritance=False, type_pair=True,
                acl=[dict(grantee=self.i.owner,grantor=self.i.owner,privilege=p,grantable=False)
                     for p in ("SELECT","INSERT","UPDATE","DELETE","TRUNCATE","REFERENCES","TRIGGER","MAINTAIN")]
                    +[dict(grantee=self.i.runtime,grantor=self.i.owner,privilege=p,grantable=False) for p in ("SELECT","INSERT")],
                column_acl=[dict(column=c,grantee=self.i.runtime,grantor=self.i.owner,privilege="UPDATE",grantable=False) for c in s.MUTABLE[item.name]],
                type_acl=[dict(grantee=self.i.owner,grantor=self.i.owner,privilege="USAGE",grantable=False)])
        self.trigger_snapshot = deepcopy(sorted(s.FK_TRIGGERS,key=lambda r:r["label"]))
        self.effective_override = None

    def execute(self, sql, parameters=None):
        q, p = " ".join(str(sql).split()), parameters or {}
        name = p.get("table")
        if "c.confrelid" in q:
            return Result(deepcopy(self.foreign_keys[(name, p["constraint"])]))
        if name in self.snapshots:
            snapshot = self.snapshots[name]
            for needle, key in (("a.attname AS name","columns"),("c.conname AS name","constraints"),
                ("pg_get_indexdef","indexes"),("pg_inherits","inheritance"),("COALESCE(c.relacl","acl"),
                ("aclexplode(c.attacl)","column_acl"),("aclexplode(t.typacl)","type_acl"),("t.typrelid=","type_pair")):
                if needle in q: return Result(deepcopy(snapshot[key]))
            if "has_table_privilege" in q:
                value = p["role"]==self.i.owner or p["role"]==self.i.runtime and p["privilege"] in {"SELECT","INSERT"}
            elif "has_column_privilege" in q:
                value = p["role"]==self.i.owner or p["role"]==self.i.runtime and (p["privilege"] in {"SELECT","INSERT"} or p["privilege"]=="UPDATE" and p["column"] in s.MUTABLE[name.split(".")[1]])
            else: raise AssertionError(q)
            return Result(value if self.effective_override is None else self.effective_override)
        if "has_type_privilege" in q and any(p.get("name") in {"oaf_website."+item.name,"oaf_website._"+item.name} for item in s.TABLES):
            value = p["role"]==self.i.owner and "WITH GRANT OPTION" not in q
            return Result(value if self.effective_override is None else self.effective_override)
        if "AS label" in q and "t.tgisinternal AS internal" in q: return Result(deepcopy(self.trigger_snapshot))
        return super().execute(sql, parameters)


@pytest.mark.parametrize("environment", ["testing", "development"])
def test_complete_0004_catalog_and_least_privilege(environment):
    c = DeliveryCatalog(environment)
    assert v.catalog_state(c,c.i) == v.DELIVERY


# The original query is fixed evidence of both the incompatible shared bind and
# the complete OID/array/ACL predicate contract. This is not a server emulator.
ORIGINAL_TYPE_PAIR_SQL = """
    SELECT t.typrelid=CAST(:table AS pg_catalog.regclass) AND a.typelem=t.oid AND t.typarray=a.oid
       AND t.typisdefined AND a.typisdefined AND a.typrelid=0 AND t.typelem=0 AND a.typarray=0
       AND t.typcategory='C' AND a.typcategory='A' AND a.typsubscript='pg_catalog.array_subscript_handler'::pg_catalog.regproc
       AND t.typacl IS NOT NULL AND a.typacl IS NULL
    FROM pg_catalog.pg_type t JOIN pg_catalog.pg_type a ON a.oid=t.typarray WHERE t.oid=CAST(:table AS pg_catalog.regtype)
"""


def type_pair_wire_query(sql, parameters):
    """Use the installed compiler/adapter offline, retaining unspecified OID 0."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
    from psycopg.adapt import Transformer
    from psycopg._queries import PostgresQuery
    query = PostgresQuery(Transformer())
    query.convert(str(text(sql).compile(dialect=PGDialect_psycopg())), parameters)
    assert query.types == (0,) and len(query.params) == 1
    return " ".join(query.query.decode().split())


def test_original_type_pair_bind_has_incompatible_oid_alias_contexts():
    # PG17 infers this one unknown parameter as regclass, then attempts the
    # unsupported regclass -> regtype cast. No PostgreSQL execution is claimed.
    wire = type_pair_wire_query(ORIGINAL_TYPE_PAIR_SQL,
                               {"table": "oaf_website.notification_verification"})
    assert wire.count("$1") == 2
    assert "CAST($1 AS pg_catalog.regclass)" in wire
    assert "CAST($1 AS pg_catalog.regtype)" in wire


@pytest.mark.parametrize("revision", ["0004", "0005"])
@pytest.mark.parametrize("environment", ["testing", "development"])
def test_actual_delivery_path_uses_text_before_distinct_oid_lookups(monkeypatch, revision, environment):
    catalog = pg_catalog(revision)
    if environment == "development":
        catalog = type(catalog)(environment)
    original_scalar = v.scalar
    queries = {}

    def recording_scalar(connection, sql, **parameters):
        if "FROM pg_catalog.pg_type t JOIN pg_catalog.pg_type a ON a.oid=t.typarray WHERE" in sql:
            queries[parameters["table"]] = sql
        return original_scalar(connection, sql, **parameters)

    monkeypatch.setattr(v, "scalar", recording_scalar)
    assert v.catalog_state(catalog, catalog.i) == catalog.marker[0]["version_num"]
    assert set(queries) == set(catalog.snapshots)
    for table, sql in queries.items():
        wire = type_pair_wire_query(sql, {"table": table})
        assert wire.count("$1") == 2
        for alias in ("regclass", "regtype"):
            assert f"CAST(CAST($1 AS pg_catalog.text) AS pg_catalog.{alias})" in wire
        # Erasing only the inner text annotations must recover EVERY original
        # identity/definition/category/handler/ACL predicate and the exact join.
        assert " ".join(sql.replace("CAST(:table AS pg_catalog.text)", ":table").split()) == " ".join(ORIGINAL_TYPE_PAIR_SQL.split())


@pytest.mark.parametrize("table", [item.name for item in s.TABLES])
@pytest.mark.parametrize("value", [False, None, 0, 1, "true", {}, {"matches": True}, [True]])
def test_generated_type_pair_requires_a_boolean_true(table, value):
    catalog = DeliveryCatalog()
    catalog.snapshots["oaf_website." + table]["type_pair"] = value
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("records", [[], [(True,), (True,)]])
def test_generated_type_pair_missing_or_duplicate_rows_fail_closed(monkeypatch, records):
    from sqlalchemy.engine.result import IteratorResult, SimpleResultMetaData
    from sqlalchemy.exc import MultipleResultsFound, NoResultFound
    catalog = DeliveryCatalog()
    original_execute = catalog.execute

    def execute(sql, parameters=None):
        if "t.typrelid=CAST(:table" in str(sql) or "t.typrelid=CAST(CAST(:table" in str(sql):
            return IteratorResult(SimpleResultMetaData(["matches"]), iter(records))
        return original_execute(sql, parameters)

    monkeypatch.setattr(catalog, "execute", execute)
    with pytest.raises((NoResultFound, MultipleResultsFound)):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("table", [item.name for item in s.TABLES])
@pytest.mark.parametrize("case", ["row_kind", "row_owner", "row_relation", "missing_row",
                                  "array_kind", "array_owner", "array_element", "missing_array"])
def test_generated_type_inventory_identity_and_ownership_remain_exact(table, case):
    catalog = DeliveryCatalog()
    name = "_" + table if case.startswith("array") or case == "missing_array" else table
    record = next(row for row in catalog.types if row["name"] == name)
    if case.startswith("missing"):
        catalog.types.remove(record)
    else:
        field = case.split("_")[1]
        record[field] = {"kind": "e", "owner": catalog.i.runtime, "relation": 0, "element": 0}[field]
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("case", ["column","constraint","check","boolean_grouping","fk","index","inheritance", "acl", "column_acl", "type_acl", "type_pair", "trigger", "effective", "relation", "dependency", "type", "marker"])
def test_delivery_catalog_drift_denied(case):
    c = DeliveryCatalog()
    snapshot=c.snapshots["oaf_website.notification_deliveries"]
    if case=="column": snapshot["columns"][0]["required"]=False
    elif case=="constraint": snapshot["constraints"].pop()
    elif case=="check": next(r for r in snapshot["constraints"] if r["kind"]=="c")["definition"]="CHECK (True)"
    elif case=="boolean_grouping":
        r=next(r for r in snapshot["constraints"] if r["name"]=="notification_deliveries_claim_check")
        r["definition"]="CHECK (status IN ('claimed','submitting') AND (claim_digest IS NOT NULL AND lease_until IS NOT NULL OR status NOT IN ('claimed','submitting')) AND claim_digest IS NULL AND lease_until IS NULL)"
    elif case=="fk": c.foreign_keys[("oaf_website.notification_deliveries", "notification_deliveries_event_fk")][0]["on_delete"]="c"
    elif case=="index": snapshot["indexes"][0]["definition"] += " WHERE true"
    elif case=="inheritance": snapshot["inheritance"]=True
    elif case=="acl": snapshot["acl"][-1]["grantee"]="PUBLIC"
    elif case=="column_acl": snapshot["column_acl"][0]["grantable"]=True
    elif case=="type_acl": snapshot["type_acl"][0]["grantee"]="PUBLIC"
    elif case=="type_pair": snapshot["type_pair"]=False
    elif case=="trigger": c.trigger_snapshot.pop()
    elif case=="effective": c.effective_override=True
    elif case=="relation": c.relations[0]["triggers"]=True
    elif case=="dependency": c.dependencies.pop()
    elif case=="type": c.types[1]["owner"]=c.i.runtime
    elif case=="marker": c.marker=[dict(version_num=v.NOTIFICATIONS)]
    with pytest.raises(MigrationError,match=Failure.DRIFT): v.catalog_state(c,c.i)


def test_check_parser_preserves_grouping_and_supports_pg17_rendering():
    assert validator.check_tree("CHECK (status IN ('pending','failed'))") == validator.check_tree("CHECK ((status = ANY (ARRAY['pending'::character varying, 'failed'::character varying])))")
    assert validator.check_tree("CHECK (attempts BETWEEN 0 AND 3)") == validator.check_tree("CHECK (((attempts >= 0) AND (attempts <= 3)))")
    assert validator.check_tree("CHECK (a AND (b OR c))") != validator.check_tree("CHECK ((a AND b) OR c)")
    assert validator.check_tree("CHECK ((a AND b) AND c)") == validator.check_tree("CHECK (a AND b AND c)")


@pytest.mark.parametrize("environment", ["testing","development"])
def test_upgrade_source_ddl_only_expected_owner_and_no_historical_alter(environment):
    identity=IDENTITIES[environment]
    sql=[]
    def execute(statement):
        sql.append(str(statement.compile(dialect=postgresql.dialect())))
        return SimpleNamespace(scalar_one=lambda:identity.owner)
    s.upgrade_notification_delivery(SimpleNamespace(execute=execute))
    joined=" ".join(sql)
    assert len([q for q in sql if q.startswith("\nCREATE TABLE")])==6
    assert "FOREIGN KEY(event_id, subscription)" in joined
    assert "DELETE" not in " ".join(q for q in sql if q.startswith("GRANT"))
    assert "ALTER TABLE oaf_website.notifications" not in joined
    assert "COMMIT" not in joined and "WITH GRANT OPTION" not in joined
    assert "GRANT UPDATE (status, updated_at)" in joined
    assert not any("GRANT UPDATE" in q and "notification_suppressions" in q for q in sql)
    assert "notification_deliveries_retry" in joined and "notification_deliveries_lease" in joined


def test_runtime_cannot_execute_ddl_and_revision_downgrade_blocked(monkeypatch):
    with pytest.raises(MigrationError,match=Failure.WRONG_IDENTITY):
        s.upgrade_notification_delivery(SimpleNamespace(execute=lambda q:Result(IDENTITIES["testing"].runtime)))
    revision=runpy.run_path(str(ROOT/v.DELIVERY_REVISION_FILE))
    sentinel=object()
    monkeypatch.setattr(alembic_op,"get_bind",lambda:sentinel)
    calls=[]
    revision["upgrade"].__globals__["upgrade_notification_delivery"]=calls.append
    revision["upgrade"]()
    assert calls==[sentinel]
    with pytest.raises(RuntimeError): revision["downgrade"]()


def test_exact_transition_noop_and_immutable_predecessor_hashes():
    assert artifacts().expected_start==v.NOTIFICATIONS
    assert artifacts(v.DELIVERY).target==v.DELIVERY
    d=json.loads((ROOT/"migrations/manifest.json").read_bytes())
    assert [r["sha256"] for r in d["revisions"][:3]]==[
        "bb51b33f3e064a02b8463593440820d65d01537f48a46b487b7cc327f0ea89a3",
        "c450ca44b71b8fa830e9fc231412f786952133d02ac8eb9db065fdb521fe01ad",
        "1c575d679981556a782c0f279097fd6f0fd47d6c2b7613d3a323424f0e61f452"]
    assert d["approval_status"]=="pending_independent_review"


@pytest.mark.parametrize("start,target",[(v.BASE,v.DELIVERY),(v.BASELINE,v.DELIVERY),(v.STATE_REQUESTS,v.DELIVERY),(v.DELIVERY,v.NOTIFICATIONS),(v.NOTIFICATIONS,"head"),(v.NOTIFICATIONS,"base")])
def test_no_jump_downgrade_or_alias(start,target):
    with pytest.raises(MigrationError,match=Failure.STARTING_REVISION):
        v.validate_artifacts(expected_start=start,target=target,manifest_hash="0"*64,revision_hash="0"*64)


@pytest.mark.parametrize("old,new", [('down_revision = "0003_notifications"','down_revision = "0002_state_requests"'),
    ('upgrade_notification_delivery(op.get_bind())','op.get_bind().commit()'),
    ('from alembic import op','import os\nfrom alembic import op'),
    ('raise RuntimeError("Ordinary migration downgrade is prohibited.")','pass')])
def test_rehashed_unsafe_revision_is_still_rejected(artifact_copy,old,new):
    path=artifact_copy/v.DELIVERY_REVISION_FILE
    path.write_text(path.read_text().replace(old,new),encoding="utf-8")
    d=json.loads((artifact_copy/"migrations/manifest.json").read_bytes())
    d["revisions"][3]["sha256"]=v.digest(path.read_bytes())
    write_manifest(artifact_copy,d)
    with pytest.raises(MigrationError,match=Failure.ARTIFACT_HASH): artifacts()


def test_unsigned_0004_runner_denied_before_credentials(monkeypatch):
    a=artifacts()
    loader=Mock(side_effect=AssertionError("No credential access"))
    monkeypatch.setattr(m,"load_migration_config",loader)
    with pytest.raises(MigrationError,match=Failure.OPERATIONAL_GATE):
        m.run(m.Request("upgrade","testing",a.expected_start,a.target,a.manifest_hash,a.revision_hash))
    loader.assert_not_called()


def test_synthetic_0004_single_use_authority_and_distinct_noop(operational,monkeypatch):
    op=operational; a=artifacts()
    request=replace(op.request,expected_start=v.NOTIFICATIONS,target=v.DELIVERY,revision_hash=a.revision_hash)
    monkeypatch.setattr(m,"catalog_state",lambda *args:v.DELIVERY if op.runner.connection.target else v.NOTIFICATIONS)
    authorization=op.issue(op.approvals(request))
    assert op.run(authorization,request)["outcome"]=="applied_and_verified"
    with pytest.raises(MigrationError,match=Failure.OPERATIONAL_GATE): op.run(authorization,request)
    op.clock.now+=timedelta(seconds=1)
    noop=replace(request,expected_start=v.DELIVERY)
    op.runner.connection.closed=False
    assert op.run(op.issue(op.approvals(noop)),noop)["outcome"]=="verified_noop"
    assert len(records(op,"claim-*.json"))==2


@pytest.mark.parametrize("phase,certainty",[("revision","not_invoked"),("commit","uncertain")])
def test_synthetic_failure_preserves_claim_and_uncertain_commit(operational,monkeypatch,phase,certainty):
    op=operational; a=artifacts()
    request=replace(op.request,expected_start=v.NOTIFICATIONS,target=v.DELIVERY,revision_hash=a.revision_hash)
    monkeypatch.setattr(m,"catalog_state",lambda *args:v.DELIVERY if op.runner.connection.target else v.NOTIFICATIONS)
    op.runner.connection.hooks[phase]=DriverError("08006" if phase=="commit" else "40P01")
    authorization=op.issue(op.approvals(request))
    with pytest.raises(MigrationError) as caught: op.run(authorization,request)
    assert caught.value.operational_result["commit_certainty"]==certainty
    assert len(records(op,"claim-*.json"))==1 and len(records(op,"terminal-*.json"))==1


@pytest.mark.parametrize("field,value", [("parent", v.STATE_REQUESTS), ("grants", []), ("target_state", v.NOTIFICATIONS)])
def test_fourth_revision_manifest_contract_cannot_be_redefined(artifact_copy, field, value):
    d=json.loads((artifact_copy/"migrations/manifest.json").read_bytes())
    d["revisions"][3][field]=value
    write_manifest(artifact_copy,d)
    with pytest.raises(MigrationError,match=Failure.ARTIFACT_HASH): artifacts()


def test_revision_docstring_is_optional_but_body_is_exact(artifact_copy):
    path=artifact_copy/v.DELIVERY_REVISION_FILE
    path.write_text(path.read_text().split("\n",1)[1],encoding="utf-8")
    d=json.loads((artifact_copy/"migrations/manifest.json").read_bytes())
    d["revisions"][3]["sha256"]=v.digest(path.read_bytes())
    write_manifest(artifact_copy,d)
    assert artifacts().target==v.DELIVERY


@pytest.mark.parametrize("environment", ["testing", "development"])
def test_prior_state_dispatch_and_preservation_checks_remain_authoritative(environment):
    from test_migration_catalog import Catalog
    from test_state_request_migration import FeatureCatalog
    for catalog, expected in ((Catalog(environment,False),v.BASE), (Catalog(environment,True),v.BASELINE),
                               (FeatureCatalog(environment),v.STATE_REQUESTS)):
        assert v.catalog_state(catalog,catalog.i)==expected


def test_0004_cannot_hide_a_rehashed_unsafe_predecessor(artifact_copy):
    path=artifact_copy/v.NOTIFICATION_REVISION_FILE
    path.write_text(path.read_text(encoding="utf-8").replace("upgrade_notifications(op.get_bind())", "pass"),encoding="utf-8")
    d=json.loads((artifact_copy/"migrations/manifest.json").read_bytes())
    d["revisions"][2]["sha256"]=v.digest(path.read_bytes())
    write_manifest(artifact_copy,d)
    with pytest.raises(MigrationError,match=Failure.ARTIFACT_HASH): artifacts()


def test_minimum_reference_schema_and_no_duplicate_recipient_list():
    names={t.name for t in s.TABLES}
    assert names=={"notification_verification","notification_confirmation_limits","notification_release_events",
                   "notification_deliveries","notification_delivery_attempts","notification_suppressions"}
    assert list(s.verification.primary_key.columns.keys())==["subscription"]
    assert list(s.deliveries.primary_key.columns.keys())==["event_id","subscription"]
    assert list(s.attempts.primary_key.columns.keys())==["event_id","subscription","attempt"]
    assert list(s.suppressions.primary_key.columns.keys())==["mailbox_digest"]
    for item in s.TABLES:
        assert not {"email","api_key","unsubscribe_token","error_body","recipient_list","content"}&set(item.c.keys())
    event_ddl=str(CreateTable(s.events).compile(dialect=postgresql.dialect()))
    assert "CONSTRAINT notification_release_events_launch UNIQUE (environment, platform)" in event_ddl
    assert set(s.MUTABLE[s.events.name])=={"status","updated_at"}
    assert s.MUTABLE[s.suppressions.name]==()


@pytest.mark.parametrize("field,value",[("enabled","D"),("internal",False),("function_schema","public"),
    ("arguments","00"),("condition","false"),("other_relation","wrong")])
def test_fk_trigger_behavior_cannot_be_silently_changed(field,value):
    catalog=DeliveryCatalog()
    catalog.trigger_snapshot[0][field]=value
    with pytest.raises(MigrationError,match=Failure.DRIFT): v.catalog_state(catalog,catalog.i)


def test_extra_trigger_cannot_hide_behind_existing_fk_trigger_flag():
    catalog=DeliveryCatalog()
    catalog.trigger_snapshot.append(dict(catalog.trigger_snapshot[0],label=None))
    with pytest.raises(MigrationError,match=Failure.DRIFT): v.catalog_state(catalog,catalog.i)


# The regression matrix uses literal PG17 definitions and independent catalog
# fields. The definition is display text; identity/actions come from pg_constraint.
def pg_catalog(revision):
    if revision == "0004":
        return DeliveryCatalog()
    from test_confirmation_outbox_migration import OutboxCatalog
    return OutboxCatalog()


# Captured R10 PostgreSQL 17.11 edge, not derived from the expected graph.
R10_TOAST_DEPENDENCY = dict(classid=1259, objid=16453, objsubid=0,
    refclassid=1259, refobjid=16444, refobjsubid=0, deptype="i")


@pytest.fixture
def r10_toast(monkeypatch):
    def replay(revision="0004", environment="testing"):
        catalog = type(pg_catalog(revision))(environment)
        parent = next(o for o in catalog.objects
                      if o["label"] == "delivery_table_notification_release_events")
        old_address = (parent["classid"], parent["objid"])
        parent.update(classid=1259, objid=16444)
        for edge in catalog.dependencies:
            if (edge["classid"], edge["objid"]) == old_address:
                edge.update(classid=1259, objid=16444)
            if (edge["refclassid"], edge["refobjid"]) == old_address:
                edge.update(refclassid=1259, refobjid=16444)
        catalog.dependencies.append(dict(R10_TOAST_DEPENDENCY))
        # Names pg_toast.pg_toast_16444 and notification_release_events are
        # descriptive evidence only. Acceptance must bind actual catalog OIDs.
        # The remaining fields model catalog metadata using the test owner.
        catalog.toast = [dict(classid=1259, objid=16453, kind="t", schema="pg_toast",
            owner=catalog.i.owner, persistence="p", acl=None, toast=0,
            parent=16444, parent_toast=16453, parent_kind="r", parent_schema="oaf_website",
            parent_owner=catalog.i.owner, parent_persistence="p")]
        catalog.toast_queries = []
        original_execute = catalog.execute

        def execute(sql, parameters=None):
            query = " ".join(str(sql).split())
            if "t.oid=p.reltoastrelid" in query:
                catalog.toast_queries.append((query, parameters))
                return Result(deepcopy(catalog.toast))
            return original_execute(sql, parameters)

        monkeypatch.setattr(catalog, "execute", execute)
        return catalog
    return replay


@pytest.mark.parametrize("revision", ["0004", "0005"])
@pytest.mark.parametrize("environment", ["testing", "development"])
def test_r10_generated_toast_with_exact_managed_dependencies(r10_toast, revision, environment):
    catalog = r10_toast(revision, environment)
    assert v.catalog_state(catalog, catalog.i) == catalog.marker[0]["version_num"]
    [(query, parameters)] = catalog.toast_queries
    assert parameters == {"parent": 16444, "source": 16453}
    assert "FROM pg_catalog.pg_class p" in query
    assert "JOIN pg_catalog.pg_class t ON t.oid=p.reltoastrelid" in query
    assert "JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace" in query
    assert "JOIN pg_catalog.pg_namespace pn ON pn.oid=p.relnamespace" in query
    assert "WHERE p.oid=:parent AND t.oid=:source" in query
    assert "'pg_catalog.pg_class'::pg_catalog.regclass::bigint AS classid" in query
    assert not re.search(r"\brelname\b", query)


@pytest.mark.parametrize("field,value", [
    ("classid", 1247), ("objid", 16454), ("objsubid", 1),
    ("refclassid", 1247), ("refobjid", 16445), ("refobjsubid", 1),
    ("deptype", "a"), ("deptype", "n"), ("deptype", "e"),
    ("deptype", "P"), ("deptype", "S"), ("deptype", "x"),
])
def test_r10_toast_edge_identity_and_relationship_fail_closed(r10_toast, field, value):
    catalog = r10_toast()
    catalog.dependencies[-1][field] = value
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.verify_dependencies(catalog, catalog.i, v.DELIVERY)


@pytest.mark.parametrize("field,value", [
    ("classid", 1247), ("objid", 16454), ("kind", "r"), ("schema", "public"),
    ("owner", "unauthorized_owner"), ("persistence", "u"), ("acl", "{forged_acl}"),
    ("toast", 16454), ("parent", 16445), ("parent_toast", 16454),
    ("parent_kind", "i"), ("parent_schema", "public"),
    ("parent_owner", "unauthorized_owner"), ("parent_persistence", "u"),
])
def test_r10_toast_catalog_metadata_fail_closed(r10_toast, field, value):
    catalog = r10_toast()
    catalog.toast[0][field] = value
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.verify_dependencies(catalog, catalog.i, v.DELIVERY)


@pytest.mark.parametrize("case", ["missing", "duplicate_catalog", "duplicate_edge",
    "other_managed_parent", "unknown_target", "reversed", "unexpected_ordinary", "missing_ordinary",
    "wrong_catalog", "invalid_default"])
def test_r10_toast_cannot_hide_other_dependency_drift(r10_toast, case):
    catalog = r10_toast()
    if case == "missing":
        catalog.toast.clear()
    elif case == "duplicate_catalog":
        catalog.toast *= 2
    elif case == "duplicate_edge":
        catalog.dependencies.append(dict(R10_TOAST_DEPENDENCY))
    elif case == "other_managed_parent":
        other = next(o for o in catalog.objects if o["label"] == "notification_table")
        catalog.dependencies[-1].update(refclassid=other["classid"], refobjid=other["objid"])
    elif case == "unknown_target":
        catalog.dependencies.append(dict(classid=1259, objid=16444, objsubid=0,
            refclassid=1259, refobjid=999999, refobjsubid=0, deptype="i"))
    elif case == "reversed":
        catalog.dependencies[-1].update(objid=16444, refobjid=16453)
    elif case == "unexpected_ordinary":
        catalog.dependencies.append(dict(catalog.dependencies[0], deptype="e"))
    elif case == "missing_ordinary":
        catalog.dependencies.pop(0)
    elif case == "wrong_catalog":
        next(o for o in catalog.objects if o["objid"] == 16444)["classid"] = 1247
        for edge in catalog.dependencies:
            if edge["objid"] == 16444:
                edge["classid"] = 1247
            if edge["refobjid"] == 16444:
                edge["refclassid"] = 1247
        catalog.dependencies[-1]["classid"] = 1247
    else:
        next(o for o in catalog.objects if o["label"] == "default_42_r")["label"] = "default_42_x"
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.verify_dependencies(catalog, catalog.i, v.DELIVERY)


@pytest.mark.parametrize("revision", ["0004", "0005"])
@pytest.mark.parametrize("style", ["qualified", "unqualified", "whitespace", "quoted"])
def test_independent_pg17_foreign_keys_and_checks(revision, style):
    catalog = pg_catalog(revision)
    for (table, name), entries in catalog.foreign_keys.items():
        entry = entries[0]
        target = entry["referenced_table"]
        local = ", ".join(entry["columns"])
        remote = ", ".join(entry["referenced_columns"])
        if style == "qualified":
            definition = f"FOREIGN KEY({local}) REFERENCES oaf_website.{target} ({remote})"
        elif style == "unqualified":
            definition = f"FOREIGN KEY ({local}) REFERENCES {target}({remote})"
        elif style == "whitespace":
            definition = f"FOREIGN KEY  ( {local} )\n REFERENCES  {target} ( {remote} ) ON UPDATE NO ACTION ON DELETE NO ACTION"
        else:
            local = ', '.join('"' + n + '"' for n in entry["columns"])
            remote = ', '.join('"' + n + '"' for n in entry["referenced_columns"])
            definition = f'FOREIGN KEY ({local}) REFERENCES "oaf_website"."{target}"({remote})'
        next(r for r in catalog.snapshots[table]["constraints"] if r["name"] == name)["definition"] = definition
    # Both revisions must accept the independent PostgreSQL <> ALL rendering.
    tables = ["notification_deliveries"]
    if revision == "0005":
        tables.append("notification_confirmation_intents")
    for table in tables:
        constraints = catalog.snapshots["oaf_website." + table]["constraints"]
        definitions = {"claim_check": PG_CLAIM_CHECK, "status_check": PG_STATUS_CHECK,
            "attempts_check": "CHECK (((attempts >= 0) AND (attempts <= 3)))",
            "digest_check": "CHECK (((claim_digest IS NULL) OR ((claim_digest)::text ~ '^[0-9a-f]{64}$'::text)))",
            "accepted_check": "CHECK ((((status)::text = 'accepted'::text) = (accepted_at IS NOT NULL)))"}
        for suffix, definition in definitions.items():
            next(r for r in constraints if r["name"] == table + "_" + suffix)["definition"] = definition
    assert v.catalog_state(catalog, catalog.i) == catalog.marker[0]["version_num"]


@pytest.mark.parametrize("revision", ["0004", "0005"])
@pytest.mark.parametrize("field,value", [
    ("referenced_schema", "public"), ("referenced_table", "notification_suppressions"),
    ("referenced_columns", ["token_digest"]), ("columns", ["token_digest"]),
    ("on_delete", "c"), ("on_delete", "n"), ("on_delete", "d"),
    ("on_delete", "r"), ("on_update", "c"), ("match", "f"),
])
def test_actual_fk_identity_and_actions_are_authoritative(revision, field, value):
    catalog = pg_catalog(revision)
    table = "oaf_website.notification_verification" if revision == "0004" else "oaf_website.notification_confirmation_intents"
    constraint = table.split(".")[1] + "_subscription_fk"
    # Even plausible unchanged deparser text cannot override actual catalog drift.
    catalog.foreign_keys[(table, constraint)][0][field] = value
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("field", ["columns", "referenced_columns", "both", "missing", "extra"])
def test_composite_fk_order_and_exact_cardinality(field):
    catalog = DeliveryCatalog()
    entries = catalog.foreign_keys[("oaf_website.notification_delivery_attempts", "notification_delivery_attempts_delivery_fk")]
    if field == "both":
        entries[0]["columns"].reverse()
        entries[0]["referenced_columns"].reverse()
    elif field == "missing":
        entries.clear()
    elif field == "extra":
        entries.append(deepcopy(entries[0]))
    else:
        entries[0][field].reverse()
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("definition", [
    "CHECK (status NOT IN ('claimed', 'submitting'))",
    "CHECK ((status <> ALL (ARRAY['claimed', 'submitting'])))",
    "CHECK ((((status)::text) <> ALL (((ARRAY[('claimed'::character varying)::text, 'submitting'::text])::text[]))))",
    "check (status <> all ((ARRAY['claimed', 'submitting'])::character varying[]))",
])
def test_not_in_pg17_tree_is_independently_specified(definition):
    assert validator.check_tree(definition, s.deliveries.columns) == (
        "not_in", ("column", "status"), (("text", "claimed"), ("text", "submitting")))


@pytest.mark.parametrize("definition", [
    "CHECK (status IN ('claimed', 'submitting'))",
    "CHECK ((status = ANY ((ARRAY['claimed'::character varying, 'submitting'::character varying])::text[])))",
])
def test_in_pg17_tree_is_independently_specified(definition):
    assert validator.check_tree(definition) == (
        "in", ("column", "status"), (("text", "claimed"), ("text", "submitting")))


@pytest.mark.parametrize("revision", ["0004", "0005"])
@pytest.mark.parametrize("case", ["operator", "quantifier", "value", "null", "type", "missing", "weakened", "grouping", "unsupported"])
def test_independent_pg17_check_drift_is_rejected(revision, case):
    catalog = pg_catalog(revision)
    table = "notification_deliveries" if revision == "0004" else "notification_confirmation_intents"
    constraints = catalog.snapshots["oaf_website." + table]["constraints"]
    record = next(r for r in constraints if r["name"] == table + "_claim_check")
    record["definition"] = PG_CLAIM_CHECK
    if case == "operator": record["definition"] = PG_CLAIM_CHECK.replace("<> ALL", "= ALL")
    elif case == "quantifier": record["definition"] = PG_CLAIM_CHECK.replace("<> ALL", "<> ANY")
    elif case == "value": record["definition"] = PG_CLAIM_CHECK.replace("'submitting'", "'accepted'")
    elif case == "null": record["definition"] = PG_CLAIM_CHECK.replace("'submitting'::character varying", "NULL::text")
    elif case == "type": record["definition"] = PG_CLAIM_CHECK.replace("::text[]", "::integer[]")
    elif case == "missing": constraints.remove(record)
    elif case == "weakened": record["definition"] = PG_CLAIM_CHECK + " OR claim_digest IS NULL"
    elif case == "grouping": record["definition"] = PG_CLAIM_CHECK.replace("AND (claim_digest IS NOT NULL)", "OR (claim_digest IS NOT NULL)")
    else: record["definition"] = "CHECK (coalesce(claim_digest, '') = '')"
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("definition", [
    None, "x" * 16385, "CHECK (attempts = " + "9" * 5000 + ")", "", "CHECK", "CHECK (", "CHECK ()", "CHECK (status) garbage",
    "CHECK (status @ 'claimed')", "CHECK (status);", "CHECK (status = 'unterminated)",
    "CHECK (status NOT = 'claimed')", "CHECK (status NOT BETWEEN 1 AND 3)",
    "CHECK (status = ALL (ARRAY['claimed']))", "CHECK (status <> ANY (ARRAY['claimed']))",
    "CHECK (status < ANY (ARRAY['claimed']))", "CHECK (status <> ALL ('claimed'))",
    "CHECK (status <> ALL (ARRAY[]))", "CHECK (status <> ALL (ARRAY[NULL]))",
    "CHECK (status IN ())", "CHECK (status IN (1))", "CHECK (status IN ('claimed', NULL))",
    "CHECK (status::integer = 'claimed')", "CHECK (status::character = 'claimed')",
    "CHECK (status::character varying(2) = 'cl')", "CHECK (attempts::text > '1')",
    "CHECK ((attempts >= 0)::text = 'true')", "CHECK ('claimed'::text[] = status)",
    "CHECK (ARRAY['claimed']::text = status)", "CHECK (status = ANY (ARRAY[1]))",
    "CHECK (status = ANY (ARRAY['claimed']::text[1]))", "CHECK (status IS TRUE)",
    "CHECK (NOT (status = 'claimed'))", "CHECK (status = lower('CLAIMED'))",
    "CHECK (status = 'claimed' COLLATE other)", "CHECK (__import__('os'))",
    "CHECK (status BETWEEN 0 OR 3)", "CHECK (status = ANY ARRAY['claimed'])",
    "CHECK (status = ANY (ARRAY['claimed'))", "CHECK (status IN ('claimed' 'submitting'))",
    "CHECK (" + "(" * 500 + "status" + ")" * 500 + ")",
])
def test_unsupported_or_malformed_checks_fail_closed(definition):
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        validator.check_tree(definition, s.deliveries.columns)


@pytest.mark.parametrize("left,right", [
    ("status IN ('AND')", "status IN ('and')"),
    ("status IN ('a''b')", "status IN ('ab')"),
    ("status NOT IN ('claimed')", "status IN ('claimed')"),
    ("claim_digest IS NULL", "claim_digest IS NOT NULL"),
    ("status NOT IN ('claimed')", "status NOT IN ('claimed') OR status IS NULL"),
    ("status ~ 'claimed'", "status IN ('claimed')"),
    ("attempts >= 0 AND attempts <= 3", "attempts > 0 AND attempts <= 3"),
    ("(status = 'accepted') = (accepted_at IS NOT NULL)", "status = 'accepted' OR accepted_at IS NOT NULL"),
])
def test_literals_operators_nulls_and_boolean_meaning_remain_distinct(left, right):
    assert validator.check_tree("CHECK (" + left + ")") != validator.check_tree("CHECK (" + right + ")")


def test_sql_quoted_literal_is_preserved_without_keyword_substitution():
    assert validator.check_tree("CHECK (status = 'AND IS NOT NULL IN OR a''b')") == (
        "=", ("column", "status"), ("text", "AND IS NOT NULL IN OR a'b"))


@pytest.mark.parametrize("definition,changes", [
    ("FOREIGN KEY (subscription) REFERENCES notification_suppressions(unsubscribe_digest)",
        {"referenced_table": "notification_suppressions"}),
    ("FOREIGN KEY (subscription) REFERENCES public.notifications(unsubscribe_digest)",
        {"referenced_schema": "public"}),
    ("FOREIGN KEY (subscription) REFERENCES notifications(token_digest)",
        {"referenced_columns": ["token_digest"]}),
    ("FOREIGN KEY (token_digest) REFERENCES notifications(unsubscribe_digest)",
        {"columns": ["token_digest"]}),
    ("FOREIGN KEY (subscription) REFERENCES notifications(unsubscribe_digest) ON DELETE CASCADE",
        {"on_delete": "c"}),
    ("FOREIGN KEY (subscription) REFERENCES notifications(unsubscribe_digest) ON UPDATE RESTRICT",
        {"on_update": "r"}),
])
@pytest.mark.parametrize("revision", ["0004", "0005"])
def test_independent_incorrect_fk_definitions_and_corresponding_catalog(revision, definition, changes):
    catalog = pg_catalog(revision)
    table = "notification_verification" if revision == "0004" else "notification_confirmation_intents"
    name = table + "_subscription_fk"
    next(r for r in catalog.snapshots["oaf_website." + table]["constraints"] if r["name"] == name)["definition"] = definition
    catalog.foreign_keys[("oaf_website." + table, name)][0].update(changes)
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("definition,changes", [
    ("FOREIGN KEY (subscription, event_id) REFERENCES notification_deliveries(event_id, subscription)",
        {"columns": ["subscription", "event_id"]}),
    ("FOREIGN KEY (event_id, subscription) REFERENCES notification_deliveries(subscription, event_id)",
        {"referenced_columns": ["subscription", "event_id"]}),
    ("FOREIGN KEY (subscription, event_id) REFERENCES notification_deliveries(subscription, event_id)",
        {"columns": ["subscription", "event_id"], "referenced_columns": ["subscription", "event_id"]}),
])
def test_independent_wrong_order_fk_definitions_and_catalog(definition, changes):
    catalog = DeliveryCatalog()
    table = "oaf_website.notification_delivery_attempts"
    name = "notification_delivery_attempts_delivery_fk"
    next(r for r in catalog.snapshots[table]["constraints"] if r["name"] == name)["definition"] = definition
    catalog.foreign_keys[(table, name)][0].update(changes)
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)
