"""Authenticated callbacks against actual accepted confirmation/release ledgers."""
import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
import json
from unittest.mock import Mock

import pytest
from sqlalchemy.sql.dml import Insert

from oaf_website import brevo_unsubscribe as b, notification_management as m
from oaf_website import state_requests as runtime
from oaf_website import confirmation_outbox as outbox
from oaf_website.confirmation_outbox_schema import intents, confirmation_attempts
from oaf_website.notification_delivery_schema import deliveries, attempts, suppressions, verification, events
from oaf_website.notifications import SubscriptionStore
from oaf_website.notification_dispatch import ReleaseDispatcher, validate_failure
from test_notification_delivery import Model,SECRET,subscribe,payload,EVENT
from test_notification_management import managed, PREFERENCES, ACTION
from test_state_requests import ORIGIN
from test_brevo import CONFIG,PAGE,response,ACCEPTED

BEARER='synthetic-webhook-secret-testing-'+'a'*32


def accepted(kind='confirmation'):
    model,store,digest,token=managed(verified=kind=='release')
    transport=Mock(return_value=response())
    if kind=='confirmation':
        processor=outbox.ConfirmationOutboxStore(model,SECRET,'testing',management_enabled=True)
        assert outbox.ConfirmationDispatcher(processor,CONFIG,PAGE,transport=transport).process().processed==1
    else:
        store.accept_event(payload())
        assert ReleaseDispatcher(store,CONFIG,PAGE,transport=transport).process(EVENT).processed==1
    return model,store,digest,token


def event(model,**changes):
    # Full synthetic shape from Brevo's transactional Unsubscribed contract.
    return dict(dict(event='unsubscribed',email='subscriber1@example.invalid',id=123,
                     **{'message-id':ACCEPTED.message_id, 'X-Mailin-custom':'synthetic-custom'},
                     ts=int(model.now.timestamp()),ts_event=int(model.now.timestamp()),
                     date='2026-10-15 14:00:00',subject='SYNTHETIC PRIVATE SUBJECT',template_id=22,
                     tag='["transactionalTag"]',ts_epoch=int(model.now.timestamp()*1000),
                     sending_ip='192.0.2.1',user_agent='Synthetic browser',device_used='MOBILE',
                     mirror_link='https://example.invalid/private-preview',contact_id=8),**changes)


def app_client(model,store,config=None):
    config=b.BrevoWebhookConfig('testing',BEARER) if config is None else config
    app=runtime._build_app(None,runtime.BrowserRecognition(SECRET),ORIGIN,environment=store.environment,
        subscription_store=SubscriptionStore(model,management_store=store),brevo_webhook_config=config)
    return app,app.test_client()


def send(client,data,**kwargs):
    return client.post(b.WEBHOOK_PATH,base_url=ORIGIN,json=data,
                       headers=kwargs.pop('headers',{'Authorization':'Bearer '+BEARER}),**kwargs)


def test_event_timestamp_before_submission_is_rejected_without_mutation():
    model,store,_,_=accepted()
    _,client=app_client(model,store)
    before=deepcopy(model.records)
    assert send(client,event(model,ts_event=int(model.now.timestamp())-1)).status_code==400
    assert model.records==before


def test_direct_rejection_without_diagnostic_collector_preserves_database():
    model,store,_,_=accepted()
    before=deepcopy(model.records)
    data=b.event_payload(event(model,**{'message-id':'unknown@example.invalid'}))
    assert b.process_unsubscribe(store,data)=='retry'
    assert model.records==before


def test_rejection_then_unclassified_processing_failure_retains_first_cause(monkeypatch,caplog):
    model,store,_,_=accepted()
    _,client=app_client(model,store)
    def fail(store,event,*,diagnostics,receipt):
        diagnostics.append(b._failure('webhook_correlation','webhook_accepted_message_present'))
        raise RuntimeError('synthetic private failure')
    monkeypatch.setattr(b,'process_unsubscribe',fail)
    assert send(client,event(model)).status_code==429
    record=json.loads(caplog.records[-1].getMessage().split(': ',1)[1])
    detail=validate_failure(record['first_failure'])
    assert detail['predicate']=='webhook_accepted_message_present'
    assert detail['side_effects']=='database_transaction_unacknowledged'


@pytest.mark.parametrize('kind',['confirmation','release'])
@pytest.mark.parametrize('brackets',[True,False])
def test_valid_authenticated_event_commits_original_withdrawal_and_suppression(kind,brackets):
    model,store,digest,token=accepted(kind); app,client=app_client(model,store)
    old_verify=deepcopy(model.rows(verification)); old_sends=deepcopy(model.rows(intents)+model.rows(deliveries)+model.rows(attempts)+model.rows(confirmation_attempts))
    data=event(model,**{'message-id':ACCEPTED.message_id if brackets else ACCEPTED.message_id[1:-1]})
    assert send(client,data).json=={'status':'processed'}
    assert model.rows(m.notifications)[0]['unsubscribed_at']==model.now
    assert model.rows(suppressions)[0]['reason']=='provider_block'
    audit=model.rows(m.changes)[0]
    assert audit['source']=='brevo' and audit['provider_message_id']==ACCEPTED.message_id[1:-1]
    assert model.rows(verification)==old_verify
    assert model.rows(intents)+model.rows(deliveries)+model.rows(attempts)+model.rows(confirmation_attempts)==old_sends
    assert BEARER not in repr(model.records)


def test_webhook_id_is_not_message_id_or_occurrence_identity():
    model,store,digest,token=accepted(); _,client=app_client(model,store)
    first=event(model); assert send(client,first).status_code==200
    before=deepcopy(model.records)
    model.elapse(seconds=10)
    assert send(client,event(model,id=999999)).status_code==200
    assert model.records==before
    assert len(model.rows(m.changes))==1


@pytest.mark.parametrize('headers',[{}, {'Authorization':BEARER},{'Authorization':'Bearer '+'b'*64},
    {'Authorization':'Basic '+BEARER},{'Authorization':'Bearer '+BEARER+', Bearer '+BEARER},
    {'Authorization':'Bearer '+BEARER+'x'},{'Authorization':'Bearer '+'é'*64}])
def test_forged_or_missing_bearer_does_not_read_or_mutate(headers):
    model,store,_,_=accepted(); _,client=app_client(model,store)
    before=deepcopy(model.records); statements=len(model.statements)
    assert send(client,event(model),headers=headers).status_code==401
    assert model.records==before and len(model.statements)==statements


def test_no_cookie_or_browser_csrf_needed_but_http_and_query_are_rejected():
    model,store,_,_=accepted(); _,client=app_client(model,store)
    assert not client.get_cookie('__Host-oaf-state-browser')
    assert client.post(b.WEBHOOK_PATH,base_url='http://website.example',json=event(model),
                       headers={'Authorization':'Bearer '+BEARER}).status_code==401
    assert client.post(b.WEBHOOK_PATH+'?token=redacted',base_url=ORIGIN,json=event(model),
                       headers={'Authorization':'Bearer '+BEARER}).status_code==401
    assert send(client,event(model)).status_code==200


@pytest.mark.parametrize('change',[{'email':'other@example.invalid'}, {'message-id':'Other@relay.example'},
    {'message-id':123},{'message-id':'<<id@example.invalid>>'},{'message-id':'id'},{'message-id':'id@host '},
    {'event':'delivered'},{'ts_event':True},{'ts_event':-1},{'ts_event':10**15},{'ts':False}, {'id':True},
    {'environment':'development'},{'event':'UNSUBSCRIBED'},{'email':[]},{'message-id':'é@host'},
    {'subject':[]},{'date':{}},{'tags':[{}]},{'tag':123}])
def test_invalid_or_uncorrelated_events_cannot_withdraw(change):
    model,store,_,_=accepted(); _,client=app_client(model,store); before=deepcopy(model.records)
    result=send(client,event(model,**change))
    assert result.status_code in {400,429}
    assert model.records==before


@pytest.mark.parametrize('field',['message-id','email','event','ts_event'])
def test_missing_fields_never_use_fallback_identity(field):
    model,store,_,_=accepted(); _,client=app_client(model,store)
    data=event(model); data.pop(field)
    assert send(client,data).status_code==400 and not model.rows(m.changes)


@pytest.mark.parametrize('raw',['[]','null','{"event":"unsubscribed","event":"unsubscribed"}',
                               '{"event":NaN}','{"event":Infinity}','{bad'])
def test_strict_bounded_json_and_no_batch_processing(raw):
    model,store,_,_=accepted(); _,client=app_client(model,store)
    result=client.post(b.WEBHOOK_PATH,base_url=ORIGIN,data=raw,content_type='application/json',
                       headers={'Authorization':'Bearer '+BEARER})
    assert result.status_code==400 and not model.rows(m.changes)


def test_webhook_only_larger_body_bound_and_private_fields_not_retained():
    model,store,_,_=accepted(); _,client=app_client(model,store)
    assert send(client,event(model,subject='PRIVATE SUBJECT '+('x'*1500))).status_code==200
    assert 'PRIVATE SUBJECT' not in repr(model.records)
    assert send(client,event(model,subject='x'*17000)).status_code==413
    csrf=client.get('/api/notifications/session',base_url=ORIGIN).json['csrf_token']
    assert client.post('/api/notifications/manage/recovery',base_url=ORIGIN,data='x'*1500,
        content_type='application/json',headers={'Origin':ORIGIN,'X-CSRF-Token':csrf}).status_code==413


def test_old_lifecycle_event_never_withdraws_new_independent_consent():
    model,store,digest,token=accepted(); _,client=app_client(model,store)
    store.unsubscribe_legacy(digest); old_withdrawal=model.rows(m.notifications)[0]['unsubscribed_at']
    model.elapse(seconds=60); new_digest=subscribe(model,2,email='subscriber1@example.invalid')
    confirmation=store.request_confirmation('subscriber1@example.invalid'); assert store.confirm(confirmation)=='verified'
    new_verify=deepcopy(model.rows(verification)[-1])
    assert send(client,event(model)).status_code==200
    new=next(r for r in model.rows(m.notifications) if r['unsubscribe_digest']==new_digest)
    assert new['unsubscribed_at'] is None and new['preferences_revision']==0
    assert model.rows(m.notifications)[0]['unsubscribed_at']==old_withdrawal
    assert model.rows(verification)[-1]==new_verify
    assert model.rows(suppressions)[0]['reason']=='provider_block'
    # Provider suppression survives and is distinct from new consent withdrawal.
    assert store.request_confirmation('subscriber1@example.invalid') is None


def test_duplicate_events_are_atomic_under_concurrency():
    model,store,_,_=accepted(); data=b.event_payload(event(model))
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert set(pool.map(lambda _:b.process_unsubscribe(store,data),range(8)))=={'processed'}
    assert len(model.rows(m.changes))==len(model.rows(suppressions))==1


@pytest.mark.parametrize('failure',['connect','execute','commit','uncertain'])
def test_transaction_failure_returns_retryable_429_and_idempotent_retry(failure):
    model,store,_,_=accepted(); _,client=app_client(model,store)
    before=deepcopy(model.records); model.failure=failure
    assert send(client,event(model)).status_code==429
    if failure!='uncertain': assert model.records==before
    model.failure=None
    assert send(client,event(model)).status_code==200
    assert len(model.rows(m.changes))==len(model.rows(suppressions))==1


def test_suppression_insert_failure_rolls_back_withdrawal_and_receipt(monkeypatch,caplog):
    model,store,_,_=accepted(); _,client=app_client(model,store); begin=model.begin
    @contextmanager
    def failing():
        with begin() as connection:
            execute=connection.execute
            def run(statement):
                if isinstance(statement,Insert) and statement.table.name==suppressions.name: raise RuntimeError('private')
                return execute(statement)
            connection.execute=run; yield connection
    monkeypatch.setattr(model,'begin',failing); before=deepcopy(model.records)
    assert send(client,event(model)).status_code==429
    assert model.records==before
    detail=json.loads(next(r.getMessage() for r in caplog.records
        if r.getMessage().startswith('Notification operation failed: ')).split(': ',1)[1])
    assert detail['first_failure']['operation']=='transaction_body'
    assert detail['first_failure']['side_effects']=='database_rolled_back'
    assert 'private' not in json.dumps(detail)


@pytest.mark.parametrize('case',['missing','uncertain','rejected','contradiction','ambiguous','too_old','future','wrong_environment','audit_time'])
def test_no_guessing_of_missing_uncertain_or_contradictory_correlation(case):
    model,store,_,_=accepted('release' if case=='wrong_environment' else 'confirmation'); _,client=app_client(model,store)
    parent=(model.rows(deliveries) if case=='wrong_environment' else model.rows(intents))[0]
    attempt=(model.rows(attempts) if case=='wrong_environment' else model.rows(confirmation_attempts))[0]
    data=event(model)
    if case=='missing': parent['provider_message_id']=None; attempt['provider_message_id']=None
    if case=='uncertain': parent['status']='uncertain'; parent['outcome']='submission_unknown'; attempt['outcome']='submission_unknown'
    if case=='rejected': parent['status']='rejected'; parent['outcome']='provider_rejected'
    if case=='contradiction': attempt['provider_message_id']='<different@example.invalid>'
    if case=='audit_time': attempt['finished_at']+=timedelta(seconds=1)
    if case=='ambiguous':
        other=dict(parent,intent='f'*64); model.rows(intents).append(other)
        model.rows(confirmation_attempts).append(dict(attempt,intent='f'*64))
    if case=='too_old': data['ts_event']-=1; data['ts']-=1
    if case=='future': data['ts_event']+=301; data['ts']+=301
    if case=='wrong_environment': model.rows(events)[0]['environment']='development'
    before=deepcopy(model.records)
    assert send(client,data).status_code in {400,429}
    assert model.records==before


def test_existing_suppression_evidence_is_preserved_and_pending_delivery_stops():
    model,store,digest,token=accepted(); store.suppress('subscriber1@example.invalid','complaint')
    before=deepcopy(model.rows(suppressions)); _,client=app_client(model,store)
    assert send(client,event(model)).status_code==200 and model.rows(suppressions)==before


@pytest.mark.parametrize('profile',['testing','development'])
def test_exact_protected_environment_configuration_loader(profile):
    loader=Mock(return_value=BEARER)
    config=b.load_brevo_webhook_config(profile,credential_account='synthetic',environ={'OAF_ENV':profile},credential_loader=loader)
    loader.assert_called_once_with(f'OAF Website/{profile}/Brevo/UnsubscribeWebhook','synthetic',{'OAF_ENV':profile},exact_target=True)
    assert BEARER not in repr(config) and config.environment==profile


@pytest.mark.parametrize('profile,environ',[('production',{'OAF_ENV':'production'}),('testing',{'OAF_ENV':'development'}),
    ('testing',{'OAF_ENV':'testing','BREVO_WEBHOOK_TOKEN':'forbidden'}),('testing',{'OAF_ENV':'testing','PGHOST':'forbidden'})])
def test_invalid_configuration_rejected_before_credentials(profile,environ):
    loader=Mock()
    with pytest.raises(ValueError): b.load_brevo_webhook_config(profile,credential_account='synthetic',environ=environ,credential_loader=loader)
    loader.assert_not_called()


def test_environment_mismatch_and_default_off():
    model,store,_,_=accepted()
    with pytest.raises(ValueError): app_client(model,store,b.BrevoWebhookConfig('development',BEARER))
    with pytest.raises(ValueError): b.validate_webhook_config(b.BrevoWebhookConfig('testing',BEARER),'development')
    other=runtime._build_app(None,runtime.BrowserRecognition(SECRET),ORIGIN,subscription_store=SubscriptionStore(model))
    assert send(other.test_client(),event(model)).status_code==429


def diagnostic(caplog, predicate, context, status, *, side_effects='none'):
    records=[r for r in caplog.records if r.getMessage().startswith('Notification operation failed: ')]
    assert len(records)==1
    text=records[0].getMessage()
    detail=json.loads(text.split(': ',1)[1])
    assert detail['operation']=='brevo_unsubscribe' and detail['http_status']==status
    first=validate_failure(detail['first_failure'])
    assert detail['event_outcome'] == ('rejected' if context else 'accepted')
    if context:
        assert 'webhook_receipt' not in detail
        if predicate != 'webhook_allowed_fields':
            assert first['expected'] == predicate + '_satisfied'
            assert first['observed'] == predicate + '_failed'
        if side_effects == 'none':
            expected = ['database_mutation', 'provider_submission']
            if context != 'webhook_correlation':
                expected = ['event_correlation', 'database_transaction'] + expected
            assert first['dependent_not_run'] == expected
    assert first['stage']=='notifications' and first['context']==context
    assert first['predicate']==predicate and first['side_effects']==side_effects
    assert datetime.fromisoformat(first['timestamp_utc']).utcoffset()==timedelta(0)
    for private in (BEARER,ACCEPTED.message_id,ACCEPTED.message_id[1:-1],SECRET.decode(),
                    'subscriber1@example.invalid','other@example.invalid','SYNTHETIC PRIVATE SUBJECT',
                    'synthetic-custom','private-preview','unknown-private-key','synthetic private','Bearer '):
        assert private not in text
    return detail


@pytest.mark.parametrize('change,predicate',[
    ({'event':'delivered'},'webhook_event_name'),
    ({'unknown-private-key':'private'},'webhook_allowed_fields'),
    *[({name:True},'webhook_'+name+'_integer') for name in ('ts_event','ts','id','template_id','contact_id','ts_epoch')],
    *[({name:-1},'webhook_'+name+'_range') for name in ('ts_event','ts','id','template_id','contact_id','ts_epoch')],
    ({'ts_event':253402300800},'webhook_ts_event_range'),
    ({'ts':0},'webhook_ts_range'),
    *[({name:[]},'webhook_'+code+'_text') for name,code in
      (('date','date'),('subject','subject'),('X-Mailin-custom','custom'),('tag','tag'),
       ('sending_ip','sending_ip'),('user_agent','user_agent'),('device_used','device_used'),('mirror_link','mirror_link'))],
    *[({name:'x'*8193},'webhook_'+code+'_length') for name,code in
      (('date','date'),('subject','subject'),('X-Mailin-custom','custom'),('tag','tag'),
       ('sending_ip','sending_ip'),('user_agent','user_agent'),('device_used','device_used'),('mirror_link','mirror_link'))],
    ({'tags':'private'},'webhook_tags_array'),({'tags':['x']*51},'webhook_tags_count'),
    ({'tags':[{}]},'webhook_tags_text'),({'tags':['x'*257]},'webhook_tags_length'),
    ({'email':[]},'webhook_email_format'),({'message-id':123},'webhook_message_id_text'),
    ({'message-id':'x'*201},'webhook_message_id_length'),({'message-id':'invalid'},'webhook_message_id_format'),
])
def test_event_rejections_record_exact_safe_predicate(change,predicate,caplog):
    model,store,_,_=accepted(); _,client=app_client(model,store); before=deepcopy(model.records)
    result=send(client,event(model,**change))
    assert result.status_code==400 and result.json=={'status':'error','message':'Invalid event.'}
    assert model.records==before
    diagnostic(caplog,predicate,'webhook_event',400)


@pytest.mark.parametrize('raw,predicate',[
    ('[]','webhook_event_object'),('null','webhook_event_object'),('{}','webhook_required_fields'),
    ('{"event":"unsubscribed","event":"private"}','webhook_json_unique_keys'),
    ('{"event":NaN}','webhook_json_finite_constants'),('{"event":Infinity}','webhook_json_finite_constants'),
    ('{bad','webhook_json_decode'),(b'\xff','webhook_json_decode'),
])
def test_json_rejections_record_exact_safe_predicate(raw,predicate,caplog):
    model,store,_,_=accepted(); _,client=app_client(model,store); before=deepcopy(model.records)
    result=client.post(b.WEBHOOK_PATH,base_url=ORIGIN,data=raw,content_type='application/json',
                       headers={'Authorization':'Bearer '+BEARER})
    assert result.status_code==400 and model.records==before
    diagnostic(caplog,predicate,'webhook_json' if predicate.startswith('webhook_json') else 'webhook_event',400)


@pytest.mark.parametrize('name',['event','original'])
def test_unsupported_platform_timestamp_is_safe(name,monkeypatch,caplog):
    model,store,_,_=accepted(); _,client=app_client(model,store); before=deepcopy(model.records)
    real=b.datetime; calls=[]
    def convert(value,tz):
        calls.append(value)
        if len(calls)==(1 if name=='event' else 2): raise OSError('synthetic private timestamp')
        return real.fromtimestamp(value,tz)
    monkeypatch.setattr(b,'datetime',Mock(fromtimestamp=convert))
    assert send(client,event(model)).status_code==400 and model.records==before
    detail=diagnostic(caplog,'webhook_'+name+'_time_supported','webhook_event',400)
    assert detail['first_failure']['exception_class']=='OSError'


@pytest.mark.parametrize('case,predicate,status',[
    ('future','webhook_event_not_future',400),('time_order','webhook_time_order',400),
    ('orphan','webhook_attempt_parent_present',400),('submitting','webhook_parent_accepted',429),
    ('status','webhook_parent_accepted',400),('outcome','webhook_parent_outcome',400),
    ('parent_message','webhook_parent_message',400),('accepted_at','webhook_parent_accepted_at',400),
    ('attempt_missing','webhook_attempt_present',400),('attempt_outcome','webhook_attempt_outcome',400),
    ('attempt_message','webhook_attempt_message',400),('submitting_at','webhook_attempt_submitting_at',400),
    ('finished_at','webhook_attempt_finished_at',400),('acceptance_time','webhook_acceptance_time_match',400),
    ('attempt_time','webhook_attempt_time_order',400),('latest_attempt','webhook_latest_attempt_match',400),
    ('release_missing','webhook_release_present',400),('environment','webhook_release_environment',400),
    ('missing','webhook_accepted_message_present',429),('ambiguous','webhook_accepted_message_unique',400),
    ('subscriber','webhook_subscriber_present',400),('recipient','webhook_recipient_match',400),
    ('original_time','webhook_original_after_submission',400),
])
def test_correlation_rejections_record_exact_safe_predicate(case,predicate,status,caplog):
    release=case in {'release_missing','environment'}
    model,store,_,_=accepted('release' if release else 'confirmation'); _,client=app_client(model,store)
    parent_table,attempt_table=(deliveries,attempts) if release else (intents,confirmation_attempts)
    parent=model.rows(parent_table)[0]; attempt=model.rows(attempt_table)[0]; data=event(model)
    if case=='future': data['ts_event']+=301
    if case=='time_order': data['ts']+=1
    if case=='orphan': model.rows(parent_table).clear()
    if case in {'status','submitting'}: parent['status']='submitting' if case=='submitting' else 'rejected'
    if case=='outcome': parent['outcome']='provider_rejected'
    if case=='parent_message': parent['provider_message_id']='<different@example.invalid>'
    if case=='accepted_at': parent['accepted_at']=None
    if case=='attempt_missing': parent['attempts']=2
    if case=='attempt_outcome': attempt['outcome']='submission_unknown'
    if case=='attempt_message': attempt['provider_message_id']='<different@example.invalid>'
    if case=='submitting_at': attempt['submitting_at']=None
    if case=='finished_at': attempt['finished_at']=None
    if case=='acceptance_time': attempt['finished_at']+=timedelta(seconds=1)
    if case=='attempt_time': attempt['submitting_at']+=timedelta(seconds=1)
    if case=='latest_attempt': model.rows(attempt_table).append(dict(attempt,attempt=2))
    if case=='release_missing': model.rows(events).clear()
    if case=='environment': model.rows(events)[0]['environment']='development'
    if case=='missing': parent['provider_message_id']=None; attempt['provider_message_id']=None
    if case=='ambiguous':
        model.rows(parent_table).append(dict(parent,intent='f'*64))
        model.rows(attempt_table).append(dict(attempt,intent='f'*64))
    if case=='subscriber': model.rows(m.notifications).clear()
    if case=='recipient': data['email']='other@example.invalid'
    if case=='original_time': data['ts']-=1
    before=deepcopy(model.records)
    result=send(client,data)
    assert result.status_code==status and model.records==before
    assert result.json['message']==('Invalid event correlation.' if status==400 else 'Event processing unavailable.')
    diagnostic(caplog,predicate,'webhook_correlation',status)


@pytest.mark.parametrize('case,predicate,status',[
    ('config','webhook_config_present',429),('store','webhook_store_present',429),
    ('http','webhook_https',401),('query','webhook_no_query',401),
    ('unicode','webhook_authorization_ascii',401),('bearer','webhook_authorization_match',401),
    ('media','webhook_json_media_type',415),
])
def test_rejection_before_parsing_never_accesses_store(case,predicate,status,caplog):
    from flask import Flask, jsonify
    app=Flask(__name__); store=Mock()
    def error(message,status): return jsonify(status='error',message=message),status
    b.register_brevo_unsubscribe(app,None if case=='store' else store,
        None if case=='config' else b.BrevoWebhookConfig('testing',BEARER),error)
    response=app.test_client().post(b.WEBHOOK_PATH+('?private=private' if case=='query' else ''),
        base_url='http://website.example' if case=='http' else ORIGIN,data='{bad',
        content_type='text/plain' if case=='media' else 'application/json',
        headers={'Authorization':'Bearer '+('é' if case=='unicode' else 'wrong' if case=='bearer' else BEARER)})
    assert response.status_code==status and not store.mock_calls
    context='webhook_configuration' if case in {'config','store'} else 'webhook_media_type' if case=='media' else 'webhook_authentication'
    diagnostic(caplog,predicate,context,status)


def test_first_failure_is_not_replaced_by_later_failures(caplog):
    model,store,_,_=accepted(); _,client=app_client(model,store)
    assert send(client,event(model,event='delivered',email=[],subject=[])).status_code==400
    diagnostic(caplog,'webhook_event_name','webhook_event',400)
    caplog.clear(); model.failure='commit'; before=deepcopy(model.records)
    assert send(client,event(model,ts_event=int(model.now.timestamp())+301)).status_code==429
    detail=diagnostic(caplog,'webhook_event_not_future','webhook_correlation',429,
                      side_effects='database_commit_uncertain')
    assert detail['transaction_failure']['operation']=='transaction_commit'
    assert detail['transaction_failure']['exception_class']=='RuntimeError'
    assert model.records==before


@pytest.mark.parametrize('failure,operation,side_effects',[
    ('connect','database_begin','none'),('execute','advisory_lock','database_rolled_back'),
    ('commit','transaction_commit','database_commit_uncertain'),('uncertain','transaction_commit','database_commit_uncertain'),
])
def test_processing_failure_retains_transaction_certainty(failure,operation,side_effects,caplog):
    model,store,_,_=accepted(); _,client=app_client(model,store); before=deepcopy(model.records); model.failure=failure
    assert send(client,event(model)).status_code==429
    record=next(r for r in caplog.records if r.getMessage().startswith('Notification operation failed: '))
    detail=json.loads(record.getMessage().split(': ',1)[1]); first=validate_failure(detail['first_failure'])
    assert detail['http_status']==429 and first['operation']==operation and first['side_effects']==side_effects
    assert first['exception_class']=='RuntimeError' and 'synthetic private' not in record.getMessage()
    if failure!='uncertain': assert model.records==before
    else: assert len(model.rows(m.changes))==len(model.rows(suppressions))==1


def test_wrapped_database_codes_do_not_expose_exception_text(monkeypatch,caplog):
    from sqlalchemy.exc import OperationalError
    model,store,_,_=accepted(); _,client=app_client(model,store); before=deepcopy(model.records)
    original=RuntimeError('synthetic private '+BEARER); original.sqlstate='23505'
    error=OperationalError('SYNTHETIC PRIVATE SUBJECT',{'email':'subscriber1@example.invalid'},original)
    error.hresult=-2147467259; error.returncode=2
    monkeypatch.setattr(store,'_change',Mock(side_effect=error))
    assert send(client,event(model)).status_code==429 and model.records==before
    detail=diagnostic(caplog,'operation_failed',None,429,side_effects='database_rolled_back')
    assert detail['first_failure']['operation']=='transaction_body'
    assert detail['first_failure']['exception_class']=='OperationalError'
    assert detail['first_failure']['sqlstate']=='23505' and detail['first_failure']['hresult']=='0x80004005'
    assert detail['first_failure']['exit_code']==2


def test_documented_unsubscribed_schema_already_matches_allowlist():
    # Synthetic shape only: https://developers.brevo.com/docs/transactional-webhooks#unsubscribed
    model, _, _, _ = accepted()
    data = event(model)
    assert b.ALLOWED_FIELDS == set(data) | {'tags', 'link', 'sender_email', 'source', 'uuid'}
    assert b.event_payload(data) == b.event_payload(dict(data, tags=['synthetic']))
    minimal = {name: data[name] for name in ('event', 'email', 'message-id', 'ts_event')}
    assert b.event_payload(minimal) == b.event_payload(data)


@pytest.mark.parametrize('name', ['reason', 's_returnpath', 'camp_id', 'campaign_name',
    'list_id', 'segment_ids', 'unsupported_field', 'message_id', 'event_type', 'authorization'])
def test_unsupported_fields_still_rejected_and_sanitized_names_retained(name):
    model, _, _, _ = accepted()
    with pytest.raises(ValueError) as caught:
        b.event_payload(event(model, **{name: 'PRIVATE-VALUE-must-never-be-retained'}))
    first = validate_failure(caught.value.notification_failure)
    assert first['field_validation'] == dict(offending_field_names=[name],
        offending_field_count=1, redacted_name_count=0, omitted_name_count=0)
    assert first['expected'] == 'set(data) <= ALLOWED_FIELDS'
    assert first['observed'] == 'set(data) - ALLOWED_FIELDS is nonempty'
    assert 'PRIVATE-VALUE' not in json.dumps(first)


@pytest.mark.parametrize('sink_failure', ['none', 'logger', 'evidence', 'both'])
def test_field_failure_connected_http_sinks_first_cause_and_privacy(
        sink_failure, tmp_path, monkeypatch, caplog, capsys):
    from oaf_website import notification_dispatch as diagnostics
    model, store, _, _ = accepted()
    app, client = app_client(model, store)
    evidence = tmp_path / 'instance' / 'failures.jsonl'
    monkeypatch.setattr(diagnostics, 'EVIDENCE_PATH', evidence)
    transaction = Mock(side_effect=AssertionError('Transaction must not run'))
    monkeypatch.setattr(store, '_transaction', transaction)
    private = 'PRIVATE-PROVIDER-VALUE-subscriber@example.invalid'
    if sink_failure in {'logger', 'both'}:
        monkeypatch.setattr(app.logger, 'warning', Mock(side_effect=OSError(private)))
    if sink_failure in {'evidence', 'both'}:
        monkeypatch.setattr(diagnostics, '_append_failure', Mock(side_effect=OSError(private)))
    data = event(model, event='delivered', link=private, sender_email=private,
                 source=private, uuid=private, reason=private, unsupported_field=private)
    # Hostile field names must not turn a name-only diagnostic into a value sink.
    unsafe_names = [BEARER, private, 'subscriber@example.invalid', 'unknown-private-key',
                    'name\nforged', 'UpperCase', 'x' * 65, 'a' * 32, '0123456789abcdef' * 4,
                    'synthetic_bearer_value_' + 'a' * 16]
    data.update({name: private for name in unsafe_names})
    before = deepcopy(model.records)
    response = send(client, data)
    assert response.status_code == 400
    assert response.json == {'status': 'error', 'message': 'Invalid event.'}
    transaction.assert_not_called()
    assert model.records == before
    if evidence.exists():
        lines = evidence.read_text(encoding='utf-8').splitlines()
        assert len(lines) == 1
        detail = json.loads(lines[0])
    else:
        output = capsys.readouterr().err
        detail = json.loads(output.split('Notification operation failed: ', 1)[1])
    first = validate_failure(detail['first_failure'])
    assert first['predicate'] == 'webhook_allowed_fields'  # precedes invalid event name
    assert first['stage'] == 'notifications' and first['context'] == 'webhook_event'
    assert first['side_effects'] == 'none' and detail['http_status'] == 400
    assert first['field_validation'] == dict(offending_field_names=['reason', 'unsupported_field'],
        offending_field_count=len(unsafe_names) + 2, redacted_name_count=len(unsafe_names), omitted_name_count=0)
    assert first['dependent_not_run'] == [
        'event_correlation', 'database_transaction', 'database_mutation', 'provider_submission']
    assert datetime.fromisoformat(first['timestamp_utc']).utcoffset() == timedelta(0)
    assert len(first['evidence_ref']) == 32
    if sink_failure in {'logger', 'both'}:
        assert detail['logging_failure']['exception_class'] == 'OSError'
    if sink_failure in {'evidence', 'both'}:
        assert detail['evidence_failure']['exception_class'] == 'OSError'
    visible = json.dumps(detail) + caplog.text + response.text
    for value in unsafe_names + [private, ACCEPTED.message_id, SECRET.decode(),
            'SYNTHETIC PRIVATE SUBJECT', 'synthetic-custom', 'private-preview', 'Bearer ']:
        assert value not in visible
    assert 'field_validation' not in response.text and 'evidence_ref' not in response.text
    log_records = [record for record in caplog.records
                   if record.getMessage().startswith('Notification operation failed: ')]
    if sink_failure in {'none', 'evidence'}:
        assert len(log_records) == 1
        logged = json.loads(log_records[0].getMessage().split(': ', 1)[1])
        assert logged['first_failure'] == first


def test_field_diagnostics_are_bounded_and_deterministic():
    names = {'field_' + chr(97 + i // 26) + chr(97 + i % 26) for i in range(40)}
    first = b._failure('webhook_event', 'webhook_allowed_fields', field_names=names).notification_failure
    assert validate_failure(first) is first
    assert first['field_validation'] == dict(offending_field_names=sorted(names)[:32],
        offending_field_count=40, redacted_name_count=0, omitted_name_count=8)
    # Rewrapping a later failure keeps the originating correlation and field rule.
    from oaf_website.notification_dispatch import safe_failure
    later = RuntimeError('PRIVATE-LATER-FAILURE')
    later.notification_failure = first
    assert safe_failure('processor', 'terminal_publication', later) is first


@pytest.mark.parametrize('change', [
    {'offending_field_names': ['name\nforged']},
    {'offending_field_names': ['subscriber@example.invalid']},
    {'offending_field_names': ['b', 'a']},
    {'offending_field_names': ['a', 'a']},
    {'offending_field_names': ['a'] * 33},
    {'offending_field_count': 0}, {'redacted_name_count': True}, {'omitted_name_count': -1},
    {'private_value': 'PRIVATE-VALUE'},
])
def test_untrusted_field_diagnostic_details_rejected(change):
    first = b._failure('webhook_event', 'webhook_allowed_fields', field_names={'reason'}).notification_failure
    first['field_validation'].update(change)
    with pytest.raises(ValueError):
        validate_failure(first)


@pytest.mark.parametrize('name,value', [
    ('expected', 'PRIVATE-EXPECTED'), ('observed', 'PRIVATE-OBSERVED'),
    ('context', 'webhook_correlation'), ('predicate', 'webhook_event_name'),
    ('side_effects', 'database_committed'), ('dependent_not_run', []),
    ('field_validation', None),
])
def test_field_diagnostic_rule_cannot_cross_other_boundaries(name, value):
    first = b._failure('webhook_event', 'webhook_allowed_fields', field_names={'reason'}).notification_failure
    first[name] = value
    with pytest.raises(ValueError):
        validate_failure(first)


@pytest.mark.parametrize('metadata', [
    {'link': 'https://example.invalid/SYNTHETIC-METADATA'},
    {'sender_email': 'SYNTHETIC-METADATA@example.invalid'},
    {'source': 'SYNTHETIC-METADATA'},
    {'uuid': '00000000-0000-0000-0000-000000000001'},
    dict(link='https://example.invalid/SYNTHETIC-METADATA', sender_email='other@example.invalid',
         source='development', uuid='Other@relay.example'),
    dict(link='', sender_email='', source='', uuid=''),
    dict(link={'email': 'other@example.invalid'}, sender_email=['other@example.invalid'],
         source=True, uuid=None),
])
def test_observed_optional_metadata_is_discarded_before_correlation(metadata):
    # Synthetic values only; actual observed evidence establishes names, not types.
    model, _, _, _ = accepted()
    data = event(model)
    assert b.event_payload(dict(data, **metadata)) == b.event_payload(data)
    assert set(b.event_payload(dict(data, **metadata))) == {
        'email', 'message_id', 'event_at', 'original_at'}


@pytest.mark.parametrize('kind', ['confirmation', 'release'])
def test_observed_metadata_cannot_change_withdrawal_identity_audit_or_idempotence(kind, caplog):
    model, store, digest, _ = accepted(kind)
    other_digest = subscribe(model, 2, email='other@example.invalid')
    _, client = app_client(model, store)
    data = event(model)
    before = deepcopy(model.records)
    assert send(client, data).status_code == 200
    expected = deepcopy(model.records)
    model.records = deepcopy(before)  # Restore only the existing synthetic model.
    metadata = dict(link='https://example.invalid/SYNTHETIC-METADATA/' + other_digest,
                    sender_email='other@example.invalid', source='development', uuid=other_digest)
    assert send(client, dict(data, **metadata)).status_code == 200
    assert model.records == expected
    original = next(r for r in model.rows(m.notifications) if r['unsubscribe_digest'] == digest)
    other = next(r for r in model.rows(m.notifications) if r['unsubscribe_digest'] == other_digest)
    assert original['unsubscribed_at'] == model.now and other['unsubscribed_at'] is None
    assert model.rows(m.changes)[0]['source'] == 'brevo'
    assert send(client, dict(data, link=None, sender_email={}, source=[], uuid=False)).status_code == 200
    assert model.records == expected
    assert 'SYNTHETIC-METADATA' not in repr(model.records) + caplog.text


@pytest.mark.parametrize('case', [
    'bearer', 'message', 'recipient', 'event', 'timestamp', 'ambiguous',
    'missing_message', 'missing_recipient', 'missing_event', 'missing_timestamp',
])
def test_observed_metadata_never_supplies_authority_or_missing_required_evidence(case, monkeypatch, caplog):
    model, store, _, _ = accepted()
    _, client = app_client(model, store)
    data = event(model, link='https://example.invalid/SYNTHETIC-METADATA',
                 sender_email='subscriber1@example.invalid', source='unsubscribed', uuid=ACCEPTED.message_id)
    headers = {'Authorization': 'Bearer ' + BEARER}
    if case == 'bearer': headers = {}
    if case == 'message': data['message-id'] = 'Other@relay.example'
    if case == 'recipient': data['email'] = 'other@example.invalid'
    if case == 'event': data['event'] = 'delivered'
    if case == 'timestamp': data['ts_event'] = True
    if case == 'ambiguous':
        model.rows(intents).append(dict(model.rows(intents)[0], intent='f' * 64))
        model.rows(confirmation_attempts).append(dict(model.rows(confirmation_attempts)[0], intent='f' * 64))
    missing = dict(missing_message='message-id', missing_recipient='email',
                   missing_event='event', missing_timestamp='ts_event')
    if case in missing: data.pop(missing[case])
    if case not in {'message', 'recipient', 'ambiguous'}:
        transaction = Mock(side_effect=AssertionError('Transaction must not run'))
        monkeypatch.setattr(store, '_transaction', transaction)
    before = deepcopy(model.records)
    assert send(client, data, headers=headers).status_code == (401 if case == 'bearer' else 429 if case == 'message' else 400)
    assert model.records == before
    if case not in {'message', 'recipient', 'ambiguous'}: transaction.assert_not_called()
    assert 'SYNTHETIC-METADATA' not in caplog.text


@pytest.mark.parametrize('case,status,predicate', [
    ('oversize', 413, None),
    ('duplicate', 400, 'webhook_json_unique_keys'),
    ('nonfinite', 400, 'webhook_json_finite_constants'),
])
def test_observed_metadata_retains_request_size_and_strict_json_checks(case, status, predicate, monkeypatch, caplog):
    model, store, _, _ = accepted()
    _, client = app_client(model, store)
    transaction = Mock(side_effect=AssertionError('Transaction must not run'))
    monkeypatch.setattr(store, '_transaction', transaction)
    raw = json.dumps(event(model))[:-1]
    if case == 'oversize': raw += ', "link": "' + 'x' * 17000 + '"}'
    if case == 'duplicate': raw += ', "uuid": "SYNTHETIC-METADATA", "uuid": "duplicate"}'
    if case == 'nonfinite': raw += ', "source": NaN}'
    before = deepcopy(model.records)
    result = client.post(b.WEBHOOK_PATH, base_url=ORIGIN, data=raw, content_type='application/json',
                         headers={'Authorization': 'Bearer ' + BEARER})
    assert result.status_code == status and model.records == before
    transaction.assert_not_called()
    if predicate is not None: diagnostic(caplog, predicate, 'webhook_json', status)
    assert 'SYNTHETIC-METADATA' not in caplog.text


@pytest.mark.parametrize('kind', ['confirmation', 'release'])
def test_transport_receipt_links_commit_and_idempotent_ack(kind, monkeypatch, tmp_path, caplog):
    from oaf_website import notification_dispatch as d
    model, store, subscription, token = accepted(kind)
    _, client = app_client(model, store)
    evidence = tmp_path / 'instance/failures.jsonl'
    monkeypatch.setattr(d, 'EVIDENCE_PATH', evidence)
    first = send(client, event(model))
    assert first.status_code == 200 and first.json == {'status': 'processed'}
    audit = deepcopy(model.rows(m.changes)[0])
    committed = deepcopy(model.records)
    second = send(client, event(model, id=999, **{'message-id': ACCEPTED.message_id[1:-1]}))
    assert second.status_code == 200 and second.json == first.json
    assert model.records == committed
    records = [json.loads(line) for line in evidence.read_text().splitlines()]
    assert len(records) == 2
    for record, outcome in zip(records, ['processed_withdrawal', 'idempotent_acknowledgement']):
        assert record['event_outcome'] == outcome
        assert record['webhook_receipt'] == dict(environment='testing', receipt_digest=audit['action_digest'])
        assert record['side_effects'] == 'database_committed'
        assert record['http_status'] == 200 and len(record['evidence_ref']) == 32
        assert datetime.fromisoformat(record['timestamp_utc']).utcoffset() == timedelta(0)
        assert 'first_failure' not in record
    assert records[0]['evidence_ref'] != records[1]['evidence_ref']
    visible = evidence.read_text() + caplog.text + first.text + second.text
    for value in [subscription, token, BEARER, SECRET.decode(), ACCEPTED.message_id[1:-1],
                  'subscriber1@example.invalid', 'SYNTHETIC PRIVATE SUBJECT', 'synthetic-custom',
                  'https://example.invalid/private-preview']:
        assert value not in visible
    assert 'receipt_digest' not in first.text


@pytest.mark.parametrize('phase', ['connect', 'execute', 'audit', 'commit', 'uncertain', 'ack_commit'])
def test_receipt_on_failure_never_claims_committed_processing(phase, monkeypatch, tmp_path, caplog):
    from oaf_website import notification_dispatch as d
    model, store, _, _ = accepted()
    _, client = app_client(model, store)
    if phase == 'ack_commit':
        assert send(client, event(model)).status_code == 200
    evidence = tmp_path / 'instance/failures.jsonl'
    monkeypatch.setattr(d, 'EVIDENCE_PATH', evidence)
    caplog.clear()
    before = deepcopy(model.records)
    if phase == 'audit':
        monkeypatch.setattr(store, '_change', Mock(side_effect=RuntimeError('PRIVATE-ERROR')))
    else:
        model.failure = 'commit' if phase == 'ack_commit' else phase
    result = send(client, event(model))
    assert result.status_code == 429
    record = json.loads(evidence.read_text())
    first = validate_failure(record['first_failure'])
    assert record['event_outcome'] == ('unavailable' if phase in {'connect', 'execute'} else 'accepted')
    if phase in {'connect', 'execute'}:
        assert 'webhook_receipt' not in record
    else:
        mailbox = store._digest('mailbox', event(model)['email'])
        expected = store._digest('brevo-unsubscribed', 'testing:' + ACCEPTED.message_id[1:-1] + ':' + mailbox)
        assert record['webhook_receipt']['receipt_digest'] == expected
    if phase in {'commit', 'uncertain', 'ack_commit'}:
        assert first['side_effects'] == 'database_commit_uncertain'
        assert first['dependent_not_run'] == ['automatic_retry']
    else:
        assert first['side_effects'] == ('none' if phase == 'connect' else 'database_rolled_back')
        if phase in {'connect', 'execute'}:
            not_run = ['event_correlation', 'database_mutation', 'provider_submission']
            if phase == 'connect': not_run.insert(1, 'database_transaction')
            assert first['dependent_not_run'] == not_run
    assert 'Notification operation completed' not in caplog.text
    assert 'PRIVATE-ERROR' not in evidence.read_text() + caplog.text
    assert model.records == before if phase != 'uncertain' else len(model.rows(m.changes)) == 1


@pytest.mark.parametrize('fault', ['logger', 'evidence', 'both'])
def test_committed_receipt_survives_reporting_failure(fault, monkeypatch, tmp_path, capsys):
    from oaf_website import notification_dispatch as d
    model, store, _, _ = accepted()
    app, client = app_client(model, store)
    evidence = tmp_path / 'instance/failures.jsonl'
    monkeypatch.setattr(d, 'EVIDENCE_PATH', evidence)
    if fault in {'logger', 'both'}:
        monkeypatch.setattr(app.logger, 'warning', Mock(side_effect=OSError('PRIVATE-LOGGER')))
    if fault in {'evidence', 'both'}:
        monkeypatch.setattr(d, '_append_failure', Mock(side_effect=OSError('PRIVATE-EVIDENCE')))
    response = send(client, event(model))
    assert response.status_code == 200 and response.json == {'status': 'processed'}
    output = capsys.readouterr().err
    record = json.loads(output.split('Notification operation completed: ', 1)[1])
    assert record['event_outcome'] == 'processed_withdrawal'
    assert record['side_effects'] == 'database_committed'
    assert record['webhook_receipt']['receipt_digest'] == model.rows(m.changes)[0]['action_digest']
    if fault in {'logger', 'both'}: assert record['logging_failure']['exception_class'] == 'OSError'
    if fault in {'evidence', 'both'}: assert record['evidence_failure']['exception_class'] == 'OSError'
    assert 'PRIVATE-' not in output


def test_rejection_then_commit_and_logging_failure_keeps_first_and_not_run(monkeypatch, tmp_path, capsys):
    from oaf_website import notification_dispatch as d
    model, store, _, _ = accepted()
    app, client = app_client(model, store)
    evidence = tmp_path / 'instance/failures.jsonl'
    monkeypatch.setattr(d, 'EVIDENCE_PATH', evidence)
    monkeypatch.setattr(app.logger, 'warning', Mock(side_effect=OSError('PRIVATE-SECONDARY')))
    model.failure = 'commit'
    assert send(client, event(model, ts_event=int(model.now.timestamp()) + 301)).status_code == 429
    record = json.loads(evidence.read_text())
    first = validate_failure(record['first_failure'])
    assert first['predicate'] == 'webhook_event_not_future'
    assert first['dependent_not_run'] == ['automatic_retry']
    assert record['transaction_failure']['operation'] == 'transaction_commit'
    assert record['logging_failure']['operation'] == 'terminal_publication'
    assert 'webhook_receipt' not in record and record['event_outcome'] == 'rejected'
    fallback = json.loads(capsys.readouterr().err.split('Notification operation failed: ', 1)[1])
    assert fallback['first_failure']['evidence_ref'] == first['evidence_ref']


@pytest.mark.parametrize('value', [None, {}, {'environment': 'testing', 'receipt_digest': 'private'},
    {'environment': 'production', 'receipt_digest': 'a' * 64},
    {'environment': 'testing', 'receipt_digest': 'a' * 64, 'email': 'private'}])
def test_receipt_diagnostic_rejects_unbounded_values(value):
    from oaf_website import notification_dispatch as d
    with pytest.raises(ValueError): d._webhook_receipt(value)


def test_matched_receipt_retains_first_failure_through_rollback_and_logger_errors(monkeypatch, tmp_path):
    from oaf_website import notification_dispatch as d
    model, store, _, _ = accepted()
    app, client = app_client(model, store)
    evidence = tmp_path / 'instance/failures.jsonl'
    monkeypatch.setattr(d, 'EVIDENCE_PATH', evidence)
    primary = RuntimeError('PRIVATE-AUDIT')
    primary.notification_failure = d.safe_failure('notifications', 'audit_insert', primary)
    @contextmanager
    def fail_rollback():
        with model.begin() as connection:
            try: yield connection
            except RuntimeError: raise OSError('PRIVATE-ROLLBACK') from None
    store.engine = Mock(begin=fail_rollback)
    monkeypatch.setattr(store, '_change', Mock(side_effect=primary))
    monkeypatch.setattr(app.logger, 'warning', Mock(side_effect=OSError('PRIVATE-LOGGER')))
    assert send(client, event(model)).status_code == 429
    record = json.loads(evidence.read_text())
    assert record['first_failure']['evidence_ref'] == primary.notification_failure['evidence_ref']
    assert record['first_failure']['operation'] == 'audit_insert'
    assert record['first_failure']['side_effects'] == 'database_rollback_uncertain'
    assert record['first_failure']['dependent_not_run'] == ['automatic_retry']
    assert record['rollback_failure']['operation'] == 'transaction_rollback'
    assert record['logging_failure']['operation'] == 'terminal_publication'
    assert record['event_outcome'] == 'accepted' and len(record['webhook_receipt']['receipt_digest']) == 64
    assert not model.rows(m.changes) and not model.rows(suppressions)
    assert 'PRIVATE-' not in evidence.read_text()
