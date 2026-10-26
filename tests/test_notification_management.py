"""V2 source behavior using guarded SQL transactions and fake provider only."""
import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.sql.dml import Insert

from oaf_website import notification_management as m, state_requests as runtime
from oaf_website import confirmation_outbox as outbox
from oaf_website import notification_messages as messages
from oaf_website.notifications import SubscriptionStore, UnsubscribeCapabilities
from oaf_website.notification_delivery import NotificationDeliveryStore
from oaf_website.notification_delivery_schema import verification, suppressions, deliveries, attempts
from oaf_website.confirmation_outbox_schema import confirmation_attempts
from oaf_website.notification_dispatch import ReleaseDispatcher
from test_notification_delivery import Model, SECRET, NOW, subscribe, payload, EVENT
from test_notifications import post
from test_state_requests import ORIGIN
from test_brevo import CONFIG, PAGE, response
from test_testing_https import factory

PREFERENCES = dict(web_launch=True, android_launch=True, ios_launch=True, state="CA", consent=True)
ACTION = "a" * 64


@pytest.mark.parametrize('context', ['invalid', 1])
def test_capability_issue_rejects_invalid_explicit_context(context):
    with pytest.raises(ValueError):
        m.ManagementCapabilities(SECRET, 'testing').issue('a'*64, 0, NOW, context=context)


def test_session_rejects_invalid_browser_and_diverged_revision():
    model, store, _, token = managed()
    with pytest.raises(m.ManagementUnavailable) as caught:
        store.sessions._browser('invalid')
    assert caught.value.notification_failure['predicate']=='browser_format'
    state = store.sessions.issue(token, 'b'*64, model.now)
    cookie = store.sessions.cookie(state, model.now)['value']
    model.rows(m.notifications)[0]['preferences_revision']=2
    with pytest.raises(m.ManagementUnavailable) as caught:
        store.save_session(cookie, 'b'*64, ACTION, 0)
    assert caught.value.notification_failure['predicate']=='management_session_revision'


@pytest.mark.parametrize('revision',[True,2])
def test_session_save_rejects_revision_outside_current_or_preceding_authority(revision):
    model,store,_,token=managed()
    state=store.sessions.issue(token,'b'*64,model.now)
    cookie=store.sessions.cookie(state,model.now)['value']
    before=deepcopy(model.records)
    with pytest.raises(m.ManagementConflict) as caught:
        store.save_session(cookie,'b'*64,ACTION,revision)
    assert caught.value.notification_failure['predicate']=='management_revision_conflict'
    assert model.records==before


def test_save_rejects_revision_different_from_capability():
    _, store, _, token = managed()
    with pytest.raises(m.ManagementConflict) as caught:
        store.save(token, ACTION, 1)
    assert caught.value.notification_failure['predicate']=='management_revision_required'


def test_update_failure_rolls_back_audit_and_preserves_origin(monkeypatch):
    model, store, _, token = managed()
    before = deepcopy(model.records)
    monkeypatch.setattr(store, '_update', Mock(side_effect=RuntimeError('synthetic private SQL')))
    with pytest.raises(RuntimeError) as caught:
        store.save(token, ACTION, 0)
    assert caught.value.notification_failure['operation']=='subscription_update'
    assert model.records==before


def test_recovery_global_budget_denial_does_not_select_subscriber(monkeypatch):
    model, store, _, _ = managed()
    before = deepcopy(model.records)
    select = Mock(side_effect=AssertionError('must not query subscriber after budget denial'))
    monkeypatch.setattr(store, '_get', select)
    monkeypatch.setattr(store, '_budget', lambda *a: False)
    assert store.request_recovery('subscriber1@example.invalid') is None
    select.assert_not_called()
    assert model.records==before


@pytest.mark.parametrize('error,status', [(m.ManagementUnavailable(), 400),
    (m.ManagementInputError('Choose valid notification preferences.'), 400), (RuntimeError('private'), 503)])
def test_management_save_handler_classifies_store_failures(monkeypatch, error, status):
    model, store, _, token = managed()
    _, client, csrf = browser(model, store)
    monkeypatch.setattr(store, 'save', Mock(side_effect=error))
    reply=post(client, csrf, dict(token=token, action=ACTION, revision=0), '/api/notifications/manage/save')
    assert reply.status_code==status
    assert token not in reply.get_data(as_text=True)


@pytest.mark.parametrize('endpoint,body', [
    ('save', {}),
    ('save', dict(action=ACTION, revision=0, preferences=[])),
    ('recovery', []), ('recovery', dict(email='invalid')),
    ('withdrawal-receipt', dict(action=ACTION, revision=0, preferences=[])),
    ('withdrawal-ack', dict(action=ACTION, revision=0, receipt='invalid', preferences=[])),
])
def test_management_payload_rejections_preserve_database(endpoint, body):
    model, store, _, _ = managed()
    _, client, csrf = browser(model, store)
    before=deepcopy(model.records)
    assert post(client, csrf, body, '/api/notifications/manage/'+endpoint).status_code==400
    assert model.records==before


@pytest.mark.parametrize('endpoint,method,body', [
    ('recovery', 'request_recovery', dict(email='subscriber1@example.invalid')),
    ('withdrawal-receipt', 'prepare_withdrawal', dict(action=ACTION, revision=0, token='synthetic')),
    ('withdrawal-ack', 'acknowledge_withdrawal', dict(action=ACTION, revision=0, receipt='synthetic')),
])
def test_management_recovery_and_receipt_internal_failures_are_private(monkeypatch, endpoint, method, body):
    model, store, _, _ = managed()
    _, client, csrf = browser(model, store)
    monkeypatch.setattr(store, method, Mock(side_effect=RuntimeError('synthetic private failure')))
    reply=post(client, csrf, body, '/api/notifications/manage/'+endpoint)
    assert reply.status_code==503
    assert 'synthetic private' not in reply.get_data(as_text=True)


@pytest.mark.parametrize('endpoint', ['save', 'recovery', 'withdrawal-receipt', 'withdrawal-ack'])
def test_management_disabled_endpoints_fail_without_mutation(endpoint):
    app=runtime._build_app(None, runtime.BrowserRecognition(SECRET), ORIGIN,
        subscription_store=SubscriptionStore(Model()))
    client=app.test_client()
    csrf=client.get('/api/notifications/session',base_url=ORIGIN).json['csrf_token']
    assert post(client,csrf,{},'/api/notifications/manage/'+endpoint).status_code==503


@pytest.mark.parametrize('endpoint', ['recovery', 'withdrawal-receipt'])
def test_management_malformed_json_returns_payload_failure(endpoint):
    model,store,_,_=managed()
    _,client,csrf=browser(model,store)
    reply=client.post('/api/notifications/manage/'+endpoint,base_url=ORIGIN,data='{',content_type='application/json',
        headers={'Origin':ORIGIN,'X-CSRF-Token':csrf})
    assert reply.status_code==400


@pytest.mark.parametrize('action,revision', [('invalid',0),(ACTION,-1)])
def test_management_action_requires_valid_identity_and_revision(action,revision):
    with pytest.raises(m.ManagementInputError):
        m.action_payload(action,revision,None)


def test_withdrawal_receipt_requires_current_revision():
    _,store,_,token=managed()
    with pytest.raises(m.ManagementUnavailable) as caught:
        store.prepare_withdrawal(None,'b'*64,ACTION,1,token=token)
    assert caught.value.notification_failure['predicate']=='withdrawal_revision'


def test_prior_management_revision_requires_its_audit():
    model,store,_,token=managed()
    model.rows(m.notifications)[0]['preferences_revision']=1
    token=store.capabilities.continuation(token,1)
    before=deepcopy(model.records)
    with pytest.raises(m.ManagementUnavailable) as caught:
        store.save(token,ACTION,1)
    assert caught.value.notification_failure['predicate']=='management_prior_audit_present'
    assert model.records==before


def diagnostic_view_case(case):
    """Synthetic authority only; never reads the installed subscriber database."""
    model, store, digest, token = managed(verified=case == "verified" or case.startswith("session_"))
    if case == "signature":
        token = token[:-1] + ("0" if token[-1] != "0" else "1")
    elif case == "expired":
        model.elapse(days=30)
    elif case == "lifecycle":
        token = store.capabilities.issue("f" * 64, 0, model.now)
    elif case == "revision":
        token = store.capabilities.issue(digest, 1, model.now)
    elif case == "future":
        token = store.capabilities.issue(digest, 0, model.now + timedelta(seconds=10))
    elif case == "predates":
        token = store.capabilities.issue(digest, 0, model.now - timedelta(seconds=2))
    elif case == "withdrawn":
        model.rows(m.notifications)[0]["unsubscribed_at"] = model.now
    elif case == "environment":
        token = m.ManagementCapabilities(SECRET, "development").issue(digest, 0, model.now)
    elif case in {"range", "lifetime"}:
        parts = token.split(".")
        if case == "range": parts[3] = "2147483647"
        else: parts[5] = str(int(parts[4]) + 30 * 86400 + 1)
        body = ".".join(parts[:-1])
        token = body + "." + store.capabilities._sign(body)
    elif case == "format":
        token = "synthetic-private-canary"
    return model, store, token


@pytest.mark.parametrize("case,predicate", [
    ("unverified", None), ("verified", None),
    ("signature", "capability_signature"), ("expired", "capability_expired"),
    ("lifecycle", "lifecycle_missing"), ("revision", "lifecycle_revision"),
    ("future", "capability_not_yet_valid"), ("predates", "capability_predates_lifecycle"),
    ("withdrawn", "lifecycle_withdrawn"), ("environment", "capability_environment"),
    ("range", "capability_revision_range"), ("lifetime", "capability_lifetime"),
    ("format", "capability_format"), ("missing", "management_cookie_missing"),
    ("shape", "management_request_shape"),
])
def test_management_rejection_diagnostics_contract(case, predicate, caplog):
    from datetime import datetime
    from oaf_website.notification_dispatch import validate_failure
    model, store, token = diagnostic_view_case(case)
    app, client, csrf = browser(model, store)
    before = deepcopy(model.records)
    body = {} if case == "missing" else {"token": token, "unexpected": "synthetic-private-canary"} if case == "shape" else {"token": token}
    caplog.clear()
    reply = post(client, csrf, body, "/api/notifications/manage")
    assert model.records == before
    assert reply.headers["Cache-Control"] == "no-store"
    assert reply.headers["Referrer-Policy"] == "no-referrer"
    if predicate is None:
        assert reply.status_code == 200 and not caplog.records
        if case == "unverified":
            assert reply.json["status"] == "withdrawal_only" and reply.json["revision"] == 0
            assert "preferences" not in reply.json and "token" not in reply.json
            assert client.get_cookie(SESSION_COOKIE, domain="website.example") is None
        else:
            assert reply.json["status"] == "preferences"
            assert client.get_cookie(SESSION_COOKIE, domain="website.example") is not None
        return
    assert reply.status_code == 400 and reply.json == dict(status="error", message=m.UNAVAILABLE)
    assert len(caplog.records) == 1 and caplog.records[0].exc_info is None
    detail = json.loads(caplog.records[0].getMessage().split(": ", 1)[1])
    assert set(detail) == {"operation", "http_status", "first_failure"}
    assert detail["operation"] == "management_view" and detail["http_status"] == 400
    failure = validate_failure(detail["first_failure"])
    assert failure["predicate"] == predicate and failure["exception_class"] == "ManagementUnavailable"
    assert failure["side_effects"] == ("none" if case in {"shape", "missing"} else "database_rolled_back")
    assert datetime.fromisoformat(failure["timestamp_utc"]).utcoffset() == timedelta(0)
    assert all(failure[key] is None for key in ("sqlstate", "hresult", "exit_code"))
    combined = caplog.text + reply.get_data(as_text=True)
    for private in (token, csrf, SECRET.decode(), "subscriber1@example.invalid", "synthetic-private-canary", ORIGIN):
        assert private not in combined
    assert predicate not in reply.get_data(as_text=True)


@pytest.mark.parametrize("case,predicate", [
    ("signature", "session_cookie_signature"), ("shape", "session_shape"),
    ("browser", "session_browser"), ("future", "session_not_yet_valid"),
    ("expired", "session_expired"), ("lifetime", "session_lifetime"),
    ("authority_expiry", "session_capability_expiry"),
    ("authority_issue", "session_capability_issue"),
    ("unverified", "consent_unverified"), ("valid", None),
])
def test_management_rejection_diagnostics_session(case, predicate, caplog):
    model, store, digest, token = managed()
    app, client, csrf = browser(model, store)
    assert post(client, csrf, {"token": token}, "/api/notifications/manage").status_code == 200
    cookie = client.get_cookie(SESSION_COOKIE, domain="website.example").value
    state = store.sessions.serializer.loads(cookie)
    if case == "shape": state["extra"] = "synthetic-private-canary"
    elif case == "browser": state["browser"] = "f" * 64
    elif case == "future": state["started"] += 1
    elif case == "expired": model.elapse(minutes=30)
    elif case == "lifetime": state["expires"] += 1
    elif case == "authority_expiry":
        state["token"] = store.capabilities.issue(digest, 0, model.now, lifetime=timedelta(minutes=1))
    elif case == "authority_issue":
        state["started"] -= 1
        state["expires"] -= 1
    elif case == "unverified": model.rows(verification)[0]["verified_at"] = None
    cookie = store.sessions.serializer.dumps(state)
    if case == "signature": cookie = "synthetic-private-canary"
    client.set_cookie(SESSION_COOKIE, cookie, domain="website.example", secure=True)
    before = deepcopy(model.records)
    caplog.clear()
    reply = post(client, csrf, {}, "/api/notifications/manage")
    assert model.records == before
    if predicate is None:
        assert reply.status_code == 200 and not caplog.records
        return
    assert reply.status_code == 400 and reply.json == dict(status="error", message=m.UNAVAILABLE)
    assert len(caplog.records) == 1
    detail = json.loads(caplog.records[0].getMessage().split(": ", 1)[1])
    assert detail["first_failure"]["predicate"] == predicate
    assert detail["first_failure"]["side_effects"] == "database_rolled_back"
    assert cookie not in caplog.text and token not in caplog.text


def test_management_rejection_diagnostics_first_failure_and_rollback(caplog):
    model, store, token = diagnostic_view_case("signature")
    app, client, csrf = browser(model, store)
    model.elapse(days=31)  # Signature is still the first failing predicate.
    started = model.begin
    @contextmanager
    def failing_rollback():
        try:
            with started() as connection:
                yield connection
        except m.ManagementUnavailable:
            raise RuntimeError("synthetic-private-canary") from None
    model.begin = failing_rollback
    caplog.clear()
    reply = post(client, csrf, {"token": token}, "/api/notifications/manage")
    assert reply.status_code == 503
    detail = json.loads(caplog.records[0].getMessage().split(": ", 1)[1])
    assert detail["http_status"] == 503
    assert detail["first_failure"]["predicate"] == "capability_signature"
    assert detail["first_failure"]["side_effects"] == "database_rollback_uncertain"
    assert detail["rollback_failure"]["exception_class"] == "RuntimeError"
    assert "synthetic-private-canary" not in caplog.text
    assert token not in caplog.text


def test_management_rejection_diagnostics_csrf_still_precedes_authority(caplog):
    model, store, token = diagnostic_view_case("signature")
    app, client, csrf = browser(model, store)
    before = deepcopy(model.records)
    caplog.clear()
    reply = post(client, "0" * 64, {"token": token}, "/api/notifications/manage")
    assert reply.status_code == 403 and len(caplog.records) == 1
    detail = json.loads(caplog.records[0].getMessage().split(": ", 1)[1])
    assert detail["first_failure"]["predicate"] == "csrf_signature"
    assert detail["first_failure"]["side_effects"] == "none"
    assert detail["first_failure"]["dependent_not_run"] == ["database_mutation", "provider_submission"]
    assert token not in caplog.text and csrf not in caplog.text
    assert model.records == before


def managed(*, verified=True, environment="testing"):
    model = Model()
    store = m.NotificationManagementStore(model, SECRET, environment)
    digest = subscribe(model)
    confirmation = store.request_confirmation("subscriber1@example.invalid")
    if verified:
        assert store.confirm(confirmation) == "verified"
    token = store.capabilities.issue(digest, 0, model.now)
    return model, store, digest, token


def browser(model, store, *, static=False):
    subscriptions = SubscriptionStore(model, management_store=store)
    app = runtime._build_app(None, runtime.BrowserRecognition(SECRET), ORIGIN,
                             subscription_store=subscriptions, environment=store.environment)
    if static:
        from oaf_website.local_testing import public_files
        public_files(app)
    client = app.test_client()
    csrf = client.get('/api/notifications/session', base_url=ORIGIN).json['csrf_token']
    return app, client, csrf


def test_authorized_read_save_continuation_and_consent_history():
    model, store, digest, token = managed()
    original = deepcopy(model.rows(verification))
    consent_at = model.rows(m.notifications)[0]['created_at']
    assert store.preferences(token)['preferences'] == dict(web_launch=True, android_launch=True, ios_launch=True, state=None)
    model.elapse(seconds=30)
    result = store.save(token, ACTION, 0, PREFERENCES)
    assert result['status'] == 'saved' and result['revision'] == 1
    assert store.preferences(result['token'])['preferences']['state'] == 'CA'
    assert store.capabilities.read(result['token'], model.now)['expires'] == store.capabilities.read(token, model.now)['expires']
    with pytest.raises(m.ManagementUnavailable): store.preferences(token)
    row, audit = model.rows(m.notifications)[0], model.rows(m.changes)[0]
    assert row['created_at'] == consent_at and row['consent_version'] == 'gramanna-announcements-v1'
    assert audit['before_state'] is None and audit['after_state'] == 'CA'
    assert audit['state_granted_at'] == model.now and audit['android_launch_granted_at'] == consent_at
    assert audit['consent_version'] == m.CONSENT_VERSION
    assert model.rows(verification) == original
    assert token not in repr(model.records) and result['token'] not in repr(model.records)


@pytest.mark.parametrize('name,value', [('web_launch',False),('android_launch',False),('ios_launch',False),('state','TX'),('state',None)])
def test_each_supported_preference_can_change(name,value):
    model, store, digest, token = managed()
    result = store.save(token,ACTION,0,dict(PREFERENCES,**{name:value}))
    assert store.preferences(result['token'])['preferences'][name] == value


@pytest.mark.parametrize('unselect', [False,True])
def test_full_withdrawal_keeps_prior_preferences_and_verification(unselect):
    model,store,digest,token = managed()
    original = deepcopy(model.rows(m.notifications)[0])
    verified = deepcopy(model.rows(verification))
    selections = dict(web_launch=False,android_launch=False,ios_launch=False,state=None,consent=False) if unselect else None
    assert store.save(token,ACTION,0,selections)['status']=='unsubscribed'
    snapshot=deepcopy(model.records)
    assert store.save(token,ACTION,0,selections)['status']=='unsubscribed'
    assert model.records==snapshot
    assert all(model.rows(m.notifications)[0][n]==original[n] for n in m.PREFERENCE_COLUMNS)
    assert model.rows(verification)==verified
    with pytest.raises(m.ManagementUnavailable): store.preferences(token)
    with pytest.raises(m.ManagementConflict): store.save(token,'b'*64,0,PREFERENCES)
    new_digest=subscribe(model,2,email='subscriber1@example.invalid')
    assert new_digest!=digest
    store.unsubscribe_legacy(digest)
    assert model.rows(m.notifications)[1]['unsubscribed_at'] is None


@pytest.mark.parametrize('bad', [None,'','bad','f'*64,[],{},123,'m2.testing.bad','a'*64+'.'+'b'*64])
def test_non_management_authorities_cannot_read_or_edit(bad):
    model,store,_,_=managed()
    snapshot=deepcopy(model.records)
    with pytest.raises(m.ManagementUnavailable): store.preferences(bad)
    with pytest.raises(m.ManagementUnavailable): store.save(bad,ACTION,0,PREFERENCES)
    assert model.records==snapshot


@pytest.mark.parametrize('case',['signature','environment','lifecycle','revision','expiry','future','wrong_key','overlong'])
def test_capability_binding_and_rejection(case):
    model,store,digest,token=managed()
    if case=='signature': token=token[:-1]+('0' if token[-1]!='0' else '1')
    if case=='environment': token=m.ManagementCapabilities(SECRET,'development').issue(digest,0,model.now)
    if case=='lifecycle': token=store.capabilities.issue('f'*64,0,model.now)
    if case=='revision': token=store.capabilities.issue(digest,1,model.now)
    if case=='expiry': model.elapse(days=30)
    if case=='future': token=store.capabilities.issue(digest,0,model.now+timedelta(seconds=1))
    if case=='wrong_key': token=m.ManagementCapabilities(b'x'*32,'testing').issue(digest,0,model.now)
    if case=='overlong': token+='x'*1000
    snapshot=deepcopy(model.records)
    with pytest.raises(m.ManagementUnavailable): store.preferences(token)
    assert model.records==snapshot


def test_unverified_capability_can_only_withdraw_until_explicit_confirmation():
    model,store,digest,token=managed(verified=False)
    with pytest.raises(m.ManagementUnavailable): store.preferences(token)
    with pytest.raises(m.ManagementUnavailable): store.save(token,ACTION,0,PREFERENCES)
    assert not model.rows(m.changes)
    assert store.save(token,ACTION,0)['status']=='unsubscribed'
    assert model.rows(verification)[0]['verified_at'] is None


@pytest.mark.parametrize('change', [dict(web_launch=1),dict(android_launch=None),dict(ios_launch='true'),
    dict(state='XX'),dict(state=[]),dict(consent=False),dict(consent=1),dict(extra=True)])
def test_strict_preferences_and_explicit_consent(change):
    model,store,_,token=managed()
    before=deepcopy(model.records)
    with pytest.raises(ValueError): store.save(token,ACTION,0,dict(PREFERENCES,**change))
    assert model.records==before


def test_replays_conflicts_and_eight_concurrent_edits():
    model,store,_,token=managed()
    with ThreadPoolExecutor(max_workers=8) as pool:
        same=list(pool.map(lambda _:store.save(token,ACTION,0,PREFERENCES),range(8)))
    assert all(r==same[0] for r in same) and len(model.rows(m.changes))==1
    with pytest.raises(m.ManagementConflict): store.save(token,ACTION,0,dict(PREFERENCES,state='TX'))
    token=same[0]['token']
    def save(number):
        try: return store.save(token,f'{number:064x}',1,dict(PREFERENCES,state='TX'))['status']
        except m.ManagementConflict: return 'conflict'
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes=list(pool.map(save,range(8)))
    assert outcomes.count('saved')==1 and outcomes.count('conflict')==7
    assert len(model.rows(m.changes))==2


@pytest.mark.parametrize('failure',['connect','execute','commit','uncertain'])
def test_database_failure_and_identical_retry_converge(failure):
    model,store,_,token=managed()
    before=deepcopy(model.records); model.failure=failure
    with pytest.raises(RuntimeError): store.save(token,ACTION,0,PREFERENCES)
    if failure!='uncertain': assert model.records==before
    model.failure=None
    assert store.save(token,ACTION,0,PREFERENCES)['status']=='saved'
    assert len(model.rows(m.changes))==1


def test_audit_insert_failure_rolls_back_preferences(monkeypatch):
    model,store,_,token=managed()
    begin=model.begin
    @contextmanager
    def fail():
        with begin() as connection:
            execute=connection.execute
            def run(statement):
                if isinstance(statement,Insert) and statement.table.name==m.changes.name: raise RuntimeError('synthetic')
                return execute(statement)
            connection.execute=run
            yield connection
    monkeypatch.setattr(model,'begin',fail)
    before=deepcopy(model.records)
    with pytest.raises(RuntimeError): store.save(token,ACTION,0,PREFERENCES)
    assert model.records==before


def test_legacy_is_withdrawal_only_and_unknown_valid_receipt_is_generic():
    model,store,digest,token=managed()
    app,client,csrf=browser(model,store)
    legacy=UnsubscribeCapabilities(SECRET).issue(digest)
    assert post(client,csrf,{'token':legacy},'/api/notifications/manage').status_code==400
    for receipt in (legacy,UnsubscribeCapabilities(SECRET).issue('f'*64),legacy):
        assert post(client,csrf,{'token':receipt},'/api/notifications/unsubscribe').status_code==200
    assert len(model.rows(m.changes))==1 and model.rows(m.changes)[0]['source']=='legacy'
    assert post(client,csrf,{'email':'subscriber1@example.invalid'},'/api/notifications/manage').status_code==400


@pytest.mark.parametrize('path', ['/api/notifications/manage','/api/notifications/manage/save','/api/notifications/manage/recovery',
    '/api/notifications/manage/withdrawal-receipt','/api/notifications/manage/withdrawal-ack'])
def test_browser_post_requires_origin_csrf_and_strict_json(path):
    model,store,_,token=managed(); app,client,csrf=browser(model,store)
    before=deepcopy(model.records)
    for headers in ({},{'Origin':'https://evil.invalid','X-CSRF-Token':csrf},{'Origin':ORIGIN,'X-CSRF-Token':'f'*64}):
        assert post(client,csrf,{'token':token},path,headers=headers).status_code==403
    assert client.post(path,base_url=ORIGIN,data='{"email":"a@b.co","email":"b@b.co"}',content_type='application/json',
                       headers={'Origin':ORIGIN,'X-CSRF-Token':csrf}).status_code==400
    assert model.records==before


def test_public_no_lookup_disclosure_and_no_get_mutations_or_sends(monkeypatch):
    model,store,_,token=managed(); app,client,csrf=browser(model,store,static=True)
    sender=Mock(side_effect=AssertionError('No send from browser'))
    monkeypatch.setattr(outbox.BrevoAdapter,'submit',sender)
    before=deepcopy(model.records)
    for path in ('/manage-notifications.html','/assets/notification-management.js','/gramanna.html',
                 '/api/notifications/manage','/api/notifications/manage/save','/api/notifications/manage/recovery'):
        client.get(path,base_url=ORIGIN); client.head(path,base_url=ORIGIN)
    assert model.records==before
    assert post(client,csrf,{'email':'subscriber1@example.invalid'},'/api/notifications/manage').status_code==400
    sender.assert_not_called()


@pytest.mark.parametrize('case',['known','unknown','withdrawn','suppressed','throttled'])
def test_recovery_privacy_quota_and_no_revocation(case):
    model,store,digest,token=managed(); app,client,csrf=browser(model,store)
    original=deepcopy(model.rows(verification)); model.elapse(seconds=60)
    email='subscriber1@example.invalid'
    if case=='unknown': email='unknown@example.invalid'
    if case=='withdrawn': store.unsubscribe_legacy(digest)
    if case=='suppressed': store.suppress(email,'provider_block')
    if case=='throttled': model.now-=timedelta(seconds=60)
    reply=post(client,csrf,{'email':email},'/api/notifications/manage/recovery')
    assert reply.status_code==200 and reply.json==dict(status='received',message=m.RECOVERY_RECEIVED)
    assert model.rows(verification)==original
    recovery=[r for r in model.rows(m.intents) if r['purpose']=='management']
    assert len(recovery)==(1 if case=='known' else 0)
    if case in {'known','unknown','suppressed','throttled'}: assert store.preferences(token)['revision']==0


def test_recovery_reuses_processor_and_never_confirms_or_bypasses_suppression():
    model,store,digest,token=managed(); model.elapse(seconds=60)
    original=deepcopy(model.rows(verification)); store.request_recovery('subscriber1@example.invalid')
    processor=outbox.ConfirmationOutboxStore(model,SECRET,'testing',management_enabled=True)
    transport=Mock(return_value=response())
    assert outbox.ConfirmationDispatcher(processor,CONFIG,PAGE,transport=transport).process().processed==1
    body=json.loads(transport.call_args.args[1]); assert 'Manage Preferences' in body['textContent']
    assert body['htmlContent'].count('<a href=')==1
    recovery_token=body['textContent'].split('#manage=')[1].split()[0]
    assert store.preferences(recovery_token)['revision']==0
    assert processor.confirm(recovery_token)=='unavailable' and model.rows(verification)==original
    assert recovery_token not in repr(model.records)
    model.elapse(seconds=60); store.request_recovery('subscriber1@example.invalid')
    store.suppress('subscriber1@example.invalid','provider_block')
    assert outbox.ConfirmationDispatcher(processor,CONFIG,PAGE,transport=transport).process().processed==0
    assert transport.call_count==1


@pytest.mark.parametrize('reason',['expiry','revision','withdrawn','wrong_key'])
def test_management_intent_final_eligibility(reason):
    model,store,digest,token=managed(); model.elapse(seconds=60); store.request_recovery('subscriber1@example.invalid')
    processor=outbox.ConfirmationOutboxStore(model,SECRET,'testing',management_enabled=True)
    intent=next(r['intent'] for r in model.rows(m.intents) if r['purpose']=='management')
    claim=processor.claim_confirmation(intent); assert claim
    if reason=='expiry': model.elapse(hours=24)
    if reason=='revision': store.save(token,ACTION,0,PREFERENCES)
    if reason=='withdrawn': store.unsubscribe_legacy(digest)
    if reason=='wrong_key': processor.secret=b'x'*32
    if reason=='wrong_key':
        with processor._transaction() as (connection,now):
            with pytest.raises(ValueError): processor._eligible_confirmation(connection,model.rows(m.intents)[-1],now)
    else:
        assert processor.prepare_confirmation(intent,claim,PAGE) is None


def test_unverified_recovery_uses_existing_confirmation_purpose_and_footer():
    model,store,digest,token=managed(verified=False); model.elapse(seconds=60)
    store.request_recovery('subscriber1@example.invalid')
    assert all(r['purpose']=='confirmation' for r in model.rows(m.intents))
    processor=outbox.ConfirmationOutboxStore(model,SECRET,'testing',management_enabled=True)
    send=Mock(return_value=response())
    assert outbox.ConfirmationDispatcher(processor,CONFIG,PAGE,transport=send).process().processed==1
    body=json.loads(send.call_args.args[1]); assert '/confirm-email.html#confirm-email=' in body['textContent']
    assert '/manage-notifications.html#manage=' in body['textContent']
    assert 'Manage Preferences' in body['htmlContent']
    assert model.rows(verification)[0]['verified_at'] is None


@pytest.mark.parametrize('zone', ['UTC', 'America/Los_Angeles'])
@pytest.mark.parametrize('month,day', [(10, 23), (2, 20)])
@pytest.mark.parametrize('microsecond', [0, 123456, 999999])
def test_confirmation_footer_elapsed_lifetime_and_unverified_withdrawal(zone, month, day, microsecond):
    model = Model()
    model.now = datetime(2026, month, day, 12, 0, 0, microsecond, tzinfo=ZoneInfo(zone))
    store = m.NotificationManagementStore(model, SECRET, 'testing')
    subscribe(model)
    confirmation = store.request_confirmation('subscriber1@example.invalid')
    processor = outbox.ConfirmationOutboxStore(model, SECRET, 'testing', management_enabled=True)
    intent = model.rows(m.intents)[0]['intent']
    claim = processor.claim_confirmation(intent)
    _, message = processor.prepare_confirmation(intent, claim, PAGE)
    token = message.text.split('#manage=')[1].split()[0]
    assert '#confirm-email=' + confirmation in message.text
    assert '#manage=' + token in message.html
    authority = store.capabilities.read(token, model.now)
    issued_utc = model.now.astimezone(timezone.utc)
    assert authority['issued'] == int(issued_utc.timestamp())
    assert authority['expires'] == int((issued_utc + timedelta(days=30)).timestamp())
    assert authority['expires'] - authority['issued'] == 30 * 86400
    deadline = datetime.fromtimestamp(authority['expires'], timezone.utc)
    store.capabilities.read(token, deadline - timedelta(microseconds=1))
    for elapsed in (timedelta(0), timedelta(seconds=1)):
        with pytest.raises(m.ManagementUnavailable) as rejected:
            store.capabilities.read(token, deadline + elapsed)
        assert rejected.value.notification_failure['predicate'] == 'capability_expired'
    before = deepcopy(model.records)
    result, cookie = store.open_session(token, 'c' * 64)
    assert result['status'] == 'withdrawal_only' and cookie is None
    assert 'preferences' not in result and model.records == before
    with pytest.raises(m.ManagementUnavailable) as rejected:
        store.save(token, ACTION, 0, PREFERENCES)
    assert rejected.value.notification_failure['predicate'] == 'consent_unverified'
    assert store.save(token, ACTION, 0)['status'] == 'unsubscribed'
    assert model.rows(verification)[0]['verified_at'] is None


@pytest.mark.parametrize('month,day', [(10, 31), (3, 7)])
@pytest.mark.parametrize('microsecond', [0, 123456, 999999])
def test_management_recovery_elapsed_lifetime(month, day, microsecond):
    model = Model()
    model.now = datetime(2026, month, day, 12, 0, 0, microsecond,
                         tzinfo=ZoneInfo('America/Los_Angeles'))
    store = m.NotificationManagementStore(model, SECRET, 'testing')
    subscribe(model)
    assert store.confirm(store.request_confirmation('subscriber1@example.invalid')) == 'verified'
    model.elapse(seconds=60)
    verified = deepcopy(model.rows(verification))
    store.request_recovery('subscriber1@example.invalid')
    processor = outbox.ConfirmationOutboxStore(model, SECRET, 'testing', management_enabled=True)
    intent = next(row['intent'] for row in model.rows(m.intents) if row['purpose'] == 'management')
    claim = processor.claim_confirmation(intent)
    _, message = processor.prepare_confirmation(intent, claim, PAGE)
    token = message.text.split('#manage=')[1].split()[0]
    authority = store.capabilities.read(token, model.now)
    assert authority['expires'] - authority['issued'] == 86400
    assert store.preferences(token)['revision'] == 0
    assert store.confirm(token) == 'unavailable' and model.rows(verification) == verified
    deadline = datetime.fromtimestamp(authority['expires'], timezone.utc)
    model.now = deadline - timedelta(microseconds=1)
    assert store.preferences(token)['revision'] == 0
    model.now = deadline
    with pytest.raises(m.ManagementUnavailable) as rejected:
        store.preferences(token)
    assert rejected.value.notification_failure['predicate'] == 'capability_expired'


@pytest.mark.parametrize('excess', [1, 3600])
def test_management_excessive_elapsed_lifetime_remains_rejected(excess):
    model, store, digest, token = managed()
    parts = token.split('.')
    parts[5] = str(int(parts[4]) + 30 * 86400 + excess)
    body = '.'.join(parts[:-1])
    excessive = body + '.' + store.capabilities._sign(body)
    before = deepcopy(model.records)
    with pytest.raises(m.ManagementUnavailable) as rejected:
        store.open_session(excessive, 'c' * 64)
    assert rejected.value.notification_failure['predicate'] == 'capability_lifetime'
    assert model.records == before
    with pytest.raises(ValueError):
        store.capabilities.issue(digest, 0, model.now, lifetime=timedelta(days=30, seconds=excess))


@pytest.mark.parametrize('zone', ['UTC', 'America/Los_Angeles'])
def test_confirmation_email_separate_24_hour_lifetime(zone):
    model = Model()
    model.now = datetime(2026, 10, 23, 12, 0, 0, 123456, tzinfo=ZoneInfo(zone))
    store = m.NotificationManagementStore(model, SECRET, 'testing')
    subscribe(model)
    requested = store.request_confirmation('subscriber1@example.invalid')
    processor = outbox.ConfirmationOutboxStore(model, SECRET, 'testing', management_enabled=True)
    intent = model.rows(m.intents)[0]['intent']
    _, message = processor.prepare_confirmation(intent, processor.claim_confirmation(intent), PAGE)
    token = message.text.split('#confirm-email=')[1].split()[0]
    assert token == requested
    record = model.rows(verification)[0]
    assert record['expires_at'].timestamp() - record['issued_at'].timestamp() == 86400
    with pytest.raises(m.ManagementUnavailable) as rejected:
        store.capabilities.read(token, model.now)
    assert rejected.value.notification_failure['predicate'] == 'capability_format'
    model.now = record['expires_at'].astimezone(timezone.utc) - timedelta(microseconds=1)
    assert store.confirm(token) == 'verified'
    model.now += timedelta(microseconds=1)
    assert store.confirm(token) == 'unavailable'


@pytest.mark.parametrize('platform',['android','ios'])
def test_new_or_readded_preference_cannot_enlarge_old_audience(platform):
    model,store,digest,token=managed(); name=platform+'_launch'
    first=store.save(token,ACTION,0,dict(PREFERENCES,**{name:False}))
    store.accept_event(payload(platform)); model.elapse(seconds=1)
    second=store.save(first['token'],'b'*64,1,PREFERENCES)
    assert store.prepare_event(EVENT)=='completed'
    assert not model.rows(deliveries)
    assert store.preferences(second['token'])['preferences'][name] is True


@pytest.mark.parametrize('change',['removed','readded','withdrawn'])
def test_claimed_delivery_rechecks_edits_at_submission(change):
    model,store,digest,token=managed(); store.accept_event(payload()); store.prepare_event(EVENT)
    claim=store.claim(EVENT,digest); assert claim
    if change=='withdrawn': store.save(token,ACTION,0)
    else:
        saved=store.save(token,ACTION,0,dict(PREFERENCES,android_launch=False))
        if change=='readded':
            model.elapse(seconds=1); store.save(saved['token'],'b'*64,1,PREFERENCES)
    assert store.begin_submission(EVENT,digest,claim) is None
    assert model.rows(deliveries)[0]['status']=='suppressed'


def test_release_management_footer_uses_revision_at_locked_submission():
    model,store,digest,token=managed(); store.accept_event(payload())
    saved=store.save(token,ACTION,0,PREFERENCES)
    send=Mock(return_value=response())
    assert ReleaseDispatcher(store,CONFIG,PAGE,transport=send).process(EVENT).processed==1
    body=json.loads(send.call_args.args[1]); link=body['textContent'].split('#manage=')[1].split()[0]
    assert store.capabilities.read(link,model.now)['revision']==1
    assert store.preferences(link)['preferences']['state']=='CA'


def test_default_off_management_api_is_inert():
    model=Model(); app=runtime._build_app(None,runtime.BrowserRecognition(SECRET),ORIGIN,subscription_store=SubscriptionStore(model))
    client=app.test_client(); session=client.get('/api/notifications/session',base_url=ORIGIN).json
    assert session['management_enabled'] is False
    for path in ('/api/notifications/manage','/api/notifications/manage/save','/api/notifications/manage/recovery',
                 '/api/notifications/manage/withdrawal-receipt','/api/notifications/manage/withdrawal-ack'):
        assert post(client,session['csrf_token'],{},path).status_code==503
    assert not model.statements


@pytest.mark.parametrize('page',['https://website.example/gramanna.html','https://website.example/confirm-email.html','https://website.example/manage-notifications.html'])
def test_management_destination_and_body_links(page):
    model,store,digest,token=managed()
    assert messages.secure_management_page(page)=='https://website.example/manage-notifications.html'
    message=messages.verification_message('a'*64,page.replace('/manage-notifications.html','/confirm-email.html'),management_token=token)
    assert 'Manage Preferences: https://website.example/manage-notifications.html#manage='+token in message.text
    assert 'Manage Preferences</a>' in message.html
    for content in (message.text, message.html):
        assert 'confirmation link expires 24 hours after your request' in content
        assert ('This management link expires 30 days after this email is prepared. '
                'Viewing or changing preferences requires email confirmation.') in content
        assert 'Manage Preferences or Unsubscribe' not in content
        assert 'unsubscribe without confirming your email' not in content


def test_scheduler_default_bytes_and_new_explicit_flag(monkeypatch):
    import base64, xml.etree.ElementTree as ET
    from oaf_website import confirmation_schedule as schedule
    for profile in ('testing','development'):
        for enabled in (False,True):
            arguments=dict(profile=profile,windows_user='S-1-5-21-1-2-3-4',enabled=enabled,account='synthetic',page=PAGE,
                           recipient='subscriber1@example.invalid' if profile=='testing' else None)
            original=schedule.task_xml(**arguments)
            assert '<?xml' not in original
            configured=ET.fromstring(schedule.task_xml(**arguments,management_enabled=True))
            encoded=configured.find('.//{*}Arguments').text.split()[-1]
            command=base64.b64decode(encoded).decode('utf-16-le')
            assert ('--enable-management' in command) is enabled
            assert configured.find('.//{*}Settings/{*}Enabled').text=='false'


def test_simultaneous_edit_and_delivery_claim_obeys_final_cutoff():
    model,store,digest,token=managed(); store.accept_event(payload()); store.prepare_event(EVENT)
    model.elapse(seconds=1)
    def edit():
        return store.save(token,ACTION,0,dict(PREFERENCES,android_launch=False))
    with ThreadPoolExecutor(max_workers=2) as pool:
        changing=pool.submit(edit); claiming=pool.submit(store.claim,EVENT,digest)
        changing.result(); claim=claiming.result()
    if claim is not None: assert store.begin_submission(EVENT,digest,claim) is None
    assert model.rows(deliveries)[0]['status']=='suppressed'


def test_simultaneous_withdrawal_and_save_never_reactivates():
    model,store,digest,token=managed()
    def save():
        try: return store.save(token,ACTION,0,PREFERENCES)
        except m.ManagementConflict: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        saving=pool.submit(save); withdrawing=pool.submit(store.unsubscribe_legacy,digest)
        saving.result(); withdrawing.result()
    assert model.rows(m.notifications)[0]['unsubscribed_at'] is not None
    assert len(model.rows(m.changes)) in {1,2}


def test_recovery_management_uncertainty_has_no_automatic_retry():
    model,store,digest,token=managed(); model.elapse(seconds=60); store.request_recovery('subscriber1@example.invalid')
    from oaf_website.brevo import ProviderOutcome
    processor=outbox.ConfirmationOutboxStore(model,SECRET,'testing',management_enabled=True)
    dispatcher=outbox.ConfirmationDispatcher(processor,CONFIG,PAGE,transport=Mock())
    dispatcher.adapter.submit=Mock(return_value=ProviderOutcome('submission_unknown'))
    assert dispatcher.process().processed==1
    model.elapse(hours=1); assert dispatcher.process().processed==0
    assert dispatcher.adapter.submit.call_count==1
    assert next(r for r in model.rows(m.intents) if r['purpose']=='management')['status']=='uncertain'


def test_testing_recovery_recipient_scope_and_no_suppression_reversal():
    from oaf_website.brevo import TestingRecipientScope as Scope
    model,store,digest,token=managed(); other=subscribe(model,2)
    confirmation=store.request_confirmation('subscriber2@example.invalid'); assert store.confirm(confirmation)=='verified'
    model.elapse(seconds=60)
    store.request_recovery('subscriber1@example.invalid'); store.request_recovery('subscriber2@example.invalid')
    processor=outbox.ConfirmationOutboxStore(model,SECRET,'testing',management_enabled=True,
        recipient_scope=Scope('testing','subscriber1@example.invalid'))
    transport=Mock(return_value=response())
    assert outbox.ConfirmationDispatcher(processor,CONFIG,PAGE,transport=transport).process().processed==1
    assert json.loads(transport.call_args.args[1])['to']==[{'email':'subscriber1@example.invalid'}]
    assert next(r for r in model.rows(m.intents) if r['purpose']=='management' and r['subscription']==other)['status']=='pending'
    store.suppress('subscriber1@example.invalid','provider_block'); before=deepcopy(model.rows(suppressions))
    saved=store.save(token,ACTION,0,PREFERENCES)
    assert saved['status']=='saved' and model.rows(suppressions)==before


def test_https_management_configuration_validated_before_protected_key(monkeypatch):
    from oaf_website import local_testing as local
    from oaf_website.brevo_unsubscribe import BrevoWebhookConfig
    monkeypatch.setenv('OAF_ENV','testing')
    key=Mock(side_effect=AssertionError('No key access')); monkeypatch.setattr(local,'recognition_secret',key)
    for options in (dict(management_enabled=1),dict(brevo_webhook_config=BrevoWebhookConfig('testing','x'*32)),
                    dict(management_enabled=True,brevo_webhook_config=BrevoWebhookConfig('development','x'*32))):
        with pytest.raises(ValueError): local.testing_https_app(public_origin=ORIGIN,confirmation_page=PAGE,**options)
    key.assert_not_called()


def test_processor_cli_forwards_explicit_management_flag_only(monkeypatch,capsys):
    from oaf_website import confirmation_processor as processor
    from oaf_website.notification_dispatch import BatchResult
    process=Mock(return_value=BatchResult('disabled')); monkeypatch.setattr(processor,'process_confirmations',process)
    assert processor.main(['--environment','testing','--enable-management'])==2
    assert process.call_args.kwargs['management_enabled'] is True
    assert process.call_args.kwargs['enabled'] is False


@pytest.mark.parametrize('preferences',[None,False,[],1])
def test_malformed_preferences_are_never_interpreted_as_withdrawal(preferences):
    model,store,_,token=managed(); app,client,csrf=browser(model,store); before=deepcopy(model.records)
    result=post(client,csrf,dict(token=token,action=ACTION,revision=0,preferences=preferences),'/api/notifications/manage/save')
    assert result.status_code==400 and model.records==before


def test_actual_browser_api_read_save_unsubscribe_and_headers():
    model,store,digest,token=managed(); app,client,csrf=browser(model,store)
    viewed=post(client,csrf,{'token':token},'/api/notifications/manage')
    assert viewed.status_code==200 and viewed.json['status']=='preferences'
    body=dict(token=token,action=ACTION,revision=0,preferences=PREFERENCES)
    assert len(json.dumps(body).encode())<1024
    saved=post(client,csrf,body,'/api/notifications/manage/save')
    assert saved.status_code==200 and saved.json['status']=='saved' and saved.json['revision']==1
    for result in (viewed,saved):
        assert result.headers['Cache-Control']=='no-store'
        assert result.headers['Referrer-Policy']=='no-referrer'
    assert post(client,csrf,body,'/api/notifications/manage/save').json==saved.json
    assert post(client,csrf,{'token':token},'/api/notifications/manage').status_code==400
    result=post(client,csrf,dict(token=saved.json['token'],action='b'*64,revision=1),'/api/notifications/manage/save')
    assert result.status_code==200 and result.json['status']=='unsubscribed'


def test_explicit_factory_injects_one_engine_and_does_not_process(factory,monkeypatch):
    from oaf_website.local_testing import testing_https_app
    from oaf_website.brevo_unsubscribe import BrevoWebhookConfig
    monkeypatch.setenv('OAF_ENV','testing')
    app=testing_https_app(public_origin=ORIGIN,confirmation_page=PAGE,confirmation_enabled=True,
                          management_enabled=True,brevo_webhook_config=BrevoWebhookConfig('testing','x'*32))
    assert app.extensions['state_requests_engine'] is factory.model
    client=app.test_client(); session=client.get('/api/notifications/session',base_url=ORIGIN).json
    assert session['management_enabled'] is True and session['confirmation_enabled'] is True
    assert client.get('/manage-notifications.html',base_url=ORIGIN).status_code==200
    assert not factory.model.statements
    factory.forbidden.assert_not_called()


def test_append_only_history_reads_need_no_update_grant():
    model,store,digest,token=managed()
    saved=store.save(token,ACTION,0,PREFERENCES)
    store.save(saved['token'],'b'*64,1,dict(PREFERENCES,state='TX'))
    reads=[q for q in model.statements if q.startswith('SELECT') and 'FROM oaf_website.notification_preference_changes' in q]
    assert reads and all('FOR UPDATE' not in q for q in reads)
    assert any('FROM oaf_website.notifications' in q and 'FOR UPDATE' in q for q in model.statements)


def test_unexpected_database_value_error_is_sanitized_and_retry_converges(monkeypatch):
    model,store,digest,token=managed(); app,client,csrf=browser(model,store); begin=model.begin
    @contextmanager
    def lost_acknowledgement():
        with begin() as connection: yield connection
        raise ValueError('PRIVATE DATABASE DIAGNOSTIC '+token)
    monkeypatch.setattr(model,'begin',lost_acknowledgement)
    body=dict(token=token,action=ACTION,revision=0,preferences=PREFERENCES)
    failed=post(client,csrf,body,'/api/notifications/manage/save')
    assert failed.status_code==503 and 'PRIVATE DATABASE' not in failed.text and token not in failed.text
    monkeypatch.setattr(model,'begin',begin)
    assert post(client,csrf,body,'/api/notifications/manage/save').json['status']=='saved'
    assert len(model.rows(m.changes))==1


SESSION_COOKIE = '__Host-oaf-notification-management'
RECOGNITION_COOKIE = '__Host-oaf-state-browser'
BROWSER = '1' * 64


def session_cookie(client):
    return client.get_cookie(SESSION_COOKIE, domain='website.example').value


def test_management_session_navigation_reload_and_fresh_browser():
    model,store,_,token=managed(); app,client,csrf=browser(model,store,static=True)
    before=deepcopy(model.records)
    initial=post(client,csrf,{'token':token},'/api/notifications/manage')
    assert initial.status_code==200 and initial.json['preferences']==dict(
        web_launch=True,android_launch=True,ios_launch=True,state=None)
    header=initial.headers['Set-Cookie']
    assert header.startswith(SESSION_COOKIE+'=')
    assert all(value in header for value in ('Secure','HttpOnly','SameSite=Lax','Path=/','Max-Age=1800'))
    assert 'Domain=' not in header and 'token' not in initial.json and token not in initial.text
    cookie=session_cookie(client)
    for path in ('/gramanna.html','/manage-notifications.html','/manage-notifications.html'):
        assert client.get(path,base_url=ORIGIN).status_code==200
        model.elapse(seconds=1)
        resumed=post(client,csrf,{},'/api/notifications/manage')
        assert resumed.json==initial.json and 'Set-Cookie' not in resumed.headers
        assert session_cookie(client)==cookie
    fresh=app.test_client()
    fresh_csrf=fresh.get('/api/notifications/session',base_url=ORIGIN).json['csrf_token']
    assert post(fresh,fresh_csrf,{},'/api/notifications/manage').status_code==400
    assert model.records==before


@pytest.mark.parametrize('lifetime,elapsed',[(30*86400,1800),(20,20)])
def test_session_fixed_deadline_and_original_link_expiry(lifetime,elapsed):
    model,store,digest,_=managed()
    token=store.capabilities.issue(digest,0,model.now,lifetime=timedelta(seconds=lifetime))
    _,cookie=store.open_session(token,BROWSER)
    state=store.sessions.read(cookie['value'],BROWSER,model.now)
    assert state['expires']==int(model.now.timestamp())+elapsed
    assert cookie['max_age']==elapsed
    model.elapse(seconds=elapsed-1)
    assert store.session_preferences(cookie['value'],BROWSER)['revision']==0
    model.elapse(seconds=1)
    with pytest.raises(m.ManagementUnavailable): store.session_preferences(cookie['value'],BROWSER)
    with pytest.raises(m.ManagementUnavailable): store.save_session(cookie['value'],BROWSER,ACTION,0,PREFERENCES)
    assert not model.rows(m.changes)


@pytest.mark.parametrize('case',['tampered','truncated','missing','oversize','wrong_browser',
                               'recognition','legacy','confirmation','wrong_key','wrong_environment'])
def test_session_denies_invalid_credentials_and_other_purposes(case):
    model,store,digest,token=managed(); _,cookie=store.open_session(token,BROWSER)
    value=cookie['value']; browser_token=BROWSER
    if case=='tampered':
        body,signature=value.rsplit('.',1)
        value=body+'.'+('A' if signature[0]!='A' else 'B')+signature[1:]
    if case=='truncated': value=value[:30]
    if case=='missing': value=None
    if case=='oversize': value+='x'*2048
    if case=='wrong_browser': browser_token='2'*64
    if case=='recognition': _,value=runtime.BrowserRecognition(SECRET).issue()
    if case=='legacy': value=UnsubscribeCapabilities(SECRET).issue(digest)
    if case=='confirmation':
        subscribe(model,2)
        value=store.request_confirmation('subscriber2@example.invalid')
        assert value is not None
    if case in {'wrong_key','wrong_environment'}:
        caps=m.ManagementCapabilities(b'x'*32 if case=='wrong_key' else SECRET,
                                      'development' if case=='wrong_environment' else 'testing')
        value=m.ManagementSessions(caps).cookie(store.sessions.issue(token,BROWSER,model.now),model.now)['value']
    before=deepcopy(model.records)
    with pytest.raises(m.ManagementUnavailable): store.session_preferences(value,browser_token)
    with pytest.raises(m.ManagementUnavailable): store.save_session(value,browser_token,ACTION,0,PREFERENCES)
    assert model.records==before


@pytest.mark.parametrize('change',[{'expires':int(NOW.timestamp())+1801},
    {'started':int(NOW.timestamp())+1},{'expires':int(NOW.timestamp())},{'started':True},
    {'browser':'wrong'},{'token':'legacy'},{'extra':True}])
def test_even_signed_session_requires_valid_bounded_fields(change):
    model,store,_,token=managed()
    state=store.sessions.issue(token,BROWSER,model.now); state.update(change)
    cookie=store.sessions.serializer.dumps(state)
    with pytest.raises(m.ManagementUnavailable): store.session_preferences(cookie,BROWSER)


def test_session_cannot_exceed_link_deadline_even_with_otherwise_valid_signed_fields():
    model,store,digest,_=managed()
    token=store.capabilities.issue(digest,0,model.now,lifetime=timedelta(seconds=20))
    state=store.sessions.issue(token,BROWSER,model.now); state['expires']+=1
    with pytest.raises(m.ManagementUnavailable):
        store.session_preferences(store.sessions.serializer.dumps(state),BROWSER)


def test_session_save_continuation_and_both_lost_response_retry_paths():
    model,store,_,token=managed(); app,client,csrf=browser(model,store)
    post(client,csrf,{'token':token},'/api/notifications/manage')
    original_cookie=session_cookie(client)
    original=store.sessions.serializer.loads(original_cookie)
    model.elapse(seconds=60)
    body=dict(action=ACTION,revision=0,preferences=PREFERENCES)
    saved=post(client,csrf,body,'/api/notifications/manage/save')
    assert saved.json==dict(status='saved',revision=1) and token not in saved.text
    continued=store.sessions.serializer.loads(session_cookie(client))
    assert continued['expires']==original['expires'] and continued['started']==original['started']
    assert continued['token']!=original['token'] and 'Max-Age=1740' in saved.headers['Set-Cookie']
    # Cookie received, body lost: the identical old revision/action still converges.
    assert post(client,csrf,body,'/api/notifications/manage/save').json==saved.json
    # Neither cookie nor body received: the original cookie/action also converges.
    client.set_cookie(SESSION_COOKIE,original_cookie,domain='website.example')
    assert post(client,csrf,body,'/api/notifications/manage/save').json==saved.json
    assert len(model.rows(m.changes))==1
    assert post(client,csrf,dict(body,preferences=dict(PREFERENCES,state='TX')),
                '/api/notifications/manage/save').status_code==409
    resumed=post(client,csrf,{},'/api/notifications/manage')
    assert resumed.json['revision']==1 and resumed.json['preferences']['state']=='CA'
    model.elapse(seconds=60)
    second=post(client,csrf,dict(action='b'*64,revision=1,preferences=dict(PREFERENCES,state='TX')),
                '/api/notifications/manage/save')
    assert second.json==dict(status='saved',revision=2)
    assert store.sessions.serializer.loads(session_cookie(client))['expires']==original['expires']
    assert post(client,csrf,{},'/api/notifications/manage').json['preferences']['state']=='TX'
    model.elapse(seconds=1680)
    assert post(client,csrf,{},'/api/notifications/manage').status_code==400
    assert client.get_cookie(SESSION_COOKIE,domain='website.example') is None


@pytest.mark.parametrize('revocation',['withdrawal','revision','unverified','missing_lifecycle','key_rotation'])
def test_sessions_revalidate_current_authority_for_reads_and_saves(revocation):
    model,store,digest,token=managed(); _,cookie=store.open_session(token,BROWSER)
    if revocation=='withdrawal': store.unsubscribe_legacy(digest)
    if revocation=='revision': store.save(token,'b'*64,0,PREFERENCES)
    if revocation=='unverified': model.rows(verification)[0]['verified_at']=None
    if revocation=='missing_lifecycle': model.records[m.notifications.name]=[]
    if revocation=='key_rotation': store=m.NotificationManagementStore(model,b'x'*32,'testing')
    before=deepcopy(model.records)
    with pytest.raises(m.ManagementUnavailable): store.session_preferences(cookie['value'],BROWSER)
    with pytest.raises((m.ManagementUnavailable,m.ManagementConflict)):
        store.save_session(cookie['value'],BROWSER,ACTION,0,PREFERENCES)
    assert model.records==before


@pytest.mark.parametrize('all_off',[False,True])
def test_complete_unsubscribe_clears_session_and_copied_cookie_is_denied(all_off):
    model,store,_,token=managed(); app,client,csrf=browser(model,store)
    post(client,csrf,{'token':token},'/api/notifications/manage'); cookie=session_cookie(client)
    body=dict(action=ACTION,revision=0)
    if all_off: body['preferences']=dict(web_launch=False,android_launch=False,ios_launch=False,state=None,consent=False)
    assert post(client,csrf,body,'/api/notifications/manage/save').json['status']=='unsubscribed'
    assert client.get_cookie(SESSION_COOKIE,domain='website.example') is None
    client.set_cookie(SESSION_COOKIE,cookie,domain='website.example')
    assert post(client,csrf,{},'/api/notifications/manage').status_code==400
    client.set_cookie(SESSION_COOKIE,cookie,domain='website.example')
    assert post(client,csrf,dict(action='b'*64,revision=0,preferences=PREFERENCES),
                '/api/notifications/manage/save').status_code==400
    assert len(model.rows(m.changes))==1


@pytest.mark.parametrize('credential',['legacy','unverified'])
def test_withdrawal_only_capability_never_acquires_management_session(credential):
    model,store,digest,token=managed(verified=credential!='unverified'); app,client,csrf=browser(model,store)
    if credential=='legacy': token=UnsubscribeCapabilities(SECRET).issue(digest)
    opened=post(client,csrf,{'token':token},'/api/notifications/manage')
    assert opened.status_code==(200 if credential=='unverified' else 400)
    if credential=='unverified':
        assert opened.json['status']=='withdrawal_only' and opened.json['revision']==0
        assert 'preferences' not in opened.json and 'token' not in opened.json
    assert client.get_cookie(SESSION_COOKIE,domain='website.example') is None
    assert post(client,csrf,{},'/api/notifications/manage').status_code==400
    assert not model.rows(m.changes)


@pytest.mark.parametrize('path',['/api/notifications/manage','/api/notifications/manage/save'])
def test_cookie_authority_still_requires_origin_fetch_metadata_csrf_and_json(path):
    model,store,_,token=managed(); app,client,csrf=browser(model,store)
    post(client,csrf,{'token':token},'/api/notifications/manage')
    body={} if path.endswith('/manage') else dict(action=ACTION,revision=0,preferences=PREFERENCES)
    before=deepcopy(model.records)
    for headers in ({},{'Origin':'https://evil.invalid','X-CSRF-Token':csrf},
                    {'Origin':ORIGIN,'X-CSRF-Token':'f'*64},
                    {'Origin':ORIGIN,'X-CSRF-Token':csrf,'Sec-Fetch-Site':'cross-site'},
                    {'Origin':ORIGIN,'X-CSRF-Token':csrf,'Sec-Fetch-Site':'same-site'}):
        assert post(client,csrf,body,path,headers=headers).status_code==403
    assert client.post(path,base_url=ORIGIN,data='{}',content_type='text/plain',
                       headers={'Origin':ORIGIN,'X-CSRF-Token':csrf}).status_code==415
    assert model.records==before
    assert post(client,csrf,{},'/api/notifications/manage').status_code==200


@pytest.mark.parametrize('failure',['connect','execute','commit','uncertain'])
def test_session_save_atomic_audit_and_commit_failure_recovery(failure,caplog):
    model,store,_,token=managed(); app,client,csrf=browser(model,store)
    post(client,csrf,{'token':token},'/api/notifications/manage'); cookie=session_cookie(client)
    before=deepcopy(model.records); body=dict(action=ACTION,revision=0,preferences=PREFERENCES)
    model.failure=failure
    failed=post(client,csrf,body,'/api/notifications/manage/save')
    assert failed.status_code==503 and 'Set-Cookie' not in failed.headers
    assert token not in failed.text+caplog.text and cookie not in failed.text+caplog.text
    if failure!='uncertain': assert model.records==before
    model.failure=None
    assert post(client,csrf,body,'/api/notifications/manage/save').json==dict(status='saved',revision=1)
    assert len(model.rows(m.changes))==1


def test_session_browser_binding_cannot_transfer_between_recognized_browsers():
    model,store,_,token=managed(); app,client,csrf=browser(model,store)
    post(client,csrf,{'token':token},'/api/notifications/manage')
    other=app.test_client(); other_csrf=other.get('/api/notifications/session',base_url=ORIGIN).json['csrf_token']
    other.set_cookie(SESSION_COOKIE,session_cookie(client),domain='website.example')
    assert post(other,other_csrf,{},'/api/notifications/manage').status_code==400
    assert post(client,csrf,{},'/api/notifications/manage').status_code==200


def test_session_cannot_replay_old_save_after_later_save_or_withdrawal():
    model,store,digest,token=managed(); _,first=store.open_session(token,BROWSER)
    _,second=store.save_session(first['value'],BROWSER,ACTION,0,PREFERENCES)
    _,third=store.save_session(second['value'],BROWSER,'b'*64,1,dict(PREFERENCES,state='TX'))
    before=deepcopy(model.records)
    with pytest.raises(m.ManagementUnavailable): store.save_session(first['value'],BROWSER,ACTION,0,PREFERENCES)
    assert model.records==before
    store.unsubscribe_legacy(digest)
    with pytest.raises(m.ManagementUnavailable): store.save_session(third['value'],BROWSER,'b'*64,1,dict(PREFERENCES,state='TX'))


def test_suppression_remains_permanent_during_session_edit():
    model,store,_,token=managed(); _,cookie=store.open_session(token,BROWSER)
    store.suppress('subscriber1@example.invalid','provider_block'); blocked=deepcopy(model.rows(suppressions))
    saved,_=store.save_session(cookie['value'],BROWSER,ACTION,0,PREFERENCES)
    assert saved['status']=='saved' and model.rows(suppressions)==blocked


@pytest.mark.parametrize('all_off',[False,True])
@pytest.mark.parametrize('lost_headers',[False,True])
def test_withdrawal_receipt_covers_both_lost_response_cases(all_off,lost_headers,caplog):
    model,store,_,token=managed(); app,client,csrf=browser(model,store)
    primary=subscribe(model,2,email='primary@example.invalid')
    original_primary=deepcopy(model.rows(m.notifications)[1])
    post(client,csrf,{'token':token},'/api/notifications/manage'); cookie=session_cookie(client)
    body=dict(action=ACTION,revision=0)
    if all_off: body['preferences']=dict(web_launch=False,android_launch=False,ios_launch=False,state=None,consent=False)
    before=deepcopy(model.records)
    prepared=post(client,csrf,body,'/api/notifications/manage/withdrawal-receipt')
    assert prepared.status_code==200 and set(prepared.json)=={'receipt'}
    receipt=prepared.json['receipt']; assert model.records==before
    ack=dict(body,receipt=receipt)
    # Receipt alone before commitment has no authority to perform withdrawal.
    assert post(client,csrf,ack,'/api/notifications/manage/withdrawal-ack').status_code==400
    assert model.records==before
    result=post(client,csrf,body,'/api/notifications/manage/save')
    assert result.json==dict(status='unsubscribed',revision=1)
    assert client.get_cookie(SESSION_COOKIE,domain='website.example') is None
    committed=deepcopy(model.records); withdrawn=model.rows(m.notifications)[0]['unsubscribed_at']
    if lost_headers: client.set_cookie(SESSION_COOKIE,cookie,domain='website.example')
    model.elapse(seconds=20)
    repeat=post(client,csrf,ack,'/api/notifications/manage/withdrawal-ack')
    assert repeat.status_code==200 and repeat.json==result.json
    assert 'Max-Age=0' in repeat.headers['Set-Cookie']
    assert model.records==committed and len(model.rows(m.changes))==1
    assert model.rows(m.notifications)[0]['unsubscribed_at']==withdrawn
    assert model.rows(m.notifications)[1]==original_primary
    assert model.rows(m.notifications)[1]['unsubscribe_digest']==primary
    assert post(client,csrf,{},'/api/notifications/manage').status_code==400
    assert post(client,csrf,dict(action='b'*64,revision=1,preferences=PREFERENCES),
                '/api/notifications/manage/save').status_code==400
    assert post(client,csrf,dict(body,receipt=receipt),'/api/notifications/manage').status_code==400
    assert all(private not in caplog.text for private in (token,cookie,receipt))


def test_original_cookie_exact_withdrawal_repeat_is_bounded_and_does_not_restore_access():
    model,store,_,token=managed(); _,cookie=store.open_session(token,BROWSER)
    result,cleared=store.save_session(cookie['value'],BROWSER,ACTION,0)
    assert cleared is None
    before=deepcopy(model.records)
    assert store.save_session(cookie['value'],BROWSER,ACTION,0)==(result,None)
    with pytest.raises(m.ManagementUnavailable): store.session_preferences(cookie['value'],BROWSER)
    with pytest.raises(m.ManagementUnavailable): store.save_session(cookie['value'],BROWSER,'b'*64,0)
    model.elapse(seconds=m.WITHDRAWAL_RECEIPT_AGE+1)
    with pytest.raises(m.ManagementUnavailable): store.save_session(cookie['value'],BROWSER,ACTION,0)
    assert model.records==before


@pytest.mark.parametrize('fault',['forged','expired','browser','environment','lifecycle','action','revision',
    'payload','selected','missing_audit','key','future','overlong','later_revision','wrong_source'])
def test_receipt_rejection_is_generic_and_never_mutates(fault):
    model,store,digest,token=managed(); app,client,csrf=browser(model,store)
    post(client,csrf,{'token':token},'/api/notifications/manage')
    body=dict(action=ACTION,revision=0)
    receipt=post(client,csrf,body,'/api/notifications/manage/withdrawal-receipt').json['receipt']
    post(client,csrf,body,'/api/notifications/manage/save')
    state=store.withdrawal_signer.loads(receipt)
    if fault=='forged': receipt=receipt.rsplit('.',1)[0]+'.forged'
    if fault=='expired': model.elapse(seconds=m.WITHDRAWAL_RECEIPT_AGE)
    if fault=='browser': state['browser']='f'*64
    if fault=='environment': state['environment']='development'
    if fault=='lifecycle': state['subscription']='f'*64
    if fault=='action': body['action']='b'*64
    if fault=='revision': body['revision']=1
    if fault=='payload': body['preferences']=dict(web_launch=False,android_launch=False,ios_launch=False,state=None,consent=False)
    if fault=='selected': body['preferences']=PREFERENCES
    if fault=='missing_audit': model.records[m.changes.name]=[]
    if fault=='future': state['started']+=1
    if fault=='overlong': state['expires']+=1
    if fault=='later_revision': model.rows(m.notifications)[0]['preferences_revision']+=1
    if fault=='wrong_source': model.rows(m.changes)[0]['source']='legacy'
    if fault in {'browser','environment','lifecycle','future','overlong'}: receipt=store.withdrawal_signer.dumps(state)
    if fault=='key': receipt=m.NotificationManagementStore(model,b'x'*32,'testing').withdrawal_signer.dumps(state)
    before=deepcopy(model.records)
    denied=post(client,csrf,dict(body,receipt=receipt),'/api/notifications/manage/withdrawal-ack')
    assert denied.status_code==400 and denied.json['message']==m.UNAVAILABLE
    assert model.records==before


@pytest.mark.parametrize('verified',[False,True])
def test_direct_link_receipt_is_purpose_limited_and_capped_by_original_expiry(verified):
    model,store,digest,_=managed(verified=verified)
    token=store.capabilities.issue(digest,0,model.now,lifetime=timedelta(seconds=20))
    receipt=store.prepare_withdrawal(None,BROWSER,ACTION,0,token=token)['receipt']
    state=store.withdrawal_signer.loads(receipt)
    assert state['expires']==int(model.now.timestamp())+20
    assert token not in json.dumps(state) and 'token' not in state
    with pytest.raises(m.ManagementUnavailable): store.preferences(receipt)
    with pytest.raises(m.ManagementUnavailable): store.prepare_withdrawal(None,BROWSER,ACTION,0,PREFERENCES,token=token)
    store.save(token,ACTION,0); before=deepcopy(model.records)
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes=list(pool.map(lambda _:store.acknowledge_withdrawal(receipt,BROWSER,ACTION,0),range(8)))
    assert outcomes==[dict(status='unsubscribed',revision=1)]*8
    assert model.records==before and len(model.rows(m.changes))==1
    model.elapse(seconds=20)
    with pytest.raises(m.ManagementUnavailable): store.acknowledge_withdrawal(receipt,BROWSER,ACTION,0)


@pytest.mark.parametrize('failure',['commit','uncertain'])
def test_receipt_and_actual_route_converge_after_lost_withdrawal_commit_ack(failure):
    model,store,_,token=managed(); app,client,csrf=browser(model,store)
    post(client,csrf,{'token':token},'/api/notifications/manage')
    body=dict(action=ACTION,revision=0)
    receipt=post(client,csrf,body,'/api/notifications/manage/withdrawal-receipt').json['receipt']
    model.failure=failure
    assert post(client,csrf,body,'/api/notifications/manage/save').status_code==503
    model.failure=None
    ack=post(client,csrf,dict(body,receipt=receipt),'/api/notifications/manage/withdrawal-ack')
    assert ack.status_code==(200 if failure=='uncertain' else 400)
    if failure=='commit': assert post(client,csrf,body,'/api/notifications/manage/save').status_code==200
    assert len(model.rows(m.changes))==1


def test_receipt_cannot_transfer_to_another_recognized_browser():
    model,store,_,token=managed(); app,client,csrf=browser(model,store)
    post(client,csrf,{'token':token},'/api/notifications/manage')
    body=dict(action=ACTION,revision=0)
    receipt=post(client,csrf,body,'/api/notifications/manage/withdrawal-receipt').json['receipt']
    post(client,csrf,body,'/api/notifications/manage/save'); before=deepcopy(model.records)
    other=app.test_client(); other_csrf=other.get('/api/notifications/session',base_url=ORIGIN).json['csrf_token']
    denied=post(other,other_csrf,dict(body,receipt=receipt),'/api/notifications/manage/withdrawal-ack')
    assert denied.status_code==400 and denied.json['message']==m.UNAVAILABLE
    assert model.records==before


def test_receipt_does_not_extend_the_original_session_deadline():
    model,store,_,token=managed(); _,cookie=store.open_session(token,BROWSER)
    original=store.sessions.read(cookie['value'],BROWSER,model.now)
    model.elapse(seconds=m.MANAGEMENT_SESSION_AGE-50)
    receipt=store.prepare_withdrawal(cookie['value'],BROWSER,ACTION,0)['receipt']
    state=store.withdrawal_signer.loads(receipt)
    assert state['expires']==original['expires'] and state['expires']-state['started']==50
    store.save_session(cookie['value'],BROWSER,ACTION,0); before=deepcopy(model.records)
    model.elapse(seconds=50)
    with pytest.raises(m.ManagementUnavailable): store.acknowledge_withdrawal(receipt,BROWSER,ACTION,0)
    assert model.records==before


def test_concurrent_cookie_withdrawal_repeats_have_one_transition_and_timestamp():
    model,store,_,token=managed(); _,cookie=store.open_session(token,BROWSER)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:store.save_session(cookie['value'],BROWSER,ACTION,0),range(8)))
    assert results==[(dict(status='unsubscribed',revision=1),None)]*8
    assert len(model.rows(m.changes))==1 and model.rows(m.notifications)[0]['unsubscribed_at']==model.now
