"""Exact additive successor, catalog drift and execution gates; synthetic only."""
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
from alembic import op as alembic_op
from sqlalchemy import CheckConstraint,ForeignKeyConstraint,PrimaryKeyConstraint
from sqlalchemy.dialects import postgresql

from oaf_website import notification_management_schema as s, migration_validation as v, migrate as runner
from oaf_website import notification_delivery_validation as validator
from oaf_website import notification_schema as original, confirmation_outbox_schema as old_outbox
from oaf_website import notification_delivery_schema as old_delivery
from oaf_website.migration_config import IDENTITIES,Failure,MigrationError
from test_confirmation_outbox_migration import OutboxCatalog
from test_notification_delivery_migration import foreign_key_snapshots
from test_migration_artifacts import artifact_copy,write_manifest
from test_migration_operational import operational,records
from migration_offline import ROOT,Result,DriverError


def artifacts(start=v.OUTBOX):
    payload=(v.ROOT/'migrations/manifest.json').read_bytes()
    return v.validate_artifacts(expected_start=start,target=v.MANAGEMENT,manifest_hash=v.digest(payload),
        revision_hash=json.loads(payload)['revisions'][5]['sha256'])


class ManagementCatalog(OutboxCatalog):
    def __init__(self,environment='testing'):
        super().__init__(environment)
        self.marker=[dict(version_num=v.MANAGEMENT)]
        self.notification_columns.append(dict(name='preferences_revision',type='integer',required=True,identity='',generated='',
            dropped=False,position=10,dimensions=0,collation=0,has_default=True,default_expression='0'))
        self.notification_constraints.append(dict(name='notifications_revision_check',kind='c',validated=True,deferrable=False,
            deferred=False,keys=[10],no_inherit=False,local=True,inherited=0,definition='CHECK (preferences_revision >= 0)'))
        self.notification_column_acl=[dict(column=c,grantee=self.i.runtime,grantor=self.i.owner,privilege='UPDATE',grantable=False)
                                      for c in s.NOTIFICATION_MUTABLE]
        self.relations += [dict(name=o['name'],kind='r' if o['kind']=='table' else 'i',owner=self.i.owner,persistence='p',
            rls=False,force_rls=False,rules=False,triggers=o['kind']=='table',options=None)
            for o in s.OBJECTS if o['kind'] in {'table','index'}]
        self.relations.sort(key=lambda r:r['name'])
        self.types += [dict(name=name,kind=kind,owner=self.i.owner,relation=800 if kind=='c' else 0,element=801 if kind=='b' else 0)
                       for name,kind in ((s.changes.name,'c'),('_'+s.changes.name,'b'))]
        self.types.sort(key=lambda r:r['name'])
        labels=sorted({edge[0] for edge in s.EDGES}-{o['label'] for o in self.objects})
        self.objects += [dict(label=label,classid=29000+n,objid=30000+n) for n,label in enumerate(labels)]
        addresses={o['label']:(o['classid'],o['objid']) for o in self.objects}
        self.dependencies += [dict(classid=addresses[a][0],objid=addresses[a][1],objsubid=b,
            refclassid=addresses[c][0],refobjid=addresses[c][1],refobjsubid=d,deptype=e) for a,b,c,d,e in s.EDGES]
        self.foreign_keys.update(foreign_key_snapshots({
            ('oaf_website.notification_preference_changes','notification_preference_changes_subscription_fk'):
                ('notifications',['subscription'],['unsubscribe_digest'])}))
        for item in (s.intents,s.changes):
            if item is s.changes:
                self.snapshots['oaf_website.'+item.name]=deepcopy(self.snapshots['oaf_website.notification_confirmation_intents'])
                self.snapshots['oaf_website.'+item.name]['column_acl']=[]
            snapshot=self.snapshots['oaf_website.'+item.name]
            snapshot['columns']=validator.column_contract(item)
            snapshot['indexes']=validator.index_contract(item)
            snapshot['constraints']=[dict(name=c.name,kind='c' if isinstance(c,CheckConstraint) else 'f' if isinstance(c,ForeignKeyConstraint)
                else 'p' if isinstance(c,PrimaryKeyConstraint) else 'u',validated=True,deferrable=False,deferred=False,
                local=True,inherited=0,definition=validator.constraint_definition(c)) for c in sorted(item.constraints,key=lambda c:c.name)]
        self.purpose_defaults=[dict(default_column='purpose',expression="'confirmation'::character varying")]
        self.trigger_snapshot=deepcopy(sorted(old_delivery.FK_TRIGGERS+old_outbox.FK_TRIGGERS+s.FK_TRIGGERS,key=lambda r:r['label']))
        self.override=None

    def execute(self,sql,parameters=None):
        q,p=' '.join(str(sql).split()),parameters or {}
        if self.override is not None:
            result=self.override(q,p)
            if result is not None: return Result(result)
        if 'AS default_column' in q: return Result(deepcopy(self.purpose_defaults))
        if 'has_column_privilege' in q and "'oaf_website.notifications'" in q:
            return Result(p['role']==self.i.owner or p['role']==self.i.runtime and
                (p['privilege'] in {'SELECT','INSERT'} or p['privilege']=='UPDATE' and p['column'] in s.NOTIFICATION_MUTABLE))
        if 'has_column_privilege' in q and p.get('table')=='oaf_website.notification_preference_changes':
            return Result(p['role']==self.i.owner or p['role']==self.i.runtime and p['privilege'] in {'SELECT','INSERT'})
        if 'has_type_privilege' in q and p.get('name') in {'oaf_website.notification_preference_changes','oaf_website._notification_preference_changes'}:
            return Result(p['role']==self.i.owner and 'WITH GRANT OPTION' not in q)
        return super().execute(sql,parameters)


@pytest.mark.parametrize('environment',['testing','development'])
def test_complete_successor_catalog_and_effective_grants(environment):
    catalog=ManagementCatalog(environment)
    assert v.catalog_state(catalog,catalog.i)==v.MANAGEMENT


@pytest.mark.parametrize('case',['revision_column','revision_default','revision_check','immutable_email_grant','blanket_update',
    'outbox_purpose','outbox_binding','outbox_default','audit_column','audit_check','audit_acl','audit_update',
    'audit_type','audit_fk','audit_index','trigger','dependency','marker'])
def test_successor_drift_is_rejected(case):
    c=ManagementCatalog(); audit=c.snapshots['oaf_website.notification_preference_changes']; intent=c.snapshots['oaf_website.notification_confirmation_intents']
    if case=='revision_column': c.notification_columns[-1]['type']='bigint'
    if case=='revision_default': c.notification_columns[-1]['default_expression']='1'
    if case=='revision_check': c.notification_constraints[-1]['definition']='CHECK (preferences_revision >= 1)'
    if case=='immutable_email_grant': c.notification_column_acl[-1]['column']='email'
    if case=='blanket_update': c.notification_acl[-1]['privilege']='UPDATE'
    if case=='outbox_purpose': intent['columns'][-2]['required']=False
    if case=='outbox_binding': intent['columns'][-1]['type']='text'
    if case=='outbox_default': c.purpose_defaults[0]['expression']="'management'::character varying"
    if case=='audit_column': audit['columns'][0]['required']=False
    if case=='audit_check': next(r for r in audit['constraints'] if r['kind']=='c')['definition']='CHECK (TRUE)'
    if case=='audit_acl': audit['acl'][-1]['privilege']='DELETE'
    if case=='audit_update': audit['column_acl']=[dict(column='revision',grantee=c.i.runtime,grantor=c.i.owner,privilege='UPDATE',grantable=False)]
    if case=='audit_type': audit['type_acl'][0]['grantee']='PUBLIC'
    if case=='audit_fk': c.foreign_keys[('oaf_website.notification_preference_changes','notification_preference_changes_subscription_fk')][0]['on_delete']='c'
    if case=='audit_index': audit['indexes'].pop()
    if case=='trigger': c.trigger_snapshot.pop()
    if case=='dependency': c.dependencies.pop()
    if case=='marker': c.marker=[dict(version_num=v.OUTBOX)]
    with pytest.raises(MigrationError,match=Failure.DRIFT): v.catalog_state(c,c.i)


@pytest.mark.parametrize('environment',['testing','development'])
def test_minimal_additive_ddl_and_only_demonstrated_runtime_grants(environment):
    statements=[]
    def execute(statement):
        statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return Result(IDENTITIES[environment].owner)
    s.upgrade_notification_management(SimpleNamespace(execute=execute))
    sql=' '.join(statements)
    assert sum(q.startswith('\nCREATE TABLE') for q in statements)==1
    assert 'ADD COLUMN preferences_revision integer NOT NULL DEFAULT 0' in sql
    assert "ADD COLUMN purpose varchar(20) NOT NULL DEFAULT 'confirmation'" in sql
    grants=' '.join(q for q in statements if q.startswith('GRANT'))
    assert 'UPDATE (web_launch, android_launch, ios_launch, state, preferences_revision)' in grants
    assert 'DELETE' not in grants and 'WITH GRANT OPTION' not in grants
    assert 'COMMIT' not in sql and 'DROP ' not in sql and 'UPDATE oaf_website' not in sql
    assert 'preferences_revision' not in original.notifications.c
    assert 'purpose' not in old_outbox.intents.c
    assert not {'email','token','secret','body','payload'} & set(s.changes.c.keys())
    assert len(s.changes.c.subscription.foreign_keys)==1


def test_owner_only_upgrade_and_declarative_revision(monkeypatch):
    with pytest.raises(MigrationError,match=Failure.WRONG_IDENTITY):
        s.upgrade_notification_management(SimpleNamespace(execute=lambda q:Result(IDENTITIES['testing'].runtime)))
    revision=runpy.run_path(str(ROOT/v.MANAGEMENT_REVISION_FILE)); calls=[]; sentinel=object()
    monkeypatch.setattr(alembic_op,'get_bind',lambda:sentinel)
    revision['upgrade'].__globals__['upgrade_notification_management']=calls.append
    revision['upgrade'](); assert calls==[sentinel]
    assert revision['revision']==v.MANAGEMENT and revision['down_revision']==v.OUTBOX
    with pytest.raises(RuntimeError): revision['downgrade']()


@pytest.mark.parametrize('start',[v.OUTBOX,v.MANAGEMENT])
def test_only_exact_transition_and_distinct_noop_are_supported(start):
    assert artifacts(start).target==v.MANAGEMENT


@pytest.mark.parametrize('start,target',[(v.BASE,v.MANAGEMENT),(v.BASELINE,v.MANAGEMENT),(v.STATE_REQUESTS,v.MANAGEMENT),
    (v.NOTIFICATIONS,v.MANAGEMENT),(v.DELIVERY,v.MANAGEMENT),(v.MANAGEMENT,v.OUTBOX),(v.OUTBOX,'head')])
def test_jump_downgrade_stamp_or_alias_rejected(start,target):
    with pytest.raises(MigrationError,match=Failure.STARTING_REVISION):
        v.validate_artifacts(expected_start=start,target=target,manifest_hash='0'*64,revision_hash='0'*64)


@pytest.mark.parametrize('old,new', [('down_revision = "0005_confirmation_outbox"','down_revision = "0004_notification_delivery"'),
    ('upgrade_notification_management(op.get_bind())','op.get_bind().commit()'),('from alembic import op','import os\nfrom alembic import op')])
def test_rehashed_unsafe_revision_is_still_rejected(artifact_copy,old,new):
    path=artifact_copy/v.MANAGEMENT_REVISION_FILE; path.write_text(path.read_text().replace(old,new),encoding='utf-8')
    document=json.loads((artifact_copy/'migrations/manifest.json').read_bytes()); document['revisions'][5]['sha256']=v.digest(path.read_bytes())
    write_manifest(artifact_copy,document)
    with pytest.raises(MigrationError,match=Failure.ARTIFACT_HASH): artifacts()


def test_no_execution_without_owner_authority_before_credentials(monkeypatch):
    a=artifacts(); loader=Mock(side_effect=AssertionError('No credentials'))
    monkeypatch.setattr(runner,'load_migration_config',loader)
    with pytest.raises(MigrationError,match=Failure.OPERATIONAL_GATE):
        runner.run(runner.Request('upgrade','testing',a.expected_start,a.target,a.manifest_hash,a.revision_hash))
    loader.assert_not_called()


def test_synthetic_single_use_authorization_and_separate_noop(operational,monkeypatch):
    op=operational; a=artifacts()
    request=replace(op.request,expected_start=v.OUTBOX,target=v.MANAGEMENT,revision_hash=a.revision_hash)
    monkeypatch.setattr(runner,'catalog_state',lambda *args:v.MANAGEMENT if op.runner.connection.target else v.OUTBOX)
    authorization=op.issue(op.approvals(request)); assert op.run(authorization,request)['outcome']=='applied_and_verified'
    with pytest.raises(MigrationError,match=Failure.OPERATIONAL_GATE): op.run(authorization,request)
    op.clock.now+=timedelta(seconds=1); op.runner.connection.closed=False
    noop=replace(request,expected_start=v.MANAGEMENT)
    assert op.run(op.issue(op.approvals(noop)),noop)['outcome']=='verified_noop'
    assert len(records(op,'claim-*.json'))==2



# The next additive revision is prepared only. This fixture never connects.
from oaf_website import release_approval_schema as release_schema


class ReleaseCatalog(ManagementCatalog):
    def __init__(self, environment="testing"):
        super().__init__(environment)
        s = release_schema
        self.marker = [dict(version_num=v.RELEASE_APPROVALS)]
        self.relations += [dict(name=o["name"], kind="r" if o["kind"] == "table" else "i", owner=self.i.owner,
            persistence="p", rls=False, force_rls=False, rules=False, triggers=o["kind"] == "table", options=None)
            for o in s.OBJECTS if o["kind"] in {"table", "index"}]
        self.relations.sort(key=lambda r: r["name"])
        self.types += [dict(name=name, kind=kind, owner=self.i.owner, relation=900 if kind == "c" else 0,
            element=901 if kind == "b" else 0) for name,kind in ((s.revisions.name,"c"),("_"+s.revisions.name,"b"))]
        self.types.sort(key=lambda r: r["name"])
        labels = sorted({edge[0] for edge in s.EDGES} - {o["label"] for o in self.objects})
        self.objects += [dict(label=label,classid=39000+n,objid=40000+n) for n,label in enumerate(labels)]
        addresses = {o["label"]:(o["classid"],o["objid"]) for o in self.objects}
        self.dependencies += [dict(classid=addresses[a][0], objid=addresses[a][1], objsubid=b,
            refclassid=addresses[c][0], refobjid=addresses[c][1], refobjsubid=d, deptype=e) for a,b,c,d,e in s.EDGES]
        self.foreign_keys.update(foreign_key_snapshots({
            ("oaf_website.notification_release_approvals","notification_release_approvals_event_fk"):
            ("notification_release_events",["event_id"],["event_id"])}))
        item = s.revisions
        snapshot = deepcopy(self.snapshots["oaf_website.notification_preference_changes"])
        snapshot.update(columns=validator.column_contract(item), indexes=validator.index_contract(item),
            constraints=[dict(name=c.name, kind="c" if isinstance(c,CheckConstraint) else "f" if isinstance(c,ForeignKeyConstraint)
                else "p" if isinstance(c,PrimaryKeyConstraint) else "u", validated=True,deferrable=False,deferred=False,
                local=True,inherited=0,definition=validator.constraint_definition(c)) for c in sorted(item.constraints,key=lambda c:c.name)])
        self.snapshots["oaf_website."+item.name] = snapshot
        self.trigger_snapshot = sorted(self.trigger_snapshot + s.FK_TRIGGERS, key=lambda r:r["label"])

    def execute(self, sql, parameters=None):
        q,p = " ".join(str(sql).split()), parameters or {}
        if "has_column_privilege" in q and p.get("table") == "oaf_website.notification_release_approvals":
            return Result(p["role"] == self.i.owner or p["role"] == self.i.runtime and p["privilege"] in {"SELECT","INSERT"})
        if "has_type_privilege" in q and p.get("name") in {"oaf_website.notification_release_approvals", "oaf_website._notification_release_approvals"}:
            return Result(p["role"] == self.i.owner and "WITH GRANT OPTION" not in q)
        return super().execute(sql, parameters)


@pytest.mark.parametrize("environment", ["testing","development"])
def test_release_approval_catalog_uses_append_only_grants_and_exact_dependencies(environment):
    catalog = ReleaseCatalog(environment)
    assert v.catalog_state(catalog,catalog.i) == v.RELEASE_APPROVALS


@pytest.mark.parametrize("case", ["column", "acl", "dependency", "marker", "trigger", "type", "fork_index"])
def test_release_approval_catalog_rejects_drift(case):
    c = ReleaseCatalog()
    snapshot = c.snapshots["oaf_website.notification_release_approvals"]
    if case == "column": snapshot["columns"][0]["required"] = False
    if case == "acl": snapshot["acl"][-1]["privilege"] = "UPDATE"
    if case == "dependency": c.dependencies.pop()
    if case == "marker": c.marker = [dict(version_num=v.MANAGEMENT)]
    if case == "trigger": c.trigger_snapshot.pop()
    if case == "type": snapshot["type_acl"][0]["grantee"] = "PUBLIC"
    if case == "fork_index": snapshot["indexes"].pop()
    with pytest.raises(MigrationError, match=Failure.DRIFT): v.catalog_state(c,c.i)


@pytest.mark.parametrize("start", [v.MANAGEMENT, v.RELEASE_APPROVALS])
def test_release_artifact_allows_only_exact_successor_or_noop(start):
    payload = (v.ROOT/"migrations/manifest.json").read_bytes()
    document = json.loads(payload)
    assert v.validate_artifacts(expected_start=start,target=v.RELEASE_APPROVALS,
        manifest_hash=v.digest(payload),revision_hash=document["revisions"][6]["sha256"]).target == v.RELEASE_APPROVALS


@pytest.mark.parametrize("mutation", ["operation", "parent", "identity", "empty"])
def test_release_revision_source_is_exactly_declarative(artifact_copy, mutation):
    path = artifact_copy/v.RELEASE_REVISION_FILE
    source = path.read_text()
    source = source.replace("op.get_bind()", "None") if mutation == "operation" else source.replace(
        'down_revision = "0006_notification_management"', 'down_revision = "0005_confirmation_outbox"') if mutation == "parent" else source.replace(
        'revision = "0007_release_approvals"', 'revision = "0007_other"') if mutation == "identity" else ""
    path.write_text(source, encoding="utf-8")
    document = json.loads((artifact_copy/"migrations/manifest.json").read_bytes())
    document["revisions"][6]["sha256"] = v.digest(path.read_bytes())
    write_manifest(artifact_copy, document)
    from test_migration_artifacts import verify
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH): verify(artifact_copy)


@pytest.mark.parametrize("environment", ["testing", "development"])
def test_release_approval_ddl_is_additive_owner_only_and_not_executed(environment, monkeypatch):
    statements=[]
    def execute(statement):
        statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return Result(IDENTITIES[environment].owner)
    release_schema.upgrade_release_approvals(SimpleNamespace(execute=execute))
    assert sum("CREATE TABLE" in q for q in statements) == 1
    grants = " ".join(q for q in statements if q.startswith("GRANT"))
    assert "SELECT, INSERT" in grants and "UPDATE" not in grants and "DELETE" not in grants
    with pytest.raises(MigrationError, match=Failure.WRONG_IDENTITY):
        release_schema.upgrade_release_approvals(SimpleNamespace(execute=lambda q:Result(IDENTITIES[environment].runtime)))
    revision = runpy.run_path(str(ROOT/v.RELEASE_REVISION_FILE))
    calls=[]; sentinel=object()
    monkeypatch.setattr(alembic_op,"get_bind",lambda:sentinel)
    revision["upgrade"].__globals__["upgrade_release_approvals"]=calls.append
    revision["upgrade"]()
    assert calls == [sentinel] and revision["down_revision"] == v.MANAGEMENT
    with pytest.raises(RuntimeError): revision["downgrade"]()
