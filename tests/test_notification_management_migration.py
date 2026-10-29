"""Exact additive successor, catalog drift and execution gates; synthetic only."""
import migration_offline as isolation
isolation.require_early_registration()

from collections import Counter
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


class WebCatalog(ReleaseCatalog):
    def __init__(self, environment="testing"):
        super().__init__(environment)
        from oaf_website import web_launch_schema as web
        self.marker = [dict(version_num=v.WEB_LAUNCH)]
        snapshot = self.snapshots["oaf_website.notification_release_events"]
        for constraint in snapshot["constraints"]:
            if constraint["name"] in web.CHECKS:
                constraint["definition"] = "CHECK (" + web.CHECKS[constraint["name"]] + ")"
        addresses = {o["label"]:(o["classid"],o["objid"]) for o in self.objects}
        # Independent explicit catalog dependencies for platform (4) and release_id (5).
        source = addresses["delivery_constraint_notification_release_events_content_check"]
        target = addresses["delivery_table_notification_release_events"]
        self.dependencies += [dict(classid=source[0], objid=source[1], objsubid=0,
            refclassid=target[0], refobjid=target[1], refobjsubid=column, deptype=kind)
            for column in (4,5) for kind in ("a","n")]


class StateCatalog(WebCatalog):
    """Synthetic catalog using the accepted PostgreSQL 17 dependency observation."""
    def __init__(self, environment="testing"):
        super().__init__(environment)
        from oaf_website import state_availability_schema as state
        self.marker = [dict(version_num=v.STATE_AVAILABILITY)]
        self.relations.append(dict(name="notification_release_events_state", kind="i", owner=self.i.owner,
            persistence="p", rls=False, force_rls=False, rules=False, triggers=False, options=None))
        self.relations.sort(key=lambda row: row["name"])
        snapshot = self.snapshots["oaf_website.notification_release_events"]
        snapshot["constraints"] = [dict(name=c.name, kind="c" if isinstance(c, CheckConstraint) else "p",
            validated=True, deferrable=False, deferred=False, local=True, inherited=0,
            definition=validator.constraint_definition(c)) for c in sorted(state.events.constraints, key=lambda c:c.name)]
        snapshot["indexes"] = [dict(name="notification_release_events_launch",
            definition="CREATE UNIQUE INDEX notification_release_events_launch ON oaf_website.notification_release_events USING btree (environment, platform) WHERE ((platform)::text <> 'state'::text)"),
            dict(name="notification_release_events_pk", definition="CREATE UNIQUE INDEX notification_release_events_pk ON oaf_website.notification_release_events USING btree (event_id)"),
            dict(name="notification_release_events_state", definition="CREATE UNIQUE INDEX notification_release_events_state ON oaf_website.notification_release_events USING btree (environment, platform, release_id) WHERE ((platform)::text = 'state'::text)")]
        obsolete = next(obj for obj in self.objects if obj["label"] == "delivery_constraint_notification_release_events_launch")
        old_index = next(obj for obj in self.objects if obj["label"] == "delivery_index_notification_release_events_launch")
        excluded = {(obj["classid"], obj["objid"]) for obj in (obsolete, old_index)}
        self.objects.remove(obsolete)
        self.dependencies = [edge for edge in self.dependencies if (edge["classid"], edge["objid"]) not in excluded]
        self.objects.append(dict(label="delivery_index_notification_release_events_state", classid=49000, objid=50000))
        addresses = {obj["label"]:(obj["classid"], obj["objid"]) for obj in self.objects}
        target = addresses["delivery_table_notification_release_events"]
        for label, columns in (("delivery_index_notification_release_events_launch", (3,4,4)),
                               ("delivery_index_notification_release_events_state", (3,4,4,5))):
            source = addresses[label]
            self.dependencies += [dict(classid=source[0], objid=source[1], objsubid=0, refclassid=target[0],
                refobjid=target[1], refobjsubid=column, deptype="a") for column in columns]


@pytest.mark.parametrize("environment", ["testing", "development"])
def test_state_catalog_preserves_ownership_least_privilege_and_exact_scope(environment):
    catalog = StateCatalog(environment)
    assert v.catalog_state(catalog, catalog.i) == v.STATE_AVAILABILITY


def test_state_index_dependency_counts_match_verified_postgresql_17():
    from oaf_website import state_availability_schema as state
    assert Counter(map(tuple, state.ADDED_EDGES)) == Counter({
        ("delivery_index_notification_release_events_launch", 0, "delivery_table_notification_release_events", 3, "a"): 1,
        ("delivery_index_notification_release_events_launch", 0, "delivery_table_notification_release_events", 4, "a"): 2,
        ("delivery_index_notification_release_events_state", 0, "delivery_table_notification_release_events", 3, "a"): 1,
        ("delivery_index_notification_release_events_state", 0, "delivery_table_notification_release_events", 4, "a"): 2,
        ("delivery_index_notification_release_events_state", 0, "delivery_table_notification_release_events", 5, "a"): 1,
    })
    assert len(state.ADDED_EDGES) == 7


@pytest.mark.parametrize("index,column", [("launch", 3), ("launch", 4), ("state", 3), ("state", 4), ("state", 5)])
@pytest.mark.parametrize("case", ["missing", "additional", "wrong_type", "source_subobject", "referenced_column",
    "source_identity", "target_identity"])
def test_state_index_dependency_identity_and_multiplicity_fail_closed(index, column, case):
    catalog = StateCatalog()
    addresses = {obj["label"]:(obj["classid"], obj["objid"]) for obj in catalog.objects}
    source = addresses["delivery_index_notification_release_events_" + index]
    edge = next(edge for edge in catalog.dependencies
                if (edge["classid"], edge["objid"]) == source and edge["refobjsubid"] == column)
    if case == "missing": catalog.dependencies.remove(edge)
    if case == "additional": catalog.dependencies.append(deepcopy(edge))
    if case == "wrong_type": edge["deptype"] = "n"
    if case == "source_subobject": edge["objsubid"] = 1
    if case == "referenced_column": edge["refobjsubid"] = 2
    if case == "source_identity":
        other = "state" if index == "launch" else "launch"
        edge["classid"], edge["objid"] = addresses["delivery_index_notification_release_events_" + other]
    if case == "target_identity": edge["refclassid"], edge["refobjid"] = addresses["schema"]
    with pytest.raises(MigrationError, match=Failure.DRIFT): v.verify_dependencies(catalog, catalog.i, v.STATE_AVAILABILITY)


@pytest.mark.parametrize("index", ["launch", "state"])
def test_state_index_rejects_redistributed_duplicates_with_same_identities_and_total_count(index):
    catalog = StateCatalog()
    source = next(obj for obj in catalog.objects if obj["label"] == "delivery_index_notification_release_events_" + index)
    edge = next(edge for edge in catalog.dependencies if (edge["classid"], edge["objid"]) ==
                (source["classid"], source["objid"]) and edge["refobjsubid"] == 4)
    # Moving one of the two platform rows preserves the identity set and row total.
    edge["refobjsubid"] = 3
    with pytest.raises(MigrationError, match=Failure.DRIFT): v.verify_dependencies(catalog, catalog.i, v.STATE_AVAILABILITY)


@pytest.mark.parametrize("case", ["platform", "content", "state_code", "untyped_content", "predicate", "state_predicate",
    "nonunique", "keys", "extra_index", "missing_index", "index_name", "dependency", "extra_dependency",
    "old_unique_dependency", "owner", "acl", "column_acl", "type_acl", "effective_acl", "marker"])
def test_state_catalog_rejects_weakened_constraints_uniqueness_dependencies_and_grants(case):
    catalog = StateCatalog()
    snapshot = catalog.snapshots["oaf_website.notification_release_events"]
    constraint = next(c for c in snapshot["constraints"] if c["name"].endswith("content_check"))
    if case == "platform": next(c for c in snapshot["constraints"] if c["name"].endswith("platform_check"))["definition"] = "CHECK (platform IN ('android','ios','web'))"
    if case == "content": constraint["definition"] = constraint["definition"].replace("state-availability-v1", "state-v2")
    if case == "state_code": constraint["definition"] = constraint["definition"].replace("'CA'", "'DC'")
    if case == "untyped_content": constraint["definition"] = "CHECK (content_version IN ('mobile-launch-v1','web-launch-v1','state-availability-v1'))"
    if case == "predicate": snapshot["indexes"][0]["definition"] = snapshot["indexes"][0]["definition"].replace("<>", "=")
    if case == "state_predicate": snapshot["indexes"][2]["definition"] = snapshot["indexes"][2]["definition"].split(" WHERE ")[0]
    if case == "nonunique": snapshot["indexes"][2]["definition"] = snapshot["indexes"][2]["definition"].replace(" UNIQUE", "")
    if case == "keys": snapshot["indexes"][0]["definition"] = snapshot["indexes"][0]["definition"].replace("(environment, platform)", "(environment, platform, release_id)")
    if case == "extra_index": snapshot["indexes"].append(deepcopy(snapshot["indexes"][-1]))
    if case == "missing_index": snapshot["indexes"].pop()
    if case == "index_name": snapshot["indexes"][-1]["name"] = "unapproved_index"
    if case == "dependency": catalog.dependencies.pop()
    if case == "extra_dependency": catalog.dependencies.append(deepcopy(catalog.dependencies[-1]))
    if case == "old_unique_dependency": catalog.dependencies[-1]["deptype"] = "i"
    if case == "owner": catalog.relations[-1]["owner"] = catalog.i.runtime
    if case == "acl": snapshot["acl"][-1]["privilege"] = "UPDATE"
    if case == "column_acl": snapshot["column_acl"].append(dict(column="release_id", grantee=catalog.i.runtime,
        grantor=catalog.i.owner, privilege="UPDATE", grantable=False))
    if case == "type_acl": snapshot["type_acl"][0]["grantee"] = "PUBLIC"
    if case == "effective_acl": catalog.effective_override = True
    if case == "marker": catalog.marker = [dict(version_num=v.WEB_LAUNCH)]
    with pytest.raises(MigrationError, match=Failure.DRIFT): v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("start", [v.WEB_LAUNCH, v.STATE_AVAILABILITY])
def test_state_artifact_allows_only_exact_successor_and_noop(start):
    document = json.loads((ROOT/"migrations/manifest.json").read_bytes())
    assert v.validate_artifacts(expected_start=start, target=v.STATE_AVAILABILITY,
        manifest_hash=v.digest((ROOT/"migrations/manifest.json").read_bytes()),
        revision_hash=document["revisions"][8]["sha256"]).target == v.STATE_AVAILABILITY


@pytest.mark.parametrize("start", [v.WEB_LAUNCH, v.STATE_AVAILABILITY])
@pytest.mark.parametrize("observed", [None, *v.STATE_CONTRACT])
def test_state_audit_revision_inventory_is_exact_and_issues_no_authority(tmp_path, start, observed):
    from dataclasses import asdict
    from oaf_website import migration_authority as authority
    request = runner.Request("verify", "testing", start, v.STATE_AVAILABILITY, "0"*64, "1"*64)
    run_id = "00000000-0000-0000-0000-000000000001"
    sink = authority.FileAuditSink(tmp_path, run_id, "00000000-0000-0000-0000-000000000002",
        asdict(request), None)
    event = runner._Evidence(request, IDENTITIES["testing"], run_id).event()
    accepted = sink._event(replace(event, observed_start=observed))
    assert accepted["observed_start"] == observed
    assert not accepted["operational_authority_verified"] and not accepted["database_commit_confirmed"]
    with pytest.raises(MigrationError, match=Failure.OPERATIONAL_GATE):
        sink._event(replace(event, observed_start="0010_unreviewed"))
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("start,target", [(v.RELEASE_APPROVALS,v.STATE_AVAILABILITY),
    (v.STATE_AVAILABILITY,v.WEB_LAUNCH), (v.BASE,v.STATE_AVAILABILITY)])
def test_state_artifact_cannot_skip_ancestor_or_downgrade(start, target):
    with pytest.raises(MigrationError, match=Failure.STARTING_REVISION):
        v.validate_artifacts(expected_start=start, target=target, manifest_hash="0"*64, revision_hash="0"*64)


@pytest.mark.parametrize("mutation", ["operation", "parent", "identity", "empty", "manifest", "no_docstring"])
def test_state_revision_exact_shape(artifact_copy, mutation):
    path = artifact_copy/v.STATE_REVISION_FILE
    source = path.read_text()
    if mutation == "operation": source = source.replace("op.get_bind()", "None")
    if mutation == "parent": source = source.replace('down_revision = "0008_web_launch"', 'down_revision = "0007_release_approvals"')
    if mutation == "identity": source = source.replace('revision = "0009_state_availability"', 'revision = "0009_other"')
    if mutation == "empty": source = ""
    if mutation == "no_docstring": source = "\n".join(source.splitlines()[1:])
    path.write_text(source, encoding="utf-8")
    document = json.loads((artifact_copy/"migrations/manifest.json").read_bytes())
    document["revisions"][8]["sha256"] = v.digest(path.read_bytes())
    if mutation == "manifest": document["revisions"][8]["grants"] = v.RELEASE_GRANTS
    write_manifest(artifact_copy, document)
    from test_migration_artifacts import verify
    if mutation == "no_docstring": assert verify(artifact_copy).target == v.BASELINE
    else:
        with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH): verify(artifact_copy)


@pytest.mark.parametrize("environment", ["testing", "development"])
def test_state_ddl_only_changes_event_checks_and_scoped_uniqueness_under_registered_owner(environment, monkeypatch):
    from oaf_website import state_availability_schema as state
    statements = []
    def execute(statement):
        statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return Result(IDENTITIES[environment].owner)
    state.upgrade_state_availability(SimpleNamespace(execute=execute))
    assert len(statements) == 8
    assert sum("DROP CONSTRAINT" in q for q in statements) == 3
    assert sum("ADD CONSTRAINT" in q for q in statements) == 2
    assert sum(q.startswith("CREATE UNIQUE INDEX") for q in statements) == 2
    assert all("notification_release_events" in q for q in statements[1:])
    assert not any(word in " ".join(statements) for word in ("GRANT", "REVOKE", "INSERT", "DELETE", "COMMIT"))
    with pytest.raises(MigrationError, match=Failure.WRONG_IDENTITY):
        state.upgrade_state_availability(SimpleNamespace(execute=lambda q:Result(IDENTITIES[environment].runtime)))
    revision = runpy.run_path(str(ROOT/v.STATE_REVISION_FILE))
    calls = []; sentinel = object()
    monkeypatch.setattr(alembic_op, "get_bind", lambda:sentinel)
    revision["upgrade"].__globals__["upgrade_state_availability"] = calls.append
    revision["upgrade"]()
    assert calls == [sentinel] and revision["down_revision"] == v.WEB_LAUNCH
    with pytest.raises(RuntimeError): revision["downgrade"]()


@pytest.mark.parametrize("environment", ["testing", "development"])
def test_web_catalog_extends_only_typed_event_checks_and_preserves_all_acl(environment):
    catalog = WebCatalog(environment)
    assert v.catalog_state(catalog, catalog.i) == v.WEB_LAUNCH


@pytest.mark.parametrize("case", ["mobile_platform", "untyped_content", "web_id", "dependency", "extra_dependency", "marker", "acl"])
def test_web_catalog_rejects_loose_constraints_and_drift(case):
    catalog = WebCatalog()
    checks = catalog.snapshots["oaf_website.notification_release_events"]["constraints"]
    if case == "mobile_platform":
        next(c for c in checks if c["name"].endswith("platform_check"))["definition"] = "CHECK (platform IN ('android','ios'))"
    if case == "untyped_content":
        next(c for c in checks if c["name"].endswith("content_check"))["definition"] = "CHECK (content_version IN ('mobile-launch-v1','web-launch-v1'))"
    if case == "web_id":
        c = next(c for c in checks if c["name"].endswith("content_check"))
        c["definition"] = c["definition"].replace(" AND release_id = 'gramanna-web'", "")
    if case == "dependency": catalog.dependencies.pop()
    if case == "extra_dependency": catalog.dependencies.append(deepcopy(catalog.dependencies[-1]))
    if case == "marker": catalog.marker = [dict(version_num=v.RELEASE_APPROVALS)]
    if case == "acl": catalog.snapshots["oaf_website.notification_release_events"]["acl"][-1]["privilege"] = "UPDATE"
    with pytest.raises(MigrationError, match=Failure.DRIFT): v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("start", [v.RELEASE_APPROVALS, v.WEB_LAUNCH])
def test_web_artifact_exact_successor_and_noop(start):
    document = json.loads((ROOT/"migrations/manifest.json").read_bytes())
    assert v.validate_artifacts(expected_start=start, target=v.WEB_LAUNCH,
        manifest_hash=v.digest((ROOT/"migrations/manifest.json").read_bytes()),
        revision_hash=document["revisions"][7]["sha256"]).target == v.WEB_LAUNCH


@pytest.mark.parametrize("start,target", [(v.MANAGEMENT,v.WEB_LAUNCH), (v.WEB_LAUNCH,v.RELEASE_APPROVALS), (v.BASE,v.WEB_LAUNCH)])
def test_web_migration_cannot_skip_ancestor_or_downgrade(start, target):
    with pytest.raises(MigrationError, match=Failure.STARTING_REVISION):
        v.validate_artifacts(expected_start=start,target=target,manifest_hash="0"*64,revision_hash="0"*64)


@pytest.mark.parametrize("mutation", ["operation", "parent", "identity", "empty", "manifest", "no_docstring"])
def test_web_revision_exact_shape(artifact_copy, mutation):
    path = artifact_copy/v.WEB_REVISION_FILE
    source = path.read_text()
    if mutation == "operation": source = source.replace("op.get_bind()", "None")
    if mutation == "parent": source = source.replace('down_revision = "0007_release_approvals"', 'down_revision = "0006_notification_management"')
    if mutation == "identity": source = source.replace('revision = "0008_web_launch"', 'revision = "0008_other"')
    if mutation == "empty": source = ""
    if mutation == "no_docstring": source = "\n".join(source.splitlines()[1:])
    path.write_text(source, encoding="utf-8")
    document = json.loads((artifact_copy/"migrations/manifest.json").read_bytes())
    document["revisions"][7]["sha256"] = v.digest(path.read_bytes())
    if mutation == "manifest": document["revisions"][7]["grants"] = v.RELEASE_GRANTS
    write_manifest(artifact_copy, document)
    from test_migration_artifacts import verify
    if mutation == "no_docstring": assert verify(artifact_copy).target == v.BASELINE
    else:
        with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH): verify(artifact_copy)


@pytest.mark.parametrize("environment", ["testing", "development"])
def test_web_ddl_only_alters_two_checks_and_requires_registered_owner(environment, monkeypatch):
    from oaf_website import web_launch_schema as web
    statements = []
    def execute(statement):
        statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return Result(IDENTITIES[environment].owner)
    web.upgrade_web_launch(SimpleNamespace(execute=execute))
    assert len(statements) == 5
    assert all(q.startswith("ALTER TABLE oaf_website.notification_release_events ") for q in statements[1:])
    assert sum("DROP CONSTRAINT" in q for q in statements) == 2
    assert sum("ADD CONSTRAINT" in q for q in statements) == 2
    assert "'gramanna-web'" in " ".join(statements)
    with pytest.raises(MigrationError, match=Failure.WRONG_IDENTITY):
        web.upgrade_web_launch(SimpleNamespace(execute=lambda q:Result(IDENTITIES[environment].runtime)))
    revision = runpy.run_path(str(ROOT/v.WEB_REVISION_FILE))
    sentinel=object(); calls=[]
    monkeypatch.setattr(alembic_op,"get_bind",lambda:sentinel)
    revision["upgrade"].__globals__["upgrade_web_launch"] = calls.append
    revision["upgrade"]()
    assert calls == [sentinel] and revision["down_revision"] == v.RELEASE_APPROVALS
    with pytest.raises(RuntimeError): revision["downgrade"]()


def test_web_synthetic_authorization_evidence_and_separate_noop(operational, monkeypatch):
    op = operational
    document = json.loads((ROOT/"migrations/manifest.json").read_bytes())
    request = replace(op.request, expected_start=v.RELEASE_APPROVALS, target=v.WEB_LAUNCH,
                      revision_hash=document["revisions"][7]["sha256"])
    monkeypatch.setattr(runner, "catalog_state", lambda *args: v.WEB_LAUNCH if op.runner.connection.target else v.RELEASE_APPROVALS)
    authorization = op.issue(op.approvals(request))
    assert op.run(authorization, request)["outcome"] == "applied_and_verified"
    with pytest.raises(MigrationError, match=Failure.OPERATIONAL_GATE): op.run(authorization, request)
    op.clock.now += timedelta(seconds=1); op.runner.connection.closed = False
    noop = replace(request, expected_start=v.WEB_LAUNCH)
    assert op.run(op.issue(op.approvals(noop)), noop)["outcome"] == "verified_noop"
    assert len(records(op, "claim-*.json")) == 2


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
