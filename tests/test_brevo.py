"""Synthetic adapter/configuration/template checks under early offline isolation."""
import migration_offline as isolation
isolation.require_early_registration()

from dataclasses import replace
import json
import ssl
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from oaf_website import brevo as b, notification_messages as messages
from oaf_website.notifications import UnsubscribeCapabilities
from test_notification_delivery import payload, SECRET

KEY = "synthetic-brevo-key-checkpoint6g2"
PAGE = "https://website.example/gramanna.html"
MID = "<offline-message-1@relay.example>"
CONFIG = b.BrevoConfig("testing", KEY)
ACCEPTED = b.ProviderOutcome("provider_accepted", MID)


def response(status=201, data=None, **changes):
    values = dict(status=status, content_type="application/json", body=json.dumps(
        {"messageId": MID} if data is None else data).encode())
    values.update(changes)
    return b.ProviderResponse(**values)


def test_explicit_protected_loader_and_no_import_time_loading(monkeypatch):
    loader = Mock(return_value=KEY)
    monkeypatch.setattr(b, "_windows_password", loader)
    env = {"OAF_ENV": "development"}
    config = b.load_brevo_config("development", credential_account="brevo-owner", environ=env)
    loader.assert_called_once_with("OAF Website/development/Brevo/ApiKey", "brevo-owner", env, exact_target=True)
    assert config.api_key == KEY and KEY not in repr(config)
    loader.reset_mock()
    config = b.load_brevo_config("testing", credential_account="brevo-owner",
                                 environ={"OAF_ENV": "testing"}, credential_loader=loader)
    assert config.environment == "testing"
    assert loader.call_args.args[0] == "OAF Website/testing/Brevo/ApiKey"


@pytest.mark.parametrize("profile,env,account", [
    ("production", {"OAF_ENV": "production"}, "owner"),
    ("testing", {}, "owner"), ("testing", {"OAF_ENV": "development"}, "owner"),
    ("invalid", {"OAF_ENV": "invalid"}, "owner"),
    *[("testing", {"OAF_ENV": "testing", key: KEY}, "owner") for key in
      ["BREVO_API_KEY", "brevoKey", "SENDINBLUE_API_KEY", "OAF_BREVO_KEY", "DATABASE_URL", "PGHOST"]],
    *[("testing", {"OAF_ENV": "testing"}, value) for value in [None, 7, "", "a b", "a\n", "a"*129]],
])
def test_bad_configuration_rejected_before_credential_access(profile, env, account):
    loader = Mock(return_value=KEY)
    with pytest.raises(b.BrevoConfigurationError) as error:
        b.load_brevo_config(profile, credential_account=account, environ=env, credential_loader=loader)
    loader.assert_not_called()
    assert KEY not in str(error.value) and error.value.__context__ is None


@pytest.mark.parametrize("key", [None, 7, "", "x"*15, "x"*257, "key\r\nsecret-key-here", "x"*16+"?", "x"*16+" "])
def test_missing_or_invalid_key_and_loader_errors_are_sanitized(key):
    with pytest.raises(b.BrevoConfigurationError) as error:
        b.load_brevo_config("testing", credential_account="owner", environ={"OAF_ENV":"testing"},
                            credential_loader=lambda *a, **kw: key)
    assert error.value.__context__ is None
    loader = Mock(side_effect=RuntimeError(KEY))
    with pytest.raises(b.BrevoConfigurationError) as error:
        b.load_brevo_config("testing", credential_account="owner", environ={"OAF_ENV":"testing"}, credential_loader=loader)
    assert KEY not in str(error.value) and error.value.__context__ is None


@pytest.mark.parametrize("env", [None, [], "production", "unexpected"])
def test_config_never_enables_production(env):
    with pytest.raises(b.BrevoConfigurationError): b.BrevoConfig(env, KEY)


def test_actual_environment_authority_is_explicit_and_not_a_key_source(monkeypatch):
    monkeypatch.setattr(b.os, "environ", {"OAF_ENV":"testing", "BREVO_API_KEY":KEY})
    loader=Mock()
    with pytest.raises(b.BrevoConfigurationError):
        b.load_brevo_config("testing", credential_account="owner", credential_loader=loader)
    loader.assert_not_called()


@pytest.mark.parametrize("outcome,mid", [("other", None), ("provider_rejected", MID),
    ("provider_accepted", 1), ("provider_accepted", "bad\nsecret"),
    ("provider_accepted", "<"+"a"*201+"@b>")])
def test_outcomes_only_contain_allowlisted_metadata(outcome, mid):
    with pytest.raises(ValueError): b.ProviderOutcome(outcome, mid)


@pytest.mark.parametrize("status,expected", [(201,"provider_accepted"), (429,"retryable_rejection"),
    *[(code,"provider_rejected") for code in [400,401,402,403,404,405,406,409,410,413,415,422]],
    *[(code,"submission_unknown") for code in [200,202,204,301,302,307,308,408,425,500,502,503,504]],
])
def test_provider_statuses_classified_without_claiming_mailbox_delivery(status, expected):
    data={"messageId":MID} if status==201 else {"code":"invalid_parameter", "message":KEY}
    result=b.classify_response(response(status,data),KEY)
    assert result.outcome==expected
    assert result.message_id==(MID if status==201 else None)
    assert KEY not in repr(result)


@pytest.mark.parametrize("value", [
    None, [], replace(response(),status=True), replace(response(),body="not bytes"),
    replace(response(),body=b"x"*(b.MAX_RESPONSE+1)), replace(response(),content_type=1),
    replace(response(),content_type="text/html"), replace(response(),content_type="application/json; charset=ascii"),
    *[replace(response(),body=body) for body in [b"bad",b"\xff",b"[]",b"null",b"NaN",
        b'{"messageId":"one","messageId":"two"}',b'{"messageId":NaN}', b"["*1000+b"]"*1000]],
    *[response(201,body) for body in [{}, {"messageIds":[MID]}, {"messageId":MID,"extra":1},
        {"messageId":None}, {"messageId":KEY}, {"messageId":"<"+KEY+"@example>"},
        {"messageId":"bad\nvalue"}, {"messageId":"plain-id"}]],
    *[response(400,body) for body in [{}, {"code":"bad","message":""},
        {"code":1,"message":"error"}, {"code":"BAD","message":"error"},
        {"code":"a"*65,"message":"error"}, {"code":"bad","message":1},
        {"code":"bad","message":"a"*2049}, {"code":"bad","message":"error","extra":1}]],
])
def test_invalid_or_oversized_responses_are_uncertain_and_never_automatic_retries(value):
    assert b.classify_response(value,KEY)==b.ProviderOutcome("submission_unknown")


def test_accepted_response_charset_and_no_response_body_in_repr():
    value=replace(response(),content_type="Application/JSON; charset=UTF-8")
    assert b.classify_response(value,KEY)==ACCEPTED
    assert MID not in repr(value)


class Connection:
    def __init__(self, phase=None, error=None):
        self.phase,self.error=phase,error or TimeoutError(KEY)
        self.calls=[]
        self.sock=SimpleNamespace(settimeout=lambda timeout:self.hit("timeout",timeout))
    def hit(self,phase,*values):
        self.calls.append((phase,values))
        if self.phase==phase: raise self.error
    def connect(self): self.hit("connect")
    def request(self,*args,**kw): self.hit("request",args,kw)
    def getresponse(self):
        self.hit("response")
        return SimpleNamespace(status=201,getheader=lambda key,default:self.header(key,default),read=self.read)
    def header(self,key,default):
        self.hit("header",key)
        return self.headers.get(key,default)
    def read(self,limit):
        self.hit("read",limit)
        return json.dumps({"messageId":MID}).encode()
    def close(self): self.hit("close")
    headers={"Content-Type":"application/json"}


@pytest.mark.parametrize("phase,expected", [("connect","not_submitted"),("timeout","not_submitted"),
    ("request","submission_unknown"),("response","submission_unknown"),("header","submission_unknown"),
    ("read","submission_unknown"),("close","provider_accepted"),(None,"provider_accepted")])
@pytest.mark.parametrize("error", [TimeoutError(KEY),ConnectionError(KEY),ssl.SSLError(KEY),OSError(KEY)])
def test_https_phase_failures_and_no_automatic_retries(monkeypatch,phase,expected,error):
    connection=Connection(phase,error)
    factory=Mock(return_value=connection)
    monkeypatch.setattr(b,"HTTPSConnection",factory)
    result=b.BrevoHTTPS()(KEY,b"{}")
    assert result.outcome==expected and KEY not in repr(result)
    assert factory.call_count==1
    assert sum(phase=="request" for phase,_ in connection.calls)<=1
    assert connection.calls[-1][0]=="close"


def test_transport_destination_tls_timeouts_size_and_ambient_isolation(monkeypatch):
    for name in ["HTTPS_PROXY","HTTP_PROXY","ALL_PROXY","NETRC","BREVO_API_KEY","SSLKEYLOGFILE"]:
        monkeypatch.setenv(name,"synthetic-untrusted-ambient-value")
    connection=Connection()
    factory=Mock(return_value=connection)
    monkeypatch.setattr(b,"HTTPSConnection",factory)
    assert b.BrevoHTTPS()(KEY,b"{}")==ACCEPTED
    args,kw=factory.call_args
    assert args==(b.HOST,443) and kw["timeout"]==5
    assert kw["context"].verify_mode==ssl.CERT_REQUIRED and kw["context"].check_hostname
    assert kw["context"].keylog_filename is None
    assert ("timeout",(10,)) in connection.calls and ("read",(8193,)) in connection.calls
    request=next(values for phase,values in connection.calls if phase=="request")
    assert request[0]==("POST","/v3/smtp/email")
    assert request[1]["headers"]=={"api-key":KEY,"Content-Type":"application/json","Accept":"application/json","Accept-Encoding":"identity"}


def test_tls_context_creation_failure_and_compressed_response_are_safe(monkeypatch):
    original_context=b.ssl.SSLContext
    monkeypatch.setattr(b.ssl,"SSLContext",Mock(side_effect=RuntimeError(KEY)))
    assert b.BrevoHTTPS()(KEY,b"{}").outcome=="not_submitted"
    monkeypatch.setattr(b.ssl,"SSLContext",original_context)
    connection=Connection()
    connection.headers={"Content-Encoding":"gzip"}
    monkeypatch.setattr(b,"HTTPSConnection",Mock(return_value=connection))
    assert b.BrevoHTTPS()(KEY,b"{}").outcome=="submission_unknown"
    assert not any(phase=="read" for phase,_ in connection.calls)


@pytest.mark.parametrize("template", ["verification","android","ios"])
def test_fixed_request_identities_and_platform_templates(template):
    transport=Mock(return_value=response())
    if template=="verification":
        message=messages.verification_message("a"*64,PAGE)
        assert "#confirm-email="+"a"*64 in message.text
        assert "24 hours" in message.text
    else:
        event=payload(template)
        message=messages.release_message(event,"b"*64,UnsubscribeCapabilities(SECRET),PAGE)
        assert event["release_url"] in message.text and event["release_url"] in message.html
        assert ("Android" if template=="android" else "Apple iOS") in message.subject
        assert PAGE.replace('/gramanna.html','/manage-notifications.html')+"#unsubscribe=" in message.text
        token=message.text.split("#unsubscribe=")[1].split()[0]
        assert UnsubscribeCapabilities(SECRET).read(token)=="b"*64
    assert "a"*64 not in repr(message) and "b"*64 not in repr(message)
    assert b.BrevoAdapter(CONFIG,transport=transport).submit("User@example.invalid",message)==ACCEPTED
    key,body=transport.call_args.args
    data=json.loads(body)
    assert key==KEY and KEY not in body.decode()
    assert data["sender"]=={"name":"Ovis Alms Foundation","email":"communications@updates.ovisalmsfoundation.org"}
    assert data["replyTo"]=={"email":"contact@ovisalmsfoundation.org"}
    assert data["to"]==[{"email":"user@example.invalid"}]
    assert set(data)=={"sender","replyTo","to","subject","textContent","htmlContent"}


@pytest.mark.parametrize("result", [None, {}, RuntimeError(KEY), b.ProviderOutcome("not_submitted"),
    b.ProviderOutcome("provider_accepted","<"+KEY+"@example>"), ACCEPTED])
def test_injected_transport_returns_only_safe_outcomes(result):
    transport=Mock(side_effect=result) if isinstance(result,Exception) else Mock(return_value=result)
    actual=b.BrevoAdapter(CONFIG,transport=transport).submit("a@example.invalid",messages.verification_message("a"*64,PAGE))
    expected=result if isinstance(result,b.ProviderOutcome) and result.message_id!="<"+KEY+"@example>" else b.ProviderOutcome("submission_unknown")
    assert actual==expected and KEY not in repr(actual)
    assert transport.call_count==1


def test_default_transport_and_invalid_adapter_configuration():
    assert isinstance(b.BrevoAdapter(CONFIG).transport,b.BrevoHTTPS)
    with pytest.raises(b.BrevoConfigurationError): b.BrevoAdapter(None)


@pytest.mark.parametrize("page", [None, 3, "http://website.example/gramanna.html", "https://a:b@website.example/gramanna.html",
    "https://a@website.example/gramanna.html", "https://website.example:444/gramanna.html",
    "https://website.example:bad/gramanna.html", "https://website.example/gramanna.html?secret=x",
    "https://website.example/gramanna.html#secret", "https://website.example", "https://website.example//bad%0a.html",
    "https:///gramanna.html", "https://website.example/gramanna.html\n", "https://website.example/../gramanna.html"])
def test_untrusted_confirmation_and_withdrawal_pages_fail_safely(page):
    with pytest.raises(ValueError) as error: messages.secure_page(page)
    assert error.value.__context__ is None
    with pytest.raises(ValueError) as error: messages.secure_confirmation_page(page)
    assert error.value.__context__ is None


@pytest.mark.parametrize('authority', ['website.example', 'website.example:443'])
@pytest.mark.parametrize('path', ['/gramanna.html', '/confirm-email.html'])
def test_confirmation_destination_is_dedicated_with_exact_legacy_configuration_compatibility(authority, path):
    page = 'https://' + authority + path
    destination = 'https://' + authority + '/confirm-email.html'
    assert messages.secure_confirmation_page(page) == destination
    message = messages.verification_message('a' * 64, page)
    assert destination + '#confirm-email=' + 'a' * 64 in message.text
    assert destination + '#confirm-email=' + 'a' * 64 in message.html
    assert '/gramanna.html' not in message.text + message.html
    # The withdrawal page contract is independently restricted to its old path.
    if path == '/confirm-email.html':
        with pytest.raises(ValueError): messages.secure_page(page)
        with pytest.raises(ValueError):
            messages.release_message(payload(), 'b' * 64, UnsubscribeCapabilities(SECRET), page)


@pytest.mark.parametrize('page', [
    'http://website.example/confirm-email.html',
    'https://website.example:5443/confirm-email.html',
    'https://user@website.example/confirm-email.html',
    'https://website.example/confirm-email.html?token=private',
    'https://website.example/confirm-email.html#confirm-email=private',
    'https://website.example/confirm-email.html?',
    'https://website.example/confirm-email.html#',
    'https://website.example/sub/confirm-email.html',
    'https://website.example/../confirm-email.html',
    'https://website.example/%63onfirm-email.html',
    'https://website.example//confirm-email.html',
    'https://website.example/CONFIRM-EMAIL.html',
    'https://website.example/confirm-email.html/',
    'https://website.example/confirm-email.html\n',
    'https://-bad.example/confirm-email.html',
    'https://bad..example/confirm-email.html',
])
def test_confirmation_path_extension_never_accepts_other_destinations(page):
    with pytest.raises(ValueError): messages.secure_confirmation_page(page)
    with pytest.raises(ValueError): messages.verification_message('a' * 64, page)


@pytest.mark.parametrize("token", [None, 3, "", "A"*64, "f"*63, "f"*64+"\n"])
def test_verification_tokens_keep_existing_strict_purpose_and_shape(token):
    with pytest.raises(ValueError): messages.verification_message(token,PAGE)


@pytest.mark.parametrize("changes", [{"content_version":"arbitrary-copy"}, {"release_id":7},
    {"release_url":7}, {"release_id":"a"*151}, {"platform":"web"},
    {"release_url":"https://evil.example/app"}, {"release_id":"invalid"}])
def test_no_invented_store_urls_or_general_announcements(changes):
    with pytest.raises(ValueError): messages.release_message(payload(**changes),"a"*64,UnsubscribeCapabilities(SECRET),PAGE)


@pytest.mark.parametrize("subscription", [None, 7, "bad", "A"*64])
def test_release_withdrawal_is_bound_to_original_lifecycle(subscription):
    with pytest.raises(ValueError): messages.release_message(payload(),subscription,UnsubscribeCapabilities(SECRET),PAGE)


@pytest.mark.parametrize("variable", ["SSL_CERT_FILE", "SSL_CERT_DIR"])
def test_ambient_custom_ca_files_fail_before_connection(monkeypatch, variable):
    monkeypatch.setenv(variable,"synthetic-untrusted-file")
    factory=Mock()
    monkeypatch.setattr(b,"HTTPSConnection",factory)
    assert b.BrevoHTTPS()(KEY,b"{}").outcome=="not_submitted"
    factory.assert_not_called()


@pytest.mark.parametrize("status", [202, 302, 500])
def test_unexpected_status_preserves_safe_provider_id_for_later_reconciliation(status):
    assert b.classify_response(response(status),KEY)==b.ProviderOutcome("submission_unknown",MID)


@pytest.mark.parametrize("status", [99, 600])
def test_invalid_status_cannot_preserve_untrusted_identifier(status):
    assert b.classify_response(response(status),KEY)==b.ProviderOutcome("submission_unknown")


@pytest.mark.parametrize("setting,value", [("PYTHON_KEYRING_BACKEND","untrusted.backend"),
    ("UNTRUSTED_KEYRING_PROPERTY_USERNAME","untrusted-account")])
def test_existing_loader_rejects_credential_backend_overrides_before_native_access(setting,value):
    with pytest.raises(b.BrevoConfigurationError) as error:
        b.load_brevo_config("testing",credential_account="owner",environ={"OAF_ENV":"testing",setting:value})
    assert error.value.__context__ is None
    assert not isolation.ATTEMPTS


@pytest.mark.parametrize("content_type", ["application /json", "ap plication/json"])
def test_malformed_media_types_cannot_be_normalized_into_acceptance(content_type):
    assert b.classify_response(replace(response(),content_type=content_type),KEY)==b.ProviderOutcome("submission_unknown")


def test_withdrawal_link_requires_the_existing_gramanna_page():
    with pytest.raises(ValueError):
        messages.release_message(payload(),"a"*64,UnsubscribeCapabilities(SECRET),"https://website.example/contact.html")
