"""HTTPS startup with Flask in-process clients and mocked TLS/server dependencies."""
import migration_offline as isolation
isolation.require_early_registration()

from contextlib import nullcontext
import importlib
import ssl
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.engine import URL

from oaf_website import local_testing as local, local_testing_https as host, state_requests as api
from oaf_website import confirmation_outbox as outbox
from oaf_website.database_config import DatabaseConfig
from test_notification_delivery import Model, SECRET

ORIGIN = "https://testing.example.invalid"
PAGE = ORIGIN + "/gramanna.html"
ARGS = ["--environment", "testing", "--public-origin", ORIGIN, "--confirmation-page", PAGE,
        "--tls-certificate", "C:/synthetic/certificate.pem", "--tls-private-key", "C:/synthetic/key.pem"]


@pytest.fixture
def factory(monkeypatch):
    model = Model()
    config = DatabaseConfig("testing", URL.create("postgresql+psycopg", username="oaf_website_test_app",
        password="synthetic", host="127.0.0.1", port=5432, database="oaf_website_test"))
    loader = Mock(return_value=config)
    key = Mock(return_value=SECRET)
    creator, listener = Mock(return_value=model), Mock()
    forbidden = Mock(side_effect=AssertionError("No provider or processor during startup"))
    monkeypatch.setattr(api, "load_testing_database_config", loader)
    monkeypatch.setattr(api, "load_database_config", forbidden)
    monkeypatch.setattr(api, "create_engine", creator)
    monkeypatch.setattr(api.event, "listen", listener)
    monkeypatch.setattr(local, "recognition_secret", key)
    monkeypatch.setattr(outbox.ConfirmationDispatcher, "process", forbidden)
    monkeypatch.setattr(outbox.BrevoAdapter, "submit", forbidden)
    return SimpleNamespace(model=model, loader=loader, key=key, creator=creator,
                           listener=listener, forbidden=forbidden)


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("page_path", ["/gramanna.html", "/confirm-email.html"])
def test_factory_persistent_key_testing_identity_allowlist_and_no_processing(factory, enabled, page_path):
    options = dict(confirmation_enabled=True) if enabled else {}
    app = local.testing_https_app(public_origin=ORIGIN, confirmation_page=ORIGIN + page_path, **options)
    factory.key.assert_called_once_with(require_existing=True)
    factory.loader.assert_called_once_with()
    assert app.extensions["state_requests_engine"] is factory.model
    assert factory.listener.call_args.args[:2] == (factory.model, "checkout")
    connect = factory.creator.call_args.kwargs["connect_args"]
    assert connect["require_auth"] == "scram-sha-256"
    factory.forbidden.assert_not_called()
    assert not factory.model.statements  # Building never connects, mutates or processes.
    public = {r.rule.lstrip("/") for r in app.url_map.iter_rules() if r.endpoint.startswith("public_")}
    assert public == set(local.PUBLIC_FILES)
    client = app.test_client()
    before = repr(factory.model.records)
    for path in ("/confirm-email.html", "/assets/email-confirmation.js", "/gramanna.html"):
        result = client.get(path, base_url=ORIGIN)
        assert result.status_code == 200
        assert result.headers['Cache-Control'] == 'no-store'
    assert repr(factory.model.records) == before
    assert not factory.model.statements  # A page/scanner GET cannot consume a token.
    session = client.get("/api/notifications/session", base_url=ORIGIN)
    assert session.json["confirmation_enabled"] is enabled
    cookie = session.headers["Set-Cookie"]
    assert cookie.startswith("__Host-oaf-state-browser=")
    assert all(value in cookie for value in ("Secure", "HttpOnly", "SameSite=Lax", "Path=/"))
    assert "Domain=" not in cookie
    for path in ("/config/local/private", "/.git/config", "/oaf_website/brevo.py", "/docs/WORKFLOW.md"):
        assert client.get(path, base_url=ORIGIN).status_code == 404
    if not enabled:
        before = repr(factory.model.records)
        for path, body in (("confirmation", {"email": "synthetic@example.invalid"}),
                           ("confirm", {"token": "a" * 64})):
            result = client.post("/api/notifications/" + path, base_url=ORIGIN, json=body,
                headers={"Origin": ORIGIN, "X-CSRF-Token": session.json["csrf_token"]})
            assert result.status_code == 503
        assert repr(factory.model.records) == before


@pytest.mark.parametrize("origin,page", [
    ("http://127.0.0.1", "http://127.0.0.1/gramanna.html"),
    (ORIGIN, "http://testing.example.invalid/gramanna.html"),
    (ORIGIN + ":5443", ORIGIN + ":5443/gramanna.html"),
    (ORIGIN, "https://other.example.invalid/gramanna.html"),
    (ORIGIN, PAGE + "#private"), (ORIGIN, PAGE + "?private=x"),
    ("https://-invalid.example", "https://-invalid.example/gramanna.html"),
    ("https://bad..example", "https://bad..example/gramanna.html"),
    (ORIGIN + "/", PAGE), (ORIGIN + "/path", ORIGIN + "/path/gramanna.html"),
    ("https://user:private@testing.example.invalid", "https://user:private@testing.example.invalid/gramanna.html"),
    (None, PAGE), (ORIGIN, None), (ORIGIN, "https://testing.example.invalid/")])
def test_invalid_origin_page_rejected_before_protected_loads(factory, origin, page):
    with pytest.raises(ValueError):
        local.testing_https_app(public_origin=origin, confirmation_page=page)
    factory.key.assert_not_called()
    factory.loader.assert_not_called()
    factory.creator.assert_not_called()


@pytest.mark.parametrize('page', [
    'https://other.example.invalid/confirm-email.html',
    ORIGIN + ':5443/confirm-email.html',
    ORIGIN + '/confirm-email.html?private=x',
    ORIGIN + '/confirm-email.html#private',
    ORIGIN + '/nested/confirm-email.html',
])
def test_dedicated_page_still_requires_exact_configured_origin_before_runtime_access(factory, page):
    with pytest.raises(ValueError):
        local.testing_https_app(public_origin=ORIGIN, confirmation_page=page)
    factory.key.assert_not_called()
    factory.loader.assert_not_called()
    factory.creator.assert_not_called()


@pytest.mark.parametrize("enabled", [None, 0, 1, "true", []])
def test_invalid_activation_precedes_protected_access(factory, enabled):
    with pytest.raises(ValueError):
        local.testing_https_app(public_origin=ORIGIN, confirmation_page=PAGE, confirmation_enabled=enabled)
    factory.key.assert_not_called()
    factory.loader.assert_not_called()


@pytest.mark.parametrize("environment", ["development", "production", "Testing", ""])
def test_https_never_falls_back_from_testing(factory, monkeypatch, environment):
    monkeypatch.setenv("OAF_ENV", environment)
    with pytest.raises(ValueError):
        local.testing_https_app(public_origin=ORIGIN, confirmation_page=PAGE)
    factory.key.assert_not_called()
    factory.loader.assert_not_called()


def test_explicit_standard_port_origin_is_compatible(factory):
    local.testing_https_app(public_origin=ORIGIN + ":443", confirmation_page=ORIGIN + ":443/gramanna.html")
    factory.key.assert_called_once_with(require_existing=True)


def test_https_session_keeps_server_origin_and_browser_csrf_protections(factory):
    app = local.testing_https_app(public_origin=ORIGIN, confirmation_page=PAGE, confirmation_enabled=True)
    client = app.test_client()
    session = client.get("/api/notifications/session", base_url=ORIGIN)
    path = "/api/notifications/confirmation"
    body = {"email": "synthetic@example.invalid"}
    csrf = session.json["csrf_token"]
    for headers in ({"Origin": ORIGIN}, {"Origin": "https://other.example.invalid", "X-CSRF-Token": csrf},
                    {"Origin": ORIGIN, "X-CSRF-Token": csrf, "Sec-Fetch-Site": "cross-site"}):
        assert client.post(path, base_url=ORIGIN, json=body, headers=headers).status_code == 403
    assert not factory.model.statements
    result = client.post(path, base_url=ORIGIN, json=body,
                         headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "Sec-Fetch-Site": "same-origin"})
    assert result.status_code == 200
    assert result.headers["Cache-Control"] == "no-store"
    assert result.headers["X-Content-Type-Options"] == "nosniff"
    factory.forbidden.assert_not_called()


def test_tls_requires_existing_distinct_absolute_files_and_sanitizes_errors(tmp_path, monkeypatch):
    certificate, key = tmp_path / "certificate.pem", tmp_path / "key.pem"
    certificate.write_text("synthetic invalid certificate")
    key.write_text("synthetic invalid key")
    creator = Mock()
    monkeypatch.setattr(host.ssl, "SSLContext", creator)
    for values in ((None, key), ("adhoc", key), ("relative.pem", key),
                   (certificate, certificate), (certificate, tmp_path / "missing.pem")):
        with pytest.raises(ValueError, match="Existing valid TLS"):
            host.tls_context(*values)
    creator.assert_not_called()
    context = creator.return_value
    context.load_cert_chain.side_effect = ssl.SSLError("synthetic-private-key-location")
    with pytest.raises(ValueError, match="^Existing valid TLS certificate and private key are required.$"):
        host.tls_context(certificate, key)
    assert context.minimum_version == ssl.TLSVersion.TLSv1_2


def test_tls_explicit_server_context_ignores_ambient_key_logging(tmp_path, monkeypatch):
    certificate, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    certificate.write_text("synthetic-certificate")
    key.write_text("synthetic-key")
    context = Mock()
    creator = Mock(return_value=context)
    monkeypatch.setattr(host.ssl, "SSLContext", creator)
    monkeypatch.setenv("SSLKEYLOGFILE", str(tmp_path / "must-not-exist"))
    assert host.tls_context(certificate, key) is context
    creator.assert_called_once_with(ssl.PROTOCOL_TLS_SERVER)
    assert context.load_cert_chain.call_args.args == (str(certificate), str(key))
    with pytest.raises(ValueError, match="Interactive TLS key passwords"):
        context.load_cert_chain.call_args.kwargs["password"]()
    assert context.minimum_version == ssl.TLSVersion.TLSv1_2
    assert not (tmp_path / "must-not-exist").exists()


@pytest.fixture
def startup(monkeypatch):
    engine = Mock()
    engine.connect.return_value = nullcontext()
    app = SimpleNamespace(extensions={"state_requests_engine": engine})
    factory, tls, maker = Mock(return_value=app), Mock(return_value=object()), Mock()
    monkeypatch.setattr(host, "testing_https_app", factory)
    monkeypatch.setattr(host, "tls_context", tls)
    monkeypatch.setattr(host, "make_server", maker)
    return SimpleNamespace(engine=engine, factory=factory, tls=tls, maker=maker)


@pytest.mark.parametrize("enabled", [False, True])
def test_explicit_startup_binds_loopback_443_without_reload_or_processor(startup, enabled, capsys):
    assert host.main(ARGS + (["--enable-confirmation"] if enabled else [])) == 0
    startup.factory.assert_called_once_with(public_origin=ORIGIN, confirmation_page=PAGE,
                                           confirmation_enabled=enabled)
    startup.engine.connect.assert_called_once_with()
    startup.maker.assert_called_once_with("127.0.0.1", 443, startup.factory.return_value,
        threaded=True, ssl_context=startup.tls.return_value, request_handler=host.QuietHandler)
    startup.maker.return_value.serve_forever.assert_called_once_with()
    startup.maker.return_value.server_close.assert_called_once_with()
    startup.engine.dispose.assert_called_once_with()
    assert "processor OFF" in capsys.readouterr().out


@pytest.mark.parametrize("phase", ["tls", "factory", "identity", "bind", "serve", "close", "dispose"])
def test_startup_failures_are_private_and_cleanup_is_attempted(startup, phase, capsys):
    target = {"tls": startup.tls, "factory": startup.factory, "identity": startup.engine.connect,
              "bind": startup.maker, "serve": startup.maker.return_value.serve_forever,
              "close": startup.maker.return_value.server_close, "dispose": startup.engine.dispose}[phase]
    target.side_effect = RuntimeError("synthetic-private-key-path-database-password")
    assert host.main(ARGS) == 2
    output = capsys.readouterr()
    assert "BLOCKED:" in output.out and "synthetic-private" not in output.out + output.err
    import json
    from oaf_website.notification_dispatch import validate_failure
    record = json.loads(output.err.splitlines()[0].split(": ", 1)[1])
    first = validate_failure(record["first_failure"])
    assert first["operation"] == {"tls":"tls_context", "factory":"application_startup",
        "identity":"database_checkout", "bind":"server_bind", "serve":"server_execution",
        "close":"dispose", "dispose":"dispose"}[phase]
    assert first["exception_class"] == "RuntimeError"
    if phase in {"identity", "bind", "serve", "close", "dispose"}:
        startup.engine.dispose.assert_called_once_with()
    if phase == "identity": startup.maker.assert_not_called()


def test_invalid_page_and_environment_stop_before_tls_or_runtime(startup, monkeypatch, capsys):
    assert host.main([arg.replace(PAGE, "http://testing.example.invalid/gramanna.html") for arg in ARGS]) == 2
    monkeypatch.setenv("OAF_ENV", "development")
    assert host.main(ARGS) == 2
    assert host.main(ARGS + ["--unknown", "synthetic-private"]) == 2
    assert "synthetic-private" not in capsys.readouterr().out
    startup.tls.assert_not_called()
    startup.factory.assert_not_called()
    startup.maker.assert_not_called()


def test_module_import_does_not_start_host_or_load_tls(startup):
    # Reload only the definition module, keeping the underlying runtime forbidden.
    importlib.reload(local)
    startup.tls.assert_not_called()
    startup.factory.assert_not_called()
    startup.maker.assert_not_called()
