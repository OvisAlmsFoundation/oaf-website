"""Local owner authorization and append-only migration evidence.

No I/O at import. Same-Windows-account files are not tamper-proof and UUIDs
provide references, not cryptographic identity. Approval records are supplied
independently; this module never approves artifacts or prerequisites.
"""

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import UUID, uuid4

from .migration_config import IDENTITIES, Failure, MigrationError, select_identity
from .migration_validation import BASE, BASELINE, STATE_REQUESTS, NOTIFICATIONS, DELIVERY, OUTBOX, MANAGEMENT, RELEASE_APPROVALS, validate_artifacts


PREREQUISITES = frozenset({
    'dependency_acceptance', 'bootstrap_validation', 'lock_and_timeouts',
    'search_path_and_postconditions', 'recovery_procedure', 'audit_policies',
})
_SCOPE = ('action', 'environment', 'expected_start', 'target', 'manifest_hash', 'revision_hash')


def _now():
    return datetime.now(timezone.utc)


def _require(condition):
    if not condition:
        raise MigrationError(Failure.OPERATIONAL_GATE)


def _uuid(value):
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except ValueError:
        return False


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _utc(value):
    _require(isinstance(value, str))
    parsed = datetime.fromisoformat(value)
    _require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0))
    return parsed


def audit_destination():
    """Exact Stage 4C precedent, with a separate migration child directory."""
    local = os.environ.get('LOCALAPPDATA')
    _require(isinstance(local, str) and bool(local))
    base = Path(local)
    _require(base.is_absolute())
    root = base / 'OAF Website' / 'BootstrapAudit' / 'MigrationAudit'
    # Reject redirects instead of silently adopting a different destination.
    _require(root.resolve() == root and root.parent.is_dir())
    root.mkdir(exist_ok=True)
    _require(root.is_dir())
    return root


def _save(path, record):
    """Never overwrite/delete, including partial writes and interrupted claims."""
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(record, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _read(path):
    _require(path.resolve() == path and path.is_file())
    payload = path.read_bytes()
    _require(len(payload) <= 64_000)
    record = json.loads(payload, object_pairs_hook=_unique)
    _require(type(record) is dict)
    return record, hashlib.sha256(payload).hexdigest()


def _publish_completion(path, authorization_id, *, run_id=None, evidence=None):
    """Publish only AFTER every content write, flush, fsync and close succeeds.

    The exclusive hard link is the completion point (Windows local filesystem).
    No fallible synchronization follows publication. Both names are retained;
    pending JSON alone is never completion. Unsupported publication fails closed.
    This does not strengthen the documented power-loss or same-account boundary.
    """
    _, digest = _read(path)
    pending = path.with_name('pending-' + path.name)
    _save(pending, {
        'format': 1, 'kind': 'record_completion', 'record': path.name,
        'sha256': digest, 'authorization_id': authorization_id, 'run_id': run_id,
        'evidence': evidence or {},
    })
    completed = path.with_name('completed-' + path.name)
    try:
        os.link(pending, completed)
    except (Exception, KeyboardInterrupt):
        # An interrupted response can follow successful atomic publication.
        # Resolve that exact link read-only; never retry, overwrite, or delete.
        # All content synchronization already succeeded before this boundary.
        try:
            published = completed.samefile(pending)
        except OSError:
            published = False
        if not published:
            raise


def _completed(path, authorization_id, *, run_id=None):
    record, digest = _read(path)
    completion, _ = _read(path.with_name('completed-' + path.name))
    _require(set(completion) == {'format', 'kind', 'record', 'sha256',
                                 'authorization_id', 'run_id', 'evidence'})
    _require(type(completion['format']) is int and completion['format'] == 1)
    _require(completion['kind'] == 'record_completion' and completion['record'] == path.name)
    _require(completion['sha256'] == digest and completion['authorization_id'] == authorization_id)
    _require(completion['run_id'] == run_id and type(completion['evidence']) is dict)
    return record, digest, completion['evidence']


def _authorization(root, identifier):
    _require(_uuid(identifier))
    record, digest, evidence = _completed(root / f'authorization-{identifier}.json', identifier)
    _require(not evidence)
    _require(set(record) == {'format', 'kind', 'id', 'issued_utc', 'expires_utc',
                             'request', 'artifact_approval', 'prerequisite_approval', 'predecessor'})
    _require(type(record['format']) is int and record['format'] == 1)
    _require(record['kind'] == 'owner_authorization' and record['id'] == identifier)
    return record, digest


def _completed_run(root, claim_path):
    """Read a completed, internally consistent run bound to its exact claim."""
    claim, claim_hash = _read(claim_path)
    _require(claim['kind'] == 'authorization_claimed' and _uuid(claim['run_id']))
    identifier, run_id, scope = claim['authorization_id'], claim['run_id'], claim['request']
    authorization, authorization_hash = _authorization(root, identifier)
    _require(claim['authorization_sha256'] == authorization_hash)
    _require(authorization['request'] == scope and authorization['predecessor'] == claim['predecessor'])
    _require(claim_path.name == f'claim-{scope["environment"]}-{claim["predecessor"]["sequence"] + 1:08d}.json')
    terminal, _, evidence = _completed(root / f'terminal-{run_id}.json', identifier, run_id=run_id)
    _require(set(terminal) == {'format', 'kind', 'sequence', 'authorization_id', 'event'})
    _require(type(terminal['format']) is int and terminal['format'] == 1)
    _require(terminal['kind'] == 'execution_finalized' and terminal['authorization_id'] == identifier)
    paths = sorted(root.glob(f'event-{run_id}-*.json'))
    _require(type(terminal['sequence']) is int and terminal['sequence'] == len(paths) + 1)
    expected = {claim_path.name: claim_hash}
    sink = FileAuditSink(root, run_id, identifier, scope, _utc(authorization['expires_utc']))
    history = []
    for sequence, path in enumerate(paths, 1):
        _require(path.name == f'event-{run_id}-{sequence:08d}.json')
        record, digest = _read(path)
        _require(set(record) == {'format', 'kind', 'sequence', 'authorization_id', 'event'})
        _require(type(record['format']) is int and record['format'] == 1)
        _require(record['kind'] == 'execution_event' and record['sequence'] == sequence)
        _require(record['authorization_id'] == identifier)
        history.append(sink._validate_event(record['event']))
        expected[path.name] = digest
    _require(evidence == expected)
    event = sink._validate_event(terminal['event'])
    _require(event['phase'] == 'finalization' and event['operational_authority_verified'])
    _require(event['cleanup']['audit_finalize'] == 'unconfirmed')
    _require(event['cleanup_attempts']['audit_finalize'] == ['unconfirmed'])
    # Completion acknowledges terminal persistence; the payload itself describes
    # the attempt. Reject contradictions between earlier phases and the terminal.
    _require(all(not old['mutation_started'] or event['mutation_started'] for old in history))
    _require(all(not old['database_commit_confirmed'] or event['database_commit_confirmed'] for old in history))
    return event, history


def _continuation_state(event, history):
    """Return a proven starting state, or None for exceptional reconciliation."""
    if event['secondary_failures'] or any(
            value in {'failed', 'unconfirmed'} for key, value in event['cleanup'].items()
            if key != 'audit_finalize'):
        return None
    phases = [old['phase'] for old in history]
    history_consistent = all(
        old['failure'] is None and old['failed_phase'] is None and old['outcome'] == 'pending'
        and old['operational_authority_verified']
        and old['commit_certainty'] == ('confirmed' if old['phase'] == 'postcommit' else 'not_invoked')
        and old['database_commit_confirmed'] == (old['phase'] == 'postcommit')
        and old['mutation_started'] == (old['phase'] in {'precommit', 'commit_ready', 'postcommit'})
        for old in history)
    if not history_consistent:
        return None
    clean = (event['failure'] is None and event['failed_phase'] is None
             and event['interruption_phase'] is None and event['verified_identity']
             and event['observed_start'] == event['expected_start']
             and event['audit_write_outcome'] == 'confirmed_successful'
             and event['lock_outcome'] == 'release_confirmed'
             and all(event['cleanup'][key] == 'confirmed_successful'
                     for key in _COMPONENTS - {'audit_finalize'}))
    if (clean and event['outcome'] == 'applied_and_verified' and event['action'] == 'upgrade'
            and event['database_commit_confirmed'] and event['commit_certainty'] == 'confirmed'
            and event['mutation_started'] and event['transaction_outcome'] == 'committed_confirmed'
            and event['validation_outcome'] == 'postcommit_passed'
            and phases == ['authorization', 'lock', 'preflight', 'revision', 'precommit', 'commit_ready', 'postcommit']):
        return event['target']
    nonmutating = (not event['mutation_started'] and not event['database_commit_confirmed']
                   and event['commit_certainty'] == 'not_invoked'
                   and event['transaction_outcome'] == 'rollback_confirmed')
    expected_outcome = ('verified_target' if event['expected_start'] == event['target'] else 'verified_start')
    if (clean and nonmutating and event['validation_outcome'] == 'preflight_passed'
            and phases == ['authorization', 'lock', 'preflight']
            and ((event['action'] == 'upgrade' and event['outcome'] == 'verified_noop'
                  and event['expected_start'] == event['target'])
                 or (event['action'] == 'verify' and event['outcome'] == expected_outcome))):
        return event['expected_start']
    # Only failures with conclusive absence of mutation and safe cleanup qualify.
    # Drift, identity/authority discrepancies, and unknown state still reconcile.
    safe_failure = event['failure'] in {
        Failure.CREDENTIAL_UNAVAILABLE, Failure.LOCK_BUSY, Failure.OPERATIONAL_GATE,
        Failure.AUDIT_WRITE, Failure.INTERRUPTED, Failure.STATEMENT_TIMEOUT,
        Failure.CONNECTION, Failure.DEADLOCK, Failure.SERIALIZATION,
    }
    before_connection = (event['failed_phase'] in {'authorization', 'credential', 'connection'}
                         and event['transaction_outcome'] == 'not_started'
                         and event['lock_outcome'] == 'not_acquired')
    safe_rollback = (nonmutating
                     and event['lock_outcome'] in {'release_confirmed', 'absence_confirmed', 'not_acquired'}
                     and event['cleanup']['rollback'] == 'confirmed_successful'
                     and event['cleanup']['connection_close'] == 'confirmed_successful'
                     and event['cleanup']['engine_dispose'] == 'confirmed_successful'
                     and event['validation_outcome'] in {'not_checked', 'preflight_passed'}
                     and event['observed_start'] in {None, event['expected_start']}
                     and event['failed_phase'] in {'connection', 'lock', 'preflight', 'revision'})
    if (safe_failure and event['outcome'] == 'failed' and not event['mutation_started']
            and not event['database_commit_confirmed'] and event['commit_certainty'] == 'not_invoked'
            and (before_connection or safe_rollback)):
        return event['expected_start']
    return None


def _ordinary_predecessor(root, environment, predecessor, expected_start):
    try:
        event, history = _completed_run(root, root / f'claim-{environment}-{predecessor["sequence"]:08d}.json')
        return _continuation_state(event, history) == expected_start
    except Exception:
        return False  # Partial/missing/contradictory evidence needs reconciliation.


def _scope(request):
    select_identity(request.environment)
    _require(request.action in {'verify', 'upgrade'})
    return {key: getattr(request, key) for key in _SCOPE}


def _artifacts(request):
    return validate_artifacts(expected_start=request.expected_start, target=request.target,
                              manifest_hash=request.manifest_hash, revision_hash=request.revision_hash)


def _previous(root, environment):
    """Contiguous immutable environment slots serialize different authorizations.

    Hash raw bytes even for an interrupted/partial claim: the owner can reconcile
    that exact evidence without repairing, deleting or reusing the old slot.
    """
    paths = sorted(root.glob(f'claim-{environment}-*.json'))
    for sequence, path in enumerate(paths, 1):
        _require(path.name == f'claim-{environment}-{sequence:08d}.json')
        _require(path.resolve() == path and path.is_file())
    if not paths:
        return {'sequence': 0, 'sha256': None}
    return {'sequence': len(paths), 'sha256': hashlib.sha256(paths[-1].read_bytes()).hexdigest()}


def _reference(root, prefix, reference):
    _require(type(reference) is dict and set(reference) == {'id', 'sha256'})
    _require(_uuid(reference['id']) and _hash(reference['sha256']))
    record, actual = _read(root / f'{prefix}-{reference["id"]}.json')
    _require(actual == reference['sha256'])
    return record


def _approval(record, kind, reference, fields, now):
    _require(set(record) == {'format', 'kind', 'id', 'reviewer_id', 'approved_utc', 'decision'} | fields)
    _require(type(record['format']) is int and record['format'] == 1)
    _require(record['kind'] == kind and record['decision'] == 'approved')
    _require(record['id'] == reference['id'] and _uuid(record['reviewer_id']))
    _require(_utc(record['approved_utc']) <= now)


def _testing_validation(root, scope, testing_run):
    """A citation stays current only through proven ordinary testing successors.

    Claim slots, not timestamps or unexecuted issuances, order the evidence.
    An exceptional successor permanently invalidates older citations. A fresh
    citation must itself have completed after valid predecessor-bound recovery.
    """
    _require(_uuid(testing_run))
    frontier = _previous(root, 'testing')
    paths = [root / f'claim-testing-{sequence:08d}.json'
             for sequence in range(1, frontier['sequence'] + 1)]
    matches = []
    for index, path in enumerate(paths):
        try:
            claim, _ = _read(path)
            if claim.get('run_id') == testing_run:
                matches.append(index)
        except Exception:
            continue  # Earlier partial claims can be explicitly reconciled.
    _require(len(matches) == 1)
    first = matches[0]
    predecessor = {
        'sequence': first,
        'sha256': hashlib.sha256(paths[first - 1].read_bytes()).hexdigest() if first else None,
    }
    for index in range(first, len(paths)):
        claim, digest = _read(paths[index])
        _require(set(claim) == {'format', 'kind', 'utc', 'authorization_id', 'authorization_sha256',
                                'run_id', 'request', 'predecessor', 'recovery'})
        _require(type(claim['format']) is int and claim['format'] == 1)
        _require(claim['predecessor'] == predecessor)
        authorization, _ = _authorization(root, claim['authorization_id'])
        issued, expires = _utc(authorization['issued_utc']), _utc(authorization['expires_utc'])
        _require(issued <= _utc(claim['utc']) < expires <= issued + timedelta(hours=24))
        event, history = _completed_run(root, paths[index])
        _require(event['environment'] == 'testing')
        _require(all(event[key] == scope[key] for key in ('manifest_hash', 'revision_hash', 'target')))
        # Validate actual authorization and predecessor evidence as well as the
        # terminal. Matching completion hashes alone cannot establish recovery.
        _approvals(root, claim['request'], authorization['artifact_approval'],
                   authorization['prerequisite_approval'], predecessor, issued)
        _require(_continuation_state(event, history) == scope['target'])
        if index == first:
            _require(event['run_id'] == testing_run and event['action'] == 'upgrade')
            _require(event['outcome'] in {'applied_and_verified', 'verified_noop'} and event['failure'] is None)
        predecessor = {'sequence': index + 1, 'sha256': digest}
    # Do not accept a scan overtaken by another process claiming a testing slot.
    _require(_previous(root, 'testing') == frontier)


def _approvals(root, scope, artifact_ref, prerequisite_ref, predecessor, now):
    artifact = _reference(root, 'artifact-approval', artifact_ref)
    _approval(artifact, 'artifact_approval', artifact_ref,
              {'manifest_hash', 'revision_hash'}, now)
    _require(all(artifact[key] == scope[key] for key in ('manifest_hash', 'revision_hash')))
    prerequisite = _reference(root, 'prerequisite-approval', prerequisite_ref)
    _approval(prerequisite, 'prerequisite_approval', prerequisite_ref,
              {'environment', 'expected_start', 'approvals', 'predecessor',
               'owner_reconciliation', 'testing_validation_run'}, now)
    _require(prerequisite['environment'] == scope['environment'])
    _require(prerequisite['expected_start'] == scope['expected_start'])
    _require(type(prerequisite['approvals']) is dict and set(prerequisite['approvals']) == PREREQUISITES)
    _require(all(_uuid(value) for value in prerequisite['approvals'].values()))
    _require(prerequisite['predecessor'] == predecessor)
    if predecessor['sequence']:
        # Routine completed evidence determines continuation. Exceptional cases
        # need the existing exact-predecessor owner reconciliation attestation.
        claim = root / f'claim-{scope["environment"]}-{predecessor["sequence"]:08d}.json'
        _require(_utc(prerequisite['approved_utc']).timestamp() >= claim.stat().st_mtime)
        _require(prerequisite['owner_reconciliation'] == 'completed' or (
            prerequisite['owner_reconciliation'] == 'not_applicable'
            and _ordinary_predecessor(root, scope['environment'], predecessor, scope['expected_start'])))
    else:
        _require(prerequisite['owner_reconciliation'] == 'not_applicable')
    testing_run = prerequisite['testing_validation_run']
    if scope['environment'] == 'development':
        _testing_validation(root, scope, testing_run)
    else:
        _require(testing_run is None)


def issue_authorization(specification, *, owner_issue=False):
    """Separate deliberate owner action; never called by runner/authority.

    specification references independently supplied approvals by UUID and byte
    hash. It cannot approve them. Consumption requires separately published
    completion evidence; no real record is issued by offline validation.
    """
    try:
        _require(owner_issue is True)
        _require(type(specification) is dict and set(specification) == {
            'request', 'artifact_approval', 'prerequisite_approval', 'expires_utc'})
        from .migrate import Request
        request = Request(**specification['request'])
        scope = _scope(request)
        _artifacts(request)
        now = _now()
        expiry = _utc(specification['expires_utc'])
        _require(now < expiry <= now + timedelta(hours=24))
        root = audit_destination()
        previous = _previous(root, request.environment)
        _approvals(root, scope, specification['artifact_approval'],
                   specification['prerequisite_approval'], previous, now)
        authorization_id = str(uuid4())
        record = {
            'format': 1, 'kind': 'owner_authorization', 'id': authorization_id,
            'issued_utc': now.isoformat(), 'expires_utc': expiry.isoformat(),
            'request': scope, 'artifact_approval': specification['artifact_approval'],
            'prerequisite_approval': specification['prerequisite_approval'],
            'predecessor': previous,
        }
        path = root / f'authorization-{authorization_id}.json'
        _save(path, record)
        _publish_completion(path, authorization_id)
        return authorization_id
    except (Exception, KeyboardInterrupt):
        error = MigrationError(Failure.OPERATIONAL_GATE)
        error.denial_persisted = record_denial(None, str(uuid4()), error.classification, operation='issuance')
        raise error from None


def record_denial(request, run_id, classification, *, authorization_id=None, operation='execution'):
    """Never serialize rejected input, exception text, paths or provider values."""
    try:
        environment, action = getattr(request, 'environment', None), getattr(request, 'action', None)
        event = {
            'format': 1, 'kind': 'authorization_denied', 'utc': _now().isoformat(),
            'run_id': run_id if _uuid(run_id) else None,
            'authorization_id': authorization_id if authorization_id and _uuid(authorization_id) else None,
            'environment': environment if isinstance(environment, str) and environment in IDENTITIES else None,
            'action': action if isinstance(action, str) and action in {'plan', 'verify', 'upgrade'} else None,
            'classification': MigrationError(classification).classification,
            'operation': operation if operation in {'issuance', 'execution'} else 'execution',
            'commit_certainty': 'not_invoked',
        }
        _save(audit_destination() / f'denial-{uuid4()}.json', event)
        return True
    except (Exception, KeyboardInterrupt):
        return False


class FileOperationalAuthority:
    """Only consumes an existing owner record. No flags, hashes or duck types approve."""

    __slots__ = ('authorization_id', '_binding')

    def __init__(self, authorization_id):
        self.authorization_id = authorization_id
        self._binding = None

    def authorize(self, request, run_id, artifacts):
        try:
            _require(self._binding is None and _uuid(self.authorization_id) and _uuid(run_id))
            scope = _scope(request)
            _require(_artifacts(request) == artifacts)
            root = audit_destination()
            record, record_hash = _authorization(root, self.authorization_id)
            _require(record['request'] == scope)
            now = _now()
            issued, expires = _utc(record['issued_utc']), _utc(record['expires_utc'])
            _require(issued <= now < expires <= issued + timedelta(hours=24))
            previous = _previous(root, request.environment)
            _require(record['predecessor'] == previous)
            _approvals(root, scope, record['artifact_approval'], record['prerequisite_approval'], previous, issued)
            _require(_now() < expires)
            claim = {
                'format': 1, 'kind': 'authorization_claimed', 'utc': now.isoformat(),
                'authorization_id': self.authorization_id, 'authorization_sha256': record_hash,
                'run_id': run_id, 'request': scope, 'predecessor': previous,
                'recovery': 'classify_completed_evidence_or_require_owner_reconciliation',
            }
            # Every contender for this environment/predecessor uses the SAME
            # path. Exclusive creation wins once across processes and IDs.
            path = root / f'claim-{request.environment}-{previous["sequence"] + 1:08d}.json'
            _save(path, claim)
            sink = FileAuditSink(root, run_id, self.authorization_id, scope, expires)
            sink.evidence[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            self._binding = (request, run_id, sink, self.authorization_id, record_hash)
            if request.environment == 'development':
                self.require_binding(request, run_id, sink)
            return sink
        except (Exception, KeyboardInterrupt):
            error = MigrationError(Failure.OPERATIONAL_GATE)
            error.denial_persisted = record_denial(request, run_id, error.classification,
                                                  authorization_id=self.authorization_id)
            raise error from None

    def require_binding(self, request, run_id, sink):
        try:
            _require(type(sink) is FileAuditSink and not sink.finalized)
            record, digest = _authorization(sink.root, self.authorization_id)
            _require(self._binding == (request, run_id, sink, self.authorization_id, digest))
            _require(sink.authorization_id == self.authorization_id and sink.run_id == run_id)
            _require(record['request'] == _scope(request) == sink.scope)
            issued, expires = _utc(record['issued_utc']), _utc(record['expires_utc'])
            if request.environment == 'development':
                # Reuse the runner/env checks after claim creation and at the
                # final mutation/commit boundaries; DB locks are per environment.
                _approvals(sink.root, sink.scope, record['artifact_approval'],
                           record['prerequisite_approval'], record['predecessor'], issued)
            _require(sink.expires == expires and issued <= _now() < expires <= issued + timedelta(hours=24))
        except Exception:
            raise MigrationError(Failure.OPERATIONAL_GATE) from None


_VALUES = frozenset('''authorization credential connection lock preflight revision precommit
commit_ready commit postcommit finalization not_acquired acquisition_unconfirmed acquired
release_confirmed absence_confirmed release_unconfirmed busy not_checked preflight_passed
precommit_passed postcommit_passed postcommit_failed failed not_invoked invocation_begun
uncertain rejected confirmed postcommit_verification_failed pending verified_target
verified_start verified_noop applied_and_verified not_attempted unconfirmed
confirmed_successful not_started setup_readonly_active setup_rollback_confirmed
active_before_mutation mutation_possible committed_confirmed unknown commit_rejected
rollback_unconfirmed rollback_confirmed during_commit after_confirmed_commit
before_commit_invocation during_transaction_execution before_transaction_mutation
cleanup_rollback cleanup_advisory_unlock cleanup_connection_close cleanup_engine_dispose
cleanup_audit_finalize audit_finalization rollback advisory_unlock connection_close
engine_dispose audit_finalize'''.split()) | frozenset(
    value for key, value in vars(Failure).items() if key.isupper())
_COMPONENTS = {'rollback', 'advisory_unlock', 'connection_close', 'engine_dispose', 'audit_finalize'}
_ATTEMPTS = {'failed', 'unconfirmed', 'confirmed_successful'}


class FileAuditSink:
    def __init__(self, root, run_id, authorization_id, scope, expires):
        self.root, self.run_id, self.authorization_id = root, run_id, authorization_id
        self.scope, self.expires, self.finalized = scope, expires, False
        self.sequence = 0
        self.evidence = {}

    def _event(self, event):
        _require(not self.finalized)
        data = asdict(event)
        return self._validate_event(data)

    def _validate_event(self, data):
        # Validate the complete contract without importing migrate a second time
        # when its CLI is running as __main__.
        _require(set(data) == set(_SCOPE) | {
            'run_id', 'utc', 'expected_database', 'expected_authenticated', 'expected_effective',
            'verified_identity', 'verified_database', 'verified_authenticated', 'verified_effective',
            'observed_start', 'phase', 'failed_phase', 'lock_outcome', 'validation_outcome',
            'commit_certainty', 'outcome', 'failure', 'operational_authority_verified',
            'audit_write_outcome', 'transaction_outcome', 'database_commit_confirmed',
            'mutation_started', 'interruption_phase', 'cleanup', 'cleanup_attempts', 'secondary_failures'})
        _require(data['run_id'] == self.run_id)
        _utc(data['utc'])
        _require(all(data[key] == self.scope[key] for key in _SCOPE))
        identity = IDENTITIES[self.scope['environment']]
        for key, expected in {'database': identity.database, 'authenticated': identity.migrator,
                              'effective': identity.owner}.items():
            _require(data[f'expected_{key}'] == expected)
            _require(data[f'verified_{key}'] in {None, expected})
        _require(data['observed_start'] in {None, BASE, BASELINE, STATE_REQUESTS, NOTIFICATIONS, DELIVERY, OUTBOX, MANAGEMENT, RELEASE_APPROVALS})
        for key in ('verified_identity', 'operational_authority_verified', 'database_commit_confirmed', 'mutation_started'):
            _require(type(data[key]) is bool)
        for key in ('phase', 'failed_phase', 'lock_outcome', 'validation_outcome', 'commit_certainty',
                    'outcome', 'failure', 'audit_write_outcome', 'transaction_outcome', 'interruption_phase'):
            _require(data[key] is None or data[key] in _VALUES)
        _require(set(data['cleanup']) == set(data['cleanup_attempts']) == _COMPONENTS)
        _require(all(value in _ATTEMPTS | {'not_attempted'} for value in data['cleanup'].values()))
        _require(all(value in _ATTEMPTS for attempts in data['cleanup_attempts'].values() for value in attempts))
        for key, attempts in data['cleanup_attempts'].items():
            expected = ('failed' if 'failed' in attempts else 'unconfirmed' if 'unconfirmed' in attempts
                        else 'confirmed_successful' if attempts else 'not_attempted')
            _require(data['cleanup'][key] == expected)
        for failure in data['secondary_failures']:
            _require(set(failure) == {'component', 'classification'})
            _require(failure['component'] in _COMPONENTS | {'commit'})
            _require(failure['classification'] in _VALUES)
        return data

    def write(self, event):
        try:
            data = self._event(event)
            # An early expiry check saves unnecessary writes. The runner/env
            # also revalidate AFTER persistence at their final action boundaries.
            if event.phase not in {'postcommit', 'finalization'}:
                _require(_now() < self.expires)
            self.sequence += 1
            path = self.root / f'event-{self.run_id}-{self.sequence:08d}.json'
            _save(path, {
                'format': 1, 'kind': 'execution_event', 'sequence': self.sequence,
                'authorization_id': self.authorization_id, 'event': data})
            self.evidence[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception:
            raise MigrationError(Failure.AUDIT_WRITE) from None

    def finalize(self, event):
        try:
            data = self._event(event)
            path = self.root / f'terminal-{self.run_id}.json'
            _save(path, {
                'format': 1, 'kind': 'execution_finalized', 'sequence': self.sequence + 1,
                'authorization_id': self.authorization_id, 'event': data})
            _publish_completion(path, self.authorization_id, run_id=self.run_id, evidence=self.evidence)
            self.finalized = True
        except Exception:
            raise MigrationError(Failure.AUDIT) from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise MigrationError(Failure.INVALID_CONFIGURATION)


def main(argv=None):
    parser = _Parser(description='Separate owner issuance; never executes migrations', allow_abbrev=False)
    parser.add_argument('action', choices=('issue',))
    parser.add_argument('--specification', required=True)
    parser.add_argument('--owner-issue', action='store_true', required=True)
    try:
        args = parser.parse_args(argv)
        specification, _ = _read(Path(args.specification).resolve())
        authorization_id = issue_authorization(specification, owner_issue=args.owner_issue)
    except (Exception, KeyboardInterrupt) as error:
        if not hasattr(error, 'denial_persisted'):
            record_denial(None, str(uuid4()), Failure.OPERATIONAL_GATE, operation='issuance')
        print(json.dumps({'outcome': 'denied', 'classification': Failure.OPERATIONAL_GATE}))
        return 1
    print(json.dumps({'outcome': 'issued', 'authorization_id': authorization_id}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
