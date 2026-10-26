"""Frozen offline supersession fixture; synthetic identities only.

Retains the original retirement, successor, consumption and reporting functions.
The original and successor compete for the same real exclusive consumption slot.
Historical evidence requires explicit synthetic input; no operational entry point.
"""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import re
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT
spec = importlib.util.spec_from_file_location(
    'confirmation_once_fixture', Path(__file__).with_name('confirmation_once.py'))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
Gate, demand, helpers, sha = base.Gate, base.demand, base.helpers, base.sha
AUTHORITY = base.AUTHORITY
SUCCESSOR = AUTHORITY / 'supersession-v1'
OLD_PACKAGE = '3' * 64
OLD_ID = '00000000-0000-4000-8000-000000000001'
OLD_SHA = '4' * 64
RETIRE_KIND = 'owner_step5_confirmation_terminal_supersession'
NEW_KIND = 'owner_step5_confirmation_superseding_single_use'


def historical_stop():
    raise Gate('synthetic_history_required')


def now():
    return datetime.now(timezone.utc)


def clock(b):
    base.validate_binding(b, now())


def original(directory, b, *, unused=False):
    clock(b)
    h = helpers()
    record, digest, evidence = h._completed(directory / 'authorization.json', OLD_ID)
    demand(digest == OLD_SHA and record['id'] == OLD_ID and not evidence
           and record['package_sha256'] == OLD_PACKAGE
           and record['scope'] == base.scope_fields(b), 'original_authority_identity')
    if unused:
        # Retain the accepted consumer's entire validation before retirement.
        base.read_authority(directory, b, OLD_PACKAGE)
    return record, digest


def read_retirement(directory, successor, b, package_hash):
    original(directory, b)
    record, digest, evidence = helpers()._completed(directory / 'single-shot-used.json', OLD_ID)
    fields = {'format', 'kind', 'id', 'authorization_sha256', 'original_package_sha256',
              'successor_package_sha256', 'successor_namespace', 'run_id', 'retired_utc',
              'expires_utc', 'state', 'retry_authorized'}
    demand(set(record) == fields and type(record['format']) is int and record['format'] == 1
           and record['kind'] == RETIRE_KIND and record['id'] == OLD_ID
           and record['authorization_sha256'] == OLD_SHA
           and record['original_package_sha256'] == OLD_PACKAGE
           and record['successor_package_sha256'] == package_hash
           and record['successor_namespace'] == 'supersession-v1'
           and record['expires_utc'] == base.EXPIRES and record['state'] == 'SUPERSEDED'
           and record['retry_authorized'] is False and not evidence
           and re.fullmatch('[a-f0-9]{32}', record['run_id']) is not None,
           'terminal_supersession_binding')
    started, _ = helpers()._read(successor / 'supersession-started.once')
    retired = datetime.fromisoformat(record['retired_utc'])
    demand(started == record and retired.utcoffset().total_seconds() == 0
           and datetime.fromisoformat(base.ISSUED) <= retired <= now(), 'terminal_supersession_history')
    return record, digest


def supersede_and_issue(directory, successor, b, package_hash, run, emit, *, owner=False):
    demand(owner is True, 'explicit_owner_supersession')
    demand(re.fullmatch('[A-F0-9]{64}', package_hash) is not None
           and re.fullmatch('[a-f0-9]{32}', run) is not None, 'supersession_identity')
    emit('terminal_supersession', 'STARTED')
    original(directory, b, unused=True)
    h = helpers()
    terminal = dict(format=1, kind=RETIRE_KIND, id=OLD_ID, authorization_sha256=OLD_SHA,
        original_package_sha256=OLD_PACKAGE, successor_package_sha256=package_hash,
        successor_namespace='supersession-v1', run_id=run, retired_utc=now().isoformat(),
        expires_utc=base.EXPIRES, state='SUPERSEDED', retry_authorized=False)
    # A failure here leaves the original executable and grants no successor.
    # This reservation is never repaired, deleted or retried automatically.
    h._save(successor / 'supersession-started.once', terminal)
    clock(b)
    # SAME old consumption slot, SAME exclusive fsync helper. A stale old reader
    # must fail CreateNew; if the old consumer already won, this must fail.
    marker = directory / 'single-shot-used.json'
    h._save(marker, terminal)
    h._publish_completion(marker, OLD_ID)
    read_retirement(directory, successor, b, package_hash)
    emit('terminal_supersession', 'PASS')
    emit('owner_issuance', 'STARTED')
    _, retirement_sha = read_retirement(directory, successor, b, package_hash)
    identifier = str(uuid4())
    h._save(successor / 'issuance-started.once', dict(id=identifier, utc=now().isoformat()))
    record = dict(format=1, kind=NEW_KIND, id=identifier, owner_issued_utc=now().isoformat(),
        original_approval='owner_approved_same_original_confirmation_supersession',
        expires_utc=base.EXPIRES, binding_sha256=base.BINDING_HASH,
        sealed_source_sha256=base.SEAL_HASH, package_sha256=package_hash,
        scope=base.scope_fields(b), retry_authorized=False, predecessor_id=OLD_ID,
        predecessor_sha256=OLD_SHA, retirement_sha256=retirement_sha)
    clock(b)
    path = successor / 'authorization.json'
    h._save(path, record)
    h._publish_completion(path, identifier)
    read_successor(directory, successor, b, package_hash)
    emit('owner_issuance', 'PASS')
    return record


def read_successor(directory, successor, b, package_hash, *, unused=True):
    terminal, retirement_sha = read_retirement(directory, successor, b, package_hash)
    h = helpers()
    record, _ = h._read(successor / 'authorization.json')
    published, digest, evidence = h._completed(successor / 'authorization.json', record['id'])
    fields = {'format', 'kind', 'id', 'owner_issued_utc', 'original_approval', 'expires_utc',
              'binding_sha256', 'sealed_source_sha256', 'package_sha256', 'scope',
              'retry_authorized', 'predecessor_id', 'predecessor_sha256', 'retirement_sha256'}
    demand(set(record) == fields and published == record and not evidence
           and type(record['format']) is int and record['format'] == 1
           and record['kind'] == NEW_KIND and h._uuid(record['id']) and record['id'] != OLD_ID
           and record['original_approval'] == 'owner_approved_same_original_confirmation_supersession'
           and record['expires_utc'] == base.EXPIRES and record['binding_sha256'] == base.BINDING_HASH
           and record['sealed_source_sha256'] == base.SEAL_HASH and record['package_sha256'] == package_hash
           and record['scope'] == base.scope_fields(b) and record['retry_authorized'] is False
           and record['predecessor_id'] == OLD_ID and record['predecessor_sha256'] == OLD_SHA
           and record['retirement_sha256'] == retirement_sha, 'successor_authority_binding')
    issued = datetime.fromisoformat(record['owner_issued_utc'])
    started, _ = h._read(successor / 'issuance-started.once')
    demand(set(started) == {'id', 'utc'} and started['id'] == record['id']
           and issued.utcoffset().total_seconds() == 0
           and datetime.fromisoformat(terminal['retired_utc']) <= datetime.fromisoformat(started['utc']) <= issued <= now(),
           'successor_issuance_history')
    if unused:
        demand(not (successor / 'single-shot-used.json').exists(), 'authority_consumed')
    return record, digest


def consume_and_call(directory, successor, b, package_hash, run, call, emit):
    record, digest = read_successor(directory, successor, b, package_hash)
    emit('authority_consumption', 'STARTED')
    helpers()._save(successor / 'single-shot-used.json', dict(format=1, kind=NEW_KIND,
        id=record['id'], authorization_sha256=digest, run_id=run, consumed_utc=now().isoformat()))
    emit('authority_consumption', 'PASS')
    after, after_digest = read_successor(directory, successor, b, package_hash, unused=False)
    demand(after == record and after_digest == digest, 'authority_final_boundary')
    emit('sealed_processor', 'STARTED')
    return call()


def operational(mode, directory, run, emit):
    emit('accepted_binding', 'STARTED')
    b = base.binding()
    clock(b)
    emit('accepted_binding', 'PASS')
    package_hash = sha(PACKAGE / 'SOURCE-IDENTITIES.json')
    demand(mode in ('OwnerSupersede', 'Execute'), 'operational_mode')
    authority_gate = 'original_authority' if mode == 'OwnerSupersede' else 'successor_authority'
    emit(authority_gate, 'STARTED')
    if mode == 'OwnerSupersede':
        original(AUTHORITY, b, unused=True)
    else:
        read_successor(AUTHORITY, SUCCESSOR, b, package_hash)
    emit(authority_gate, 'PASS')
    from oaf_website.confirmation_schedule import _local_run_lock
    from oaf_website.notification_dispatch import validate_failure, safe_failure
    result = None
    with _local_run_lock():
        emit('original_live_preflight', 'STARTED')
        historical_stop()
        # Same actual DB-clock, pristine attempt, original lifecycle, consent,
        # suppression and independent session checks; no substituted eligibility.
        base.ledger(b, before=True)
        emit('original_live_preflight', 'PASS')
        if mode == 'OwnerSupersede':
            supersede_and_issue(AUTHORITY, SUCCESSOR, b, package_hash, run, emit, owner=True)
            return dict(status='ISSUED', processed=0, first_failure=None, retry_authorized=False)
        read_successor(AUTHORITY, SUCCESSOR, b, package_hash)
        originating = None
        try:
            sealed = base.load_module(base.SEALED / 'execute-bound-v1.py', 'oaf_step5_sealed')
            result = consume_and_call(AUTHORITY, SUCCESSOR, b, package_hash, run,
                sealed.run_owner_authorized_once, emit)
            demand(result.status in ('processed', 'unavailable') and type(result.processed) is int
                   and 0 <= result.processed <= 1, 'processor_result')
            if result.first_failure is not None:
                validate_failure(result.first_failure)
            helpers()._save(directory / 'processor-result.json', dict(status=result.status,
                processed=result.processed, first_failure=result.first_failure, retry_authorized=False))
            emit('sealed_processor', 'PASS' if result.first_failure is None else 'BLOCKED')
        except BaseException as exc:
            originating = exc
            raise
        finally:
            if (SUCCESSOR / 'single-shot-used.json').exists():
                emit('outcome_observation', 'STARTED')
                try:
                    observation = base.ledger(b, before=False)
                    helpers()._save(directory / 'outcome.json', observation)
                    emit('outcome_observation', 'PASS')
                except BaseException:
                    emit('outcome_observation', 'ERROR')
                    if originating is None:
                        raise
    accepted = not observation['issues'] and observation['classification'] == 'provider_accepted_submission'
    return dict(status=result.status if accepted else 'unavailable', processed=result.processed,
        observation=observation, first_failure=result.first_failure or (None if accepted else
            safe_failure('processor', 'processor_result', predicate='invalid_result',
                side_effects='acknowledged_outcomes_retained')), retry_authorized=False)


def main():
    mode, run, path = sys.argv[1:]
    directory = Path(path).resolve()
    demand(directory.parent == ROOT / 'instance' and directory.name == 'step5-confirmation-run-' + run,
           'run_identity')
    events = []
    def emit(operation, status):
        row = dict(format=1, run_id=run, utc=now().isoformat(), operation=operation, status=status)
        helpers()._save(directory / ('event-%03d.json' % len(events)), row)
        events.append((operation, status))
        print(base.json.dumps(row), flush=True)
    try:
        answer = operational(mode, directory, run, emit)
        code = 0 if answer['status'] in ('ISSUED', 'processed') and answer['first_failure'] is None else 2
        helpers()._save(directory / 'child-result.json', dict(format=1, run_id=run, mode=mode,
            native_exit=code, **answer))
    except BaseException as exc:
        code = 130 if isinstance(exc, KeyboardInterrupt) else 1
        predicate = (str(exc) if type(exc) is Gate else 'interrupted_unknown' if code == 130 else
                     'reservation_conflict' if isinstance(exc, FileExistsError) else 'operation_unavailable')
        retained = {}
        if (directory / 'processor-result.json').is_file():
            retained, _ = helpers()._read(directory / 'processor-result.json')
        order = ['accepted_binding', 'original_authority' if mode == 'OwnerSupersede' else 'successor_authority',
                 'original_live_preflight'] + (
            ['terminal_supersession', 'owner_issuance'] if mode == 'OwnerSupersede' else
            ['authority_consumption', 'sealed_processor', 'outcome_observation'])
        reached = {op for op, _ in events}
        not_run = [op for op in order if op not in reached]
        unfinished = [op for op in order if next((st for candidate, st in reversed(events)
                                                if candidate == op), None) == 'STARTED']
        stopped = unfinished[0] if unfinished else events[-1][0] if events else 'child_initialization'
        for op in not_run:
            emit(op, 'NOT_RUN')
        helpers()._save(directory / 'child-result.json', dict(format=1, run_id=run, mode=mode,
            native_exit=code, status='ERROR', processed=retained.get('processed', getattr(exc, 'acknowledged_processed', 0)),
            first_failure=retained.get('first_failure') or dict(predicate=predicate, exception_class=type(exc).__name__,
                utc=now().isoformat(), expected='verified_exclusive_original_confirmation_boundary',
                observed='UNAVAILABLE', native_exit=code),
            stopped_stage=stopped, not_run=not_run, acknowledged_processor_result=retained, retry_authorized=False))
        print('ERROR ' + predicate, flush=True)
    return code
