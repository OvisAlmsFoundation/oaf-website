"""Frozen offline confirmation handoff fixture; synthetic identities only.

Authority, consumption and reporting functions retain the original adapter's
behavior and use the tracked migration_authority exclusive/fsync/completion
helpers. Live binding, ledger and sealed-code loading require explicit test
inputs. This fixture has no command-line entry point or operational authority.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT
SEALED = ROOT / 'synthetic-sealed-input-required'
AUTHORITY = ROOT / 'synthetic-authority-input-required'
ISSUED = '2026-10-23T20:17:13.754265+00:00'
EXPIRES = '2026-10-24T20:17:13.754265+00:00'
SEAL_HASH = '1' * 64
BINDING_HASH = '2' * 64
KIND = 'owner_step5_confirmation_single_use'


def binding():
    raise Gate('synthetic_binding_required')


def ledger(b, *, before):
    raise Gate('synthetic_ledger_required')


def load_module(path, name):
    raise Gate('synthetic_sealed_processor_required')


class Gate(ValueError):
    pass


def demand(ok, code):
    if not ok:
        raise Gate(code)


def now():
    return datetime.now(timezone.utc)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def helpers():
    # Reuse the established exclusive/fsync and pending -> hard-link completion
    # mechanism. No migration issuer, adapter, authorization or DB is invoked.
    from oaf_website import migration_authority
    return migration_authority


def validate_binding(b, current):
    from oaf_website.notification_schema import CONSENT_VERSION
    demand(b['format'] == 1 and b['environment'] == 'testing'
           and b['purpose'] == 'confirmation' and b['scope_type'] == 'ConfirmationIntentScope'
           and b['management_revision'] is None and type(b['attempt']) is int and b['attempt'] == 1
           and b['issued_at'] == ISSUED and b['expires_at'] == EXPIRES
           and b['consent_version'] == CONSENT_VERSION
           and b['authority_issued'] is False and b['authority_consumed'] is False,
           'original_confirmation_binding')
    demand(datetime.fromisoformat(ISSUED) <= current < datetime.fromisoformat(EXPIRES), 'original_expiry')


def scope_fields(b):
    return {k: b[k] for k in ('environment', 'recipient', 'purpose', 'management_revision',
        'preferences_revision', 'consent_version', 'intent_fingerprint', 'identity_fingerprint',
        'issued_at', 'expires_at', 'attempt', 'credential_account', 'confirmation_page')}


def issue(directory, b, package_hash, owner_issue=False):
    demand(owner_issue is True, 'explicit_owner_issuance')
    current = now()
    validate_binding(b, current)
    # One fixed namespace per accepted intent across every package/run. A partial
    # or interrupted issuance is retained and cannot be replaced/reissued.
    identifier = str(uuid4())
    h = helpers()
    h._save(directory / 'issuance-started.once', dict(id=identifier, utc=current.isoformat()))
    record = dict(format=1, kind=KIND, id=identifier, owner_issued_utc=current.isoformat(),
        original_approval='owner_approved_one_original_testing_confirmation_attempt_one',
        expires_utc=b['expires_at'], binding_sha256=BINDING_HASH, sealed_source_sha256=SEAL_HASH,
        package_sha256=package_hash, scope=scope_fields(b), retry_authorized=False)
    path = directory / 'authorization.json'
    h._save(path, record)
    h._publish_completion(path, identifier)
    return record


def read_authority(directory, b, package_hash):
    h = helpers()
    record, _ = h._read(directory / 'authorization.json')
    published, digest, evidence = h._completed(directory / 'authorization.json', record['id'])
    demand(published == record and not evidence, 'authority_publication')
    fields = {'format','kind','id','owner_issued_utc','original_approval','expires_utc',
              'binding_sha256','sealed_source_sha256','package_sha256','scope','retry_authorized'}
    demand(set(record) == fields and type(record['format']) is int and record['format'] == 1
           and record['kind'] == KIND and h._uuid(record['id'])
           and record['original_approval'] == 'owner_approved_one_original_testing_confirmation_attempt_one'
           and record['retry_authorized'] is False and record['scope'] == scope_fields(b)
           and record['binding_sha256'] == BINDING_HASH and record['sealed_source_sha256'] == SEAL_HASH
           and record['package_sha256'] == package_hash and record['expires_utc'] == EXPIRES,
           'confirmation_authority_binding')
    issued = datetime.fromisoformat(record['owner_issued_utc'])
    demand(issued.utcoffset().total_seconds() == 0 and datetime.fromisoformat(ISSUED) <= issued <= now()
           and now() < datetime.fromisoformat(EXPIRES), 'authority_expiry')
    demand(not (directory / 'single-shot-used.json').exists(), 'authority_consumed')
    return record, digest


def consume_and_call(directory, b, package_hash, run, call, emit):
    record, digest = read_authority(directory, b, package_hash)
    emit('authority_consumption', 'STARTED')
    # CreateNew/fsync before any credential/provider/processor entry. Never
    # delete this marker, including on early failure, interruption or cleanup.
    helpers()._save(directory / 'single-shot-used.json', dict(format=1, kind=KIND,
        id=record['id'], authorization_sha256=digest, run_id=run, consumed_utc=now().isoformat()))
    emit('authority_consumption', 'PASS')
    # Validate completed bytes again after durable consumption; no permission to
    # retry exists even if this last boundary or the STARTED persistence fails.
    completed, after, _ = helpers()._completed(directory / 'authorization.json', record['id'])
    demand(after == digest and completed == record and now() < datetime.fromisoformat(EXPIRES), 'authority_final_boundary')
    emit('sealed_processor', 'STARTED')
    return call()


def operational(mode, directory, run, emit):
    emit('accepted_binding', 'STARTED')
    b = binding()
    emit('accepted_binding', 'PASS')
    package_hash = sha(PACKAGE / 'SOURCE-IDENTITIES.json')
    if mode == 'OwnerIssue':
        emit('owner_issuance', 'STARTED')
        issue(AUTHORITY, b, package_hash, owner_issue=True)
        emit('owner_issuance', 'PASS')
        return dict(status='ISSUED', processed=0, first_failure=None, retry_authorized=False)
    demand(mode == 'Execute', 'operational_mode')
    read_authority(AUTHORITY, b, package_hash)
    from oaf_website.confirmation_schedule import _local_run_lock
    from oaf_website.notification_dispatch import validate_failure, safe_failure
    result = None
    with _local_run_lock():
        emit('original_live_preflight', 'STARTED')
        ledger(b, before=True)
        emit('original_live_preflight', 'PASS')
        try:
            sealed = load_module(SEALED / 'execute-bound-v1.py', 'oaf_step5_sealed')
            result = consume_and_call(AUTHORITY, b, package_hash, run, sealed.run_owner_authorized_once, emit)
            demand(result.status in ('processed','unavailable') and type(result.processed) is int
                   and 0 <= result.processed <= 1, 'processor_result')
            if result.first_failure is not None:
                validate_failure(result.first_failure)
            # Persist acknowledged progress before observation/cleanup/reporting.
            helpers()._save(directory / 'processor-result.json', dict(status=result.status,
                processed=result.processed, first_failure=result.first_failure, retry_authorized=False))
            emit('sealed_processor', 'PASS' if result.first_failure is None else 'BLOCKED')
        finally:
            if (AUTHORITY / 'single-shot-used.json').exists():
                emit('outcome_observation', 'STARTED')
                try:
                    observation = ledger(b, before=False)
                    helpers()._save(directory / 'outcome.json', observation)
                    emit('outcome_observation', 'PASS')
                except BaseException:
                    emit('outcome_observation', 'ERROR')
                    # The processor result/consumed marker remain authoritative;
                    # observation failure cannot erase an acknowledged outcome.
                    raise
    accepted = (not observation['issues'] and observation['classification'] == 'provider_accepted_submission')
    return dict(status=result.status if accepted else 'unavailable', processed=result.processed,
        observation=observation, first_failure=result.first_failure or (None if accepted else
            safe_failure('processor','processor_result',predicate='invalid_result',
                side_effects='acknowledged_outcomes_retained')), retry_authorized=False)


def main():
    # No generic path/recipient/intent override. The owner launcher provides only
    # its exclusive run directory and the explicit action; never run in this batch.
    mode, run, path = sys.argv[1:]
    directory = Path(path).resolve()
    demand(directory.parent == ROOT / 'instance' and directory.name == 'step5-confirmation-run-' + run, 'run_identity')
    events = []
    def emit(operation, status):
        row = dict(format=1, run_id=run, utc=now().isoformat(), operation=operation, status=status)
        helpers()._save(directory / ('event-%03d.json' % len(list(directory.glob('event-*.json')))), row)
        events.append((operation, status))
        print(json.dumps(row), flush=True)
    code = 1
    try:
        answer = operational(mode, directory, run, emit)
        code = 0 if answer['status'] in ('ISSUED','processed') and answer['first_failure'] is None else 2
        helpers()._save(directory / 'child-result.json', dict(format=1, run_id=run, mode=mode, native_exit=code, **answer))
    except BaseException as exc:
        code = 1
        predicate = str(exc) if type(exc) is Gate else 'interrupted_unknown' if isinstance(exc, KeyboardInterrupt) else 'operation_unavailable'
        retained = {}
        if (directory / 'processor-result.json').is_file():
            retained, _ = helpers()._read(directory / 'processor-result.json')
        order = ['accepted_binding','owner_issuance'] if mode == 'OwnerIssue' else [
            'accepted_binding','original_live_preflight','authority_consumption','sealed_processor','outcome_observation']
        reached = {operation for operation, _ in events}
        not_run = [operation for operation in order if operation not in reached]
        unfinished = [operation for operation in order if next(
            (status for candidate, status in reversed(events) if candidate == operation), None) == 'STARTED']
        stopped = unfinished[0] if unfinished else events[-1][0] if events else 'child_initialization'
        for operation in not_run:
            emit(operation, 'NOT_RUN')
        helpers()._save(directory / 'child-result.json', dict(format=1, run_id=run, mode=mode,
            native_exit=1, status='ERROR', processed=retained.get('processed',getattr(exc,'acknowledged_processed',0)),
            first_failure=retained.get('first_failure') or dict(predicate=predicate, exception_class=type(exc).__name__),
            stopped_stage=stopped,
            not_run=not_run, acknowledged_processor_result=retained, retry_authorized=False))
        print('ERROR ' + predicate, flush=True)
    return code
