"""Accepted safeguard corrections: existing guarded model and fake transport only."""
import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta, datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import OperationalError

from oaf_website import confirmation_outbox as outbox, confirmation_processor as processor, confirmation_schedule as schedule
from oaf_website.brevo import TestingRecipientScope as RecipientScope, ProviderOutcome
from oaf_website.notification_dispatch import safe_failure, validate_failure, BatchResult
from oaf_website.notification_delivery_schema import verification
from oaf_website.notification_management_schema import intents
from test_notification_management import managed
from test_notification_delivery import SECRET
from test_confirmation_processor import runtime, invoke, reserve
from test_brevo import CONFIG, PAGE, response

MAILBOX='subscriber1@example.invalid'
PACKAGE=Path(__file__).absolute().parents[1]/'.pytest_cache/operational-safeguards-v1-20261021'
OFFLINE_EVIDENCE_DIRECTORY=os.environ.get('TEST_EVIDENCE_DIRECTORY')


def confirmation_scoped_setup():
    model,manager,_,_=managed(verified=False)
    record=deepcopy(next(row for row in model.rows(intents) if row['purpose']=='confirmation'))
    constraint=outbox.ConfirmationIntentScope(outbox.intent_fingerprint(record['intent']),outbox.intent_identity(record),
        record['created_at']+timedelta(hours=24),issued_at=record['created_at'])
    store=outbox.ConfirmationOutboxStore(model,SECRET,'testing',recipient_scope=RecipientScope('testing',MAILBOX),
        management_enabled=True,intent_scope=constraint)
    return model,manager,store,record


def test_confirmation_scope_selects_exact_intent_before_limit_and_preserves_other_work():
    model,_,store,target=confirmation_scoped_setup()
    foreign=dict(target,intent='0'*64,purpose='management',management_revision=0)
    model.rows(intents).insert(0,foreign)
    assert store.candidates(1)==[target['intent']]
    statements=[s for s in model.statements if 'ORDER BY' in s and 'LIMIT' in s][-2:]
    assert all(s.index('notification_confirmation_intents.intent =')<s.index('LIMIT') for s in statements)
    send=Mock(return_value=response())
    assert outbox.ConfirmationDispatcher(store,CONFIG,PAGE,transport=send).process(limit=1).processed==1
    assert send.call_count==1 and foreign==model.rows(intents)[0]


@pytest.mark.parametrize('boundary',['claim','preparation'])
def test_confirmation_scope_rejects_other_same_mailbox_intent_at_locked_boundaries(boundary):
    model,_,store,target=confirmation_scoped_setup()
    foreign=dict(target,intent='0'*64)
    model.rows(intents).append(foreign)
    if boundary=='preparation':
        claim='f'*64
        foreign.update(status='claimed',attempts=1,claim_digest=store._digest('confirmation-claim',claim),
            lease_until=model.now+timedelta(minutes=5),next_attempt_at=None)
    before=deepcopy(model.records)
    with pytest.raises(outbox.ManagementIntentMismatch,match='Exceptional'):
        if boundary=='claim':store.claim_confirmation(foreign['intent'])
        else:store.prepare_confirmation(foreign['intent'],claim,PAGE)
    assert model.records==before


def test_confirmation_scope_withdrawn_history_and_new_same_mailbox_lifecycle_do_not_cross():
    from oaf_website.notifications import SubscriptionStore
    from test_notification_delivery import subscribe
    model,_,store,target=confirmation_scoped_setup()
    SubscriptionStore(model).unsubscribe(target['subscription'])
    subscribe(model,2,email=MAILBOX)
    ordinary=outbox.ConfirmationOutboxStore(model,SECRET,'testing',management_enabled=True)
    model.elapse(seconds=60);ordinary.request_confirmation(MAILBOX)
    fresh=deepcopy(next(r for r in model.rows(intents) if r['subscription']!=target['subscription']))
    assert store.candidates(1)==[target['intent']]
    send=Mock()
    result=outbox.ConfirmationDispatcher(store,CONFIG,PAGE,transport=send).process()
    assert result.processed==0
    send.assert_not_called()
    assert next(r for r in model.rows(intents) if r['intent']==fresh['intent'])==fresh


@pytest.mark.parametrize('field,value',[
    ('purpose','management'),('management_revision',0),('subscription','b'*64),
    ('token_digest','c'*64),('intent','d'*64)])
def test_confirmation_scope_immutable_identity_rejects_changes(field,value):
    model,_,store,target=confirmation_scoped_setup()
    with pytest.raises(outbox.ManagementIntentMismatch):store.intent_scope.require(dict(target,**{field:value}),model.now)


@pytest.mark.parametrize('field',['issued_at','expires_at','token_digest'])
def test_confirmation_scope_rejects_current_verification_supersession(field):
    model,_,store,target=confirmation_scoped_setup()
    current=model.rows(verification)[0]
    current[field]='f'*64 if field=='token_digest' else current[field]+timedelta(seconds=1)
    before=deepcopy(model.records)
    with pytest.raises(outbox.ManagementIntentMismatch):store.candidates(1)
    assert model.records==before


@pytest.mark.parametrize('when',['selection','claim','render','before_commit'])
def test_confirmation_scope_original_expiry_at_each_boundary(when,monkeypatch):
    model,_,store,target=confirmation_scoped_setup()
    before=deepcopy(model.rows(verification))
    if when=='selection':
        model.now=store.intent_scope.deadline
        with pytest.raises(outbox.ManagementIntentMismatch):store.candidates(1)
    elif when=='claim':
        store.candidates(1);model.now=store.intent_scope.deadline
        with pytest.raises(outbox.ManagementIntentMismatch):store.claim_confirmation(target['intent'])
    else:
        claim=store.claim_confirmation(target['intent'])
        if when=='render':
            render=outbox.verification_message
            def expire(*args,**kw):
                message=render(*args,**kw);model.now=store.intent_scope.deadline;return message
            monkeypatch.setattr(outbox,'verification_message',expire)
        else:
            update=store._update
            def expire(*args,**kw):
                result=update(*args,**kw)
                if kw.get('submitting_at') is not None:model.now=store.intent_scope.deadline
                return result
            monkeypatch.setattr(store,'_update',expire)
        with pytest.raises(outbox.ManagementIntentMismatch):store.prepare_confirmation(target['intent'],claim,PAGE)
    assert model.rows(verification)==before
    assert next(r for r in model.rows(intents) if r['intent']==target['intent'])['status']!='submitting'


@pytest.mark.parametrize('attempts',[1,2,3])
def test_confirmation_scope_attempt_one_excludes_retry(attempts):
    model,_,store,target=confirmation_scoped_setup()
    model.rows(intents)[0].update(status='failed',attempts=attempts)
    with pytest.raises(outbox.ManagementIntentMismatch):store.candidates(1)
    with pytest.raises(outbox.ManagementIntentMismatch):store.claim_confirmation(target['intent']) if attempts<3 else store.intent_scope.require(model.rows(intents)[0],model.now)


def test_confirmation_scope_expired_claim_recovery_is_exact_and_cannot_retry():
    model,_,store,target=confirmation_scoped_setup()
    foreign=dict(target,intent='0'*64)
    model.rows(intents).insert(0,foreign)
    foreign.update(status='claimed',attempts=1,claim_digest=store._digest('confirmation-claim','f'*64),
        lease_until=model.now+timedelta(minutes=5),next_attempt_at=None)
    store.claim_confirmation(target['intent'])
    foreign=deepcopy(model.rows(intents)[0])
    model.elapse(minutes=6)
    assert store.candidates(1)==[]
    assert model.rows(intents)[0]==foreign
    assert next(r for r in model.rows(intents) if r['intent']==target['intent'])['outcome']=='claim_expired'
    model.elapse(seconds=60)
    with pytest.raises(outbox.ManagementIntentMismatch):store.claim_confirmation(target['intent'])


def test_confirmation_scope_concurrent_claims_create_one_durable_attempt():
    from oaf_website.confirmation_outbox_schema import confirmation_attempts
    model,_,store,target=confirmation_scoped_setup()
    barrier=Barrier(2)
    def claim():
        barrier.wait();return store.claim_confirmation(target['intent'])
    with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(lambda _:claim(),range(2)))
    assert sum(c is not None for c in claims)==1
    assert len(model.rows(confirmation_attempts))==1 and model.rows(confirmation_attempts)[0]['attempt']==1


@pytest.mark.parametrize('phase',['submitting','unknown','outcome_commit_unknown'])
def test_confirmation_scope_submission_uncertainty_never_retries(phase):
    model,_,store,target=confirmation_scoped_setup()
    claim=store.claim_confirmation(target['intent']);assert store.prepare_confirmation(target['intent'],claim,PAGE)
    if phase=='submitting':model.elapse(minutes=6);assert store.candidates(1)==[]
    elif phase=='unknown':assert store.confirmation_outcome(target['intent'],claim,'submission_unknown')
    else:
        model.failure='uncertain'
        with pytest.raises(RuntimeError):store.confirmation_outcome(target['intent'],claim,'submission_unknown')
        model.failure=None
    before=deepcopy(model.records)
    send=Mock()
    assert outbox.ConfirmationDispatcher(store,CONFIG,PAGE,transport=send).process().processed==0
    send.assert_not_called();assert model.records==before


def test_confirmation_scope_retains_accepted_outcome_after_expiry_and_supersession():
    model,_,store,target=confirmation_scoped_setup()
    claim=store.claim_confirmation(target['intent']);assert store.prepare_confirmation(target['intent'],claim,PAGE)
    model.now=store.intent_scope.deadline+timedelta(seconds=1)
    model.rows(verification)[0]['token_digest']='e'*64
    assert store.confirmation_outcome(target['intent'],claim,'provider_accepted','synthetic-id')
    assert model.rows(intents)[0]['status']=='accepted'


def test_confirmation_scope_late_same_mailbox_work_never_joins_batch(monkeypatch):
    model,_,store,target=confirmation_scoped_setup()
    select=store.candidates
    foreign=dict(target,intent='0'*64,purpose='management',management_revision=0)
    def insert_after_selection(limit):
        result=select(limit);model.rows(intents).append(deepcopy(foreign));return result
    monkeypatch.setattr(store,'candidates',insert_after_selection)
    send=Mock(return_value=response())
    assert outbox.ConfirmationDispatcher(store,CONFIG,PAGE,transport=send).process().processed==1
    assert send.call_count==1 and model.rows(intents)[1]==foreign


@pytest.mark.parametrize('change',['suppressed','verified','superseded'])
def test_confirmation_scope_preserves_final_backend_eligibility(change):
    from oaf_website.notification_delivery_schema import suppressions
    model,manager,store,target=confirmation_scoped_setup()
    claim=store.claim_confirmation(target['intent'])
    if change=='suppressed':model.rows(suppressions).append(dict(mailbox_digest=store._digest('mailbox',MAILBOX)))
    if change=='verified':model.rows(verification)[0]['verified_at']=model.now
    if change=='superseded':
        model.elapse(seconds=60);manager.request_confirmation(MAILBOX)
        with pytest.raises(outbox.ManagementIntentMismatch):store.candidates(1)
    assert store.prepare_confirmation(target['intent'],claim,PAGE) is None
    assert next(r for r in model.rows(intents) if r['intent']==target['intent'])['status']!='submitting'


def confirmation_cli(target):
    return ['--confirmation-intent-fingerprint',outbox.intent_fingerprint(target['intent']),
        '--confirmation-identity-fingerprint',outbox.intent_identity(target),
        '--confirmation-issued-at',target['created_at'].isoformat(),
        '--confirmation-expires-at',(target['created_at']+timedelta(hours=24)).isoformat()]


def test_confirmation_scope_crosses_existing_processor_cli_with_synthetic_dependencies(runtime,capsys):
    model,_,_,target=confirmation_scoped_setup();runtime.model.records=deepcopy(model.records)
    assert processor.main(['--environment','testing','--enable-processing','--enable-management',
        '--brevo-account','synthetic-account','--confirmation-page',PAGE,'--testing-recipient',MAILBOX,*confirmation_cli(target)])==0
    assert json.loads(capsys.readouterr().out)=={'status':'processed','processed':1}
    assert runtime.transport.call_count==1


@pytest.mark.parametrize('change',['missing','duplicate','mixed','expiry','environment','activation'])
def test_confirmation_scope_cli_rejection_precedes_protected_access(runtime,capsys,change):
    _,_,_,target=confirmation_scoped_setup()
    args=['--environment','testing','--enable-processing','--enable-management','--testing-recipient',MAILBOX,
        '--confirmation-page',PAGE,'--brevo-account','synthetic-account',*confirmation_cli(target)]
    if change=='missing':args=args[:-2]
    if change=='duplicate':args+=args[-2:]
    if change=='mixed':args+=['--management-deadline',target['created_at'].isoformat()]
    if change=='expiry':args[-1]=(target['created_at']+timedelta(hours=25)).isoformat()
    if change=='environment':args[1]='development'
    if change=='activation':args.remove('--enable-management')
    assert processor.main(args) in (1,2)
    for mock in (runtime.provider_loader,runtime.testing_loader,runtime.secret_loader,runtime.creator,runtime.transport):mock.assert_not_called()


@pytest.mark.parametrize('change',[
    {'revision':0},{'attempt':2},{'issued_at':None},{'deadline':datetime(2026,10,17,tzinfo=timezone.utc)}])
def test_confirmation_scope_requires_original_24_hour_anchors_and_attempt_one(change):
    _,_,store,_=confirmation_scoped_setup()
    values=dict(intent_fingerprint=store.intent_scope.intent_fingerprint,identity_fingerprint=store.intent_scope.identity_fingerprint,
        issued_at=store.intent_scope.issued_at,deadline=store.intent_scope.deadline)
    values.update(change)
    with pytest.raises(ValueError):outbox.ConfirmationIntentScope(**values)

def scoped_setup():
    model, manager, _, _ = managed()
    model.elapse(seconds=60)
    manager.request_recovery(MAILBOX)
    record=next(row for row in model.rows(intents) if row['purpose']=='management')
    constraint=outbox.ManagementIntentScope(outbox.intent_fingerprint(record['intent']),outbox.intent_identity(record),
        record['created_at']+timedelta(hours=24))
    store=outbox.ConfirmationOutboxStore(model,SECRET,'testing',recipient_scope=RecipientScope('testing',MAILBOX),
        management_enabled=True,intent_scope=constraint)
    return model,manager,store,deepcopy(record)

@pytest.mark.parametrize('late',[False,True])
def test_other_same_mailbox_intent_is_excluded_even_after_selection(late,monkeypatch):
    model,manager,store,target=scoped_setup()
    def another():
        model.elapse(seconds=60);manager.request_recovery(MAILBOX)
        return deepcopy(next(row for row in model.rows(intents) if row['purpose']=='management' and row['intent']!=target['intent']))
    if not late: foreign=another()
    if late:
        select=store.candidates
        def select_then_insert(limit):
            selected=select(limit)
            nonlocal foreign
            foreign=another()
            return selected
        foreign=None
        monkeypatch.setattr(store,'candidates',select_then_insert)
    send=Mock(return_value=response())
    result=outbox.ConfirmationDispatcher(store,CONFIG,PAGE,transport=send).process()
    assert result.processed==send.call_count==1
    assert next(row for row in model.rows(intents) if row['intent']==foreign['intent'])==foreign
    assert next(row for row in model.rows(intents) if row['intent']==target['intent'])['status']=='accepted'

def test_candidate_bypass_cannot_claim_other_intent_same_mailbox(monkeypatch):
    model,manager,store,target=scoped_setup()
    model.elapse(seconds=60);manager.request_recovery(MAILBOX)
    foreign=next(row for row in model.rows(intents) if row['purpose']=='management' and row['intent']!=target['intent'])
    before=deepcopy(model.records)
    monkeypatch.setattr(store,'candidates',lambda _: [foreign['intent']])
    send=Mock()
    result=outbox.ConfirmationDispatcher(store,CONFIG,PAGE,transport=send).process()
    assert result.status=='unavailable' and result.first_failure['predicate']=='intent_identity'
    assert model.records==before
    send.assert_not_called()

@pytest.mark.parametrize('field,value,predicate',[
    ('purpose','confirmation','intent_purpose'),('management_revision',1,'intent_revision'),
    ('subscription','b'*64,'intent_lifecycle_binding'),('attempts',1,'intent_attempt'),
    ('token_digest','c'*64,'intent_lifecycle_binding')])
def test_exact_constraint_rejects_identity_purpose_revision_lifecycle_and_attempt(field,value,predicate):
    model,_,store,target=scoped_setup()
    changed=dict(target,**{field:value})
    with pytest.raises(outbox.ManagementIntentMismatch) as caught:
        store.intent_scope.require(changed,model.now)
    assert caught.value.predicate==predicate

@pytest.mark.parametrize('when',['selection','claim','final_render','before_commit'])
def test_deadline_expiry_blocks_each_submission_boundary(when,monkeypatch):
    model,_,store,target=scoped_setup()
    if when=='selection':
        model.now=store.intent_scope.deadline
        with pytest.raises(outbox.ManagementIntentMismatch):store.candidates(20)
    elif when=='claim':
        assert store.candidates(20)==[target['intent']]
        model.now=store.intent_scope.deadline
        with pytest.raises(outbox.ManagementIntentMismatch):store.claim_confirmation(target['intent'])
    else:
        claim=store.claim_confirmation(target['intent'])
        if when=='final_render':
            render=outbox.management_message
            def expire(*args,**kw):
                message=render(*args,**kw);model.now=store.intent_scope.deadline;return message
            monkeypatch.setattr(outbox,'management_message',expire)
        else:
            update=store._update
            def expire(*args,**kw):
                result=update(*args,**kw)
                if kw.get('submitting_at') is not None:model.now=store.intent_scope.deadline
                return result
            monkeypatch.setattr(store,'_update',expire)
        with pytest.raises(outbox.ManagementIntentMismatch):store.prepare_confirmation(target['intent'],claim,PAGE)
    assert next(row for row in model.rows(intents) if row['intent']==target['intent'])['status']!='submitting'
    assert store.first_failure['predicate']=='intent_deadline'

def test_original_expired_authority_is_never_replaced_or_renewed():
    model,_,store,target=scoped_setup()
    model.now=datetime(2026,10,22,tzinfo=timezone.utc)
    before=deepcopy(model.records)
    send=Mock()
    result=outbox.ConfirmationDispatcher(store,CONFIG,PAGE,transport=send).process()
    assert result.status=='unavailable' and result.processed==0
    assert model.records==before
    send.assert_not_called()

def test_expired_authority_does_not_erase_provider_acceptance():
    model,_,store,target=scoped_setup()
    claim=store.claim_confirmation(target['intent'])
    assert store.prepare_confirmation(target['intent'],claim,PAGE)
    model.now=store.intent_scope.deadline+timedelta(seconds=1)
    assert store.confirmation_outcome(target['intent'],claim,'provider_accepted','synthetic-id')
    assert next(row for row in model.rows(intents) if row['intent']==target['intent'])['status']=='accepted'

def test_recovery_does_not_mutate_second_same_mailbox_claim():
    model,manager,store,target=scoped_setup()
    store.claim_confirmation(target['intent'])
    model.elapse(seconds=60);manager.request_recovery(MAILBOX)
    foreign=next(row for row in model.rows(intents) if row['purpose']=='management' and row['intent']!=target['intent'])
    ordinary=outbox.ConfirmationOutboxStore(model,SECRET,'testing',management_enabled=True)
    ordinary.claim_confirmation(foreign['intent'])
    before=deepcopy(next(row for row in model.rows(intents) if row['intent']==foreign['intent']))
    model.elapse(minutes=6)
    assert store.candidates(20)==[]
    assert next(row for row in model.rows(intents) if row['intent']==foreign['intent'])==before

def test_existing_recurring_processing_retains_multiple_intents_and_retry_behavior():
    model,manager,store,_=scoped_setup()
    model.elapse(seconds=60);manager.request_recovery(MAILBOX)
    ordinary=outbox.ConfirmationOutboxStore(model,SECRET,'testing',management_enabled=True)
    send=Mock(return_value=response())
    assert outbox.ConfirmationDispatcher(ordinary,CONFIG,PAGE,transport=send).process().processed==2
    assert send.call_count==2

@pytest.mark.parametrize('failure',['connect','execute','commit','uncertain'])
def test_originating_database_failure_has_safe_actionable_detail(failure):
    model,_,store,_=scoped_setup();model.failure=failure
    send=Mock()
    result=outbox.ConfirmationDispatcher(store,CONFIG,PAGE,transport=send).process()
    detail=validate_failure(result.first_failure)
    assert detail['operation']=={'connect':'database_begin','execute':'advisory_lock','commit':'transaction_commit','uncertain':'transaction_commit'}[failure]
    assert detail['stage']=='outbox' and detail['timestamp_utc'].endswith('+00:00')
    assert detail['expected'] and detail['observed']
    assert 'private' not in json.dumps(detail) and MAILBOX not in json.dumps(detail)
    send.assert_not_called()

def test_wrapped_sqlstate_hresult_and_native_exit_are_preserved_without_exception_text():
    driver=RuntimeError('private-token-and-sql-parameters');driver.sqlstate='40001'
    error=OperationalError('private sql',{'email':MAILBOX},driver)
    error.hresult=-2147467259;error.returncode=23
    detail=validate_failure(safe_failure('outbox','outcome',error,side_effects='submission_possible'))
    assert detail['sqlstate']=='40001' and detail['hresult']=='0x80004005' and detail['exit_code']==23
    assert 'private' not in json.dumps(detail) and MAILBOX not in json.dumps(detail)

def test_cleanup_failure_preserves_accepted_progress_and_first_failure(runtime):
    reserve(runtime);runtime.model.dispose.side_effect=RuntimeError('private cleanup')
    result=invoke()
    assert result.processed==1 and result.status=='unavailable'
    assert result.first_failure['operation']=='dispose'
    assert runtime.model.rows(intents)[0]['status']=='accepted'

def test_provider_acceptance_evidence_survives_unacknowledged_outcome_commit(monkeypatch):
    model,_,store,_=scoped_setup()
    original=store.confirmation_outcome
    def fail_commit(*args,**kwargs):
        model.failure='uncertain'
        return original(*args,**kwargs)
    monkeypatch.setattr(store,'confirmation_outcome',fail_commit)
    result=outbox.ConfirmationDispatcher(store,CONFIG,PAGE,transport=Mock(return_value=response())).process()
    assert result.status=='unavailable' and result.processed==0
    assert result.first_failure['operation']=='transaction_commit'
    assert result.first_failure['context']=='outcome'
    assert result.first_failure['provider_outcome']=='provider_accepted'
    assert result.first_failure['side_effects']=='database_commit_uncertain'

def test_scheduler_reporting_failure_preserves_count_and_original_failure(runtime,monkeypatch,tmp_path,capsys):
    monkeypatch.setattr(schedule,'ROOT',tmp_path)
    original=schedule._append
    count=0
    def append(record):
        nonlocal count
        count+=1
        if count==2:raise OSError('private report failure')
        original(record)
    monkeypatch.setattr(schedule,'_append',append)
    reserve(runtime)
    assert schedule.run_scheduled(profile='testing',enabled=True,account='synthetic',page=PAGE,recipient=MAILBOX)==1
    observed=json.loads(capsys.readouterr().out)
    assert observed['processed']==1 and observed['first_failure']['operation']=='terminal_publication'
    assert runtime.model.rows(intents)[0]['status']=='accepted'

def load_preflight(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(PACKAGE))
    spec=importlib.util.spec_from_file_location('safeguard_preflight',PACKAGE/'preflight.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def test_outcome_observation_requires_no_provider_or_protected_key(monkeypatch):
    module=load_preflight(monkeypatch)
    source=(PACKAGE/'preflight.py').read_text()
    tree=__import__('ast').parse(source)
    # The actual classifier observes a consistent accepted result without a store
    # or a key. Its identity anchors are the existing immutable fingerprints.
    model,_,store,target=scoped_setup()
    claim=store.claim_confirmation(target['intent']);store.prepare_confirmation(target['intent'],claim,PAGE)
    store.confirmation_outcome(target['intent'],claim,'provider_accepted','synthetic-id')
    from oaf_website.notification_schema import notifications
    from oaf_website.confirmation_outbox_schema import confirmation_attempts
    parents=deepcopy(model.rows(intents));histories=deepcopy(model.rows(confirmation_attempts))
    data=[deepcopy(model.rows(notifications)),deepcopy(model.rows(verification)),parents,histories,[],[],[]]
    monkeypatch.setattr(module,'ORIGINAL_INTENT',outbox.intent_fingerprint(target['intent']))
    monkeypatch.setattr(module,'EXPIRES',store.intent_scope.deadline)
    baseline=module.observe(data,None,model.now,{})
    assert baseline['outcomes'][0]['provider_acceptance_recorded'] is True
    assert baseline['observation_complete'] and baseline['protected_key_matches_original'] is None
    assert not baseline['submission_eligible'] and not baseline['delivery_or_retry_authorized']

def test_preflight_started_and_failed_events_are_exclusive_and_sanitized(monkeypatch,tmp_path):
    module=load_preflight(monkeypatch)
    module.CONTEXT.update(phase='readiness',event_directory=tmp_path)
    driver=RuntimeError('private sql');driver.sqlstate='42501'
    def fail():raise OperationalError('private sql',{'recipient':MAILBOX},driver)
    assert module.check('database_inventory',fail,required=False) is None
    files=sorted(tmp_path.glob('check-*.json'))
    assert len(files)==2
    records=[json.loads(file.read_text()) for file in files]
    assert [record['status'] for record in records]==['STARTED','ERROR']
    assert records[1]['sqlstate']=='42501' and records[1]['operation']=='database_inventory'
    assert 'private sql' not in ''.join(file.read_text() for file in files)
    assert MAILBOX not in ''.join(file.read_text() for file in files)

@pytest.mark.parametrize('phase',['after','readiness'])
@pytest.mark.parametrize('fault',['none','identity','dispose','privilege'])
def test_actual_readonly_snapshot_is_independent_of_provider_readiness(monkeypatch,tmp_path,phase,fault,capsys):
    import sys
    import sqlalchemy
    from sqlalchemy.sql.elements import TextClause
    from oaf_website import database_config, local_testing, brevo
    module=load_preflight(monkeypatch)
    model,_,store,target=scoped_setup()
    claim=store.claim_confirmation(target['intent']);store.prepare_confirmation(target['intent'],claim,PAGE)
    store.confirmation_outcome(target['intent'],claim,'provider_accepted','synthetic-id')
    original=deepcopy(model.records)
    transaction=model.begin();connection=transaction.__enter__()
    lifecycle=[];statements=[]
    class Result:
        def __init__(self,value):self.value=value
        def scalar_one(self):return self.value
        def one(self):return self.value
        def mappings(self):return self.value
    class ReadOnly:
        def execution_options(self,**values):
            assert values==dict(isolation_level='REPEATABLE READ',postgresql_readonly=True)
            return self
        def __enter__(self):return self
        def __exit__(self,*args):lifecycle.append('close')
        def begin(self):return SimpleNamespace(rollback=rollback)
        @contextmanager
        def begin_nested(self):yield
        def execute(self,statement,params=None):
            sql=str(statement);statements.append(sql)
            if isinstance(statement,TextClause):
                if sql=='SHOW transaction_read_only':return Result('on')
                if sql=='SHOW transaction_isolation':return Result('repeatable read')
                if sql.startswith('SELECT current_database()'):
                    return Result(('wrong' if fault=='identity' else 'oaf_website_test','oaf_website_test_app','oaf_website_test_app','127.0.0.1',5432,17))
                if sql.startswith("SELECT current_setting('statement_timeout')"):return Result(('10s','5s','30s'))
                if 'pg_stat_activity' in sql:return Result(0)
                if sql.startswith('SELECT EXISTS'):return Result(True)
                if sql.startswith('SELECT has_table_privilege'):
                    if fault=='privilege':raise OperationalError('private catalog',{},RuntimeError('private'))
                    return Result(True)
                raise AssertionError('unexpected synthetic SQL')
            return Result(connection.execute(statement.params(**params) if params else statement).value)
    def rollback():
        lifecycle.append('rollback');error=RuntimeError('synthetic rollback')
        transaction.__exit__(type(error),error,None)
    def dispose():
        lifecycle.append('dispose')
        if fault=='dispose':raise OSError('private cleanup')
    monkeypatch.setattr(sqlalchemy,'create_engine',lambda *args,**kw:SimpleNamespace(connect=lambda:ReadOnly(),dispose=dispose))
    monkeypatch.setattr(sqlalchemy.event,'listen',lambda *args:None)
    monkeypatch.setattr(database_config,'load_testing_database_config',lambda:SimpleNamespace(profile='testing',url=SimpleNamespace(
        database='oaf_website_test',username='oaf_website_test_app',host='127.0.0.1',port=5432)))
    monkeypatch.setattr(database_config,'_validate_environment',lambda *args:'testing')
    monkeypatch.setattr(database_config,'_read_settings',lambda *args:{})
    provider=Mock(side_effect=AssertionError('provider readiness must not be required'))
    key=Mock(side_effect=AssertionError('protected key must not be required'))
    monkeypatch.setattr(brevo,'load_brevo_config',provider);monkeypatch.setattr(local_testing,'recognition_secret',key)
    plain=module.plain
    monkeypatch.setattr(module,'plain',lambda path:Path(path) if 'config' in Path(path).parts else plain(path))
    monkeypatch.setattr(module,'verify_checkout_files',lambda:dict(owner_sid='synthetic',source={}))
    contract=json.loads((PACKAGE/'package-contract.json').read_text())
    contract.update(original_identities={},current_reviewed_source_fingerprint=module.fingerprint({}))
    monkeypatch.setattr(module,'original_contract',lambda:contract)
    monkeypatch.setattr(module,'BASE',tmp_path);monkeypatch.setattr(module,'utc_now',lambda:model.now)
    monkeypatch.setattr(module,'MAILBOX',MAILBOX);monkeypatch.setattr(module,'PRIMARY_MAILBOX','primary@example.invalid')
    monkeypatch.setattr(module,'ORIGINAL_INTENT',outbox.intent_fingerprint(target['intent']))
    monkeypatch.setattr(module,'EXPIRES',store.intent_scope.deadline)
    (tmp_path/'package-contract.json').write_text(json.dumps(contract));(tmp_path/'review-pins.json').write_text('{}')
    directory=tmp_path/('run-'+'d'*32);directory.mkdir()
    (directory/(phase+'-system.json')).write_text(json.dumps(dict(trust_established=True,owner_sid='synthetic',isolated=False)))
    module.CONTEXT.clear()
    if fault=='identity':
        with pytest.raises(module.Stop):module.snapshot(phase,directory,model.now,model.now,None)
        assert not any('FROM oaf_website.' in sql for sql in statements)
    elif fault=='dispose':
        with pytest.raises(OSError):module.snapshot(phase,directory,model.now,model.now,None)
        assert module.CONTEXT['known_result']['outcomes'][0]['provider_acceptance_recorded']
    else:
        result=module.snapshot(phase,directory,model.now,model.now,None)
        assert result['observation_complete'] and result['outcomes'][0]['provider_acceptance_recorded']
        assert result['submission_eligible'] is False and result['current_configuration_matches'] is None
        assert result['protected_key_matches_original'] is None
    provider.assert_not_called();key.assert_not_called()
    assert lifecycle==['rollback','close','dispose'] and model.records==original
    assert all(sql.startswith(('SELECT ','SHOW ')) for sql in statements)

def test_actual_backend_producer_handoff_retains_acknowledgment_through_reporting_failure(runtime,monkeypatch,tmp_path,capsys):
    import os
    monkeypatch.setattr(schedule,'ROOT',tmp_path)
    reserve(runtime);runtime.model.dispose.side_effect=OSError('private cleanup')
    append=schedule._append
    def reject_terminal(record):
        if record['status']!='started':raise OSError('private reporting failure')
        append(record)
    monkeypatch.setattr(schedule,'_append',reject_terminal)
    code=schedule.run_scheduled(profile='testing',enabled=True,account='synthetic',page=PAGE,recipient=MAILBOX)
    record=json.loads(capsys.readouterr().out)
    assert code==1 and record['processed']==1 and record['status']=='reporting_failed'
    assert record['first_failure']['operation']=='dispose'
    assert runtime.model.rows(intents)[0]['status']=='accepted'
    destination=OFFLINE_EVIDENCE_DIRECTORY
    if destination:
        path=Path(destination);assert path.is_relative_to(PACKAGE)
        with (path/'backend-producer.json').open('x',encoding='utf-8') as stream:
            json.dump(record,stream);stream.flush();os.fsync(stream.fileno())

def test_exceptional_scope_crosses_actual_schedule_and_processor_cli(runtime,monkeypatch,tmp_path,capsys):
    model,manager,store,target=scoped_setup()
    model.elapse(seconds=60);manager.request_recovery(MAILBOX)
    foreign=deepcopy(next(row for row in model.rows(intents) if row['purpose']=='management' and row['intent']!=target['intent']))
    runtime.model.records=deepcopy(model.records);runtime.model.now=model.now
    monkeypatch.setattr(schedule,'ROOT',tmp_path)
    assert schedule.run_scheduled(profile='testing',enabled=True,management_enabled=True,
        account='synthetic',page=PAGE,recipient=MAILBOX,
        management_intent_fingerprint=store.intent_scope.intent_fingerprint,
        management_identity_fingerprint=store.intent_scope.identity_fingerprint,
        management_deadline=store.intent_scope.deadline.isoformat())==0
    result=json.loads(capsys.readouterr().out)
    assert result['processed']==runtime.transport.call_count==1
    assert next(row for row in runtime.model.rows(intents) if row['intent']==foreign['intent'])==foreign

@pytest.mark.parametrize('arguments',[
    ['--management-intent-fingerprint','A'*64],
    ['--management-intent-fingerprint','A'*64,'--management-intent-fingerprint','A'*64],
    ['--management-intent-fingerprint','A'*64,'--management-identity-fingerprint','B'*64,'--management-deadline','invalid'],
])
def test_partial_duplicate_or_invalid_exceptional_scope_rejects_before_protected_access(runtime,capsys,arguments):
    assert processor.main(['--environment','testing','--enable-processing','--enable-management',*arguments])==2
    assert json.loads(capsys.readouterr().out)['processed']==0
    assert runtime.transport.call_count==runtime.creator.call_count==runtime.provider_loader.call_count==0


# Step 5 confirmation-only handoff. Real authority helpers; synthetic files only.
@pytest.fixture
def step5_once(tmp_path, monkeypatch):
    path=Path(__file__).resolve().parents[1]/'.pytest_cache/step5-confirmation-once-v1-20261023/confirmation_once.py'
    spec=importlib.util.spec_from_file_location('step5_once_synthetic',path)
    adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
    clock=datetime.fromisoformat(adapter.ISSUED)+timedelta(minutes=10)
    monkeypatch.setattr(adapter,'now',lambda:clock)
    from oaf_website.notification_schema import CONSENT_VERSION
    b=dict(format=1,environment='testing',purpose='confirmation',scope_type='ConfirmationIntentScope',
        management_revision=None,preferences_revision=0,consent_version=CONSENT_VERSION,attempt=1,
        issued_at=adapter.ISSUED,expires_at=adapter.EXPIRES,authority_issued=False,authority_consumed=False,
        recipient=MAILBOX,intent_fingerprint='A'*64,identity_fingerprint='B'*64,
        credential_account='synthetic',confirmation_page=PAGE)
    return adapter,b,tmp_path


def test_step5_once_explicit_issuance_and_permanent_consumption(step5_once):
    a,b,d=step5_once
    with pytest.raises(a.Gate,match='explicit_owner_issuance'):a.issue(d,b,'C'*64)
    record=a.issue(d,b,'C'*64,owner_issue=True)
    assert record['owner_issued_utc']!=b['issued_at']
    assert record['scope']==a.scope_fields(b) and record['expires_utc']==a.EXPIRES
    calls=Mock(return_value='synthetic-result');events=[]
    assert a.consume_and_call(d,b,'C'*64,'synthetic-run',calls,lambda *v:events.append(v))=='synthetic-result'
    assert calls.call_count==1 and ('authority_consumption','PASS') in events
    with pytest.raises(a.Gate,match='authority_consumed'):
        a.consume_and_call(d,b,'C'*64,'another-run',calls,lambda *v:None)
    assert calls.call_count==1


@pytest.mark.parametrize('field,value',[
    ('intent_fingerprint','D'*64),('identity_fingerprint','E'*64),('purpose','management'),
    ('recipient','other@example.invalid'),('attempt',2),('consent_version','other'),
    ('issued_at','2026-10-23T20:17:14+00:00'),('expires_at','2026-10-25T20:17:13.754265+00:00')])
def test_step5_once_rejects_scope_expansion(step5_once,field,value):
    a,b,d=step5_once;a.issue(d,b,'C'*64,owner_issue=True)
    altered=dict(b,**{field:value})
    with pytest.raises(a.Gate):a.read_authority(d,altered,'C'*64)
    assert not (d/'single-shot-used.json').exists()


def test_step5_once_expired_authority_and_stale_source(step5_once,monkeypatch):
    a,b,d=step5_once;a.issue(d,b,'C'*64,owner_issue=True)
    with pytest.raises(a.Gate,match='confirmation_authority_binding'):a.read_authority(d,b,'D'*64)
    monkeypatch.setattr(a,'now',lambda:datetime.fromisoformat(a.EXPIRES))
    with pytest.raises(a.Gate,match='authority_expiry'):a.read_authority(d,b,'C'*64)
    with pytest.raises(a.Gate,match='original_expiry'):a.issue(d,b,'C'*64,owner_issue=True)
    assert not (d/'single-shot-used.json').exists()


def test_step5_once_pending_publication_cannot_execute_or_reissue(step5_once,monkeypatch):
    a,b,d=step5_once;h=a.helpers()
    with monkeypatch.context() as m:
        m.setattr(h,'_publish_completion',Mock(side_effect=OSError('synthetic-private')))
        with pytest.raises(OSError):a.issue(d,b,'C'*64,owner_issue=True)
    assert (d/'authorization.json').exists() and not (d/'completed-authorization.json').exists()
    with pytest.raises(Exception):a.read_authority(d,b,'C'*64)
    with pytest.raises(FileExistsError):a.issue(d,b,'C'*64,owner_issue=True)


@pytest.mark.parametrize('error',[RuntimeError('private'),KeyboardInterrupt()])
def test_step5_once_interruption_and_early_failure_never_release_consumption(step5_once,error):
    a,b,d=step5_once;a.issue(d,b,'C'*64,owner_issue=True)
    call=Mock(side_effect=error)
    with pytest.raises(type(error)):a.consume_and_call(d,b,'C'*64,'run',call,lambda *v:None)
    assert (d/'single-shot-used.json').exists()
    with pytest.raises(a.Gate,match='authority_consumed'):a.consume_and_call(d,b,'C'*64,'run2',call,lambda *v:None)
    assert call.call_count==1


def test_step5_once_consumption_fsync_failure_never_calls_processor(step5_once,monkeypatch):
    a,b,d=step5_once;a.issue(d,b,'C'*64,owner_issue=True)
    h=a.helpers();save=h._save
    def fail(path,value):
        save(path,value)
        if path.name=='single-shot-used.json':raise OSError('synthetic-fsync-failure')
    monkeypatch.setattr(h,'_save',fail);call=Mock()
    with pytest.raises(OSError):a.consume_and_call(d,b,'C'*64,'run',call,lambda *v:None)
    call.assert_not_called();assert (d/'single-shot-used.json').exists()


def test_step5_once_interrupted_completed_link_is_recognized_without_republication(step5_once,monkeypatch):
    a,b,d=step5_once;h=a.helpers();link=h.os.link;count=[]
    def interrupt(source,target):
        count.append(1);link(source,target);raise KeyboardInterrupt()
    monkeypatch.setattr(h.os,'link',interrupt)
    a.issue(d,b,'C'*64,owner_issue=True)
    assert len(count)==1 and a.read_authority(d,b,'C'*64)[0]['kind']==a.KIND


@pytest.mark.parametrize('outcome',['accepted','unknown','cleanup_failed'])
def test_step5_once_handoff_crosses_existing_processor_with_one_synthetic_submission(step5_once,runtime,monkeypatch,outcome):
    a,b,d=step5_once
    model,_,_,target=confirmation_scoped_setup()
    runtime.model.records=deepcopy(model.records);runtime.model.now=model.now
    constraint=outbox.ConfirmationIntentScope(outbox.intent_fingerprint(target['intent']),outbox.intent_identity(target),
        target['created_at']+timedelta(hours=24),issued_at=target['created_at'])
    if outcome=='unknown':runtime.transport.side_effect=TimeoutError('private')
    if outcome=='cleanup_failed':runtime.model.dispose.side_effect=RuntimeError('private')
    a.issue(d,b,'C'*64,owner_issue=True)
    def call():
        return processor.process_confirmations(expected_profile='testing',enabled=True,credential_account='synthetic',
            confirmation_page=PAGE,testing_recipient=MAILBOX,management_enabled=True,intent_scope=constraint)
    result=a.consume_and_call(d,b,'C'*64,'run',call,lambda *v:None)
    assert runtime.transport.call_count==1 and result.processed==1
    saved=runtime.model.rows(intents)[0]
    assert saved['outcome']==('submission_unknown' if outcome=='unknown' else 'provider_accepted')
    if outcome=='cleanup_failed':assert result.first_failure['operation']=='dispose'
    with pytest.raises(a.Gate,match='authority_consumed'):a.consume_and_call(d,b,'C'*64,'run2',call,lambda *v:None)
    assert runtime.transport.call_count==1


@pytest.mark.parametrize('observation_failure',[False,True])
def test_step5_once_main_persists_acknowledged_failure_and_nonzero_exit(step5_once,monkeypatch,observation_failure):
    a,b,d=step5_once
    package=d/'package';package.mkdir();(package/'SOURCE-IDENTITIES.json').write_text('{}')
    authority=d/'authority';authority.mkdir()
    instance=d/'instance';instance.mkdir();run=instance/'step5-confirmation-run-synthetic';run.mkdir()
    monkeypatch.setattr(a,'ROOT',d);monkeypatch.setattr(a,'PACKAGE',package);monkeypatch.setattr(a,'AUTHORITY',authority)
    monkeypatch.setattr(a,'binding',lambda:b)
    a.issue(authority,b,a.sha(package/'SOURCE-IDENTITIES.json'),owner_issue=True)
    failure=safe_failure('processor','dispose',RuntimeError(),side_effects='acknowledged_outcomes_retained')
    sealed=SimpleNamespace(run_owner_authorized_once=Mock(return_value=BatchResult('unavailable',1,failure)))
    monkeypatch.setattr(a,'load_module',lambda *v:sealed)
    @contextmanager
    def lock():yield
    monkeypatch.setattr(schedule,'_local_run_lock',lock)
    def observe(binding,*,before):
        if not before and observation_failure:raise OSError('private observation')
        return dict(classification='provider_accepted_submission',issues=[])
    monkeypatch.setattr(a,'ledger',observe)
    monkeypatch.setattr(a.sys,'argv',['synthetic','Execute','synthetic',str(run)])
    assert a.main() in (1,2)
    result=json.loads((run/'child-result.json').read_text())
    assert result['first_failure']['operation']=='dispose'
    assert result['processed']==1
    assert (run/'processor-result.json').exists() and (authority/'single-shot-used.json').exists()
    assert sealed.run_owner_authorized_once.call_count==1
    second=instance/'step5-confirmation-run-second';second.mkdir()
    monkeypatch.setattr(a.sys,'argv',['synthetic','Execute','second',str(second)])
    assert a.main()==1
    assert sealed.run_owner_authorized_once.call_count==1


def test_step5_once_competing_consumers_allow_one_call(step5_once):
    a,b,d=step5_once;a.issue(d,b,'C'*64,owner_issue=True)
    barrier=Barrier(2);call=Mock(return_value='synthetic')
    def execute(number):
        barrier.wait()
        try:return a.consume_and_call(d,b,'C'*64,str(number),call,lambda *v:None)
        except (a.Gate,FileExistsError):return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(execute,range(2)))
    assert results.count('synthetic')==1 and results.count('blocked')==1 and call.call_count==1


def test_step5_once_expiry_after_consumption_stops_before_processor(step5_once,monkeypatch):
    a,b,d=step5_once;a.issue(d,b,'C'*64,owner_issue=True);call=Mock()
    def emit(operation,status):
        if (operation,status)==('authority_consumption','PASS'):
            monkeypatch.setattr(a,'now',lambda:datetime.fromisoformat(a.EXPIRES))
    with pytest.raises(a.Gate,match='authority_final_boundary'):
        a.consume_and_call(d,b,'C'*64,'run',call,emit)
    call.assert_not_called();assert (d/'single-shot-used.json').exists()


# Terminal supersession: only synthetic directories, real original consumer and
# existing exclusive/fsync/completed-link evidence interfaces.
@pytest.fixture
def step5_supersession(step5_once, monkeypatch):
    old,b,tmp=step5_once
    source=PACKAGE.parent/'step5-authorization-supersession-v1-20261023/confirmation_once.py'
    spec=importlib.util.spec_from_file_location('step5_supersession_synthetic',source)
    new=importlib.util.module_from_spec(spec);spec.loader.exec_module(new)
    monkeypatch.setattr(new,'base',old)
    monkeypatch.setattr(new,'Gate',old.Gate);monkeypatch.setattr(new,'demand',old.demand)
    monkeypatch.setattr(new,'now',old.now)
    directory=tmp/'old';directory.mkdir()
    successor=directory/'supersession-v1';successor.mkdir()
    issued=old.issue(directory,b,new.OLD_PACKAGE,owner_issue=True)
    monkeypatch.setattr(new,'OLD_ID',issued['id'])
    monkeypatch.setattr(new,'OLD_SHA',old.sha(directory/'authorization.json').lower())
    return SimpleNamespace(new=new,old=old,b=b,d=directory,s=successor,
        package_hash='D'*64,run='a'*32,events=[],emit=lambda *v:None)


def supersede(f, emit=None):
    return f.new.supersede_and_issue(f.d,f.s,f.b,f.package_hash,f.run,emit or f.emit,owner=True)


def successor_call(f, call, emit=None):
    return f.new.consume_and_call(f.d,f.s,f.b,f.package_hash,'b'*32,call,emit or f.emit)


def test_step5_supersession_original_remains_authoritative_until_transition(step5_supersession):
    f=step5_supersession;call=Mock(return_value='original')
    with pytest.raises(f.new.Gate,match='explicit_owner_supersession'):
        f.new.supersede_and_issue(f.d,f.s,f.b,f.package_hash,f.run,f.emit)
    assert f.old.consume_and_call(f.d,f.b,f.new.OLD_PACKAGE,'original-run',call,f.emit)=='original'
    with pytest.raises(f.old.Gate,match='authority_consumed'):supersede(f)
    assert call.call_count==1 and not (f.s/'authorization.json').exists()


def test_step5_supersession_terminal_preserves_original_history_and_denies_old(step5_supersession):
    f=step5_supersession
    before={p.name:p.read_bytes() for p in f.d.iterdir() if p.is_file()}
    record=supersede(f)
    terminal,_=f.new.read_retirement(f.d,f.s,f.b,f.package_hash)
    assert terminal['state']=='SUPERSEDED' and record['predecessor_id']==f.new.OLD_ID
    assert record['scope']==f.old.scope_fields(f.b) and record['expires_utc']==f.old.EXPIRES
    assert all((f.d/name).read_bytes()==value for name,value in before.items())
    call=Mock(return_value='new')
    with pytest.raises(f.old.Gate,match='authority_consumed'):
        f.old.consume_and_call(f.d,f.b,f.new.OLD_PACKAGE,'stale-original',call,f.emit)
    assert successor_call(f,call)=='new'
    with pytest.raises(f.new.Gate,match='authority_consumed'):successor_call(f,call)
    assert call.call_count==1


@pytest.mark.parametrize('point',[
    'before_start','after_start','partial_marker','after_marker','retirement_publication',
    'after_retirement_publication','after_retirement_pass','after_issuance_start',
    'after_successor_record','successor_publication','after_successor_publication'])
def test_step5_supersession_failure_boundaries_are_permanent(step5_supersession,monkeypatch,point):
    f=step5_supersession;h=f.new.helpers();save=h._save;publish=h._publish_completion
    def write(path,value):
        if point=='before_start' and path.name=='supersession-started.once':raise OSError('private')
        if point=='partial_marker' and path==f.d/'single-shot-used.json':
            path.write_text('{');raise OSError('private fsync')
        save(path,value)
        after={'after_start':f.s/'supersession-started.once','after_marker':f.d/'single-shot-used.json',
               'after_issuance_start':f.s/'issuance-started.once','after_successor_record':f.s/'authorization.json'}
        if point in after and path==after[point]:raise OSError('private')
    def publication(path,identifier,**kw):
        if point=='retirement_publication' and path==f.d/'single-shot-used.json':raise OSError('private')
        if point=='successor_publication' and path==f.s/'authorization.json':raise OSError('private')
        publish(path,identifier,**kw)
        if point=='after_retirement_publication' and path==f.d/'single-shot-used.json':raise KeyboardInterrupt()
        if point=='after_successor_publication' and path==f.s/'authorization.json':raise KeyboardInterrupt()
    def emit(op,status):
        if point=='after_retirement_pass' and (op,status)==('terminal_supersession','PASS'):raise OSError('private reporting')
    with monkeypatch.context() as m:
        m.setattr(h,'_save',write);m.setattr(h,'_publish_completion',publication)
        with pytest.raises((OSError,KeyboardInterrupt)):supersede(f,emit)
    marker=(f.d/'single-shot-used.json').exists()
    assert marker==(point not in ('before_start','after_start'))
    call=Mock()
    if marker:
        with pytest.raises(f.old.Gate,match='authority_consumed'):
            f.old.consume_and_call(f.d,f.b,f.new.OLD_PACKAGE,'old',call,f.emit)
        with pytest.raises(Exception):supersede(f)
    if point!='after_successor_publication':
        with pytest.raises(Exception):successor_call(f,call)
    else:
        # Completed durable publication is distinguishable read-only from a
        # missing completion. Procedure requires reconciliation after a stop.
        assert f.new.read_successor(f.d,f.s,f.b,f.package_hash)[0]['kind']==f.new.NEW_KIND
    call.assert_not_called()


def test_step5_supersession_interrupted_hardlink_acknowledgment_resolves_once(step5_supersession,monkeypatch):
    f=step5_supersession;h=f.new.helpers();link=h.os.link;links=[]
    def interrupt(source,target):
        link(source,target);links.append(target);raise KeyboardInterrupt()
    monkeypatch.setattr(h.os,'link',interrupt)
    supersede(f)
    assert len(links)==2 and f.new.read_successor(f.d,f.s,f.b,f.package_hash)[0]['kind']==f.new.NEW_KIND


def test_step5_supersession_stale_original_reader_cannot_cross_retirement(step5_supersession):
    f=step5_supersession;old_call=Mock();new_call=Mock(return_value='new')
    def stale(op,status):
        if (op,status)==('authority_consumption','STARTED'):supersede(f)
    with pytest.raises(FileExistsError):
        f.old.consume_and_call(f.d,f.b,f.new.OLD_PACKAGE,'stale',old_call,stale)
    old_call.assert_not_called()
    assert successor_call(f,new_call)=='new' and new_call.call_count==1


def test_step5_supersession_simultaneous_old_retirement_uses_same_atomic_slot(step5_supersession,monkeypatch):
    f=step5_supersession;h=f.new.helpers();save=h._save;barrier=Barrier(2)
    old_call=Mock(return_value='old');new_call=Mock(return_value='new')
    def contested(path,value):
        if path==f.d/'single-shot-used.json':barrier.wait(timeout=10)
        save(path,value)
    monkeypatch.setattr(h,'_save',contested)
    def old():
        try:return f.old.consume_and_call(f.d,f.b,f.new.OLD_PACKAGE,'race',old_call,f.emit)
        except FileExistsError:return 'blocked'
    def new():
        try:supersede(f);return successor_call(f,new_call)
        except FileExistsError:return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(old),pool.submit(new)];results=[future.result() for future in futures]
    assert results.count('blocked')==1 and old_call.call_count+new_call.call_count==1


def test_step5_supersession_simultaneous_successors_submit_at_most_once(step5_supersession):
    f=step5_supersession;supersede(f);barrier=Barrier(2);call=Mock(return_value='new')
    def execute(_):
        barrier.wait(timeout=10)
        try:return successor_call(f,call)
        except (FileExistsError,f.new.Gate):return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(execute,range(2)))
    assert results.count('new')==1 and results.count('blocked')==1 and call.call_count==1


@pytest.mark.parametrize('point',['before_retirement','after_retirement','before_execution','after_consumption'])
def test_step5_supersession_original_expiry_enforced_at_changed_boundaries(step5_supersession,monkeypatch,point):
    f=step5_supersession;expired=lambda:datetime.fromisoformat(f.old.EXPIRES);call=Mock()
    def expire():monkeypatch.setattr(f.new,'now',expired)
    if point=='before_retirement':expire()
    def emit(op,status):
        if point=='after_retirement' and (op,status)==('terminal_supersession','PASS'):expire()
        if point=='after_consumption' and (op,status)==('authority_consumption','PASS'):expire()
    if point in ('before_retirement','after_retirement'):
        with pytest.raises(f.new.Gate,match='original_expiry'):supersede(f,emit)
    else:
        supersede(f)
        if point=='before_execution':expire()
        with pytest.raises(f.new.Gate,match='original_expiry'):successor_call(f,call,emit)
    call.assert_not_called()


@pytest.mark.parametrize('field,value',[
    ('intent_fingerprint','F'*64),('identity_fingerprint','E'*64),('recipient','other@example.invalid'),
    ('purpose','management'),('attempt',2),('expires_at','2026-10-25T20:17:13.754265+00:00')])
def test_step5_supersession_never_expands_original_authority(step5_supersession,field,value):
    f=step5_supersession;supersede(f);f.b=dict(f.b,**{field:value});call=Mock()
    with pytest.raises(f.new.Gate):successor_call(f,call)
    call.assert_not_called()


@pytest.mark.parametrize('artifact',['terminal','completion','started','original','successor'])
def test_step5_supersession_missing_or_contradictory_evidence_denies_execution(step5_supersession,artifact):
    f=step5_supersession;supersede(f)
    path={'terminal':f.d/'single-shot-used.json','completion':f.d/'completed-single-shot-used.json',
          'started':f.s/'supersession-started.once','original':f.d/'authorization.json',
          'successor':f.s/'authorization.json'}[artifact]
    path.write_text('{"contradictory":true}')
    call=Mock()
    with pytest.raises(Exception):successor_call(f,call)
    with pytest.raises(Exception):f.old.consume_and_call(f.d,f.b,f.new.OLD_PACKAGE,'old',call,f.emit)
    call.assert_not_called()


@pytest.mark.parametrize('outcome',['accepted','unknown','cleanup_failed','expired_db_clock'])
def test_step5_supersession_existing_backend_claim_outcomes_and_no_retry(step5_supersession,runtime,outcome):
    f=step5_supersession;supersede(f)
    model,_,_,target=confirmation_scoped_setup()
    runtime.model.records=deepcopy(model.records);runtime.model.now=model.now
    constraint=outbox.ConfirmationIntentScope(outbox.intent_fingerprint(target['intent']),outbox.intent_identity(target),
        target['created_at']+timedelta(hours=24),issued_at=target['created_at'])
    if outcome=='unknown':runtime.transport.side_effect=TimeoutError('private')
    if outcome=='cleanup_failed':runtime.model.dispose.side_effect=RuntimeError('private')
    if outcome=='expired_db_clock':runtime.model.now=constraint.deadline
    def call():
        return processor.process_confirmations(expected_profile='testing',enabled=True,credential_account='synthetic',
            confirmation_page=PAGE,testing_recipient=MAILBOX,management_enabled=True,intent_scope=constraint)
    result=successor_call(f,call)
    expected=0 if outcome=='expired_db_clock' else 1
    assert runtime.transport.call_count==expected and result.processed==expected
    if expected:
        saved=runtime.model.rows(intents)[0]
        assert saved['outcome']==('submission_unknown' if outcome=='unknown' else 'provider_accepted')
    if outcome=='cleanup_failed':assert result.first_failure['operation']=='dispose'
    with pytest.raises(f.new.Gate,match='authority_consumed'):successor_call(f,call)
    assert runtime.transport.call_count==expected


@pytest.mark.parametrize('failure',['dispose','interrupted'])
def test_step5_supersession_child_parent_evidence_preserves_first_failure(step5_supersession,monkeypatch,failure):
    f=step5_supersession;supersede(f);a=f.new
    instance=f.d.parent/'instance';instance.mkdir();run=instance/('step5-confirmation-run-'+f.run);run.mkdir()
    package=f.d.parent/'package';package.mkdir();(package/'SOURCE-IDENTITIES.json').write_text('{}')
    monkeypatch.setattr(a,'ROOT',f.d.parent);monkeypatch.setattr(a,'PACKAGE',package)
    monkeypatch.setattr(a,'AUTHORITY',f.d);monkeypatch.setattr(a,'SUCCESSOR',f.s)
    monkeypatch.setattr(a,'sha',lambda p:f.package_hash)
    monkeypatch.setattr(f.old,'binding',lambda:f.b);monkeypatch.setattr(a,'historical_stop',lambda:None)
    @contextmanager
    def lock():yield
    monkeypatch.setattr(schedule,'_local_run_lock',lock)
    origin=safe_failure('processor','dispose',RuntimeError(),side_effects='acknowledged_outcomes_retained')
    call=Mock(side_effect=KeyboardInterrupt()) if failure=='interrupted' else Mock(return_value=BatchResult('unavailable',1,origin))
    monkeypatch.setattr(f.old,'load_module',lambda *v:SimpleNamespace(run_owner_authorized_once=call))
    def ledger(b,*,before):
        if not before:raise OSError('private observation failure')
        return {}
    monkeypatch.setattr(f.old,'ledger',ledger)
    monkeypatch.setattr(a.sys,'argv',['synthetic','Execute',f.run,str(run)])
    assert a.main()==(130 if failure=='interrupted' else 1)
    result=json.loads((run/'child-result.json').read_text())
    if failure=='dispose':assert result['first_failure']['operation']=='dispose' and result['processed']==1
    else:assert result['first_failure']['predicate']=='interrupted_unknown' and result['native_exit']==130
    assert (f.s/'single-shot-used.json').exists() and call.call_count==1
    if OFFLINE_EVIDENCE_DIRECTORY:
        # Actual producer bytes feed the actual extracted PowerShell consumer;
        # no operational authority, private binding or subscriber data is copied.
        f.new.helpers()._save(Path(OFFLINE_EVIDENCE_DIRECTORY)/('producer-'+failure+'.json'),result)


@pytest.mark.parametrize('reason',['pristine_attempt_one','original_expiry','contradictory_historical_submission'])
def test_step5_supersession_owner_live_eligibility_failure_never_retires(step5_supersession,monkeypatch,reason):
    f=step5_supersession;a=f.new
    instance=f.d.parent/'instance';instance.mkdir();run=instance/('step5-confirmation-run-'+f.run);run.mkdir()
    package=f.d.parent/'package';package.mkdir();(package/'SOURCE-IDENTITIES.json').write_text('{}')
    monkeypatch.setattr(a,'ROOT',f.d.parent);monkeypatch.setattr(a,'PACKAGE',package)
    monkeypatch.setattr(a,'AUTHORITY',f.d);monkeypatch.setattr(a,'SUCCESSOR',f.s)
    monkeypatch.setattr(f.old,'binding',lambda:f.b)
    def reject(*args,**kwargs):raise a.Gate(reason)
    monkeypatch.setattr(a,'historical_stop',reject if reason=='contradictory_historical_submission' else lambda:None)
    monkeypatch.setattr(f.old,'ledger',reject)
    @contextmanager
    def lock():yield
    monkeypatch.setattr(schedule,'_local_run_lock',lock)
    monkeypatch.setattr(a.sys,'argv',['synthetic','OwnerSupersede',f.run,str(run)])
    assert a.main()==1
    result=json.loads((run/'child-result.json').read_text())
    assert result['first_failure']['predicate']==reason and result['stopped_stage']=='original_live_preflight'
    assert result['not_run']==['terminal_supersession','owner_issuance']
    assert not (f.d/'single-shot-used.json').exists() and not (f.s/'authorization.json').exists()
