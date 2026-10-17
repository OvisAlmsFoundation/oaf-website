"""Offline Contact HTTP, SMTP, configuration and concurrency checks. No real mail."""

import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock
import ssl

import pytest

from oaf_website import contact, contact_mail as mail, state_requests as api
from oaf_website.local_testing import PUBLIC_FILES

ORIGIN = "https://website.example"
SECRET = b"contact-offline-test-only-secret-32-bytes"
PAYLOAD = {"email": "Visitor+contact@example.com", "message": "Please tell me about the Foundation."}


@pytest.fixture
def setup():
    sender = Mock(return_value=None)
    state, subscriptions = Mock(), Mock()
    app = api._build_app(state, api.BrowserRecognition(SECRET), ORIGIN,
                         subscription_store=subscriptions, contact_sender=sender)
    client = app.test_client()
    session = client.get('/api/contact/session', base_url=ORIGIN)
    csrf = session.json['csrf_token']
    return app, client, csrf, sender, state, subscriptions


def post(setup, data=PAYLOAD, **kwargs):
    _, client, csrf, *_ = setup
    headers = kwargs.pop('headers', {"Origin": ORIGIN, "X-CSRF-Token": csrf, "Sec-Fetch-Site": "same-origin"})
    return client.post('/api/contact', data=json.dumps(data), content_type='application/json',
                       base_url=ORIGIN, headers=headers, **kwargs)


def test_accepted_only_after_sender_returns_and_no_other_service_calls(setup):
    app, client, csrf, sender, state, subscriptions = setup
    def accept(email, message):
        assert email == 'visitor+contact@example.com'
        assert message == PAYLOAD['message']
        assert [value[1] for value in app.extensions['contact_guard'].submissions.values()] == ['pending']
    sender.side_effect = accept
    response = post(setup)
    assert response.status_code == 200
    assert response.json == {"status": "accepted", "message": contact.SUCCESS}
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert 'Access-Control-Allow-Origin' not in response.headers
    sender.assert_called_once()
    assert not state.mock_calls and not subscriptions.mock_calls
    assert app.config['MAX_CONTENT_LENGTH'] == 1024


@pytest.mark.parametrize('data', [
    {}, None, [], {"email": "", "message": ""}, {"email": "a@b.com"},
    {**PAYLOAD, "recipient": "attacker@example.com"}, {**PAYLOAD, "to": "attacker@example.com"},
    {**PAYLOAD, "subject": "Injected"}, {**PAYLOAD, "consent": True},
    *[{**PAYLOAD, "email": value} for value in [None, 1, [], "invalid", "a@@example.com", "a@localhost", "a..b@example.com", "a@example..com", "Name <a@example.com>", "a@example.com\r\nBcc: attacker@example.com", "a@example.com\x00", "\ta@example.com", "é@example.com", 'a'*65+'@example.com', 'a'*255]],
    *[{**PAYLOAD, "message": value} for value in [None, 1, [], "", " \n\t ", "word "*201, "a"*6001, "bad\x00text", "bad\x01text", "bad\ud800text"]],
])
def test_validation_and_recipient_routing_reject_invalid_data(setup, data):
    response = post(setup, data)
    assert response.status_code == 400
    assert response.json['status'] == 'error'
    assert '<script' not in response.json['message']
    setup[3].assert_not_called()


@pytest.mark.parametrize('message', ['word '*200, 'word\n'*200, 'word\t'*200, 'word\u2003'*200, 'x'*6000])
def test_word_and_character_boundaries(setup, message):
    assert post(setup, {**PAYLOAD, 'message': message}).status_code == 200
    setup[3].assert_called_once()


@pytest.mark.parametrize('headers', [
    {}, {"Origin": ORIGIN}, {"Origin": 'https://evil.example', "X-CSRF-Token": 'x'},
    {"Origin": 'null'}, {"Origin": ORIGIN+'/path'}, {"Sec-Fetch-Site": 'cross-site'},
])
def test_csrf_and_origin_required(setup, headers):
    assert post(setup, headers=headers).status_code == 403
    setup[3].assert_not_called()


@pytest.mark.parametrize('override', [
    {"Origin": 'https://evil.example'}, {"Sec-Fetch-Site": 'cross-site'},
    {"X-CSRF-Token": '0'*64}, {"X-CSRF-Token": 'bad'},
])
def test_valid_cookie_cannot_override_origin_or_csrf(setup, override):
    headers = {"Origin": ORIGIN, "X-CSRF-Token": setup[2], "Sec-Fetch-Site": "same-origin", **override}
    assert post(setup, headers=headers).status_code == 403
    setup[3].assert_not_called()


def test_missing_cookie_and_cross_origin_session(setup):
    app, client, csrf, sender, *_ = setup
    client.delete_cookie('__Host-oaf-state-browser', domain='website.example')
    assert post(setup).status_code == 403
    response = client.get('/api/contact/session', base_url=ORIGIN, headers={'Origin':'https://evil.example'})
    assert response.status_code == 403 and not response.headers.get('Set-Cookie')
    response = client.get('/api/contact/session', base_url=ORIGIN)
    cookie = response.headers['Set-Cookie']
    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=Lax' in cookie and 'Path=/' in cookie
    sender.assert_not_called()


def test_referer_fallback(setup):
    assert post(setup, headers={'Referer':ORIGIN+'/contact.html', 'X-CSRF-Token':setup[2]}).status_code == 200


def test_malformed_type_size_and_existing_limits(setup):
    app, client, csrf, sender, *_ = setup
    headers = {'Origin':ORIGIN, 'X-CSRF-Token':csrf}
    for data, mime, status in [('{bad','application/json',400), ('email=a','application/x-www-form-urlencoded',415), ('x'*32769,'application/json',413)]:
        response = client.post('/api/contact', data=data, content_type=mime, base_url=ORIGIN, headers=headers)
        assert response.status_code == status
    for path in ['/api/state-requests','/api/notifications']:
        response = client.post(path, data='x'*1025, content_type='application/json', base_url=ORIGIN, headers=headers)
        assert response.status_code == 413
    sender.assert_not_called()


def test_contact_allows_request_larger_than_state_contract(setup):
    assert post(setup, {**PAYLOAD, 'message':'x'*2000}).status_code == 200
    assert 'contact.html' in PUBLIC_FILES and 'assets/contact.js' in PUBLIC_FILES
    assert not any('config/' in name or name.endswith('.py') for name in PUBLIC_FILES)


def test_known_failure_is_private_and_retryable(setup, caplog):
    sender = setup[3]
    sender.side_effect = mail.DeliveryUnavailable('private-message-password')
    response = post(setup)
    assert response.status_code == 503 and response.json['message'] == contact.UNAVAILABLE
    assert 'accepted' not in response.json['message']
    assert 'private-message-password' not in caplog.text
    assert PAYLOAD['message'] not in caplog.text and PAYLOAD['email'] not in caplog.text
    sender.side_effect = None
    assert post(setup).status_code == 200
    assert sender.call_count == 2


@pytest.mark.parametrize('failure', [mail.DeliveryUncertain, RuntimeError])
def test_uncertain_send_suppresses_retry_without_claiming_success(setup, failure, caplog):
    setup[3].side_effect = failure('private-message-password')
    for _ in range(2):
        response = post(setup)
        assert response.status_code == 503 and response.json['message'] == contact.UNCERTAIN
    setup[3].assert_called_once()
    assert 'private-message-password' not in caplog.text


def test_default_unconfigured_contact_fails_safely():
    app = api._build_app(None, api.BrowserRecognition(SECRET), ORIGIN)
    client = app.test_client()
    csrf = client.get('/api/contact/session',base_url=ORIGIN).json['csrf_token']
    response = post((app,client,csrf))
    assert response.status_code == 503 and response.json['message'] == contact.UNAVAILABLE


def test_duplicate_suppression_and_rate_limits(setup):
    for _ in range(5):
        assert post(setup).status_code == 200
    response = post(setup, headers={'Origin':ORIGIN,'X-CSRF-Token':setup[2],'X-Forwarded-For':'198.51.100.2'})
    assert response.status_code == 429 and response.headers['Retry-After'] == '600'
    setup[3].assert_called_once()


def test_guard_ip_browser_global_capacity_and_expiry(monkeypatch):
    now = [0]
    guard = contact.ContactGuard(SECRET, clock=lambda:now[0])
    for i in range(5):
        assert guard.allow('browser',str(i))
    assert not guard.allow('browser','new-ip')
    for i in range(5):
        assert guard.allow(str(i),'shared-ip')
    assert not guard.allow('new-browser','shared-ip')
    guard = contact.ContactGuard(SECRET, clock=lambda:now[0])
    for i in range(60):
        assert guard.allow(str(i),str(i))
    assert not guard.allow('next','next')
    now[0] = 601
    assert guard.allow('next','next')
    monkeypatch.setattr(contact,'MAX_GUARD_ENTRIES',3)
    assert not guard.allow('other','other')
    key, state = guard.begin('browser',PAYLOAD['email'],PAYLOAD['message'])
    assert state == 'new'
    guard.finish(key,'accepted')
    assert guard.begin('browser',PAYLOAD['email'],PAYLOAD['message'])[1] == 'accepted'
    assert PAYLOAD['message'] not in repr(guard.submissions)
    assert PAYLOAD['email'] not in repr(guard.submissions)
    now[0] += 901
    assert guard.begin('browser',PAYLOAD['email'],PAYLOAD['message'])[1] == 'new'
    guard.begin('browser','two@example.com','second')
    guard.begin('browser','three@example.com','third')
    assert guard.begin('browser','four@example.com','fourth')[1] == 'full'


def test_concurrent_duplicate_has_one_sender(setup):
    app, client, csrf, sender, *_ = setup
    entered, release = Event(), Event()
    def held(*_):
        entered.set()
        assert release.wait(5)
    sender.side_effect = held
    cookie = client.get_cookie('__Host-oaf-state-browser',domain='website.example').value
    def first():
        with app.test_client() as other:
            other.set_cookie('__Host-oaf-state-browser',cookie,domain='website.example')
            return post((app,other,csrf))
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(first)
        try:
            assert entered.wait(5)
            assert post(setup).status_code == 409
        finally:
            release.set()
        assert future.result().status_code == 200
    assert post(setup).status_code == 200
    sender.assert_called_once()


def config():
    return mail.SMTPConfig('smtp.example.com',587,'starttls','smtp-account','sender@example.com','synthetic-test-password')


def test_email_headers_and_body_are_safe():
    message = mail.construct_message(config(), PAYLOAD['email'], 'Hello — thank you.\nBcc: body@example.com\n<script>text</script>')
    assert message['To'].addresses[0].addr_spec == mail.RECIPIENT
    assert message['Reply-To'].addresses[0].addr_spec == 'visitor+contact@example.com'
    assert message['From'].addresses[0].addr_spec == 'sender@example.com'
    assert message['Subject'] == mail.SUBJECT and message['Bcc'] is None
    assert message.get_content_type() == 'text/plain'
    assert message['Content-Transfer-Encoding'] == 'quoted-printable'
    assert 'Hello — thank you.' in message.get_content()
    assert message.as_bytes().isascii()
    assert '<script>text</script>' in message.get_content()
    assert message['Date'] and message['Message-ID']
    with pytest.raises(ValueError):
        mail.construct_message(config(),'a@example.com\r\nBcc: other@example.com','hello')
    assert 'synthetic-test-password' not in repr(config())


@pytest.mark.parametrize('mode', ['ssl','starttls'])
def test_smtp_authenticated_verified_tls_fixed_envelope_and_bounded_timeout(monkeypatch, mode):
    settings = replace(config(),tls_mode=mode,port=465 if mode=='ssl' else 587)
    monkeypatch.setattr(mail,'load_contact_config',lambda profile:settings)
    smtp = Mock()
    smtp.send_message.return_value = {}
    factory = Mock(return_value=smtp)
    monkeypatch.setattr(mail.smtplib,'SMTP_SSL' if mode=='ssl' else 'SMTP',factory)
    mail.ConfiguredSMTP('testing')(PAYLOAD['email'],PAYLOAD['message'])
    assert factory.call_args.kwargs['timeout'] == 5
    context = factory.call_args.kwargs['context'] if mode=='ssl' else smtp.starttls.call_args.kwargs['context']
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    smtp.login.assert_called_once_with(settings.username,settings.password)
    assert smtp.send_message.call_args.kwargs == {'from_addr':'sender@example.com','to_addrs':[mail.RECIPIENT]}
    assert smtp.ehlo.call_count == (1 if mode=='ssl' else 2)
    smtp.close.assert_called_once()
    assert not smtp.set_debuglevel.called and not smtp.quit.called
    calls = [call[0] for call in smtp.mock_calls]
    assert calls.index('login') < calls.index('send_message')
    if mode=='starttls':
        assert calls.index('starttls') < calls.index('login')


@pytest.mark.parametrize('stage,exception,expected', [
    ('starttls', ssl.SSLCertVerificationError('private'), mail.DeliveryUnavailable),
    ('login', mail.smtplib.SMTPAuthenticationError(535,b'private'), mail.DeliveryUnavailable),
    ('login', TimeoutError('private'), mail.DeliveryUnavailable),
    ('send_message', mail.smtplib.SMTPRecipientsRefused({mail.RECIPIENT:(550,b'private')}), mail.DeliveryUnavailable),
    ('send_message', mail.smtplib.SMTPDataError(550,b'private'), mail.DeliveryUnavailable),
    ('send_message', mail.smtplib.SMTPSenderRefused(553,b'private','sender@example.com'), mail.DeliveryUncertain),
    ('send_message', TimeoutError('private'), mail.DeliveryUncertain),
    ('send_message', mail.smtplib.SMTPServerDisconnected('private'), mail.DeliveryUncertain),
])
def test_smtp_failure_classification_and_no_retry(monkeypatch, caplog, stage, exception, expected):
    monkeypatch.setattr(mail,'load_contact_config',lambda profile:config())
    smtp = Mock()
    getattr(smtp,stage).side_effect = exception
    monkeypatch.setattr(mail.smtplib,'SMTP',Mock(return_value=smtp))
    with pytest.raises(expected) as caught:
        mail.ConfiguredSMTP('testing')('a@example.com','hello')
    assert not str(caught.value) and caught.value.__suppress_context__
    assert 'private' not in caplog.text
    assert smtp.send_message.call_count == (1 if stage=='send_message' else 0)
    smtp.close.assert_called_once()


@pytest.mark.parametrize('method,failure,expected_message', [
    ('login', mail.smtplib.SMTPAuthenticationError(535,b'private-smtp-response'), contact.UNAVAILABLE),
    ('send_message', mail.smtplib.SMTPDataError(554,b'private-smtp-response'), contact.UNAVAILABLE),
    ('send_message', mail.smtplib.SMTPServerDisconnected('private-smtp-response'), contact.UNCERTAIN),
])
def test_smtp_http_failure_privacy_retry_and_service_isolation(
        setup, monkeypatch, caplog, method, failure, expected_message):
    monkeypatch.setenv('OAF_ENV','development')
    monkeypatch.setattr(mail,'load_contact_config',lambda profile:config())
    smtp = Mock()
    smtp.send_message.return_value = {}
    getattr(smtp,method).side_effect = failure
    monkeypatch.setattr(mail.smtplib,'SMTP',Mock(return_value=smtp))
    _, _, _, sender, state, subscriptions = setup
    sender.side_effect = mail.ConfiguredSMTP('development')
    response = post(setup)
    assert response.status_code == 503
    assert response.json == {'status':'error','message':expected_message}
    for private in ('private-smtp-response', config().username, config().password,
                    config().from_email, PAYLOAD['email'], PAYLOAD['email'].lower(), PAYLOAD['message']):
        assert private not in response.text and private not in caplog.text
    smtp.close.assert_called_once()
    getattr(smtp,method).side_effect = None
    retry = post(setup)
    if expected_message == contact.UNCERTAIN:
        assert retry.status_code == 503 and retry.json['message'] == contact.UNCERTAIN
        sender.assert_called_once()
        smtp.send_message.assert_called_once()
    else:
        assert retry.status_code == 200 and retry.json['status'] == 'accepted'
        assert sender.call_count == 2
    assert not state.mock_calls and not subscriptions.mock_calls


def test_smtp_refusal_and_close_failure(monkeypatch):
    monkeypatch.setattr(mail,'load_contact_config',lambda profile:config())
    smtp = Mock()
    monkeypatch.setattr(mail.smtplib,'SMTP',Mock(return_value=smtp))
    smtp.send_message.return_value = {mail.RECIPIENT:(550,b'refused')}
    with pytest.raises(mail.DeliveryUnavailable):
        mail.ConfiguredSMTP('testing')('a@example.com','hello')
    smtp.send_message.return_value = {}
    smtp.close.side_effect = RuntimeError('close-failed-after-acceptance')
    assert mail.ConfiguredSMTP('testing')('a@example.com','hello') is None


def configuration_text():
    return '[testing]\nhost="smtp.example.com"\nport=587\ntls_mode="starttls"\nusername="smtp-account"\nfrom_email="sender@example.com"\n'


def test_config_exact_protected_credential_and_no_fallback(tmp_path):
    path = tmp_path/'contact.toml'
    path.write_text(configuration_text(),encoding='utf-8')
    provider = Mock(return_value='synthetic-password')
    result = mail.load_contact_config('testing', local_config_path=path, environ={'OAF_ENV':'testing'}, credential_loader=provider)
    assert result.from_email == 'sender@example.com' and result.password == 'synthetic-password'
    provider.assert_called_once_with('OAF Website/testing/Contact/SMTP','smtp-account',{'OAF_ENV':'testing'},exact_target=True)


@pytest.mark.parametrize('text,environment', [
    ('',{'OAF_ENV':'testing'}), ('bad private-toml',{'OAF_ENV':'testing'}),
    (configuration_text().replace('testing','development'),{'OAF_ENV':'testing'}),
    (configuration_text()+'password="private"\n',{'OAF_ENV':'testing'}),
    (configuration_text()+'recipient="other@example.com"\n',{'OAF_ENV':'testing'}),
    (configuration_text().replace('starttls','plain'),{'OAF_ENV':'testing'}),
    (configuration_text().replace('port=587','port=true'),{'OAF_ENV':'testing'}),
    (configuration_text().replace('sender@example.com','bad'),{'OAF_ENV':'testing'}),
    (configuration_text(),{'OAF_ENV':'development'}),
    (configuration_text(),{'OAF_ENV':'testing','OAF_SMTP_PASSWORD':'private'}),
    ('x'*8193,{'OAF_ENV':'testing'}),
])
def test_config_missing_invalid_conflicting_or_unsafe_never_reads_credentials(tmp_path,text,environment):
    path = tmp_path/'contact.toml'
    if text:
        path.write_text(text,encoding='utf-8')
    provider = Mock(return_value='synthetic-password')
    with pytest.raises(mail.DeliveryUnavailable) as caught:
        mail.load_contact_config('testing',local_config_path=path,environ=environment,credential_loader=provider)
    assert not str(caught.value)
    provider.assert_not_called()


def test_missing_protected_credential_is_sanitized(tmp_path):
    path=tmp_path/'contact.toml'
    path.write_text(configuration_text(),encoding='utf-8')
    provider=Mock(side_effect=RuntimeError('private-credential-details'))
    with pytest.raises(mail.DeliveryUnavailable) as caught:
        mail.load_contact_config('testing',local_config_path=path,environ={'OAF_ENV':'testing'},credential_loader=provider)
    assert not str(caught.value)


def test_redirected_contact_config_is_rejected_before_open_or_credentials(tmp_path, monkeypatch):
    from pathlib import Path
    path = tmp_path/'contact.toml'
    provider = Mock()
    original = Path.is_symlink
    monkeypatch.setattr(Path,'is_symlink',lambda candidate:candidate==path or original(candidate))
    with pytest.raises(mail.DeliveryUnavailable):
        mail.load_contact_config('testing',local_config_path=path,environ={'OAF_ENV':'testing'},credential_loader=provider)
    provider.assert_not_called()


def test_runtime_factory_installs_lazy_contact_sender_without_opening_mail_or_database(monkeypatch):
    settings = SimpleNamespace(profile='testing',url='synthetic-no-connection')
    engine, sender, loader = Mock(), Mock(return_value=None), Mock()
    monkeypatch.setattr(api,'load_testing_database_config',lambda:settings)
    monkeypatch.setattr(api,'create_engine',Mock(return_value=engine))
    monkeypatch.setattr(api.event,'listen',Mock())
    factory = Mock(return_value=sender)
    monkeypatch.setattr(mail,'ConfiguredSMTP',factory)
    monkeypatch.setattr(mail,'load_contact_config',loader)
    app = api.create_app(expected_profile='testing',recognition_secret=SECRET,public_origin=ORIGIN)
    factory.assert_called_once_with('testing')
    loader.assert_not_called()
    assert not engine.mock_calls
    client = app.test_client()
    csrf = client.get('/api/contact/session',base_url=ORIGIN).json['csrf_token']
    assert post((app,client,csrf)).status_code == 200
    sender.assert_called_once()
    loader.assert_not_called()
    assert not engine.mock_calls
