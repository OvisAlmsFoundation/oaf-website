"""Revision 0002 contract, exact catalog and Stage 5 gates, entirely offline."""

import migration_offline as isolation
isolation.require_early_registration()

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace
from unittest.mock import Mock

from alembic import context
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from migration_offline import ROOT, Result, DriverError
from oaf_website import migrate as m, migration_validation as v
from oaf_website.migration_config import Failure, MigrationError
from oaf_website.state_request_schema import state_requests, upgrade_state_requests
from test_migration_artifacts import artifact_copy, write_manifest
from test_migration_authorization import context_setup
from test_migration_catalog import Catalog
from test_migration_operational import operational, records


def request_artifacts(start=v.BASELINE):
    payload = (ROOT/'migrations/manifest.json').read_bytes()
    return v.validate_artifacts(expected_start=start, target=v.STATE_REQUESTS,
                               manifest_hash=v.digest(payload), revision_hash=json.loads(payload)['revisions'][1]['sha256'])


def test_single_revision_transition_and_exact_unchanged_baseline():
    a = request_artifacts()
    assert (a.expected_start, a.target) == (v.BASELINE, v.STATE_REQUESTS)
    assert request_artifacts(v.STATE_REQUESTS).expected_start == v.STATE_REQUESTS
    assert v.digest((ROOT/v.REVISION_FILE).read_bytes()) == 'bb51b33f3e064a02b8463593440820d65d01537f48a46b487b7cc327f0ea89a3'
    ddl = ' '.join(str(CreateTable(state_requests).compile(dialect=postgresql.dialect())).split())
    assert 'PRIMARY KEY (state, browser_key)' in ddl
    assert 'created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL' in ddl
    assert 'state VARCHAR(2) NOT NULL' in ddl and 'browser_key UUID NOT NULL' in ddl
    assert 'state_requests_state_check CHECK (state IN (' in ddl


@pytest.mark.parametrize('start,target', [(v.BASE, v.STATE_REQUESTS), (v.STATE_REQUESTS, v.BASELINE),
    (v.BASELINE, 'head'), (v.BASELINE, 'heads'), (v.BASELINE, 'base')])
def test_feature_revision_cannot_jump_downgrade_or_resolve_alias(start, target):
    a = request_artifacts()
    with pytest.raises(MigrationError, match=Failure.STARTING_REVISION):
        v.validate_artifacts(expected_start=start, target=target,
                             manifest_hash=a.manifest_hash, revision_hash=a.revision_hash)


@pytest.mark.parametrize('old,new', [
    ('down_revision = "0001_migration_baseline"', 'down_revision = None'),
    ('upgrade_state_requests(op.get_bind())', 'upgrade_state_requests(op.get_bind())\n    op.get_bind().commit()'),
    ('upgrade_state_requests(op.get_bind())', 'pass'),
    ('def upgrade():', '@unsafe\ndef upgrade():'),
    ('from alembic import op', 'import os\nfrom alembic import op'),
    ('raise RuntimeError("Ordinary migration downgrade is prohibited.")', 'pass'),
])
def test_rehashed_0002_shape_cannot_bypass_operation_restrictions(artifact_copy, old, new):
    path = artifact_copy/v.REQUEST_REVISION_FILE
    path.write_text(path.read_text(encoding='utf-8').replace(old, new), encoding='utf-8')
    payload = json.loads((artifact_copy/'migrations/manifest.json').read_bytes())
    payload['revisions'][1]['sha256'] = v.digest(path.read_bytes())
    write_manifest(artifact_copy, payload)
    manifest = (artifact_copy/'migrations/manifest.json').read_bytes()
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH):
        v.validate_artifacts(expected_start=v.BASELINE, target=v.STATE_REQUESTS,
                             manifest_hash=v.digest(manifest), revision_hash=payload['revisions'][1]['sha256'])


@pytest.mark.parametrize('field,value', [('grants', []), ('parent', None), ('starting_state', v.BASE)])
def test_manifest_cannot_silently_change_feature_contract(artifact_copy, field, value):
    payload = json.loads((artifact_copy/'migrations/manifest.json').read_bytes())
    payload['revisions'][1][field] = value
    write_manifest(artifact_copy, payload)
    manifest = (artifact_copy/'migrations/manifest.json').read_bytes()
    with pytest.raises(MigrationError, match=Failure.ARTIFACT_HASH):
        v.validate_artifacts(expected_start=v.BASELINE, target=v.STATE_REQUESTS,
                             manifest_hash=v.digest(manifest), revision_hash=payload['revisions'][1]['sha256'])


@pytest.mark.parametrize('environment', ['testing', 'development'])
def test_revision_only_grants_matching_runtime_and_does_not_commit(environment):
    from oaf_website.migration_config import IDENTITIES
    identity = IDENTITIES[environment]
    statements = []
    def execute(statement):
        statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return SimpleNamespace(scalar_one=lambda: identity.owner)
    upgrade_state_requests(SimpleNamespace(execute=execute))
    assert len(statements) == 4
    assert statements[1].lstrip().startswith('CREATE TABLE oaf_website.state_requests')
    assert statements[2] == 'REVOKE ALL ON TYPE oaf_website.state_requests FROM PUBLIC'
    assert statements[3] == f'GRANT SELECT, INSERT ON TABLE oaf_website.state_requests TO "{identity.runtime}"'
    assert not any(word in ' '.join(statements) for word in ['COMMIT', 'AUTOCOMMIT', 'SET ROLE', 'WITH GRANT OPTION'])


def test_runtime_cannot_apply_schema_helper():
    execute = Mock(return_value=SimpleNamespace(scalar_one=lambda: 'oaf_website_test_app'))
    with pytest.raises(MigrationError, match=Failure.WRONG_IDENTITY):
        upgrade_state_requests(SimpleNamespace(execute=execute))
    execute.assert_called_once()


class FeatureCatalog(Catalog):
    def __init__(self, environment='testing'):
        super().__init__(environment)
        owner = self.i.owner
        self.relations += [dict(name=name, kind=kind, owner=owner, persistence='p', rls=False,
                                force_rls=False, rules=False, triggers=False, options=None)
                           for name, kind in [('state_requests', 'r'), ('state_requests_pk', 'i')]]
        self.types += [dict(name='_state_requests', kind='b', owner=owner, relation=0, element=203),
                       dict(name='state_requests', kind='c', owner=owner, relation=202, element=0)]
        self.types.sort(key=lambda row: row['name'])
        self.marker = [{'version_num': v.STATE_REQUESTS}]
        self.request_columns = [
            dict(name=name, type=kind, required=True, identity='', generated='', dropped=False,
                 position=n, dimensions=0, collation=100 if n == 1 else 0, has_default=n == 3,
                 default_expression='CURRENT_TIMESTAMP' if n == 3 else None, builtin=True)
            for n, (name, kind) in enumerate([('state', 'character varying(2)'),
                ('browser_key', 'uuid'), ('created_at', 'timestamp with time zone')], 1)]
        self.request_constraints = [
            dict(name='state_requests_pk', kind='p', validated=True, deferrable=False, deferred=False,
                 keys=[1, 2], no_inherit=True, local=True, inherited=0, definition='PRIMARY KEY (state, browser_key)'),
            dict(name='state_requests_state_check', kind='c', validated=True, deferrable=False, deferred=False,
                 keys=[1], no_inherit=False, local=True, inherited=0, definition='CHECK (((state)::text = ANY ((ARRAY[' +
                 ', '.join(repr(code) + '::character varying' for code in
                           "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()) + '])::text[])))'),
        ]
        self.request_acl = [dict(grantee=owner, grantor=owner, privilege=p, grantable=False)
                            for p in ['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN']]
        self.request_acl += [dict(grantee=self.i.runtime, grantor=owner, privilege=p, grantable=False) for p in ['SELECT','INSERT']]
        self.request_type_acl = [dict(grantee=owner, grantor=owner, privilege='USAGE', grantable=False)]
        labels = ['request_table', 'request_index', 'request_row_type', 'request_array_type',
                  'request_primary_key', 'request_check', 'request_default']
        self.objects += [dict(label=label, classid=3000+n, objid=4000+n) for n, label in enumerate(labels)]
        address = {o['label']: (o['classid'], o['objid']) for o in self.objects}
        edges = [
            ('request_table', 0, 'schema', 0, 'n'),
            ('request_row_type', 0, 'request_table', 0, 'i'),
            ('request_array_type', 0, 'request_row_type', 0, 'i'),
            ('request_primary_key', 0, 'request_table', 1, 'a'),
            ('request_primary_key', 0, 'request_table', 2, 'a'),
            ('request_index', 0, 'request_primary_key', 0, 'i'),
            ('request_check', 0, 'request_table', 1, 'a'),
            ('request_check', 0, 'request_table', 1, 'n'),
            ('request_default', 0, 'request_table', 3, 'a'),
        ]
        self.dependencies += [dict(classid=address[s][0], objid=address[s][1], objsubid=sn,
                                   refclassid=address[t][0], refobjid=address[t][1], refobjsubid=tn, deptype=kind)
                              for s, sn, t, tn, kind in edges]
        self.feature_changes = {}

    def execute(self, sql, parameters=None):
        q, p = str(sql), parameters or {}
        for needle, value in self.feature_changes.items():
            if needle in q:
                return Result(value(p) if callable(value) else value)
        if "'pg_catalog.\"default\"'::pg_catalog.regcollation::oid" in q:
            return Result(100)
        if "a.attname AS name" in q and "state_requests'::pg_catalog.regclass" in q:
            return Result(deepcopy(self.request_columns))
        if "c.conname AS name" in q and "state_requests'::pg_catalog.regclass" in q:
            return Result(deepcopy(self.request_constraints))
        if "COALESCE(c.relacl" in q and "state_requests'::pg_catalog.regclass" in q:
            return Result(deepcopy(self.request_acl))
        if 'aclexplode(t.typacl)' in q:
            return Result(deepcopy(self.request_type_acl))
        if "attacl IS NOT NULL" in q:
            return Result(False)
        if "t.typrelid='oaf_website.state_requests'" in q or "state_requests_pk'::pg_catalog.regclass" in q:
            return Result(True)
        if 'has_type_privilege' in q and p['name'] in {'oaf_website.state_requests', 'oaf_website._state_requests'}:
            return Result(p['role'] == self.i.owner)
        if ('has_table_privilege' in q or 'has_any_column_privilege' in q) and 'state_requests' in q:
            return Result(p['role'] == self.i.owner or (p['role'] == self.i.runtime and p['privilege'] in {'SELECT', 'INSERT'}))
        return super().execute(sql, parameters)


@pytest.mark.parametrize('environment', ['development', 'testing'])
def test_exact_feature_catalog_and_metadata_protections(environment):
    catalog = FeatureCatalog(environment)
    assert v.catalog_state(catalog, catalog.i) == v.STATE_REQUESTS


@pytest.mark.parametrize('kind', ['table_missing', 'table_grant', 'column_missing', 'type_missing', 'type_grant'])
def test_effective_feature_privileges_fail_closed(kind):
    catalog=FeatureCatalog()
    if kind.startswith('table'):
        def privilege(p):
            if p['privilege'].endswith('WITH GRANT OPTION'):
                return kind=='table_grant'
            return False if kind=='table_missing' else (p['role']==catalog.i.owner or
                p['role']==catalog.i.runtime and p['privilege'] in {'SELECT','INSERT'})
        catalog.feature_changes['has_table_privilege']=privilege
    elif kind=='column_missing':
        catalog.feature_changes['has_any_column_privilege']=False
    else:
        execute=catalog.execute
        def type_privilege(sql,parameters=None):
            if 'has_type_privilege' in str(sql) and parameters['name'] in {
                    'oaf_website.state_requests','oaf_website._state_requests'}:
                if 'WITH GRANT OPTION' in str(sql):
                    return Result(kind=='type_grant')
                return Result(kind!='type_missing' and parameters['role']==catalog.i.owner)
            return execute(sql,parameters)
        catalog.execute=type_privilege
    with pytest.raises(MigrationError,match=Failure.DRIFT):
        v.catalog_state(catalog,catalog.i)


@pytest.mark.parametrize('case', ['owner', 'type_owner', 'marker', 'column', 'timestamp', 'nullable',
    'pk', 'check', 'extra_constraint', 'runtime_update', 'public', 'grant_option', 'type_public',
    'dependency', 'extension', 'missing_default', 'extra_table', 'triggers', 'runtime_metadata'])
def test_feature_drift_fails_closed(case):
    catalog = FeatureCatalog()
    if case == 'owner': catalog.relations[-1]['owner'] = catalog.i.runtime
    elif case == 'type_owner': catalog.types[-1]['owner'] = catalog.i.runtime
    elif case == 'marker': catalog.marker = [{'version_num': v.BASELINE}]
    elif case == 'column': catalog.request_columns[1]['type'] = 'text'
    elif case == 'timestamp': catalog.request_columns[2]['default_expression'] = 'NULL'
    elif case == 'nullable': catalog.request_columns[0]['required'] = False
    elif case == 'pk': catalog.request_constraints[0]['keys'] = [1]
    elif case == 'check': catalog.request_constraints[1]['definition'] += ' OR true'
    elif case == 'extra_constraint': catalog.request_constraints.append({})
    elif case == 'runtime_update': catalog.request_acl[-1]['privilege'] = 'UPDATE'
    elif case == 'public': catalog.request_acl[-1]['grantee'] = 'PUBLIC'
    elif case == 'grant_option': catalog.request_acl[-1]['grantable'] = True
    elif case == 'type_public': catalog.request_type_acl.append(dict(catalog.request_type_acl[0], grantee='PUBLIC'))
    elif case == 'dependency': catalog.dependencies.pop()
    elif case == 'extension': catalog.dependencies.append(dict(catalog.dependencies[0], refobjid=999999, deptype='e'))
    elif case == 'missing_default': catalog.objects.pop()
    elif case == 'extra_table': catalog.relations.append(dict(catalog.relations[-2], name='unexpected'))
    elif case == 'triggers': catalog.relations[-2]['triggers'] = True
    elif case == 'runtime_metadata': catalog.scalar_changes['has_table_privilege'] = True
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize('needle', ['i.indisunique', "t.typrelid='oaf_website.state_requests'", 'attacl IS NOT NULL'])
def test_feature_index_type_and_column_privilege_checks(needle):
    catalog = FeatureCatalog()
    catalog.feature_changes[needle] = needle == 'attacl IS NOT NULL'
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


def test_feature_alembic_preserves_context_and_exact_expected_start(context_setup, monkeypatch):
    s = context_setup
    artifacts = request_artifacts()
    s.e.request = replace(s.e.request, expected_start=v.BASELINE, target=v.STATE_REQUESTS,
                          revision_hash=artifacts.revision_hash)
    s.e.observed_start = v.BASELINE
    context.get_revision_argument.return_value = v.STATE_REQUESTS
    v.catalog_state.return_value = v.BASELINE
    with v._runner_execution(s.conn, s.i, artifacts, s.transaction, s.e, s.sink, s.authority, 701) as runner:
        s.config.attributes['oaf_runner'] = runner
        s.env()
    s.execute.assert_called_once()
    assert s.transaction.is_active and s.conn.commits == 0


def test_feature_runner_without_owner_authorization_cannot_access_credentials(monkeypatch):
    artifacts = request_artifacts()
    loader = Mock(side_effect=AssertionError('Must not access credentials'))
    monkeypatch.setattr(m, 'load_migration_config', loader)
    request = m.Request('upgrade', 'testing', artifacts.expected_start, artifacts.target,
                        artifacts.manifest_hash, artifacts.revision_hash)
    with pytest.raises(MigrationError, match=Failure.OPERATIONAL_GATE):
        m.run(request)
    loader.assert_not_called()


def test_new_revision_uses_real_file_authority_and_separately_bound_noop(operational, monkeypatch):
    op = operational
    artifacts = request_artifacts()
    request = replace(op.request, expected_start=v.BASELINE, target=v.STATE_REQUESTS,
                      revision_hash=artifacts.revision_hash)
    monkeypatch.setattr(m, 'catalog_state', lambda *args: v.STATE_REQUESTS if op.runner.connection.target else v.BASELINE)
    authorization_id = op.issue(op.approvals(request))
    assert op.run(authorization_id, request)['outcome'] == 'applied_and_verified'
    with pytest.raises(MigrationError, match=Failure.OPERATIONAL_GATE):
        op.run(authorization_id, request)
    op.clock.now += timedelta(seconds=1)
    noop = replace(request, expected_start=v.STATE_REQUESTS)
    op.runner.connection.closed = False
    assert op.run(op.issue(op.approvals(noop)), noop)['outcome'] == 'verified_noop'
    assert len(records(op, 'claim-*.json')) == 2
    assert all(record['event']['target'] == v.STATE_REQUESTS for record in records(op, 'terminal-*.json'))


@pytest.mark.parametrize('phase,sqlstate,certainty', [('revision', '40P01', 'not_invoked'),
    ('commit', '08006', 'uncertain')])
def test_feature_migration_failure_retains_claim_and_commit_classification(operational, monkeypatch, phase, sqlstate, certainty):
    op = operational
    artifacts = request_artifacts()
    request = replace(op.request, expected_start=v.BASELINE, target=v.STATE_REQUESTS,
                      revision_hash=artifacts.revision_hash)
    monkeypatch.setattr(m, 'catalog_state', lambda *args: v.STATE_REQUESTS if op.runner.connection.target else v.BASELINE)
    op.runner.connection.hooks[phase] = DriverError(sqlstate)
    authorization_id = op.issue(op.approvals(request))
    with pytest.raises(MigrationError) as caught:
        op.run(authorization_id, request)
    result = caught.value.operational_result
    assert result['commit_certainty'] == certainty
    assert result['transaction_outcome'] == ('unknown' if phase == 'commit' else 'rollback_confirmed')
    assert len(records(op, 'claim-*.json')) == 1
    assert len(records(op, 'terminal-*.json')) == 1
    assert op.runner.connection.calls.count('revision') == 1
    assert op.runner.connection.calls.count('commit') == (phase == 'commit')
