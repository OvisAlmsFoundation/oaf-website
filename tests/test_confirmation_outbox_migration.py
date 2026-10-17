"""0005 exact source lineage and synthetic catalog/authority tests; no live DDL."""
import migration_offline as isolation
isolation.require_early_registration()

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
import runpy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, PrimaryKeyConstraint
from sqlalchemy.dialects import postgresql
from alembic import op as alembic_op

from oaf_website import confirmation_outbox_schema as s, notification_delivery_schema as old
from oaf_website import migration_validation as v, notification_delivery_validation as validator, migrate as m
from oaf_website.migration_config import IDENTITIES, Failure, MigrationError
from migration_offline import ROOT, Result, DriverError
from test_notification_delivery_migration import DeliveryCatalog, foreign_key_snapshots
from test_migration_artifacts import artifact_copy, write_manifest
from test_migration_operational import operational, records


def artifacts(start=v.DELIVERY):
    payload = (v.ROOT / "migrations/manifest.json").read_bytes()
    return v.validate_artifacts(expected_start=start,target=v.OUTBOX,manifest_hash=v.digest(payload),
        revision_hash=json.loads(payload)["revisions"][4]["sha256"])


class OutboxCatalog(DeliveryCatalog):
    def __init__(self, environment="testing"):
        super().__init__(environment)
        self.marker = [dict(version_num=v.OUTBOX)]
        self.foreign_keys.update(foreign_key_snapshots({
            ("oaf_website.notification_confirmation_intents", "notification_confirmation_intents_subscription_fk"):
                ("notifications", ["subscription"], ["unsubscribe_digest"]),
            ("oaf_website.notification_confirmation_attempts", "notification_confirmation_attempts_intent_fk"):
                ("notification_confirmation_intents", ["intent"], ["intent"]),
        }))
        trigger_tables = {t["relation"] for t in old.FK_TRIGGERS+s.FK_TRIGGERS}
        for row in self.relations: row["triggers"] = row["name"] in trigger_tables
        self.relations += [dict(name=o["name"],kind="r" if o["kind"]=="table" else "i",owner=self.i.owner,
            persistence="p",rls=False,force_rls=False,rules=False,triggers=o["name"] in trigger_tables,options=None)
            for o in s.OBJECTS if o["kind"] in {"table","index"}]
        self.relations.sort(key=lambda r:r["name"])
        self.types += [dict(name=name,kind=kind,owner=self.i.owner,relation=700 if kind=="c" else 0,
            element=701 if kind=="b" else 0) for item in s.TABLES for name,kind in ((item.name,"c"),("_"+item.name,"b"))]
        self.types.sort(key=lambda r:r["name"])
        labels = sorted({edge[0] for edge in s.EDGES})
        self.objects += [dict(label=label,classid=19000+n,objid=20000+n) for n,label in enumerate(labels)]
        addresses = {o["label"]:(o["classid"],o["objid"]) for o in self.objects}
        self.dependencies += [dict(classid=addresses[a][0],objid=addresses[a][1],objsubid=b,
            refclassid=addresses[c][0],refobjid=addresses[c][1],refobjsubid=d,deptype=e) for a,b,c,d,e in s.EDGES]
        for item in s.TABLES:
            constraints = []
            for c in sorted(item.constraints,key=lambda c:c.name):
                kind = "c" if isinstance(c,CheckConstraint) else "f" if isinstance(c,ForeignKeyConstraint) else "p" if isinstance(c,PrimaryKeyConstraint) else "u"
                constraints.append(dict(name=c.name,kind=kind,validated=True,deferrable=False,deferred=False,
                    local=True,inherited=0,definition=validator.constraint_definition(c)))
            self.snapshots["oaf_website."+item.name] = dict(columns=validator.column_contract(item),constraints=constraints,
                indexes=validator.index_contract(item),inheritance=False,type_pair=True,
                acl=[dict(grantee=self.i.owner,grantor=self.i.owner,privilege=p,grantable=False)
                    for p in ("SELECT","INSERT","UPDATE","DELETE","TRUNCATE","REFERENCES","TRIGGER","MAINTAIN")]
                    + [dict(grantee=self.i.runtime,grantor=self.i.owner,privilege=p,grantable=False) for p in ("SELECT","INSERT")],
                column_acl=[dict(column=c,grantee=self.i.runtime,grantor=self.i.owner,privilege="UPDATE",grantable=False) for c in s.MUTABLE[item.name]],
                type_acl=[dict(grantee=self.i.owner,grantor=self.i.owner,privilege="USAGE",grantable=False)])
        self.trigger_snapshot = deepcopy(sorted(old.FK_TRIGGERS+s.FK_TRIGGERS,key=lambda r:r["label"]))

    def execute(self, sql, parameters=None):
        q, p = " ".join(str(sql).split()), parameters or {}
        name = p.get("table","").removeprefix("oaf_website.")
        if name in s.MUTABLE and "has_column_privilege" in q:
            value = p["role"]==self.i.owner or p["role"]==self.i.runtime and (p["privilege"] in {"SELECT","INSERT"} or p["privilege"]=="UPDATE" and p["column"] in s.MUTABLE[name])
            return Result(value)
        if "has_type_privilege" in q and any(p.get("name") in {"oaf_website."+t.name,"oaf_website._"+t.name} for t in s.TABLES):
            return Result(p["role"]==self.i.owner and "WITH GRANT OPTION" not in q)
        return super().execute(sql, parameters)


@pytest.mark.parametrize("environment", ["testing","development"])
def test_0005_exact_catalog_and_narrow_runtime_privileges(environment):
    catalog = OutboxCatalog(environment)
    assert v.catalog_state(catalog,catalog.i) == v.OUTBOX


@pytest.mark.parametrize("case", ["column","check","fk","index","acl","column_acl","type_acl","type_pair","inheritance","trigger","dependency","relation","type","marker"])
def test_outbox_drift_is_rejected(case):
    c = OutboxCatalog()
    snap = c.snapshots["oaf_website.notification_confirmation_intents"]
    if case=="column": snap["columns"][0]["required"]=False
    if case=="check": next(r for r in snap["constraints"] if r["kind"]=="c")["definition"]="CHECK (True)"
    if case=="fk": c.foreign_keys[("oaf_website.notification_confirmation_intents", "notification_confirmation_intents_subscription_fk")][0]["on_delete"]="c"
    if case=="index": snap["indexes"].pop()
    if case=="acl": snap["acl"][-1]["grantee"]="PUBLIC"
    if case=="column_acl": snap["column_acl"][0]["column"]="intent"
    if case=="type_acl": snap["type_acl"][0]["grantee"]="PUBLIC"
    if case=="type_pair": snap["type_pair"]=False
    if case=="inheritance": snap["inheritance"]=True
    if case=="trigger": c.trigger_snapshot.pop()
    if case=="dependency": c.dependencies.pop()
    if case=="relation": c.relations.pop()
    if case=="type": c.types[0]["owner"]=c.i.runtime
    if case=="marker": c.marker=[dict(version_num=v.DELIVERY)]
    with pytest.raises(MigrationError,match=Failure.DRIFT): v.catalog_state(c,c.i)


@pytest.mark.parametrize("environment", ["testing","development"])
def test_additive_source_ddl_only_uses_expected_owner(environment):
    sql=[]
    def execute(statement):
        sql.append(str(statement.compile(dialect=postgresql.dialect())))
        return Result(IDENTITIES[environment].owner)
    s.upgrade_confirmation_outbox(SimpleNamespace(execute=execute))
    joined=" ".join(sql)
    assert sum(q.startswith("\nCREATE TABLE") for q in sql)==2
    assert "ALTER TABLE" not in joined and "COMMIT" not in joined
    assert "REFERENCES oaf_website.notifications (unsubscribe_digest)" in joined
    assert "notification_confirmation_intents_retry" in joined and "notification_confirmation_intents_lease" in joined
    grants=" ".join(q for q in sql if q.startswith("GRANT"))
    assert "DELETE" not in grants and "WITH GRANT OPTION" not in grants
    assert "GRANT UPDATE (status, attempts" in grants
    assert all(c not in s.MUTABLE[s.intents.name] for c in ("intent","subscription","token_digest","created_at"))
    assert not {"email","token","body","secret","api_key"} & set(s.intents.c.keys())


def test_revision_exact_helper_and_runtime_ddl_denial(monkeypatch):
    with pytest.raises(MigrationError,match=Failure.WRONG_IDENTITY):
        s.upgrade_confirmation_outbox(SimpleNamespace(execute=lambda q:Result(IDENTITIES["testing"].runtime)))
    revision=runpy.run_path(str(ROOT/v.OUTBOX_REVISION_FILE))
    calls=[]; sentinel=object()
    monkeypatch.setattr(alembic_op,"get_bind",lambda:sentinel)
    revision["upgrade"].__globals__["upgrade_confirmation_outbox"]=calls.append
    revision["upgrade"]()
    assert calls==[sentinel]
    assert revision["revision"]==v.OUTBOX and revision["down_revision"]==v.DELIVERY
    with pytest.raises(RuntimeError): revision["downgrade"]()


def test_transition_noop_and_unsigned_runner_denied_before_credentials(monkeypatch):
    assert artifacts().expected_start==v.DELIVERY
    assert artifacts(v.OUTBOX).target==v.OUTBOX
    a=artifacts()
    loader=Mock(side_effect=AssertionError("No credential access"))
    monkeypatch.setattr(m,"load_migration_config",loader)
    with pytest.raises(MigrationError,match=Failure.OPERATIONAL_GATE):
        m.run(m.Request("upgrade","testing",a.expected_start,a.target,a.manifest_hash,a.revision_hash))
    loader.assert_not_called()


@pytest.mark.parametrize("start,target", [(v.BASE,v.OUTBOX),(v.BASELINE,v.OUTBOX),(v.STATE_REQUESTS,v.OUTBOX),
    (v.NOTIFICATIONS,v.OUTBOX),(v.OUTBOX,v.DELIVERY),(v.DELIVERY,"head")])
def test_only_exact_single_revision_transition_allowed(start,target):
    with pytest.raises(MigrationError,match=Failure.STARTING_REVISION):
        v.validate_artifacts(expected_start=start,target=target,manifest_hash="0"*64,revision_hash="0"*64)


@pytest.mark.parametrize("field,value", [("parent",v.NOTIFICATIONS),("grants",[]),("target_state",v.DELIVERY)])
def test_fifth_revision_manifest_cannot_be_redefined(artifact_copy,field,value):
    p=artifact_copy/"migrations/manifest.json"; d=json.loads(p.read_bytes())
    d["revisions"][4][field]=value; write_manifest(artifact_copy,d)
    with pytest.raises(MigrationError,match=Failure.ARTIFACT_HASH): artifacts()


@pytest.mark.parametrize("old,new", [('down_revision = "0004_notification_delivery"','down_revision = "0003_notifications"'),
    ('upgrade_confirmation_outbox(op.get_bind())','op.get_bind().commit()'),
    ('from alembic import op','import os\nfrom alembic import op'),
    ('raise RuntimeError("Ordinary migration downgrade is prohibited.")','pass')])
def test_rehashed_unsafe_successor_source_rejected(artifact_copy,old,new):
    p=artifact_copy/v.OUTBOX_REVISION_FILE; p.write_text(p.read_text().replace(old,new),encoding="utf-8")
    d=json.loads((artifact_copy/"migrations/manifest.json").read_bytes()); d["revisions"][4]["sha256"]=v.digest(p.read_bytes())
    write_manifest(artifact_copy,d)
    with pytest.raises(MigrationError,match=Failure.ARTIFACT_HASH): artifacts()


def test_revision_docstring_optional(artifact_copy):
    p=artifact_copy/v.OUTBOX_REVISION_FILE; p.write_text(p.read_text().split("\n",1)[1],encoding="utf-8")
    d=json.loads((artifact_copy/"migrations/manifest.json").read_bytes()); d["revisions"][4]["sha256"]=v.digest(p.read_bytes())
    write_manifest(artifact_copy,d)
    assert artifacts().target==v.OUTBOX


def test_synthetic_authority_is_single_use_and_noop_needs_distinct_authorization(operational,monkeypatch):
    op=operational; a=artifacts()
    request=replace(op.request,expected_start=v.DELIVERY,target=v.OUTBOX,revision_hash=a.revision_hash)
    monkeypatch.setattr(m,"catalog_state",lambda *args:v.OUTBOX if op.runner.connection.target else v.DELIVERY)
    authorization=op.issue(op.approvals(request))
    assert op.run(authorization,request)["outcome"]=="applied_and_verified"
    with pytest.raises(MigrationError,match=Failure.OPERATIONAL_GATE): op.run(authorization,request)
    op.clock.now+=timedelta(seconds=1)
    noop=replace(request,expected_start=v.OUTBOX); op.runner.connection.closed=False
    assert op.run(op.issue(op.approvals(noop)),noop)["outcome"]=="verified_noop"
    assert len(records(op,"claim-*.json"))==2


@pytest.mark.parametrize("phase,certainty",[("revision","not_invoked"),("commit","uncertain")])
def test_synthetic_failures_preserve_claims_and_uncertainty(operational,monkeypatch,phase,certainty):
    op=operational; a=artifacts()
    request=replace(op.request,expected_start=v.DELIVERY,target=v.OUTBOX,revision_hash=a.revision_hash)
    monkeypatch.setattr(m,"catalog_state",lambda *args:v.OUTBOX if op.runner.connection.target else v.DELIVERY)
    op.runner.connection.hooks[phase]=DriverError("08006" if phase=="commit" else "40P01")
    authorization=op.issue(op.approvals(request))
    with pytest.raises(MigrationError) as caught: op.run(authorization,request)
    assert caught.value.operational_result["commit_certainty"]==certainty
    assert len(records(op,"claim-*.json"))==1
