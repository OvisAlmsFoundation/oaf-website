"""Revision 0003: exact artifacts, drift rejection and unchanged migration gates."""

import migration_offline as isolation
isolation.require_early_registration()

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from migration_offline import ROOT, Result
from oaf_website import migration_validation as v
from oaf_website import migrate as m
from oaf_website.migration_config import Failure, MigrationError, IDENTITIES
from oaf_website.notification_schema import (
    CHECKS, NOTIFICATION_EDGES, active_email, notifications, upgrade_notifications,
)
from oaf_website.state_request_schema import STATE_CODES
from test_migration_artifacts import artifact_copy, write_manifest
from test_state_request_migration import FeatureCatalog
from test_migration_operational import operational, records
from migration_offline import DriverError


def artifacts(start=v.STATE_REQUESTS):
    payload = (ROOT/'migrations/manifest.json').read_bytes()
    return v.validate_artifacts(expected_start=start, target=v.NOTIFICATIONS,
            manifest_hash=v.digest(payload), revision_hash=json.loads(payload)['revisions'][2]['sha256'])


def test_revision_exact_transition_previous_revisions_unchanged_and_database_constraints():
    assert artifacts().expected_start == v.STATE_REQUESTS
    assert artifacts(v.NOTIFICATIONS).target == v.NOTIFICATIONS
    # Offline sandbox prohibits subprocesses; approved hashes are read from
    # the existing manifest and immutable 0001 is also checked independently.
    assert v.digest((ROOT/v.REVISION_FILE).read_bytes()) == 'bb51b33f3e064a02b8463593440820d65d01537f48a46b487b7cc327f0ea89a3'
    ddl = ' '.join(str(CreateTable(notifications).compile(dialect=postgresql.dialect())).split())
    index = str(CreateIndex(active_email).compile(dialect=postgresql.dialect()))
    assert 'PRIMARY KEY (unsubscribe_digest)' in ddl
    assert 'created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL' in ddl
    assert 'unsubscribed_at TIMESTAMP WITH TIME ZONE' in ddl
    assert 'CHECK (web_launch OR android_launch OR ios_launch OR state IS NOT NULL)' in ddl
    assert index == 'CREATE UNIQUE INDEX notifications_active_email ON oaf_website.notifications (email) WHERE unsubscribed_at IS NULL'


@pytest.mark.parametrize('start,target', [(v.BASE,v.NOTIFICATIONS), (v.BASELINE,v.NOTIFICATIONS),
    (v.NOTIFICATIONS,v.STATE_REQUESTS), (v.STATE_REQUESTS,'head'), (v.STATE_REQUESTS,'base')])
def test_no_revision_jump_downgrade_or_alias(start, target):
    a = artifacts()
    with pytest.raises(MigrationError, match=Failure.STARTING_REVISION):
        v.validate_artifacts(expected_start=start, target=target, manifest_hash=a.manifest_hash, revision_hash=a.revision_hash)


@pytest.mark.parametrize('old,new', [
    ('down_revision = "0002_state_requests"', 'down_revision = "0001_migration_baseline"'),
    ('upgrade_notifications(op.get_bind())', 'upgrade_notifications(op.get_bind())\n    op.get_bind().commit()'),
    ('upgrade_notifications(op.get_bind())', 'pass'),
    ('from alembic import op', 'import os\nfrom alembic import op'),
    ('raise RuntimeError("Ordinary migration downgrade is prohibited.")', 'pass'),
])
def test_even_rehashed_revision_cannot_bypass_reviewed_shape(artifact_copy, old, new):
    path = artifact_copy/v.NOTIFICATION_REVISION_FILE
    path.write_text(path.read_text(encoding='utf-8').replace(old,new),encoding='utf-8')
    document = json.loads((artifact_copy/'migrations/manifest.json').read_bytes())
    document['revisions'][2]['sha256'] = v.digest(path.read_bytes())
    write_manifest(artifact_copy, document)
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH):
        artifacts()


@pytest.mark.parametrize('environment', ['development','testing'])
def test_matching_owner_only_grants_no_commit_and_only_withdrawal_column_update(environment):
    identity = IDENTITIES[environment]
    sql = []
    def execute(statement):
        sql.append(str(statement.compile(dialect=postgresql.dialect())))
        return SimpleNamespace(scalar_one=lambda: identity.owner)
    upgrade_notifications(SimpleNamespace(execute=execute))
    assert len(sql) == 6
    assert sql[-3] == 'REVOKE ALL ON TYPE oaf_website.notifications FROM PUBLIC'
    assert sql[-2] == f'GRANT SELECT, INSERT ON TABLE oaf_website.notifications TO "{identity.runtime}"'
    assert sql[-1] == f'GRANT UPDATE (unsubscribed_at) ON TABLE oaf_website.notifications TO "{identity.runtime}"'
    assert not any(word in ' '.join(sql) for word in ['COMMIT','AUTOCOMMIT','SET ROLE','WITH GRANT OPTION'])


def test_runtime_cannot_create_schema():
    with pytest.raises(MigrationError, match=Failure.WRONG_IDENTITY):
        upgrade_notifications(SimpleNamespace(execute=lambda sql: SimpleNamespace(scalar_one=lambda: 'oaf_website_test_app')))


class NotificationCatalog(FeatureCatalog):
    def __init__(self, environment='testing'):
        super().__init__(environment)
        owner = self.i.owner
        self.relations += [dict(name=name,kind=kind,owner=owner,persistence='p',rls=False,
                            force_rls=False,rules=False,triggers=False,options=None)
                           for name,kind in [('notifications','r'),('notifications_active_email','i'),('notifications_pk','i')]]
        self.relations.sort(key=lambda r:r['name'])
        self.types += [dict(name='_notifications',kind='b',owner=owner,relation=0,element=600),
                       dict(name='notifications',kind='c',owner=owner,relation=601,element=0)]
        self.types.sort(key=lambda r:r['name'])
        self.marker = [{'version_num':v.NOTIFICATIONS}]
        self.notification_columns = [dict(name=name,type=kind,required=n not in {6,9},identity='',
                  generated='',dropped=False,position=n,dimensions=0,collation=100 if n in {1,2,6,7} else 0,
                  has_default=n==8,default_expression='CURRENT_TIMESTAMP' if n==8 else None)
                  for n,(name,kind) in enumerate([
                    ('unsubscribe_digest','character varying(64)'),('email','character varying(254)'),
                    ('web_launch','boolean'),('android_launch','boolean'),('ios_launch','boolean'),
                    ('state','character varying(2)'),('consent_version','character varying(40)'),
                    ('created_at','timestamp with time zone'),('unsubscribed_at','timestamp with time zone')],1)]
        self.notification_constraints = [dict(name='notifications_pk',kind='p',validated=True,
                deferrable=False,deferred=False,keys=[1],no_inherit=True,local=True,inherited=0,
                definition='PRIMARY KEY (unsubscribe_digest)')]
        # PostgreSQL 17 conkey values, independent of the validator's expectations.
        # Lifecycle first references unsubscribed_at (9), then created_at (8).
        check_keys = {
            'notifications_token_check': [1], 'notifications_email_check': [2],
            'notifications_preferences_check': [3, 4, 5, 6], 'notifications_state_check': [6],
            'notifications_consent_check': [7], 'notifications_lifecycle_check': [9, 8],
        }
        for name,expression in CHECKS.items():
            if name == 'notifications_state_check':
                expression = "state IS NULL OR state = ANY (ARRAY["+','.join(repr(c)+'::character varying' for c in STATE_CODES)+"])"
            self.notification_constraints.append(dict(name=name,kind='c',validated=True,deferrable=False,
                deferred=False,keys=check_keys[name],no_inherit=False,local=True,inherited=0,
                definition='CHECK (('+expression+'))'))
        self.notification_indexes = [dict(name=name,unique=True,primary=primary,valid=True,ready=True,
                live=True,nulls_not_distinct=False,attributes=1,keys=1,column=column,option=0,collation=100,
                method='btree',opclass='text_ops',opnamespace='pg_catalog',expression=None,predicate=predicate)
                for name,primary,column,predicate in [('notifications_active_email',False,2,'(unsubscribed_at IS NULL)'),
                                                      ('notifications_pk',True,1,None)]]
        self.notification_acl = [dict(grantee=owner,grantor=owner,privilege=p,grantable=False)
                                for p in ['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN']]
        self.notification_acl += [dict(grantee=self.i.runtime,grantor=owner,privilege=p,grantable=False) for p in ['SELECT','INSERT']]
        self.notification_column_acl = [dict(column='unsubscribed_at',grantee=self.i.runtime,grantor=owner,privilege='UPDATE',grantable=False)]
        self.notification_type_acl = [dict(grantee=owner,grantor=owner,privilege='USAGE',grantable=False)]
        labels = sorted({edge[0] for edge in NOTIFICATION_EDGES})
        self.objects += [dict(label=label,classid=5000+n,objid=6000+n) for n,label in enumerate(labels)]
        addresses = {o['label']:(o['classid'],o['objid']) for o in self.objects}
        self.dependencies += [dict(classid=addresses[s][0],objid=addresses[s][1],objsubid=sn,
                refclassid=addresses[t][0],refobjid=addresses[t][1],refobjsubid=tn,deptype=kind)
                for s,sn,t,tn,kind in NOTIFICATION_EDGES]
        self.notification_changes = {}

    def execute(self, sql, parameters=None):
        q,p = ' '.join(str(sql).split()),parameters or {}
        # Dispatch by concrete table reference, not the expanded inventory SQL.
        is_notification = "'oaf_website.notifications'" in q
        for needle,result in self.notification_changes.items():
            if needle in q and is_notification:
                return Result(result)
        if is_notification:
            if 'a.attname AS name' in q: return Result(deepcopy(self.notification_columns))
            if 'c.conname AS name' in q: return Result(deepcopy(self.notification_constraints))
            if 'i.indisunique AS unique' in q: return Result(deepcopy(self.notification_indexes))
            if 'COALESCE(c.relacl' in q: return Result(deepcopy(self.notification_acl))
            if 'aclexplode(c.attacl)' in q: return Result(deepcopy(self.notification_column_acl))
            if 'aclexplode(t.typacl)' in q: return Result(deepcopy(self.notification_type_acl))
            if 'pg_inherits' in q: return Result(False)
            if "t.typrelid='oaf_website.notifications'" in q: return Result(True)
            if 'has_table_privilege' in q:
                return Result(p['role']==self.i.owner or p['role']==self.i.runtime and p['privilege'] in {'SELECT','INSERT'})
            if 'has_column_privilege' in q:
                return Result(p['role']==self.i.owner or p['role']==self.i.runtime and
                    (p['privilege'] in {'SELECT','INSERT'} or p['privilege']=='UPDATE' and p['column']=='unsubscribed_at'))
        if 'has_type_privilege' in q and p['name'] in {'oaf_website.notifications','oaf_website._notifications'}:
            return Result(p['role']==self.i.owner)
        return super().execute(sql, parameters)


@pytest.mark.parametrize('environment',['development','testing'])
def test_exact_catalog_includes_preserved_state_requests(environment):
    catalog = NotificationCatalog(environment)
    assert v.catalog_state(catalog,catalog.i) == v.NOTIFICATIONS


def test_lifecycle_fixture_is_independent_of_validator(monkeypatch):
    from oaf_website.notification_schema import CHECK_COLUMNS

    monkeypatch.setitem(CHECK_COLUMNS, 'notifications_lifecycle_check', [8, 9])
    catalog = NotificationCatalog()
    lifecycle = next(c for c in catalog.notification_constraints
                     if c['name'] == 'notifications_lifecycle_check')
    assert lifecycle['keys'] == [9, 8]
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize('keys', [[8, 9], [9], [8], [9, 8, 9]])
def test_lifecycle_catalog_rejects_incorrect_column_reference_keys(keys):
    catalog = NotificationCatalog()
    lifecycle = next(c for c in catalog.notification_constraints
                     if c['name'] == 'notifications_lifecycle_check')
    lifecycle['keys'] = keys
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize('case',['column','nullability','timestamp','check','extra_check','pk','index_predicate',
    'index_unique','index_column','public_acl','runtime_update','column_update','column_grant','type_public',
    'owner','type_owner','marker','dependency','extension','extra_relation'])
def test_subscription_catalog_drift_fails_closed(case):
    c = NotificationCatalog()
    if case=='column': c.notification_columns[1]['type']='text'
    elif case=='nullability': c.notification_columns[0]['required']=False
    elif case=='timestamp': c.notification_columns[7]['default_expression']='NULL'
    elif case=='check': c.notification_constraints[-1]['definition']+=' OR true'
    elif case=='extra_check': c.notification_constraints.append({})
    elif case=='pk': c.notification_constraints[0]['keys']=[2]
    elif case=='index_predicate': c.notification_indexes[0]['predicate']='(unsubscribed_at IS NOT NULL)'
    elif case=='index_unique': c.notification_indexes[0]['unique']=False
    elif case=='index_column': c.notification_indexes[0]['column']=1
    elif case=='public_acl': c.notification_acl[-1]['grantee']='PUBLIC'
    elif case=='runtime_update': c.notification_acl[-1]['privilege']='UPDATE'
    elif case=='column_update': c.notification_column_acl[0]['column']='email'
    elif case=='column_grant': c.notification_column_acl[0]['grantable']=True
    elif case=='type_public': c.notification_type_acl[0]['grantee']='PUBLIC'
    elif case=='owner': c.relations[2]['owner']=c.i.runtime
    elif case=='type_owner': c.types[1]['owner']=c.i.runtime
    elif case=='marker': c.marker=[{'version_num':v.STATE_REQUESTS}]
    elif case=='dependency': c.dependencies.pop()
    elif case=='extension': c.dependencies.append(dict(c.dependencies[-1],refobjid=999999,deptype='e'))
    elif case=='extra_relation': c.relations.append(dict(c.relations[0],name='unexpected'))
    with pytest.raises(MigrationError,match=Failure.DRIFT):
        v.catalog_state(c,c.i)


def test_unsigned_runner_denied_before_credentials(monkeypatch):
    a = artifacts()
    loader = Mock(side_effect=AssertionError('Must not access credentials'))
    monkeypatch.setattr(m,'load_migration_config',loader)
    request = m.Request('upgrade','testing',a.expected_start,a.target,a.manifest_hash,a.revision_hash)
    with pytest.raises(MigrationError,match=Failure.OPERATIONAL_GATE):
        m.run(request)
    loader.assert_not_called()


def test_synthetic_0003_authority_single_use_and_separate_noop(operational,monkeypatch):
    op=operational
    a=artifacts()
    request=replace(op.request,expected_start=v.STATE_REQUESTS,target=v.NOTIFICATIONS,revision_hash=a.revision_hash)
    monkeypatch.setattr(m,'catalog_state',lambda *args:v.NOTIFICATIONS if op.runner.connection.target else v.STATE_REQUESTS)
    authorization=op.issue(op.approvals(request))
    assert op.run(authorization,request)['outcome']=='applied_and_verified'
    with pytest.raises(MigrationError,match=Failure.OPERATIONAL_GATE):
        op.run(authorization,request)
    op.clock.now+=timedelta(seconds=1)
    noop=replace(request,expected_start=v.NOTIFICATIONS)
    op.runner.connection.closed=False
    assert op.run(op.issue(op.approvals(noop)),noop)['outcome']=='verified_noop'
    assert len(records(op,'claim-*.json'))==2
    assert all(r['event']['target']==v.NOTIFICATIONS for r in records(op,'terminal-*.json'))


@pytest.mark.parametrize('phase,certainty',[('revision','not_invoked'),('commit','uncertain')])
def test_synthetic_0003_failure_retains_claim_and_commit_classification(operational,monkeypatch,phase,certainty):
    op=operational
    a=artifacts()
    request=replace(op.request,expected_start=v.STATE_REQUESTS,target=v.NOTIFICATIONS,revision_hash=a.revision_hash)
    monkeypatch.setattr(m,'catalog_state',lambda *args:v.NOTIFICATIONS if op.runner.connection.target else v.STATE_REQUESTS)
    op.runner.connection.hooks[phase]=DriverError('08006' if phase=='commit' else '40P01')
    authorization=op.issue(op.approvals(request))
    with pytest.raises(MigrationError) as caught:
        op.run(authorization,request)
    assert caught.value.operational_result['commit_certainty']==certainty
    assert len(records(op,'claim-*.json'))==1 and len(records(op,'terminal-*.json'))==1
    assert op.runner.connection.calls.count('revision')==1
