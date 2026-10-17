"""DEVELOPMENT activation checks with synthetic secrets and early offline guards."""

import migration_offline as isolation
isolation.require_early_registration()

from pathlib import Path
import sys
import traceback
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, call

import pytest
from sqlalchemy.engine import URL

from oaf_website import database_config as database
from oaf_website import integrations, interest_reporting, local_development as development
from oaf_website import notifications, state_requests
from oaf_website.state_request_schema import STATE_CODES

SUBMISSION = "1" * 64
REPORTING = "2" * 64
SECRET = b"s" * 32
METADATA = '[development]\nclient_id = "gramanna"\n'
PRIVATE_MARKER = "synthetic-private-marker"
STATE_PATH = integrations.PREFIX + "/state-requests"
NOTIFICATION_PATH = integrations.PREFIX + "/notifications"
REPORT_PATH = integrations.PREFIX + "/interest-summary"


@pytest.fixture
def metadata_path(tmp_path):
    path = tmp_path / "integrations.toml"
    path.write_text(METADATA, encoding="utf-8")
    return path


@pytest.fixture
def runtime(monkeypatch, metadata_path):
    # Replace the entire environment: never use inherited operational settings.
    monkeypatch.setattr(development.os, "environ", {"OAF_ENV": "development"})
    config = database.DatabaseConfig("development", URL.create(
        "postgresql+psycopg", username="oaf_website_app", password="synthetic-database-only",
        host="127.0.0.1", port=5432, database="oaf_website_dev",
    ))
    engine = SimpleNamespace(
        connect=Mock(side_effect=AssertionError("No database connections")),
        begin=Mock(side_effect=AssertionError("No database transactions")), dispose=Mock(),
    )
    db_loader, creator, listener = Mock(return_value=config), Mock(return_value=engine), Mock()
    recognition = Mock(return_value=SECRET)
    provider = Mock(side_effect=[SUBMISSION, REPORTING])
    original_loader = development.load_development_integration_config
    loader = Mock(side_effect=lambda: original_loader(local_config_path=metadata_path))
    monkeypatch.setattr(state_requests, "load_database_config", db_loader)
    monkeypatch.setattr(state_requests, "create_engine", creator)
    monkeypatch.setattr(state_requests.event, "listen", listener)
    monkeypatch.setattr(development, "recognition_secret", recognition)
    monkeypatch.setattr(development, "_windows_password", provider)
    monkeypatch.setattr(development, "load_development_integration_config", loader)
    result = SimpleNamespace(engine=engine, db_loader=db_loader, creator=creator, listener=listener,
                             recognition=recognition, provider=provider, loader=loader, path=metadata_path)
    yield result
    engine.connect.assert_not_called()
    engine.begin.assert_not_called()


@pytest.mark.parametrize("metadata", [METADATA, "invalid synthetic metadata"])
def test_ordinary_startup_ignores_integration_configuration(runtime, metadata):
    runtime.path.write_text(metadata, encoding="utf-8")
    app = development.development_app()
    runtime.loader.assert_not_called()
    runtime.provider.assert_not_called()
    runtime.recognition.assert_called_once_with()
    runtime.db_loader.assert_called_once_with(expected_profile="development")
    assert app.extensions["state_requests_engine"] is runtime.engine
    assert not any(rule.rule.startswith(integrations.PREFIX) for rule in app.url_map.iter_rules())
    client = app.test_client()
    assert client.get("/", base_url=development.ORIGIN).status_code == 200
    assert client.get("/api/state-requests/session", base_url=development.ORIGIN).status_code == 200
    assert client.get("/api/notifications/session", base_url=development.ORIGIN).status_code == 200
    assert client.post(STATE_PATH, base_url=development.ORIGIN).status_code == 404


def test_valid_activation_injects_existing_factory_without_connections(runtime):
    app = development.development_app(enable_integrations=True)
    routes = {rule.rule: rule.methods for rule in app.url_map.iter_rules()
              if rule.rule.startswith(integrations.PREFIX)}
    assert set(routes) == {STATE_PATH, NOTIFICATION_PATH, REPORT_PATH}
    assert "POST" in routes[STATE_PATH] and "POST" in routes[NOTIFICATION_PATH]
    assert "GET" in routes[REPORT_PATH]
    runtime.loader.assert_called_once_with()
    assert runtime.provider.call_args_list == [
        call(service, "gramanna", dict(development.os.environ), exact_target=True)
        for service in development.INTEGRATION_SERVICES
    ]
    runtime.recognition.assert_called_once_with()
    runtime.db_loader.assert_called_once_with(expected_profile="development")
    assert runtime.creator.call_args.kwargs["hide_parameters"] is True
    assert runtime.listener.call_args.args[1] == "checkout"


@pytest.mark.parametrize("metadata", [
    None, "", "[development]\nclient_id = '" + PRIVATE_MARKER,
    "[testing]\nclient_id = 'gramanna'", "[production]\nclient_id = 'gramanna'",
    "[development]", METADATA + "password = '" + PRIVATE_MARKER + "'",
    METADATA + "submission_credential = '" + SUBMISSION + "'",
    METADATA + "[testing]\nclient_id = 'gramanna'",
    "[development]\nclient_id = 1", "[development]\nclient_id = true",
    "[development]\nclient_id = ''", "[development]\nclient_id = '../client'",
    "[development]\nclient_id = 'GraManna'", "[development]\nclient_id = '" + "a" * 65 + "'",
    METADATA + "client_id = '" + PRIVATE_MARKER + "'",
])
def test_missing_or_invalid_requested_metadata_fails_before_secrets(runtime, metadata):
    if metadata is None:
        runtime.path.unlink()
    else:
        runtime.path.write_text(metadata, encoding="utf-8")
    with pytest.raises(integrations.IntegrationConfigurationError) as caught:
        development.development_app(enable_integrations=True)
    diagnostic = "".join(traceback.format_exception(caught.value))
    assert PRIVATE_MARKER not in diagnostic and SUBMISSION not in diagnostic
    assert caught.value.__context__ is None
    runtime.provider.assert_not_called()
    runtime.recognition.assert_not_called()
    runtime.db_loader.assert_not_called()
    runtime.creator.assert_not_called()


@pytest.mark.parametrize("permission", [0, 1])
@pytest.mark.parametrize("value", [None, "", "short", b"1" * 64, "A" * 64, "3" * 63, "3" * 65])
def test_invalid_permission_credentials_block_requested_startup(runtime, permission, value):
    values = [SUBMISSION, REPORTING]
    values[permission] = value
    runtime.provider.side_effect = values
    with pytest.raises(integrations.IntegrationConfigurationError):
        development.development_app(enable_integrations=True)
    runtime.recognition.assert_not_called()
    runtime.db_loader.assert_not_called()
    runtime.creator.assert_not_called()


@pytest.mark.parametrize("values", [(SUBMISSION, SUBMISSION), (SECRET.hex(), REPORTING),
                                   (SUBMISSION, SECRET.hex())])
def test_credentials_cannot_reuse_permissions_or_recognition_key(runtime, values):
    runtime.provider.side_effect = values
    with pytest.raises(integrations.IntegrationConfigurationError):
        development.development_app(enable_integrations=True)
    runtime.db_loader.assert_not_called()
    runtime.creator.assert_not_called()


@pytest.mark.parametrize("permission", [0, 1])
def test_credential_provider_errors_are_redacted(runtime, permission, capsys, caplog):
    runtime.provider.side_effect = ([RuntimeError(PRIVATE_MARKER)] if permission == 0
                                    else [SUBMISSION, database.DatabaseConfigurationError(PRIVATE_MARKER)])
    with pytest.raises(integrations.IntegrationConfigurationError) as caught:
        development.development_app(enable_integrations=True)
    assert PRIVATE_MARKER not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None
    assert capsys.readouterr() == ("", "") and PRIVATE_MARKER not in caplog.text
    runtime.recognition.assert_not_called()
    runtime.db_loader.assert_not_called()


@pytest.mark.parametrize("environment", [{}, {"OAF_ENV": "testing"}, {"OAF_ENV": "production"},
    {"OAF_ENV": "Development"}, {"OAF_ENV": "development", "OAF_INTEGRATIONS": "true"},
    {"OAF_ENV": "development", "OAF_REPORTING_CREDENTIAL": PRIVATE_MARKER},
    {"OAF_ENV": "development", "DATABASE_URL": PRIVATE_MARKER}])
def test_environment_restrictions_precede_config_and_credential_access(monkeypatch, metadata_path, environment):
    parser, provider = Mock(), Mock()
    monkeypatch.setattr(development.tomllib, "load", parser)
    with pytest.raises(database.DatabaseConfigurationError):
        development.load_development_integration_config(local_config_path=metadata_path,
                                                        environ=environment, credential_loader=provider)
    parser.assert_not_called()
    provider.assert_not_called()


@pytest.mark.parametrize("environment", [None, "testing", "production", "Development"])
def test_development_entry_point_rejects_environment_mismatch(runtime, environment):
    development.os.environ.clear()
    if environment is not None:
        development.os.environ["OAF_ENV"] = environment
    with pytest.raises(RuntimeError, match="requires OAF_ENV=development"):
        development.development_app(enable_integrations=True)
    runtime.loader.assert_not_called()
    runtime.recognition.assert_not_called()
    runtime.db_loader.assert_not_called()


@pytest.mark.parametrize("location", ["workspace", "config", "directory", "file"])
def test_redirected_configuration_is_rejected(monkeypatch, metadata_path, location):
    target = {"workspace": development.ROOT, "config": development.ROOT / "config",
              "directory": metadata_path.parent, "file": metadata_path}[location]
    original = Path.lstat

    def redirected(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path == target:
            return SimpleNamespace(st_file_attributes=development.stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return info

    provider = Mock()
    monkeypatch.setattr(Path, "lstat", redirected)
    with pytest.raises(integrations.IntegrationConfigurationError, match="Redirected"):
        development.load_development_integration_config(local_config_path=metadata_path,
            environ={"OAF_ENV": "development"}, credential_loader=provider)
    provider.assert_not_called()


@pytest.fixture
def synthetic_vault(monkeypatch):
    entries = {}
    read = Mock(side_effect=lambda target: entries.get(target))
    fallback = Mock(side_effect=AssertionError("Credential fallback is prohibited"))

    class Credential(dict):
        def __init__(self, service, value):
            super().__init__(TargetName=service, UserName="gramanna", Type=1, Persist=2)
            self.value = value

    class Backend:
        priority = 5
        _read_credential = staticmethod(read)
        get_credential = staticmethod(fallback)

    module = ModuleType("keyring.backends.Windows")
    module.WinVaultKeyring = Backend
    monkeypatch.setitem(sys.modules, module.__name__, module)
    for service, value in zip(development.INTEGRATION_SERVICES, (SUBMISSION, REPORTING)):
        entries[service] = Credential(service, value)
    return SimpleNamespace(entries=entries, read=read, fallback=fallback)


def test_default_provider_reads_only_exact_environment_targets(metadata_path, synthetic_vault):
    config = development.load_development_integration_config(local_config_path=metadata_path,
                                                             environ={"OAF_ENV": "development"})
    assert config == integrations.IntegrationConfig("development", "gramanna", SUBMISSION, REPORTING)
    assert SUBMISSION not in repr(config) and REPORTING not in repr(config)
    assert synthetic_vault.read.call_args_list == [call(service) for service in development.INTEGRATION_SERVICES]
    synthetic_vault.fallback.assert_not_called()


@pytest.mark.parametrize("permission", [0, 1])
@pytest.mark.parametrize("invalid", ["missing", "account", "target", "type", "persistence"])
def test_protected_target_mismatch_never_uses_fallback(metadata_path, synthetic_vault, permission, invalid):
    service = development.INTEGRATION_SERVICES[permission]
    credential = synthetic_vault.entries[service]
    # A plausible alternate compound target must never rescue a bad exact entry.
    synthetic_vault.entries["gramanna@" + service] = credential.copy()
    if invalid == "missing":
        del synthetic_vault.entries[service]
    else:
        field, value = {"account": ("UserName", "other-client"), "target": (
            "TargetName", service.replace("development", "testing")),
            "type": ("Type", 2), "persistence": ("Persist", 3)}[invalid]
        credential[field] = value
    with pytest.raises(integrations.IntegrationConfigurationError):
        development.load_development_integration_config(local_config_path=metadata_path,
                                                        environ={"OAF_ENV": "development"})
    assert synthetic_vault.read.call_args_list == [call(target) for target in
                                                  development.INTEGRATION_SERVICES[:permission + 1]]
    synthetic_vault.fallback.assert_not_called()


def test_activated_http_routes_keep_permission_separation_and_public_security(runtime, monkeypatch):
    monkeypatch.setattr(state_requests.RequestStore, "submit", Mock(return_value=True))
    monkeypatch.setattr(state_requests.RequestStore, "totals", Mock(return_value=dict.fromkeys(STATE_CODES, 0)))
    monkeypatch.setattr(notifications.SubscriptionStore, "subscribe", Mock())
    summary = dict(environment="development", reported_at_utc="2026-10-14T00:00:00.000000Z",
        state_requests=dict(accepted_total=0, by_state=dict.fromkeys(STATE_CODES, 0)),
        notifications=dict(active_total=0, preferences=dict.fromkeys(interest_reporting.PREFERENCES, 0),
                           state_availability_by_state=dict.fromkeys(STATE_CODES, 0)))
    monkeypatch.setattr(interest_reporting.InterestSummaryStore, "summary", Mock(return_value=summary))
    app = development.development_app(enable_integrations=True)
    backend = app.test_client(use_cookies=False)
    responses = []
    cases = [(STATE_PATH, "POST", SUBMISSION, {"state": "CA", "visitor_token": "a" * 64}, 201),
        (NOTIFICATION_PATH, "POST", SUBMISSION, dict(email="synthetic@example.com", android_launch=True,
            ios_launch=False, consent=True, token="b" * 64), 200), (REPORT_PATH, "GET", REPORTING, None, 200)]
    for path, method, credential, data, expected in cases:
        response = backend.open(path, method=method, json=data, base_url=development.ORIGIN,
            headers={"Authorization": "Bearer " + credential}, environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
        assert response.status_code == expected
        responses.append(response)
        other = REPORTING if credential == SUBMISSION else SUBMISSION
        denied = backend.open(path, method=method, json=data, base_url=development.ORIGIN,
            headers={"Authorization": "Bearer " + other}, environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
        assert denied.status_code == 401
        responses.append(denied)

    for options in [dict(environ_overrides={"REMOTE_ADDR": "192.0.2.1"}),
                    dict(base_url="http://localhost:5055"), dict(headers={"Origin": development.ORIGIN}),
                    dict(headers={"Cookie": "browser=value"}), dict(headers={"Sec-Fetch-Site": "same-origin"})]:
        headers = {"Authorization": "Bearer " + REPORTING, **options.pop("headers", {})}
        response = backend.get(REPORT_PATH, base_url=options.pop("base_url", development.ORIGIN),
                               headers=headers, **options)
        assert response.status_code == 403
        responses.append(response)

    public = app.test_client()
    session = public.get("/api/state-requests/session", base_url=development.ORIGIN)
    assert "HttpOnly" in session.headers["Set-Cookie"] and "SameSite=Lax" in session.headers["Set-Cookie"]
    csrf = session.json["csrf_token"]
    assert public.post("/api/state-requests", json={"state": "CA"}, base_url=development.ORIGIN).status_code == 403
    assert public.post("/api/state-requests", json={"state": "CA"}, base_url=development.ORIGIN,
        headers={"Origin": "https://other.example", "X-CSRF-Token": csrf}).status_code == 403
    responses.append(public.post("/api/state-requests", json={"state": "CA"}, base_url=development.ORIGIN,
                                headers={"Origin": development.ORIGIN, "X-CSRF-Token": csrf}))
    assert responses[-1].status_code == 201
    for path in ["/", "/gramanna.html", "/assets/notifications.js", "/api/notifications/session",
                 "/api/state-requests/totals"]:
        response = public.get(path, base_url=development.ORIGIN)
        assert response.status_code == 200
        responses.append(response)
    for path in ["/config/local/integrations.toml", "/config/local/state-request-recognition.dpapi",
                 "/oaf_website/local_development.py", "/.git/config"]:
        assert public.get(path, base_url=development.ORIGIN).status_code == 404
    for response in responses + [session]:
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "Access-Control-Allow-Origin" not in response.headers
        for secret in (SUBMISSION, REPORTING, SECRET.decode(), SECRET.hex()):
            assert secret not in response.text + str(response.headers) + repr(app.config)


@pytest.mark.parametrize("arguments,enabled", [([], False), (["--integrations"], True)])
def test_entry_point_preserves_server_binding_and_readiness(runtime, monkeypatch, capsys, arguments, enabled):
    verify = Mock()
    server = SimpleNamespace(serve_forever=Mock(), server_close=Mock())
    make_server = Mock(return_value=server)
    monkeypatch.setattr(development, "verify_runtime", verify)
    monkeypatch.setattr(development, "make_server", make_server)
    assert development.main(arguments) == 0
    assert runtime.loader.call_count == int(enabled)
    assert make_server.call_args.args[:2] == ("127.0.0.1", 5055)
    assert make_server.call_args.kwargs == {"threaded": True, "request_handler": development.QuietHandler}
    assert development.READY_LINE in capsys.readouterr().out
    verify.assert_called_once()
    server.serve_forever.assert_called_once_with()
    server.server_close.assert_called_once_with()
    runtime.engine.dispose.assert_called_once_with()


def test_requested_activation_failure_never_verifies_or_binds(runtime, monkeypatch, capsys):
    runtime.path.unlink()
    verify, server = Mock(), Mock()
    monkeypatch.setattr(development, "verify_runtime", verify)
    monkeypatch.setattr(development, "make_server", server)
    assert development.main(["--integrations"]) == 2
    output = capsys.readouterr().out
    assert "BLOCKED: DEVELOPMENT integration metadata is missing or invalid." in output
    assert development.READY_LINE not in output
    verify.assert_not_called()
    server.assert_not_called()
    runtime.recognition.assert_not_called()
    runtime.db_loader.assert_not_called()


@pytest.mark.parametrize("activation", [None, "true", 1])
def test_malformed_direct_activation_is_rejected(runtime, activation):
    with pytest.raises(integrations.IntegrationConfigurationError):
        development.development_app(enable_integrations=activation)
    runtime.loader.assert_not_called()
    runtime.recognition.assert_not_called()
    runtime.db_loader.assert_not_called()
