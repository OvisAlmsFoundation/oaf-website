"""Approved operational policies, real file adapter, synthetic approvals/DB only."""

import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import runpy
from threading import Barrier
import traceback
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from alembic import command, context
import pytest

from migration_offline import SECRET, DriverError, artifacts
from oaf_website import migrate as m, migration_authority as a, migration_validation as v
from oaf_website.migration_config import Failure, MigrationError
from test_migration_authorization import context_setup


REAL_GATE = m._require_operational_adapter


def reference(path, document):
    path.write_bytes((json.dumps(document, sort_keys=True) + '\n').encode())
    return {'id': document['id'], 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def operational(runner, tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(m, '_require_operational_adapter', REAL_GATE)
    clock = SimpleNamespace(now=datetime(2030, 1, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(a, '_now', lambda: clock.now)
    root = a.audit_destination()
    request = runner.request

    def approvals(request=request, *, reconciled=False, testing_run=None):
        previous = a._previous(root, request.environment)
        common = dict(format=1, reviewer_id=str(uuid4()), approved_utc=clock.now.isoformat(), decision='approved')
        artifact = dict(common, kind='artifact_approval', id=str(uuid4()),
                        manifest_hash=request.manifest_hash, revision_hash=request.revision_hash)
        prerequisite = dict(common, kind='prerequisite_approval', id=str(uuid4()),
                            environment=request.environment, expected_start=request.expected_start,
                            approvals={key: str(uuid4()) for key in a.PREREQUISITES},
                            predecessor=previous,
                            owner_reconciliation='completed' if reconciled else 'not_applicable',
                            testing_validation_run=testing_run)
        return dict(request=asdict(request), expires_utc=(clock.now + timedelta(hours=24)).isoformat(),
                    artifact_approval=reference(root / f'artifact-approval-{artifact["id"]}.json', artifact),
                    prerequisite_approval=reference(root / f'prerequisite-approval-{prerequisite["id"]}.json', prerequisite))

    specification = approvals()

    def issue(spec=specification):
        return a.issue_authorization(spec, owner_issue=True)

    def run(authorization_id, req=request):
        return m.run(req, authority=a.FileOperationalAuthority(authorization_id))

    return SimpleNamespace(root=root, clock=clock, runner=runner, request=request, spec=specification,
                           approvals=approvals, issue=issue, run=run)


def records(op, pattern='*.json'):
    return [json.loads(path.read_bytes()) for path in sorted(op.root.glob(pattern))]


def assert_denied(op, authorization_id, request=None):
    with pytest.raises(MigrationError) as caught:
        op.run(authorization_id, request or op.request)
    assert SECRET not in ''.join(traceback.format_exception(caught.value))
    assert records(op, 'denial-*.json')
    return caught.value


def test_exact_destination_and_no_bootstrap_access(operational, tmp_path):
    assert operational.root == tmp_path / 'OAF Website' / 'BootstrapAudit' / 'MigrationAudit'
    assert list(operational.root.parent.iterdir()) == [operational.root]
    assert not list(operational.root.glob('authorization-*'))


def test_exclusive_creation_flush_and_fsync(operational, monkeypatch):
    path = operational.root / 'synthetic.json'
    calls = []
    real_sync = a.os.fsync
    def sync(fd):
        # An independent read sees serialized bytes only after stream.flush().
        calls.append(json.loads(path.read_bytes()))
        real_sync(fd)
    monkeypatch.setattr(a.os, 'fsync', sync)
    a._save(path, {'kind': 'synthetic'})
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        a._save(path, {'kind': 'overwrite'})
    assert calls == [{'kind': 'synthetic'}]
    assert path.read_bytes() == before


def test_fsync_failure_preserves_partial_evidence(operational, monkeypatch):
    monkeypatch.setattr(a.os, 'fsync', Mock(side_effect=OSError(SECRET)))
    path = operational.root / 'synthetic.json'
    with pytest.raises(OSError):
        a._save(path, {'kind': 'synthetic'})
    assert path.is_file()
    with pytest.raises(FileExistsError):
        a._save(path, {})


def test_issuance_is_distinct_deliberate_and_utc(operational):
    op = operational
    with pytest.raises(MigrationError):
        a.issue_authorization(op.spec)
    assert not records(op, 'authorization-*.json')
    authorization_id = op.issue()
    record = records(op, 'authorization-*.json')[0]
    assert record['id'] == authorization_id and record['kind'] == 'owner_authorization'
    assert a._utc(record['issued_utc']) == op.clock.now
    assert a._utc(record['expires_utc']) - a._utc(record['issued_utc']) == timedelta(hours=24)
    assert not records(op, 'claim-*.json')
    op.runner.m.load_migration_config.assert_not_called()


@pytest.mark.parametrize('expiry', ['naive', 'nonutc', 'expired', 'over24'])
def test_bad_issuance_expiry(operational, expiry):
    op = operational
    stamp = {'naive': op.clock.now.replace(tzinfo=None),
             'nonutc': op.clock.now.astimezone(timezone(timedelta(hours=1))) + timedelta(hours=1),
             'expired': op.clock.now, 'over24': op.clock.now + timedelta(hours=24, microseconds=1)}[expiry]
    op.spec['expires_utc'] = stamp.isoformat()
    with pytest.raises(MigrationError):
        op.issue()
    assert not records(op, 'authorization-*.json')


@pytest.mark.parametrize('age', [timedelta(hours=24), timedelta(hours=25), timedelta(seconds=-1)])
def test_expired_and_future_authorizations_retained(operational, age):
    op = operational
    authorization_id = op.issue()
    path = op.root / f'authorization-{authorization_id}.json'
    original = path.read_bytes()
    op.clock.now += age
    assert_denied(op, authorization_id)
    assert path.read_bytes() == original
    assert not records(op, 'claim-*.json')
    op.runner.m.load_migration_config.assert_not_called()


@pytest.mark.parametrize('authorization_id', [None, '', SECRET, '../outside', str(uuid4())])
def test_missing_invalid_authorization_persists_sanitized_denial(operational, authorization_id):
    op = operational
    error = assert_denied(op, authorization_id)
    assert error.operational_result['audit_write_outcome'] == 'confirmed_successful'
    assert not records(op, 'authorization-*.json')  # Runner never issues.
    assert not records(op, 'claim-*.json')
    assert SECRET not in json.dumps(records(op))
    op.runner.m.load_migration_config.assert_not_called()


@pytest.mark.parametrize('field,value', [('action', 'verify'), ('environment', 'development'),
    ('expected_start', v.BASELINE), ('target', 'head'), ('manifest_hash', '0' * 64),
    ('revision_hash', '0' * 64)])
def test_authorization_bound_to_exact_request(operational, monkeypatch, field, value):
    op = operational
    authorization_id = op.issue()
    request = replace(op.request, **{field: value})
    if field == 'environment':
        monkeypatch.setenv('OAF_ENV', value)
    assert_denied(op, authorization_id, request)
    assert not records(op, 'claim-*.json')
    op.runner.m.load_migration_config.assert_not_called()


@pytest.mark.parametrize('kind', ['artifact', 'prerequisite'])
@pytest.mark.parametrize('change', ['missing', 'pending', 'hash', 'future', 'unknown'])
def test_independent_approvals_are_required_at_consumption(operational, kind, change):
    op = operational
    authorization_id = op.issue()
    ref = op.spec[kind + '_approval']
    path = op.root / f'{kind}-approval-{ref["id"]}.json'
    data = json.loads(path.read_bytes())
    if change == 'missing':
        path.rename(path.with_suffix('.synthetic-withheld'))
    else:
        data.update({'pending': {'decision': 'pending_independent_review'},
                     'hash': {'id': str(uuid4())},
                     'future': {'approved_utc': (op.clock.now + timedelta(hours=1)).isoformat()},
                     'unknown': {'password': SECRET}}[change])
        reference(path, data)
    assert_denied(op, authorization_id)
    assert not records(op, 'claim-*.json')


@pytest.mark.parametrize('kind,field,value', [
    ('artifact', 'decision', 'pending_independent_review'),
    ('artifact', 'manifest_hash', '0' * 64),
    ('prerequisite', 'approvals', {}),
    ('prerequisite', 'environment', 'development'),
    ('prerequisite', 'expected_start', v.BASELINE),
])
def test_matching_record_hashes_do_not_confer_approval(operational, kind, field, value):
    op = operational
    ref = op.spec[kind + '_approval']
    path = op.root / f'{kind}-approval-{ref["id"]}.json'
    document = json.loads(path.read_bytes())
    document[field] = value
    op.spec[kind + '_approval'] = reference(path, document)
    with pytest.raises(MigrationError):
        op.issue()
    assert not records(op, 'authorization-*.json')
    assert json.loads((v.ROOT / 'migrations/manifest.json').read_bytes())['approval_status'] == 'pending_independent_review'


def test_single_use_and_all_evidence_retained(operational):
    op = operational
    authorization_id = op.issue()
    result = op.run(authorization_id)
    assert result['outcome'] == 'applied_and_verified'
    before = {path.name: path.read_bytes() for path in op.root.iterdir()}
    assert_denied(op, authorization_id)
    assert all((op.root / name).read_bytes() == content for name, content in before.items())
    assert len(records(op, 'claim-*.json')) == 1
    assert op.runner.connection.commits == 1


@pytest.mark.parametrize('same_id', [True, False])
def test_concurrent_consumption_exclusive_across_instances_and_ids(operational, monkeypatch, same_id):
    op = operational
    ids = [op.issue(), op.issue()]
    if same_id:
        ids[1] = ids[0]
    barrier = Barrier(2)
    save = a._save
    def synchronized(path, record):
        if path.name.startswith('claim-'):
            barrier.wait(timeout=5)
        return save(path, record)
    monkeypatch.setattr(a, '_save', synchronized)
    def consume(identifier):
        try:
            return a.FileOperationalAuthority(identifier).authorize(op.request, str(uuid4()), artifacts())
        except MigrationError:
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(consume, ids))
    assert sum(result is not None for result in results) == 1
    assert len(records(op, 'claim-*.json')) == 1
    assert len(records(op, 'denial-*.json')) == 1


@pytest.mark.parametrize('failure_point', ['claim', 'authorization', 'revision', 'precommit', 'commit_ready'])
def test_audit_failure_before_mutation_or_commit_blocks(operational, monkeypatch, failure_point):
    op = operational
    identifier = op.issue()
    save = a._save
    def fail(path, record):
        if (failure_point == 'claim' and record['kind'] == 'authorization_claimed'
                or record.get('event', {}).get('phase') == failure_point):
            raise OSError(SECRET)
        return save(path, record)
    monkeypatch.setattr(a, '_save', fail)
    error = assert_denied_or_failed(op, identifier)
    assert not error.operational_result['database_commit_confirmed']
    assert op.runner.connection.commits == 0
    if failure_point in {'claim', 'authorization', 'revision'}:
        assert 'revision' not in op.runner.connection.calls
    if failure_point in {'claim', 'authorization'}:
        op.runner.m.load_migration_config.assert_not_called()


def assert_denied_or_failed(op, identifier):
    with pytest.raises(MigrationError) as caught:
        op.run(identifier)
    assert SECRET not in ''.join(traceback.format_exception(caught.value))
    assert SECRET not in json.dumps(records(op))
    return caught.value


def test_claim_fsync_failure_retained_and_no_reuse(operational, monkeypatch):
    op = operational
    identifier = op.issue()
    sync = a.os.fsync
    calls = 0
    def fail_once(fd):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(SECRET)
        sync(fd)
    monkeypatch.setattr(a.os, 'fsync', fail_once)
    assert_denied(op, identifier)
    assert records(op, 'claim-*.json')
    assert_denied(op, identifier)
    op.runner.m.load_migration_config.assert_not_called()


def test_successful_audit_sequence(operational):
    op = operational
    identifier = op.issue()
    result = op.run(identifier)
    events = records(op, 'event-*.json')
    assert [entry['event']['phase'] for entry in events] == [
        'authorization', 'lock', 'preflight', 'revision', 'precommit', 'commit_ready', 'postcommit']
    assert [entry['sequence'] for entry in events] == list(range(1, 8))
    terminal = records(op, 'terminal-*.json')[0]
    assert terminal['event']['outcome'] == result['outcome'] == 'applied_and_verified'
    assert terminal['event']['database_commit_confirmed']
    assert terminal['event']['commit_certainty'] == 'confirmed'
    assert terminal['authorization_id'] == identifier


@pytest.mark.parametrize('failure', ['revision', 'uncertain', 'postcommit_audit', 'terminal_audit'])
def test_failure_commit_certainty_and_recovery_blocking(operational, monkeypatch, failure):
    op = operational
    identifier = op.issue()
    preissued = op.issue()
    if failure in {'revision', 'uncertain'}:
        op.runner.connection.hooks['revision' if failure == 'revision' else 'commit'] = DriverError('08006')
    else:
        save = a._save
        def fail(path, record):
            if (failure == 'postcommit_audit' and record.get('event', {}).get('phase') == 'postcommit'
                    or failure == 'terminal_audit' and record['kind'] == 'execution_finalized'):
                raise OSError(SECRET)
            return save(path, record)
        monkeypatch.setattr(a, '_save', fail)
    error = assert_denied_or_failed(op, identifier)
    result = error.operational_result
    if failure == 'revision':
        assert result['transaction_outcome'] == 'rollback_confirmed'
        assert result['commit_certainty'] == 'not_invoked'
    elif failure == 'uncertain':
        assert result['commit_certainty'] == 'uncertain'
        assert result['transaction_outcome'] == 'unknown'
        assert op.runner.connection.calls.count('commit') == 1
        assert 'unlock' not in op.runner.connection.calls
    else:
        assert result['database_commit_confirmed']
        assert result['transaction_outcome'] == 'committed_confirmed'
        assert result['commit_certainty'] in {'confirmed', 'postcommit_verification_failed'}
    terminal = records(op, 'terminal-*.json')
    if failure != 'terminal_audit':
        assert terminal[0]['event']['outcome'] == 'failed'
        assert terminal[0]['event']['failed_phase'] in {'revision', 'commit', 'postcommit'}
    assert_denied(op, identifier)
    assert_denied(op, preissued)
    with pytest.raises(MigrationError):
        op.issue(op.approvals())  # No automatic recovery under a new UUID.
    assert len(records(op, 'claim-*.json')) == 1


def test_owner_reconciliation_allows_fresh_authorization_never_reuses_claim(operational):
    op = operational
    identifier = op.issue()
    a.FileOperationalAuthority(identifier).authorize(op.request, str(uuid4()), artifacts())
    first = (op.root / 'claim-testing-00000001.json').read_bytes()
    with pytest.raises(MigrationError):
        op.issue(op.approvals())
    second = op.issue(op.approvals(reconciled=True))
    a.FileOperationalAuthority(second).authorize(op.request, str(uuid4()), artifacts())
    assert second != identifier
    assert (op.root / 'claim-testing-00000001.json').read_bytes() == first
    assert (op.root / 'claim-testing-00000002.json').is_file()


def test_noop_needs_new_authorization_with_exact_start(operational):
    op = operational
    identifier = op.issue()
    op.runner.connection.target = True
    error = assert_denied_or_failed(op, identifier)
    assert error.classification == Failure.STARTING_REVISION
    assert op.runner.connection.commits == 0
    request = replace(op.request, expected_start=v.BASELINE)
    fresh = op.issue(op.approvals(request, reconciled=True))
    # Fresh synthetic session; retained target represents the observed database.
    op.runner.connection.closed = False
    result = op.run(fresh, request)
    assert result['outcome'] == 'verified_noop'
    assert not result['mutation_started'] and op.runner.connection.commits == 0
    assert len(records(op, 'claim-*.json')) == 2


@pytest.mark.parametrize('phase', ['revision', 'commit_ready'])
def test_expiry_rechecked_before_mutation_and_commit(operational, monkeypatch, phase):
    op = operational
    identifier = op.issue()
    original = a.FileAuditSink.write
    def expire(sink, event):
        if event.phase == phase:
            op.clock.now += timedelta(hours=24)
        return original(sink, event)
    monkeypatch.setattr(a.FileAuditSink, 'write', expire)
    assert_denied_or_failed(op, identifier)
    assert op.runner.connection.commits == 0
    if phase == 'revision':
        assert 'revision' not in op.runner.connection.calls


@pytest.mark.parametrize('mode', ['missing_environment', 'missing_parent', 'not_directory', 'unwritable'])
def test_unavailable_audit_destination_never_continues(operational, monkeypatch, tmp_path, mode):
    op = operational
    identifier = op.issue()
    if mode == 'missing_environment':
        monkeypatch.delenv('LOCALAPPDATA')
    elif mode == 'missing_parent':
        monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'missing'))
    elif mode == 'not_directory':
        (tmp_path / 'file').write_text('synthetic', encoding='utf-8')
        monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'file'))
    else:
        monkeypatch.setattr(a, '_save', Mock(side_effect=PermissionError(SECRET)))
    with pytest.raises(MigrationError) as caught:
        op.run(identifier)
    assert caught.value.operational_result['audit_write_outcome'] == 'failed'
    op.runner.m.load_migration_config.assert_not_called()


@pytest.mark.parametrize('field,value', [('phase', SECRET), ('failure', SECRET),
    ('expected_database', SECRET), ('manifest_hash', SECRET),
    ('secondary_failures', ({'component': 'commit', 'classification': SECRET},))])
def test_sink_refuses_secret_bearing_event(operational, field, value):
    op = operational
    identifier = op.issue()
    run_id = str(uuid4())
    sink = a.FileOperationalAuthority(identifier).authorize(op.request, run_id, artifacts())
    event = m._Evidence(op.request, m.select_identity('testing'), run_id).event()
    with pytest.raises(MigrationError):
        sink.write(replace(event, **{field: value}))
    assert SECRET not in json.dumps(records(op))
    assert not records(op, 'event-*.json')


def test_no_direct_or_subclass_authority_bypass(operational):
    op = operational
    class Forged(a.FileOperationalAuthority):
        def authorize(self, *args):
            return op.runner.sink
    for authority in (None, Forged(str(uuid4())), SimpleNamespace(authorize=lambda *args: op.runner.sink)):
        with pytest.raises(MigrationError):
            m.run(op.request, authority=authority)
    op.runner.m.load_migration_config.assert_not_called()
    assert len(records(op, 'denial-*.json')) == 3


def test_alembic_rejects_unclaimed_real_adapter_with_fabricated_evidence(operational):
    op = operational
    conn = op.runner.connection
    transaction = conn.begin()
    conn.lock = True
    authority = a.FileOperationalAuthority(op.issue())
    evidence = m._Evidence(op.request, m.select_identity('testing'), str(uuid4()))
    for key, value in dict(authorized=True, audit_acknowledged=True, verified=True,
        session_lock_verified=True, phase='revision', validation='preflight_passed',
        observed_start=v.BASE, operational_authority=authority, audit_sink=op.runner.sink,
        verified_connection=conn, verified_transaction=transaction, session_lock_backend=701).items():
        setattr(evidence, key, value)
    before = list(conn.calls)
    with pytest.raises(MigrationError, match=Failure.OPERATIONAL_GATE):
        op.runner.real_execute_revision(conn, evidence.identity, artifacts(), transaction,
                                        evidence, op.runner.sink, authority, 701)
    assert conn.calls == before
    assert not records(op, 'claim-*.json')


@pytest.mark.parametrize('action', ['verify', 'upgrade'])
def test_cli_consumes_existing_record_without_issuance(operational, action):
    op = operational
    request = replace(op.request, action=action)
    identifier = op.issue(op.approvals(request))
    assert m.main([action, '--environment', 'testing', '--expected-start', v.BASE,
                   '--target', v.BASELINE, '--manifest-sha256', request.manifest_hash,
                   '--revision-sha256', request.revision_hash, '--authorization-id', identifier]) == 0
    assert len(records(op, 'authorization-*.json')) == len(records(op, 'claim-*.json')) == 1


def test_owner_issuer_cli_never_runs_database(operational, tmp_path, capsys):
    path = tmp_path / 'synthetic-issuance.json'
    path.write_bytes(json.dumps(operational.spec).encode())
    assert a.main(['issue', '--specification', str(path), '--owner-issue']) == 0
    assert json.loads(capsys.readouterr().out)['outcome'] == 'issued'
    assert not records(operational, 'claim-*.json')
    operational.runner.m.load_migration_config.assert_not_called()


def test_development_requires_testing_validation_and_separate_authorization(operational, monkeypatch):
    op = operational
    testing_id = op.issue()
    result = op.run(testing_id)
    development = replace(op.request, environment='development')
    monkeypatch.setenv('OAF_ENV', 'development')
    with pytest.raises(MigrationError):
        op.issue(op.approvals(development))
    development_id = op.issue(op.approvals(development, testing_run=result['run_id']))
    assert_denied(op, testing_id, development)
    sink = a.FileOperationalAuthority(development_id).authorize(development, str(uuid4()), artifacts())
    assert sink.scope['environment'] == 'development'
    assert len(records(op, 'claim-testing-*.json')) == len(records(op, 'claim-development-*.json')) == 1


def test_pending_manifest_and_metadata_only_baseline_preserved():
    doc = json.loads((v.ROOT / 'migrations/manifest.json').read_bytes())
    assert doc['approval_status'] == 'pending_independent_review'
    assert doc['revisions'][0]['sha256'] == 'bb51b33f3e064a02b8463593440820d65d01537f48a46b487b7cc327f0ea89a3'
    assert v.digest((v.ROOT / v.REVISION_FILE).read_bytes()) == doc['revisions'][0]['sha256']
    assert 'oaf_website/migration_authority.py' in v.FRAMEWORK_FILES


@pytest.mark.parametrize('change', ['duplicate_key', 'extra_field', 'bad_id', 'naive', 'over24', 'truncated'])
def test_malformed_authorization_rejected_and_retained(operational, change):
    op = operational
    identifier = op.issue()
    path = op.root / f'authorization-{identifier}.json'
    data = json.loads(path.read_bytes())
    if change == 'duplicate_key':
        path.write_bytes(path.read_bytes().replace(b'{', b'{"format":1,', 1))
    elif change == 'truncated':
        path.write_bytes(b'{')
    else:
        data.update({'extra_field': {'password': SECRET}, 'bad_id': {'id': str(uuid4())},
                     'naive': {'issued_utc': '2030-01-01T00:00:00'},
                     'over24': {'expires_utc': '2030-01-03T00:00:00+00:00'}}[change])
        path.write_bytes(json.dumps(data).encode())
    before = path.read_bytes()
    assert_denied(op, identifier)
    assert path.read_bytes() == before
    assert SECRET not in json.dumps(records(op, 'denial-*.json'))
    assert not records(op, 'claim-*.json')


def test_partial_claim_requires_owner_reconciliation_of_exact_bytes(operational):
    op = operational
    path = op.root / 'claim-testing-00000001.json'
    path.write_bytes(b'{"interrupted":')
    with pytest.raises(MigrationError):
        op.issue(op.approvals())
    identifier = op.issue(op.approvals(reconciled=True))
    a.FileOperationalAuthority(identifier).authorize(op.request, str(uuid4()), artifacts())
    assert path.read_bytes() == b'{"interrupted":'
    assert (op.root / 'claim-testing-00000002.json').is_file()


def test_invalid_request_types_have_sanitized_persistent_denials(operational):
    op = operational
    assert_denied(op, str(uuid4()), replace(op.request, environment=[SECRET]))
    assert records(op, 'denial-*.json')[-1]['environment'] is None
    assert SECRET not in json.dumps(records(op, 'denial-*.json'))


@pytest.mark.parametrize('entry', ['issuer', 'migration'])
def test_cli_parser_denial_persisted_without_echoing_input(operational, capsys, entry):
    cli = a.main if entry == 'issuer' else m.main
    assert cli(['--invalid', SECRET]) == 1
    assert SECRET not in capsys.readouterr().out
    assert records(operational, 'denial-*.json')


@pytest.mark.parametrize('tamper', [None, 'sink', 'expired', 'request'])
def test_real_adapter_through_runner_and_alembic(context_setup, operational, monkeypatch, tamper):
    op, s = operational, context_setup
    identifier = op.issue()
    monkeypatch.setattr(m, '_execute_revision', op.runner.real_execute_revision)
    s.execute.side_effect = lambda: setattr(op.runner.connection, 'target', True)
    def upgrade(config, target):
        runner_context = config.attributes['oaf_runner']
        if tamper == 'sink':
            # Even mutually consistent fabricated evidence cannot replace the
            # concrete authority's actual claimed sink binding.
            runner_context.evidence.audit_sink = op.runner.sink
            runner_context = replace(runner_context, sink=op.runner.sink)
        elif tamper == 'expired':
            op.clock.now += timedelta(hours=24)
        elif tamper == 'request':
            runner_context.evidence.request = replace(op.request, action='verify')
        config.attributes['oaf_runner'] = runner_context
        monkeypatch.setattr(context, 'config', config)
        s.env()
    monkeypatch.setattr(command, 'upgrade', upgrade)
    if tamper:
        assert_denied_or_failed(op, identifier)
        s.execute.assert_not_called()
        assert op.runner.connection.commits == 0
    else:
        assert op.run(identifier)['outcome'] == 'applied_and_verified'
        s.execute.assert_called_once()
        assert op.runner.connection.commits == 1
    assert not v._ACTIVE_RUNNERS


def test_module_cli_preserves_audit_contract(context_setup, operational, monkeypatch):
    """Exercise __main__ AuditEvent class identity without subprocess/network."""
    import sys
    import sqlalchemy
    from oaf_website import migration_config as c
    op, s = operational, context_setup
    identifier = op.issue()
    monkeypatch.setattr(sqlalchemy, 'create_engine', m.create_engine)
    monkeypatch.setattr(c, 'load_migration_config', m.load_migration_config)
    monkeypatch.setattr(v, 'catalog_state', m.catalog_state)
    monkeypatch.setattr(v, 'verify_authority', m.verify_authority)
    monkeypatch.setattr(v, 'verify_identity', m.verify_identity)
    s.execute.side_effect = lambda: setattr(op.runner.connection, 'target', True)
    def upgrade(config, target):
        monkeypatch.setattr(context, 'config', config)
        s.env()
    monkeypatch.setattr(command, 'upgrade', upgrade)
    monkeypatch.setattr(sys, 'argv', ['oaf_website.migrate', 'upgrade', '--environment', 'testing',
        '--expected-start', v.BASE, '--target', v.BASELINE,
        '--manifest-sha256', op.request.manifest_hash, '--revision-sha256', op.request.revision_hash,
        '--authorization-id', identifier])
    with pytest.warns(RuntimeWarning, match='found in sys.modules'):
        with pytest.raises(SystemExit) as caught:
            runpy.run_module('oaf_website.migrate', run_name='__main__')
    assert caught.value.code == 0
    assert records(op, 'terminal-*.json')[0]['event']['outcome'] == 'applied_and_verified'


def test_claim_before_database_access_and_no_owner_issuer_called_by_runner(operational, monkeypatch):
    op = operational
    identifier = op.issue()
    issuer = Mock(side_effect=AssertionError('runner must not issue'))
    monkeypatch.setattr(a, 'issue_authorization', issuer)
    config = op.runner.m.load_migration_config.return_value
    def load(**kwargs):
        assert len(records(op, 'claim-*.json')) == 1
        assert records(op, 'event-*.json')[0]['event']['phase'] == 'authorization'
        return config
    op.runner.m.load_migration_config.side_effect = load
    op.run(identifier)
    issuer.assert_not_called()


# Independent certification regressions: these assertions fail on the Stage 5 baseline.
def test_r01_readable_authorization_after_failed_fsync_is_not_consumable(operational, monkeypatch):
    op = operational
    sync = a.os.fsync
    calls = 0
    def fail_first(fd):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(SECRET)
        sync(fd)
    with monkeypatch.context() as fault:
        fault.setattr(a.os, 'fsync', fail_first)
        with pytest.raises(MigrationError):
            op.issue()
    residual = records(op, 'authorization-*.json')[0]
    assert residual['kind'] == 'owner_authorization'
    before = (op.root / f'authorization-{residual["id"]}.json').read_bytes()
    assert_denied(op, residual['id'])
    assert (op.root / f'authorization-{residual["id"]}.json').read_bytes() == before
    op.runner.m.load_migration_config.assert_not_called()


@pytest.mark.parametrize('phase', ['revision', 'commit_ready'])
def test_r02_expiration_during_required_audit_fsync(operational, monkeypatch, phase):
    op = operational
    op.spec['expires_utc'] = (op.clock.now + timedelta(seconds=1)).isoformat()
    identifier = op.issue()
    save, sync = a._save, a.os.fsync
    def delayed(path, record):
        if record.get('event', {}).get('phase') == phase:
            with monkeypatch.context() as fault:
                def slow_sync(fd):
                    sync(fd)
                    op.clock.now += timedelta(seconds=2)
                fault.setattr(a.os, 'fsync', slow_sync)
                return save(path, record)
        return save(path, record)
    monkeypatch.setattr(a, '_save', delayed)
    error = assert_denied_or_failed(op, identifier)
    result = error.operational_result
    assert error.classification == Failure.OPERATIONAL_GATE
    assert result['commit_certainty'] == 'not_invoked'
    assert result['transaction_outcome'] == 'rollback_confirmed'
    assert op.runner.connection.commits == 0
    if phase == 'revision':
        assert not result['mutation_started']
        assert 'revision' not in op.runner.connection.calls


def test_r03_readable_failed_testing_terminal_cannot_qualify_development(operational, monkeypatch):
    op = operational
    identifier = op.issue()
    save = a._save
    def fail_terminal_sync(path, record):
        if record['kind'] == 'execution_finalized':
            with monkeypatch.context() as fault:
                fault.setattr(a.os, 'fsync', Mock(side_effect=OSError(SECRET)))
                return save(path, record)
        return save(path, record)
    with monkeypatch.context() as fault:
        fault.setattr(a, '_save', fail_terminal_sync)
        error = assert_denied_or_failed(op, identifier)
    assert error.classification == Failure.AUDIT
    assert error.operational_result['database_commit_confirmed']
    terminal = records(op, 'terminal-*.json')[0]
    assert terminal['event']['outcome'] == 'applied_and_verified'
    development = replace(op.request, environment='development')
    monkeypatch.setenv('OAF_ENV', 'development')
    with pytest.raises(MigrationError):
        op.issue(op.approvals(development, testing_run=terminal['event']['run_id']))


def test_r04_verified_success_permits_separately_authorized_successor(operational):
    op = operational
    identifier = op.issue()
    op.run(identifier)
    request = replace(op.request, expected_start=v.BASELINE)
    successor = op.issue(op.approvals(request))
    assert successor != identifier
    a.FileOperationalAuthority(successor).authorize(
        request, str(uuid4()), replace(artifacts(), expected_start=v.BASELINE))
    assert len(records(op, 'claim-*.json')) == 2


def test_r05_migration_connection_requires_exact_scram(operational):
    op = operational
    op.run(op.issue())
    assert m.create_engine.call_args.kwargs['connect_args'] == {
        'connect_timeout': 5, 'application_name': 'oaf_website_migrations',
        'require_auth': 'scram-sha-256'}


class FaultyStream:
    """Keep the real serializer and buffered file; fail a selected I/O boundary."""
    def __init__(self, stream, boundary):
        self.stream, self.boundary = stream, boundary
        self.writes = 0

    def __enter__(self):
        self.stream.__enter__()
        return self

    def __exit__(self, *args):
        result = self.stream.__exit__(*args)
        if self.boundary == 'close':
            raise OSError(SECRET)
        return result

    def write(self, value):
        self.writes += 1
        if self.boundary == 'serialization' and self.writes == 4:
            raise OSError(SECRET)
        return self.stream.write(value)

    def flush(self):
        self.stream.flush()
        if self.boundary == 'flush':
            raise OSError(SECRET)

    def fileno(self):
        return self.stream.fileno()


def inject_file_fault(monkeypatch, *, prefix, boundary):
    save, opening = a._save, Path.open
    def fault_save(path, record):
        if not path.name.startswith(prefix):
            return save(path, record)
        with monkeypatch.context() as fault:
            if boundary == 'fsync':
                fault.setattr(a.os, 'fsync', Mock(side_effect=OSError(SECRET)))
            else:
                def open_file(candidate, *args, **kwargs):
                    stream = opening(candidate, *args, **kwargs)
                    return FaultyStream(stream, boundary) if candidate == path else stream
                fault.setattr(Path, 'open', open_file)
            return save(path, record)
    monkeypatch.setattr(a, '_save', fault_save)


@pytest.mark.parametrize('prefix', ['authorization-', 'pending-authorization-'])
@pytest.mark.parametrize('boundary', ['serialization', 'flush', 'fsync', 'close'])
def test_r01_every_incomplete_issuance_boundary_is_retained_and_rejected(
        operational, monkeypatch, prefix, boundary):
    op = operational
    with monkeypatch.context() as fault:
        inject_file_fault(fault, prefix=prefix, boundary=boundary)
        with pytest.raises(MigrationError):
            op.issue()
    path, = op.root.glob('authorization-*.json')
    identifier = path.stem.removeprefix('authorization-')
    retained = {path.name: path.read_bytes() for path in op.root.iterdir()}
    assert not list(op.root.glob('completed-authorization-*'))
    assert_denied(op, identifier)
    op.runner.m.load_migration_config.assert_not_called()
    assert all((op.root / name).read_bytes() == data for name, data in retained.items())


@pytest.mark.parametrize('collision', [False, True])
def test_r01_completion_publication_is_exclusive_and_has_no_fallback(operational, monkeypatch, collision):
    op = operational
    link = a.os.link
    def fail_or_collide(source, destination):
        if collision:
            destination.write_bytes(b'{"incomplete":')
            return link(source, destination)  # Real Windows no-replace behavior.
        raise OSError(SECRET)
    with monkeypatch.context() as fault:
        fault.setattr(a.os, 'link', fail_or_collide)
        with pytest.raises(MigrationError):
            op.issue()
    record = records(op, 'authorization-*.json')[0]
    assert list(op.root.glob('pending-authorization-*.json'))
    assert_denied(op, record['id'])
    op.runner.m.load_migration_config.assert_not_called()


@pytest.mark.parametrize('change', ['id', 'record', 'digest', 'truncated', 'other_completion'])
def test_r01_consumption_requires_completion_of_exact_authorization(operational, change):
    op = operational
    identifier, other = op.issue(), op.issue()
    path = op.root / f'completed-authorization-{identifier}.json'
    completion = json.loads(path.read_bytes())
    if change == 'truncated':
        path.write_bytes(b'{')
    elif change == 'other_completion':
        path.write_bytes((op.root / f'completed-authorization-{other}.json').read_bytes())
    else:
        completion[{'id': 'authorization_id', 'record': 'record', 'digest': 'sha256'}[change]] = {
            'id': other, 'record': f'authorization-{other}.json', 'digest': '0' * 64}[change]
        path.write_bytes(json.dumps(completion).encode())
    assert_denied(op, identifier)
    op.runner.m.load_migration_config.assert_not_called()


@pytest.mark.parametrize('boundary', ['catalog', 'configure', 'begin'])
def test_r02_alembic_rechecks_after_lengthy_validation(context_setup, operational, monkeypatch, boundary):
    from contextlib import contextmanager
    op, s = operational, context_setup
    op.spec['expires_utc'] = (op.clock.now + timedelta(seconds=1)).isoformat()
    identifier = op.issue()
    monkeypatch.setattr(m, '_execute_revision', op.runner.real_execute_revision)
    def expire(*args, **kwargs):
        op.clock.now += timedelta(seconds=2)
        return v.BASE
    if boundary == 'catalog':
        v.catalog_state.side_effect = expire
    elif boundary == 'configure':
        s.configure.side_effect = expire
    else:
        @contextmanager
        def delayed_begin():
            expire()
            yield
        monkeypatch.setattr(context, 'begin_transaction', delayed_begin)
    def upgrade(config, target):
        monkeypatch.setattr(context, 'config', config)
        s.env()
    monkeypatch.setattr(command, 'upgrade', upgrade)
    error = assert_denied_or_failed(op, identifier)
    assert error.classification == Failure.OPERATIONAL_GATE
    assert not error.operational_result['mutation_started']
    assert error.operational_result['commit_certainty'] == 'not_invoked'
    assert error.operational_result['transaction_outcome'] == 'rollback_confirmed'
    s.execute.assert_not_called()
    assert op.runner.connection.commits == 0


@pytest.mark.parametrize('phase', ['revision', 'commit_ready'])
@pytest.mark.parametrize('change', ['authorization_id', 'payload', 'completion', 'clock_reversal'])
def test_r02_final_boundaries_revalidate_exact_authorization(operational, monkeypatch, phase, change):
    op = operational
    identifier = op.issue()
    authority = a.FileOperationalAuthority(identifier)
    save = a._save
    def changed(path, record):
        save(path, record)
        if record.get('event', {}).get('phase') != phase:
            return
        if change == 'authorization_id':
            authority.authorization_id = str(uuid4())
        elif change == 'clock_reversal':
            op.clock.now -= timedelta(seconds=1)
        else:
            name = f'authorization-{identifier}.json'
            if change == 'completion':
                name = 'completed-' + name
            (op.root / name).write_bytes(b'{}')
    monkeypatch.setattr(a, '_save', changed)
    with pytest.raises(MigrationError) as caught:
        m.run(op.request, authority=authority)
    assert caught.value.classification == Failure.OPERATIONAL_GATE
    assert caught.value.operational_result['commit_certainty'] == 'not_invoked'
    assert caught.value.operational_result['transaction_outcome'] == 'rollback_confirmed'
    assert op.runner.connection.commits == 0
    if phase == 'revision':
        assert not caught.value.operational_result['mutation_started']


@pytest.mark.parametrize('prefix', ['terminal-', 'pending-terminal-'])
@pytest.mark.parametrize('boundary', ['serialization', 'flush', 'fsync', 'close'])
def test_r03_testing_completion_failures_block_development_and_successors(
        operational, monkeypatch, prefix, boundary):
    op = operational
    identifier = op.issue()
    with monkeypatch.context() as fault:
        inject_file_fault(fault, prefix=prefix, boundary=boundary)
        with pytest.raises(MigrationError) as caught:
            op.run(identifier)
    result = caught.value.operational_result
    assert caught.value.classification == Failure.AUDIT
    assert result['database_commit_confirmed']
    assert result['transaction_outcome'] == 'committed_confirmed'
    assert not list(op.root.glob('completed-terminal-*'))
    preserved = {path.name: path.read_bytes() for path in op.root.iterdir()}
    with pytest.raises(MigrationError):
        op.issue(op.approvals(replace(op.request, expected_start=v.BASELINE)))
    development = replace(op.request, environment='development')
    monkeypatch.setenv('OAF_ENV', 'development')
    with pytest.raises(MigrationError):
        op.issue(op.approvals(development, testing_run=result['run_id']))
    assert all((op.root / name).read_bytes() == content for name, content in preserved.items())


def test_r03_terminal_publication_failure_keeps_acknowledged_commit(operational, monkeypatch):
    op = operational
    identifier = op.issue()
    with monkeypatch.context() as fault:
        fault.setattr(a.os, 'link', Mock(side_effect=OSError(SECRET)))
        error = assert_denied_or_failed(op, identifier)
    assert error.classification == Failure.AUDIT
    assert error.operational_result['database_commit_confirmed']
    assert records(op, 'terminal-*.json')[0]['event']['outcome'] == 'applied_and_verified'
    assert records(op, 'pending-terminal-*.json')
    assert not records(op, 'completed-terminal-*.json')
    with pytest.raises(MigrationError):
        op.issue(op.approvals(replace(op.request, expected_start=v.BASELINE)))


@pytest.mark.parametrize('outcome', ['uncertain', 'terminal_fsync'])
def test_r03_exceptional_reconciliation_requires_fresh_completed_testing_validation(
        operational, monkeypatch, outcome):
    op = operational
    identifier = op.issue()
    if outcome == 'uncertain':
        op.runner.connection.hooks['commit'] = DriverError('08006')
    with monkeypatch.context() as fault:
        if outcome == 'terminal_fsync':
            inject_file_fault(fault, prefix='terminal-', boundary='fsync')
        error = assert_denied_or_failed(op, identifier)
    original_run = error.run_id
    testing = replace(op.request, expected_start=v.BASELINE)
    with pytest.raises(MigrationError):
        op.issue(op.approvals(testing))
    # The existing prerequisite approval attests reconciliation of the exact
    # claim and independently verified DB state. It never edits the old result.
    reconciled = op.issue(op.approvals(testing, reconciled=True))
    op.runner.connection.hooks.clear()
    op.runner.connection.closed = False
    op.runner.connection.transaction = None
    op.runner.connection.lock = False
    op.runner.connection.target = True
    validation = op.run(reconciled, testing)
    assert validation['outcome'] == 'verified_noop'
    assert not validation['database_commit_confirmed']
    development = replace(op.request, environment='development')
    monkeypatch.setenv('OAF_ENV', 'development')
    with pytest.raises(MigrationError):
        op.issue(op.approvals(development, testing_run=original_run))
    fresh = op.issue(op.approvals(development, testing_run=validation['run_id']))
    assert fresh not in {identifier, reconciled}
    a.FileOperationalAuthority(fresh).authorize(development, str(uuid4()), artifacts())


@pytest.mark.parametrize('change', ['predecessor', 'state', 'decision', 'time', 'reconciliation'])
def test_r03_invalid_exceptional_reconciliation_is_rejected(operational, change):
    op = operational
    a.FileOperationalAuthority(op.issue()).authorize(op.request, str(uuid4()), artifacts())
    spec = op.approvals(reconciled=True)
    ref = spec['prerequisite_approval']
    path = op.root / f'prerequisite-approval-{ref["id"]}.json'
    document = json.loads(path.read_bytes())
    document.update({
        'predecessor': {'predecessor': {'sequence': 1, 'sha256': '0' * 64}},
        'state': {'expected_start': v.BASELINE}, 'decision': {'decision': 'pending'},
        'time': {'approved_utc': '2000-01-01T00:00:00+00:00'},
        'reconciliation': {'owner_reconciliation': 'not_applicable'},
    }[change])
    spec['prerequisite_approval'] = reference(path, document)
    with pytest.raises(MigrationError):
        op.issue(spec)


@pytest.mark.parametrize('action', ['upgrade', 'verify'])
def test_r04_verified_noop_or_verification_permits_new_authorization(operational, action):
    op = operational
    request = replace(op.request, action=action, expected_start=v.BASELINE)
    op.runner.connection.target = True
    identifier = op.issue(op.approvals(request))
    result = op.run(identifier, request)
    assert result['outcome'] in {'verified_noop', 'verified_target'}
    before = {path.name: path.read_bytes() for path in op.root.iterdir()}
    successor = op.issue(op.approvals(request))
    assert successor != identifier
    a.FileOperationalAuthority(successor).authorize(
        request, str(uuid4()), replace(artifacts(), expected_start=v.BASELINE))
    assert all((op.root / name).read_bytes() == value for name, value in before.items())
    assert_denied(op, identifier, request)


@pytest.mark.parametrize('failure', ['credential', 'connection', 'lock_busy', 'expired_before_mutation', 'drift'])
def test_r04_premutation_failure_requires_conclusive_safe_continuation(operational, monkeypatch, failure):
    op = operational
    identifier = op.issue()
    if failure == 'credential':
        m.load_migration_config.side_effect = MigrationError(Failure.CREDENTIAL_UNAVAILABLE)
    elif failure == 'connection':
        op.runner.engine.connect.side_effect = DriverError('08001')
    elif failure == 'lock_busy':
        op.runner.connection.hooks['acquire'] = MigrationError(Failure.LOCK_BUSY)
    elif failure == 'drift':
        op.runner.connection.hooks['catalog'] = MigrationError(Failure.DRIFT)
    else:
        save = a._save
        def expire(path, record):
            save(path, record)
            if record.get('event', {}).get('phase') == 'revision':
                op.clock.now += timedelta(hours=24)
        monkeypatch.setattr(a, '_save', expire)
    error = assert_denied_or_failed(op, identifier)
    assert not error.operational_result['mutation_started']
    spec = op.approvals()
    if failure == 'drift':
        with pytest.raises(MigrationError):
            op.issue(spec)
    else:
        assert op.issue(spec) != identifier


@pytest.mark.parametrize('change', ['missing_completion', 'missing_event', 'wrong_authorization',
    'commit', 'mutation', 'cleanup', 'outcome', 'event_hash', 'scope'])
def test_r04_missing_or_contradictory_completed_evidence_blocks(operational, change):
    op = operational
    result = op.run(op.issue())
    path = op.root / f'terminal-{result["run_id"]}.json'
    marker = path.with_name('completed-' + path.name)
    if change == 'missing_completion':
        marker.rename(marker.with_suffix('.withheld'))
    elif change == 'missing_event':
        event = next(op.root.glob('event-*.json'))
        event.rename(event.with_suffix('.withheld'))
    elif change == 'event_hash':
        next(op.root.glob('event-*.json')).write_bytes(b'{}')
    else:
        terminal = json.loads(path.read_bytes())
        if change == 'wrong_authorization':
            terminal['authorization_id'] = str(uuid4())
        else:
            terminal['event'].update({
                'commit': {'commit_certainty': 'uncertain'},
                'mutation': {'mutation_started': False},
                'cleanup': {'cleanup': dict(terminal['event']['cleanup'], rollback='failed')},
                'outcome': {'outcome': 'verified_noop'},
                'scope': {'environment': 'development'},
            }[change])
        path.write_bytes(json.dumps(terminal).encode())
        # Even a matching terminal digest does not excuse contradictory fields.
        completion = json.loads(marker.read_bytes())
        completion['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        marker.write_bytes(json.dumps(completion).encode())
    with pytest.raises(MigrationError):
        op.issue(op.approvals(replace(op.request, expected_start=v.BASELINE)))


@pytest.mark.parametrize('method', ['password', 'md5', 'none', 'unsupported_require_auth'])
def test_r05_authentication_rejection_has_no_weaker_retry(operational, method):
    op = operational
    # Model the libpq rejection, never an authentication exchange or connection.
    def reject():
        assert m.create_engine.call_args.kwargs['connect_args']['require_auth'] == 'scram-sha-256'
        raise DriverError('08001')
    op.runner.engine.connect.side_effect = reject
    error = assert_denied_or_failed(op, op.issue())
    assert error.classification == Failure.CONNECTION
    op.runner.engine.connect.assert_called_once()
    m.create_engine.assert_called_once()
    assert op.runner.connection.calls == ['dispose']
    assert not error.operational_result['database_commit_confirmed']


@pytest.mark.parametrize('interruption', [False, True])
def test_r01_completed_publication_with_interrupted_response_is_not_reported_failed(
        operational, monkeypatch, interruption):
    op = operational
    link = a.os.link
    def publish_then_interrupt(source, destination):
        link(source, destination)
        raise KeyboardInterrupt() if interruption else OSError(SECRET)
    with monkeypatch.context() as fault:
        fault.setattr(a.os, 'link', publish_then_interrupt)
        identifier = op.issue()
        result = op.run(identifier)
    assert result['outcome'] == 'applied_and_verified'
    assert result['cleanup']['audit_finalize'] == 'confirmed_successful'
    assert not records(op, 'denial-*.json')
    assert (op.root / f'completed-authorization-{identifier}.json').is_file()
    assert (op.root / f'completed-terminal-{result["run_id"]}.json').is_file()


@pytest.mark.parametrize('prefix', ['pending-authorization-', 'pending-terminal-'])
def test_r01_r03_no_completion_name_is_visible_until_synchronization_returns(
        operational, monkeypatch, prefix):
    op = operational
    save, sync = a._save, a.os.fsync
    observed = []
    def observe(path, record):
        if not path.name.startswith(prefix):
            return save(path, record)
        with monkeypatch.context() as fault:
            def synchronize(fd):
                observed.append(json.loads(path.read_bytes()))
                assert not path.with_name(path.name.replace('pending-', 'completed-', 1)).exists()
                sync(fd)
            fault.setattr(a.os, 'fsync', synchronize)
            return save(path, record)
    monkeypatch.setattr(a, '_save', observe)
    result = op.run(op.issue())
    assert len(observed) == 1
    assert result['outcome'] == 'applied_and_verified'



def test_r02_expiration_after_commit_invocation_preserves_acknowledged_commit(operational):
    op = operational
    op.spec['expires_utc'] = (op.clock.now + timedelta(seconds=1)).isoformat()
    def delayed_commit(connection):
        op.clock.now += timedelta(seconds=2)
    op.runner.connection.hooks['commit'] = delayed_commit
    result = op.run(op.issue())
    assert result['outcome'] == 'applied_and_verified'
    assert result['commit_certainty'] == 'confirmed'
    assert result['database_commit_confirmed']
    assert result['transaction_outcome'] == 'committed_confirmed'
    assert result['validation_outcome'] == 'postcommit_passed'
    assert records(op, 'completed-terminal-*.json')


def test_r03_older_success_stays_stale_after_unexecuted_reconciliation(operational, monkeypatch):
    op = operational
    first = op.run(op.issue())
    testing = replace(op.request, expected_start=v.BASELINE)
    second_id = op.issue(op.approvals(testing))
    op.runner.connection.closed = False
    with monkeypatch.context() as fault:
        inject_file_fault(fault, prefix='terminal-', boundary='fsync')
        with pytest.raises(MigrationError) as caught:
            op.run(second_id, testing)
    assert caught.value.classification == Failure.AUDIT
    terminal, _ = a._read(op.root / f'terminal-{caught.value.run_id}.json')
    assert terminal['event']['outcome'] == 'verified_noop'
    with pytest.raises(MigrationError):
        op.issue(op.approvals(testing))
    reconciled = op.issue(op.approvals(testing, reconciled=True))
    assert not any(c['authorization_id'] == reconciled for c in records(op, 'claim-testing-*.json'))
    development = replace(op.request, environment='development')
    monkeypatch.setenv('OAF_ENV', 'development')
    with pytest.raises(MigrationError):
        op.issue(op.approvals(development, testing_run=first['run_id']))


@pytest.fixture
def freshness(operational, monkeypatch):
    """Real issuer/consumer and published file evidence; fake DB and clock only."""
    op = operational
    first = op.run(op.issue())
    testing = replace(op.request, expected_start=v.BASELINE)
    development = replace(op.request, environment='development')

    def successor(outcome='success', *, reconciled=False, action='upgrade'):
        request = replace(testing, action=action)
        with monkeypatch.context() as fault:
            fault.setenv('OAF_ENV', 'testing')
            identifier = op.issue(op.approvals(request, reconciled=reconciled))
            if outcome == 'issued':
                return SimpleNamespace(id=identifier, run_id=None)
            if outcome == 'incomplete':
                run_id = str(uuid4())
                a.FileOperationalAuthority(identifier).authorize(
                    request, run_id, replace(artifacts(), expected_start=v.BASELINE))
                return SimpleNamespace(id=identifier, run_id=run_id)
            op.runner.connection.closed = False
            if outcome == 'terminal_fsync':
                inject_file_fault(fault, prefix='terminal-', boundary='fsync')
            elif outcome == 'safe_failure':
                fault.setattr(m, 'load_migration_config', Mock(
                    side_effect=MigrationError(Failure.CREDENTIAL_UNAVAILABLE)))
            if outcome in {'terminal_fsync', 'safe_failure'}:
                with pytest.raises(MigrationError) as caught:
                    op.run(identifier, request)
                expected = Failure.AUDIT if outcome == 'terminal_fsync' else Failure.CREDENTIAL_UNAVAILABLE
                assert caught.value.classification == expected
                run_id = caught.value.run_id
            else:
                result = op.run(identifier, request)
                assert result['outcome'] == ('verified_noop' if action == 'upgrade' else 'verified_target')
                run_id = result['run_id']
        return SimpleNamespace(id=identifier, run_id=run_id)

    return SimpleNamespace(op=op, first=first, testing=testing, development=development,
                           successor=successor)


@pytest.mark.parametrize('gate', ['issuance', 'consumption'])
@pytest.mark.parametrize('later', ['none', 'issued', 'success', 'verification', 'safe_failure',
                                  'terminal_fsync', 'incomplete'])
def test_r03_freshness_at_both_authorization_gates(freshness, monkeypatch, gate, later):
    f, op = freshness, freshness.op
    monkeypatch.setenv('OAF_ENV', 'development')
    spec = op.approvals(f.development, testing_run=f.first['run_id'])
    identifier = op.issue(spec) if gate == 'consumption' else None
    if later != 'none':
        f.successor('success' if later == 'verification' else later,
                    action='verify' if later == 'verification' else 'upgrade')
    denied = later in {'terminal_fsync', 'incomplete'}
    if denied:
        with pytest.raises(MigrationError) as caught:
            if gate == 'issuance':
                op.issue(spec)
            else:
                a.FileOperationalAuthority(identifier).authorize(f.development, str(uuid4()), artifacts())
        assert caught.value.classification == Failure.OPERATIONAL_GATE
        assert not records(op, 'claim-development-*.json')
    else:
        identifier = identifier or op.issue(spec)
        authority = a.FileOperationalAuthority(identifier)
        sink = authority.authorize(f.development, str(uuid4()), artifacts())
        authority.require_binding(f.development, sink.run_id, sink)
        assert_denied(op, identifier, f.development)


@pytest.mark.parametrize('third', ['issued', 'incomplete', 'terminal_fsync', 'safe_failure', 'success'])
def test_r03_recovery_needs_new_completed_validation_and_new_citation(freshness, monkeypatch, third):
    f, op = freshness, freshness.op
    f.successor('terminal_fsync')
    validation = f.successor(third, reconciled=True)
    monkeypatch.setenv('OAF_ENV', 'development')
    with pytest.raises(MigrationError):
        op.issue(op.approvals(f.development, testing_run=f.first['run_id']))
    spec = op.approvals(f.development, testing_run=validation.run_id)
    if third != 'success':
        with pytest.raises(MigrationError):
            op.issue(spec)
    else:
        f.successor()  # Ordinary T4 does not impose another reconciliation.
        identifier = op.issue(spec)
        assert identifier != validation.id
        assert_denied(op, validation.id, f.development)
        op.runner.connection.closed = False
        op.runner.connection.target = False
        assert op.run(identifier, f.development)['outcome'] == 'applied_and_verified'
        assert_denied(op, identifier, f.development)


@pytest.mark.parametrize('gate', ['issuance', 'consumption'])
@pytest.mark.parametrize('change', ['partial_claim', 'gap', 'malformed_name', 'missing_terminal',
    'missing_completion', 'missing_event', 'event_hash', 'contradictory_terminal',
    'cross_environment', 'artifact', 'predecessor_hash', 'missing_approval', 'pending_approval'])
def test_r03_subsequent_untrusted_evidence_fails_closed(freshness, monkeypatch, gate, change):
    f, op = freshness, freshness.op
    monkeypatch.setenv('OAF_ENV', 'development')
    spec = op.approvals(f.development, testing_run=f.first['run_id'])
    identifier = op.issue(spec) if gate == 'consumption' else None
    later = f.successor()
    claim_path = op.root / 'claim-testing-00000002.json'
    terminal_path = op.root / f'terminal-{later.run_id}.json'
    marker = terminal_path.with_name('completed-' + terminal_path.name)
    if change == 'partial_claim':
        claim_path.write_bytes(b'{')
    elif change in {'gap', 'malformed_name'}:
        claim_path.rename(op.root / ('claim-testing-00000003.json' if change == 'gap'
                                    else 'claim-testing-invalid.json'))
    elif change in {'missing_terminal', 'missing_completion', 'missing_event'}:
        path = {'missing_terminal': terminal_path, 'missing_completion': marker,
                'missing_event': next(op.root.glob(f'event-{later.run_id}-*.json'))}[change]
        path.rename(path.with_suffix('.withheld'))
    elif change == 'event_hash':
        next(op.root.glob(f'event-{later.run_id}-*.json')).write_bytes(b'{}')
    elif change in {'missing_approval', 'pending_approval'}:
        authorization, _ = a._authorization(op.root, later.id)
        ref = authorization['prerequisite_approval']
        path = op.root / f'prerequisite-approval-{ref["id"]}.json'
        if change == 'missing_approval':
            path.rename(path.with_suffix('.withheld'))
        else:
            record, _ = a._read(path)
            record['decision'] = 'pending'
            reference(path, record)
    elif change == 'predecessor_hash':
        claim, _ = a._read(claim_path)
        claim['predecessor']['sha256'] = '0' * 64
        claim_path.write_bytes(json.dumps(claim).encode())
    else:
        terminal, _ = a._read(terminal_path)
        terminal['event'].update({
            'contradictory_terminal': {'commit_certainty': 'uncertain'},
            'cross_environment': {'environment': 'development'},
            'artifact': {'manifest_hash': '0' * 64},
        }[change])
        terminal_path.write_bytes(json.dumps(terminal).encode())
        completion, _ = a._read(marker)
        completion['sha256'] = hashlib.sha256(terminal_path.read_bytes()).hexdigest()
        marker.write_bytes(json.dumps(completion).encode())
    with pytest.raises(MigrationError) as caught:
        if gate == 'issuance':
            op.issue(spec)
        else:
            a.FileOperationalAuthority(identifier).authorize(f.development, str(uuid4()), artifacts())
    assert caught.value.classification == Failure.OPERATIONAL_GATE
    assert not records(op, 'claim-development-*.json')


@pytest.mark.parametrize('boundary', ['claim', 'authorization', 'revision', 'commit_ready', 'noop', 'verify'])
def test_r03_intervening_testing_claim_blocks_development_execution(freshness, monkeypatch, boundary):
    f, op = freshness, freshness.op
    testing_id = f.successor('issued').id
    monkeypatch.setenv('OAF_ENV', 'development')
    request = replace(f.development, action='verify' if boundary == 'verify' else 'upgrade',
                      expected_start=v.BASELINE if boundary in {'noop', 'verify'} else v.BASE)
    identifier = op.issue(op.approvals(request, testing_run=f.first['run_id']))
    op.runner.connection.closed = False
    op.runner.connection.target = request.expected_start == v.BASELINE
    commits = op.runner.connection.commits
    save = a._save
    injected = []

    def interleave(path, record):
        save(path, record)
        phase = 'preflight' if boundary in {'noop', 'verify'} else boundary
        trigger = (path.name.startswith('claim-development-') if boundary == 'claim'
                   else record.get('event', {}).get('phase') == phase)
        if trigger and not injected:
            injected.append(True)
            with monkeypatch.context() as fault:
                fault.setenv('OAF_ENV', 'testing')
                a.FileOperationalAuthority(testing_id).authorize(
                    f.testing, str(uuid4()), replace(artifacts(), expected_start=v.BASELINE))

    monkeypatch.setattr(a, '_save', interleave)
    with pytest.raises(MigrationError) as caught:
        op.run(identifier, request)
    assert injected == [True]
    assert caught.value.classification == Failure.OPERATIONAL_GATE
    assert caught.value.operational_result['commit_certainty'] == 'not_invoked'
    assert op.runner.connection.commits == commits
    if boundary != 'commit_ready':
        assert not caught.value.operational_result['mutation_started']
    assert len(records(op, 'claim-development-*.json')) == 1
    assert len(records(op, 'claim-testing-*.json')) == 2


@pytest.mark.parametrize('gate', ['issuance', 'consumption'])
def test_r03_freshness_scan_rejects_concurrent_new_testing_slot(freshness, monkeypatch, gate):
    f, op = freshness, freshness.op
    testing_id = f.successor('issued').id
    monkeypatch.setenv('OAF_ENV', 'development')
    spec = op.approvals(f.development, testing_run=f.first['run_id'])
    identifier = op.issue(spec) if gate == 'consumption' else None
    completed_run = a._completed_run
    injected = []

    def consume_testing():
        with monkeypatch.context() as fault:
            fault.setenv('OAF_ENV', 'testing')
            return a.FileOperationalAuthority(testing_id).authorize(
                f.testing, str(uuid4()), replace(artifacts(), expected_start=v.BASELINE))

    with ThreadPoolExecutor(max_workers=1) as executor:
        def overtaken(root, path):
            result = completed_run(root, path)
            if not injected:
                injected.append(True)
                assert executor.submit(consume_testing).result(timeout=5) is not None
            return result
        monkeypatch.setattr(a, '_completed_run', overtaken)
        with pytest.raises(MigrationError):
            if gate == 'issuance':
                op.issue(spec)
            else:
                a.FileOperationalAuthority(identifier).authorize(f.development, str(uuid4()), artifacts())
    assert injected == [True]
    assert not records(op, 'claim-development-*.json')
    assert len(records(op, 'claim-testing-*.json')) == 2


@pytest.mark.parametrize('same_id', [True, False])
def test_r03_current_development_authorizations_still_compete_for_one_slot(freshness, monkeypatch, same_id):
    f, op = freshness, freshness.op
    f.successor()
    monkeypatch.setenv('OAF_ENV', 'development')
    spec = op.approvals(f.development, testing_run=f.first['run_id'])
    identifiers = [op.issue(spec), op.issue(spec)]
    if same_id:
        identifiers[1] = identifiers[0]
    barrier, save = Barrier(2), a._save

    def simultaneous(path, record):
        if path.name.startswith('claim-development-'):
            barrier.wait(timeout=5)
        return save(path, record)

    def consume(identifier):
        try:
            return a.FileOperationalAuthority(identifier).authorize(f.development, str(uuid4()), artifacts())
        except MigrationError:
            return None

    monkeypatch.setattr(a, '_save', simultaneous)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(consume, identifiers))
    assert sum(result is not None for result in results) == 1
    assert len(records(op, 'claim-development-*.json')) == 1


@pytest.mark.parametrize('boundary', ['catalog', 'configure', 'begin_transaction'])
def test_r03_alembic_final_boundary_rechecks_testing_freshness(context_setup, freshness, monkeypatch, boundary):
    from contextlib import contextmanager
    f, op, s = freshness, freshness.op, context_setup
    testing_id = f.successor('issued').id
    monkeypatch.setenv('OAF_ENV', 'development')
    identifier = op.issue(op.approvals(f.development, testing_run=f.first['run_id']))
    op.runner.connection.closed = False
    op.runner.connection.target = False
    commits = op.runner.connection.commits
    monkeypatch.setattr(m, '_execute_revision', op.runner.real_execute_revision)

    def intervene(*args, **kwargs):
        with monkeypatch.context() as fault:
            fault.setenv('OAF_ENV', 'testing')
            a.FileOperationalAuthority(testing_id).authorize(
                f.testing, str(uuid4()), replace(artifacts(), expected_start=v.BASELINE))
        return v.BASE

    if boundary == 'catalog':
        v.catalog_state.side_effect = intervene
    elif boundary == 'configure':
        s.configure.side_effect = intervene
    else:
        @contextmanager
        def begin():
            intervene()
            yield
        monkeypatch.setattr(context, 'begin_transaction', begin)

    def upgrade(config, target):
        monkeypatch.setattr(context, 'config', config)
        s.env()

    monkeypatch.setattr(command, 'upgrade', upgrade)
    with pytest.raises(MigrationError) as caught:
        op.run(identifier, f.development)
    assert caught.value.classification == Failure.OPERATIONAL_GATE
    assert not caught.value.operational_result['mutation_started']
    assert caught.value.operational_result['commit_certainty'] == 'not_invoked'
    assert op.runner.connection.commits == commits
    s.execute.assert_not_called()


@pytest.mark.parametrize('change', ['reconciliation', 'predecessor_hash', 'state', 'time',
                                  'decision', 'artifact_approval'])
def test_r03_fresh_validation_requires_trusted_recovery_even_with_matching_hashes(freshness, monkeypatch, change):
    f, op = freshness, freshness.op
    f.successor('terminal_fsync')
    third = f.successor(reconciled=True)
    # Synthetic corruption, rehashing every dependent record: terminal success
    # and matching hashes must not substitute for valid recovery/approval.
    authorization, _ = a._authorization(op.root, third.id)
    key = 'artifact_approval' if change == 'artifact_approval' else 'prerequisite_approval'
    ref = authorization[key]
    approval_path = op.root / f'{key.replace("_", "-")}-{ref["id"]}.json'
    approval, _ = a._read(approval_path)
    approval.update({
        'reconciliation': {'owner_reconciliation': 'not_applicable'},
        'predecessor_hash': {'predecessor': {'sequence': 2, 'sha256': '0' * 64}},
        'state': {'expected_start': v.BASE},
        'time': {'approved_utc': '2000-01-01T00:00:00+00:00'},
        'decision': {'decision': 'pending'},
        'artifact_approval': {'decision': 'pending'},
    }[change])
    authorization[key] = reference(approval_path, approval)
    claim_path = op.root / 'claim-testing-00000003.json'
    claim, _ = a._read(claim_path)
    if change == 'predecessor_hash':
        authorization['predecessor'] = claim['predecessor'] = approval['predecessor']
    auth_path = op.root / f'authorization-{third.id}.json'
    auth_path.write_bytes(json.dumps(authorization).encode())
    auth_hash = hashlib.sha256(auth_path.read_bytes()).hexdigest()
    auth_marker = auth_path.with_name('completed-' + auth_path.name)
    completion, _ = a._read(auth_marker)
    completion['sha256'] = auth_hash
    auth_marker.write_bytes(json.dumps(completion).encode())
    claim['authorization_sha256'] = auth_hash
    claim_path.write_bytes(json.dumps(claim).encode())
    terminal_marker = op.root / f'completed-terminal-{third.run_id}.json'
    completion, _ = a._read(terminal_marker)
    completion['evidence'][claim_path.name] = hashlib.sha256(claim_path.read_bytes()).hexdigest()
    terminal_marker.write_bytes(json.dumps(completion).encode())
    event, history = a._completed_run(op.root, claim_path)
    assert a._continuation_state(event, history) == v.BASELINE
    monkeypatch.setenv('OAF_ENV', 'development')
    with pytest.raises(MigrationError):
        op.issue(op.approvals(f.development, testing_run=third.run_id))


@pytest.mark.parametrize('partial', [False, True])
def test_r03_reconciled_interrupted_claim_allows_only_fresh_validation(freshness, monkeypatch, partial):
    f, op = freshness, freshness.op
    f.successor('incomplete')
    if partial:
        (op.root / 'claim-testing-00000002.json').write_bytes(b'{')
    validation = f.successor(reconciled=True)
    monkeypatch.setenv('OAF_ENV', 'development')
    with pytest.raises(MigrationError):
        op.issue(op.approvals(f.development, testing_run=f.first['run_id']))
    identifier = op.issue(op.approvals(f.development, testing_run=validation.run_id))
    a.FileOperationalAuthority(identifier).authorize(f.development, str(uuid4()), artifacts())


def test_r03_recovery_does_not_revive_previously_issued_stale_development_authorization(freshness, monkeypatch):
    f, op = freshness, freshness.op
    monkeypatch.setenv('OAF_ENV', 'development')
    identifier = op.issue(op.approvals(f.development, testing_run=f.first['run_id']))
    f.successor('terminal_fsync')
    f.successor(reconciled=True)
    with pytest.raises(MigrationError):
        a.FileOperationalAuthority(identifier).authorize(f.development, str(uuid4()), artifacts())
    assert not records(op, 'claim-development-*.json')
