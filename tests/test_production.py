"""Production boundaries with synthetic protected files and denied transports."""
import migration_offline as isolation
isolation.require_early_registration()

from contextlib import contextmanager
import importlib
from ipaddress import ip_network
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.engine import URL
from waitress.adjustments import Adjustments
from werkzeug.test import Client
from werkzeug.wrappers import Response

from oaf_website import production as host, production_config as pc
from oaf_website import database_config as db, state_requests as api
from oaf_website import brevo, brevo_unsubscribe, confirmation_processor as processor
from oaf_website import contact_mail, notification_dispatch as diagnostics
from oaf_website.confirmation_outbox import ConfirmationOutboxStore
from oaf_website.notifications import SubscriptionStore, validate_subscription
from test_notification_delivery import Model
from test_notifications import choices
from test_brevo import KEY, response

ENV = {"OAF_ENV": "production"}
REAL_READER = pc._read_file
ORIGIN = pc.PUBLIC_ORIGIN
SECRET = bytes.fromhex("ab" * 32)
METADATA = ('public_origin = "' + ORIGIN + '"\n'
            'database_host = "dpg-synthetic-a"\n'
            'trusted_proxy_cidrs = ["10.20.30.0/24"]\n')


@pytest.fixture
def production(monkeypatch, tmp_path):
    monkeypatch.setattr(pc.os, "environ", dict(ENV))
    monkeypatch.setattr(diagnostics, "EVIDENCE_PATH", tmp_path / "failures.jsonl")
    files = {"oaf-production.toml": METADATA.encode(), "recognition-key": SECRET.hex().encode(),
             "runtime-db-password": b"synthetic-db-password", "brevo-api-key": KEY.encode(),
             "webhook-token": b"synthetic-webhook-token-" + b"c" * 32,
             "smtp-password": b"synthetic-contact-password", "integration-submission": b"a" * 64,
             "integration-reporting": b"b" * 64, "integration-release": b"c" * 64}
    reader = Mock(side_effect=lambda name, **kw: files[name])
    monkeypatch.setattr(pc, "_read_file", reader)
    model = Model()
    model.dispose = Mock()
    creator = Mock(return_value=model)
    listener = Mock()
    monkeypatch.setattr(api, "create_engine", creator)
    monkeypatch.setattr(processor, "create_engine", creator)
    monkeypatch.setattr(api.event, "listen", listener)
    transport = Mock(return_value=response())
    monkeypatch.setattr(brevo, "BrevoHTTPS", lambda: transport)
    return SimpleNamespace(files=files, reader=reader, model=model, creator=creator,
                           listener=listener, transport=transport)


def activate(production, *, releases=False):
    production.files["oaf-production.toml"] = (METADATA +
        'confirmation_enabled = true\nmanagement_enabled = true\nwebhook_enabled = true\n'
        'processing_enabled = true\n' + ('integrations_enabled = true\nreleases_enabled = true\n'
                                       if releases else '')).encode()


def test_import_and_default_off_composition_are_passive(production):
    importlib.reload(host)
    production.reader.assert_not_called()
    production.creator.assert_not_called()
    assert host.process() == 2
    production.creator.assert_not_called()
    app = host.production_app()
    assert app.extensions["state_requests_engine"] is production.model
    assert not production.model.statements
    names = {call.args[0] for call in production.reader.call_args_list}
    assert names == {"oaf-production.toml", "recognition-key", "runtime-db-password"}
    production.transport.assert_not_called()
    assert production.listener.call_args.args[1] == "checkout"


def test_allowlist_same_origin_api_and_health_never_connect(production):
    app = host.production_app()
    client = app.test_client()
    for name in host.PUBLIC_FILES:
        result = client.get("/" + name, base_url=ORIGIN)
        assert result.status_code == 200
        assert result.data == (host.ROOT / name).read_bytes()
        result.close()
    for path in ("/", "/healthz", "/api/notifications/session", "/api/contact/session"):
        result = client.get(path, base_url=ORIGIN)
        assert result.status_code == 200
        assert result.headers["Cache-Control"] == "no-store"
    session = client.get("/api/notifications/session", base_url=ORIGIN)
    assert session.json["confirmation_enabled"] is False
    assert session.json["management_enabled"] is False
    assert "Access-Control-Allow-Origin" not in session.headers
    assert not production.model.statements
    production.transport.assert_not_called()


@pytest.mark.parametrize("path", ["/.git/config", "/config/production.example.toml", "/config/local/database.toml",
    "/requirements.txt", "/oaf_website/production.py", "/docs/WORKFLOW.md", "/assets/", "/instance/failures.jsonl",
    "/../requirements.txt", "/assets/%2e%2e/requirements.txt", "/etc/secrets/recognition-key"])
def test_private_paths_denied(production, path):
    assert host.production_app().test_client().get(path, base_url=ORIGIN).status_code == 404
    assert not production.model.statements


def test_public_redirected_or_missing_file_fails_closed(production, monkeypatch):
    monkeypatch.setattr(host, "PUBLIC_FILES", ("does-not-exist.html",))
    with pytest.raises(RuntimeError, match="Production application unavailable"):
        host.production_app()
    production.creator.assert_not_called()


def test_public_file_removed_after_startup_is_denied(production, monkeypatch, tmp_path):
    app = host.production_app()
    monkeypatch.setattr(host, "ROOT", tmp_path)
    assert app.test_client().get("/index.html", base_url=ORIGIN).status_code == 404


@pytest.mark.parametrize("environ", [{}, {"OAF_ENV": "testing"}, {"OAF_ENV": "development"},
    {"OAF_ENV": "Production"}, *[{**ENV, name: "synthetic-private-value"} for name in (
        "DATABASE_URL", "database_url", "PGHOST", "PGHOSTADDR", "PGSSLMODE", "PGSSLSNI",
        "PGSSLROOTCERT", "OAF_DB_URL", "OAF_DATABASE_HOST", "SQLALCHEMY_URL",
        "BREVO_API_KEY", "SMTP_PASSWORD", "SSL_CERT_FILE", "SSLKEYLOGFILE", "PYTHON_KEYRING_BACKEND")]])
def test_environment_rejected_before_file_or_secret_reads(production, environ):
    with pytest.raises(db.DatabaseConfigurationError):
        pc.load_production_settings(environ=environ)
    production.reader.assert_not_called()


@pytest.mark.parametrize("text", [METADATA.replace(ORIGIN, "https://evil.example"),
    *[METADATA.replace('dpg-synthetic-a', name) for name in (
        '127.0.0.1', 'localhost', 'arbitrary-host', 'dpg-synthetic-a.oregon-postgres.render.com',
        'dpg-synthetic-a,other', 'dpg-synthetic-a:5432', 'dpg-synthetic-a/other', 'dpg-synthetic-a-')],
    METADATA + 'sslmode="disable"\n', METADATA + 'sslrootcert="arbitrary.pem"\n',
    METADATA + 'sslsni="0"\n',
    METADATA.replace('["10.20.30.0/24"]', '["0.0.0.0/0"]'),
    METADATA.replace('["10.20.30.0/24"]', '[]'),
    METADATA + 'password="synthetic-private-value"\n',
    METADATA + 'confirmation_enabled="false"\n', METADATA + 'processing_enabled=true\n',
    METADATA + 'management_enabled=true\n', METADATA + 'releases_enabled=true\n',
    METADATA + 'webhook_enabled=true\n', 'broken="synthetic-private-value'])
def test_metadata_and_activation_dependencies_fail_closed(production, text, caplog):
    production.files["oaf-production.toml"] = text.encode()
    with pytest.raises(db.DatabaseConfigurationError) as exc:
        pc.load_production_settings()
    assert "synthetic-private-value" not in str(exc.value) + caplog.text
    assert all(call.args[0] == "oaf-production.toml" for call in production.reader.call_args_list)


@pytest.mark.parametrize("value", [b"", b"\xff", b"a\nb", b"x" * 4097])
def test_protected_secret_rejects_private_invalid_values(production, value):
    production.files["runtime-db-password"] = value
    with pytest.raises(db.DatabaseConfigurationError):
        pc.read_secret("runtime-db-password")


def test_secret_scope_key_format_and_no_creation(production):
    with pytest.raises(db.DatabaseConfigurationError): pc.read_secret("migrator-db-password")
    production.reader.assert_not_called()
    production.files["recognition-key"] = b"not-a-key"
    with pytest.raises(db.DatabaseConfigurationError): pc.recognition_secret()


@pytest.mark.parametrize("permissions,uid,regular,posix,allowed", [
    (0o600, 1001, True, True, True), (0o600, 0, True, True, True),
    (0o644, 1001, True, True, False), (0o620, 1001, True, True, False),
    (0o600, 1002, True, True, False), (0o600, 1001, False, True, False),
    (0o600, 1001, True, False, False)])
def test_protected_file_checks_real_read_boundary(production, monkeypatch, tmp_path,
        permissions, uid, regular, posix, allowed):
    # Synthetic payload only. Simulated POSIX metadata, actual file open/read.
    import os
    folder = tmp_path / "protected"
    folder.mkdir()
    (folder / "recognition-key").write_bytes(b"synthetic-file-only")
    monkeypatch.setattr(pc, "SECRETS_DIR", folder)
    monkeypatch.setattr(pc, "POSIX", posix)
    monkeypatch.setattr(os, "geteuid", lambda: 1001, raising=False)
    monkeypatch.setattr(os, "fstat", lambda fd: SimpleNamespace(st_uid=uid,
        st_mode=(0o100000 if regular else 0o040000) | permissions))
    if allowed:
        assert REAL_READER("recognition-key", secret=True) == b"synthetic-file-only"
    else:
        with pytest.raises(db.DatabaseConfigurationError): REAL_READER("recognition-key", secret=True)


def test_database_fixed_identity_tls_and_two_role_migration_selection(production):
    config = db.load_database_config(expected_profile="production")
    assert config.url.database == pc.DATABASE and config.url.username == pc.RUNTIME_ROLE
    assert config.url.host == "dpg-synthetic-a"
    assert dict(config.url.query) == {
        "sslmode": "require", "ssl_min_protocol_version": "TLSv1.2", "sslsni": "1"}
    assert config.url.username != pc.MIGRATOR_ROLE == pc.SCHEMA_OWNER
    assert "synthetic-db-password" not in repr(config)
    for change in ({"username": pc.MIGRATOR_ROLE}, {"query": {"sslmode": "disable"}},
                   {"host": "dpg-synthetic-a.oregon-postgres.render.com"},
                   {"database": "oaf_website_dev"}, {"port": 5433}):
        with pytest.raises(db.DatabaseConfigurationError):
            db.DatabaseConfig("production", config.url.set(**change))
    from oaf_website.migration_config import select_identity
    identity = select_identity("production", environ=ENV)
    assert (identity.database, identity.runtime, identity.migrator, identity.owner) == (
        pc.DATABASE, pc.RUNTIME_ROLE, pc.MIGRATOR_ROLE, pc.MIGRATOR_ROLE)


def test_internal_runtime_and_external_migrator_keep_separate_credentials(production, monkeypatch):
    from oaf_website import migration_config as migrations
    external = "dpg-synthetic-a.oregon-postgres.render.com"
    monkeypatch.setattr(migrations, "_read_production_metadata", lambda: {
        "database_host": external, "database_owner": "render_provider_owner"})
    vault = Mock(return_value="synthetic-migration-password")
    monkeypatch.setattr(migrations, "_windows_password", vault)
    runtime = pc.load_runtime_database()
    vault.assert_not_called()
    assert [call.args[0] for call in production.reader.call_args_list] == [
        "oaf-production.toml", "runtime-db-password"]
    migrator = migrations.load_migration_config(environment="production", environ=ENV)
    vault.assert_called_once_with("OAF Website/production/PostgreSQL/Migrations",
        pc.MIGRATOR_ROLE, ENV, exact_target=True)
    assert (runtime.url.host, migrator.url.host) == ("dpg-synthetic-a", external)
    assert (runtime.url.username, migrator.url.username) == (pc.RUNTIME_ROLE, pc.MIGRATOR_ROLE)
    assert (runtime.url.password, migrator.url.password) == (
        "synthetic-db-password", "synthetic-migration-password")
    assert runtime.url.database == migrator.url.database == "oaf_website_prod"
    assert dict(runtime.url.query) == dict(migrator.url.query) == {
        "sslmode": "require", "ssl_min_protocol_version": "TLSv1.2", "sslsni": "1"}
    for host_name in (runtime.url.host, "192.0.2.1", "other.external.example"):
        with pytest.raises(migrations.MigrationError):
            migrations.MigrationConfig(migrator.identity, migrator.url.set(host=host_name))


@pytest.mark.parametrize("query", [{}, {"sslmode": "require"},
    *[{**pc.TLS_QUERY, "sslmode": mode} for mode in ("disable", "allow", "prefer", "verify-ca", "verify-full")],
    {**pc.TLS_QUERY, "sslsni": "0"}, {**pc.TLS_QUERY, "sslrootcert": "arbitrary.pem"},
    {**pc.TLS_QUERY, "ssl_min_protocol_version": "TLSv1.1"},
    {**pc.TLS_QUERY, "hostaddr": "192.0.2.1"}, {**pc.TLS_QUERY, "options": "synthetic-private-value"}])
def test_runtime_url_rejects_tls_and_endpoint_overrides(production, query):
    config = pc.load_runtime_database()
    with pytest.raises(db.DatabaseConfigurationError):
        db.DatabaseConfig("production", config.url.set(query=query))


@pytest.mark.parametrize("change", [{}, {"database": "oaf_website_test"}, {"authenticated": "postgres"},
    {"effective": pc.MIGRATOR_ROLE}, {"major": 16}, {"port": 6432}, {"tls": False},
    {"dns": "evil.example"}, {"host": "not-an-ip"}])
def test_checkout_verifies_production_dns_tls_version_and_identities(production, change):
    config = pc.load_runtime_database()
    values = dict(database=pc.DATABASE, effective=pc.RUNTIME_ROLE, authenticated=pc.RUNTIME_ROLE,
                  host="10.0.0.15", port=5432, major=17, tls=True, dns=config.url.host)
    values.update(change)
    @contextmanager
    def cursor():
        yield SimpleNamespace(execute=Mock(), fetchone=lambda: tuple(values[k] for k in
            ("database", "effective", "authenticated", "host", "port", "major")))
    connection = SimpleNamespace(cursor=cursor, rollback=Mock(),
        info=SimpleNamespace(host=values["dns"]), pgconn=SimpleNamespace(ssl_in_use=values["tls"]))
    if change:
        with pytest.raises(db.DatabaseConfigurationError): api._verify_checkout(config, connection, None, None)
    else:
        api._verify_checkout(config, connection, None, None)
    connection.rollback.assert_called_once()


@pytest.mark.parametrize("peer,forwarded,proto,expected", [
    ("10.20.30.5", "198.51.100.1, 203.0.113.9", "https", "203.0.113.9"),
    ("192.0.2.5", "203.0.113.9", "https", "192.0.2.5"),
    ("10.20.30.5", "invalid", "https", "10.20.30.5"),
    ("10.20.30.5", "203.0.113.9", "http", "10.20.30.5")])
def test_proxy_peer_validation_and_caller_prefix_spoof_resistance(peer, forwarded, proto, expected):
    def echo(environ, start_response):
        return Response(json.dumps({k: environ.get(k) for k in (
            "REMOTE_ADDR", "wsgi.url_scheme", "HTTP_HOST", "HTTP_X_FORWARDED_HOST", "HTTP_FORWARDED")}))(environ, start_response)
    client = Client(host.TrustedRenderProxy(echo, (ip_network("10.20.30.0/24"),)), Response)
    result = client.get("/", headers={"X-Forwarded-For": forwarded, "X-Forwarded-Proto": proto,
        "X-Forwarded-Host": "evil.example", "Forwarded": "for=evil"},
        environ_overrides={"REMOTE_ADDR": peer})
    data = json.loads(result.data)
    assert data["REMOTE_ADDR"] == expected
    assert data["HTTP_HOST"] == "localhost"
    assert data["HTTP_X_FORWARDED_HOST"] is None and data["HTTP_FORWARDED"] is None


def test_wrong_host_http_and_foreign_origin_rejected(production):
    client = host.production_app().test_client()
    assert client.get("/", base_url="https://evil.example").status_code == 400
    assert client.get("/", base_url="http://ovisalmsfoundation.org").status_code == 400
    assert client.post("/api/contact", base_url=ORIGIN, headers={"Origin": "https://evil.example"},
                       json={"email": "visitor@example.invalid", "message": "hello"}).status_code == 403


def test_production_contact_config_and_safe_unavailable_response(production):
    smtp = ('\n[smtp]\nhost="smtp.example.org"\nport=465\ntls_mode="ssl"\n'
            'username="synthetic-account"\nfrom_email="contact@ovisalmsfoundation.org"\n')
    production.files["oaf-production.toml"] = (METADATA + smtp).encode()
    config = contact_mail.load_contact_config("production")
    assert config.password == "synthetic-contact-password"
    assert config.port == 465 and config.tls_mode == "ssl"
    assert "synthetic-contact-password" not in repr(config)
    mail = contact_mail.construct_message(config, "visitor@example.invalid", "hello")
    assert mail["To"] == contact_mail.RECIPIENT
    assert str(mail["Reply-To"]) == "visitor@example.invalid"
    production.files["oaf-production.toml"] = METADATA.encode()
    client = host.production_app().test_client()
    session = client.get("/api/contact/session", base_url=ORIGIN)
    result = client.post("/api/contact", base_url=ORIGIN, headers={"Origin": ORIGIN,
        "X-CSRF-Token": session.json["csrf_token"]},
        json={"email": "visitor@example.invalid", "message": "hello"})
    assert result.status_code == 503 and b"synthetic" not in result.data
    production.transport.assert_not_called()


@pytest.mark.parametrize("port,tls", [(25, "starttls"), (587, "ssl"), (465, "starttls")])
def test_production_smtp_unapproved_port_pair_fails(production, port, tls):
    production.files["oaf-production.toml"] += (f'\n[smtp]\nhost="smtp.example.org"\nport={port}\n'
        f'tls_mode="{tls}"\nusername="synthetic"\nfrom_email="contact@ovisalmsfoundation.org"\n').encode()
    with pytest.raises(contact_mail.DeliveryUnavailable): contact_mail.load_contact_config("production")


def test_confirmation_management_webhook_and_release_factory_seams(production):
    activate(production, releases=True)
    monkey = host.production_app()
    client = monkey.test_client()
    session = client.get("/api/notifications/session", base_url=ORIGIN)
    assert session.json["confirmation_enabled"] is True and session.json["management_enabled"] is True
    assert client.post(brevo_unsubscribe.WEBHOOK_PATH, base_url=ORIGIN, json={}).status_code == 401
    assert not production.model.statements
    assert "brevo-api-key" not in {call.args[0] for call in production.reader.call_args_list}
    production.transport.assert_not_called()


def test_production_confirmation_management_and_unsubscribe_lifecycle(production):
    from oaf_website import notification_management as management, confirmation_outbox as outbox
    from oaf_website.confirmation_outbox_schema import intents
    activate(production)
    client = host.production_app().test_client()
    csrf = client.get('/api/notifications/session', base_url=ORIGIN).json['csrf_token']
    def post(path, data):
        return client.post(path, json=data, base_url=ORIGIN,
            headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf, 'Sec-Fetch-Site': 'same-origin'})
    assert post('/api/notifications', choices()).status_code == 200
    store = management.NotificationManagementStore(production.model, SECRET, 'production')
    intent = production.model.rows(intents)[0]
    token = outbox.capability(store, intent['subscription'], intent['intent'])
    assert post('/api/notifications/confirm', {'token': token}).status_code == 200
    authority = store.capabilities.issue(intent['subscription'], 0, production.model.now)
    assert authority.startswith('m2.production.')
    with pytest.raises(management.ManagementUnavailable):
        management.ManagementCapabilities(SECRET, 'testing').read(authority, production.model.now)
    result = post('/api/notifications/manage', {'token': authority})
    assert result.status_code == 200 and result.json['status'] == 'preferences'
    result = post('/api/notifications/manage/save', {'token': authority, 'action': 'd' * 64, 'revision': 0})
    assert result.status_code == 200 and result.json['status'] == 'unsubscribed'
    assert host.process() == 0
    production.transport.assert_not_called()


def test_production_processor_existing_batch_and_no_blind_resend(production):
    activate(production)
    store = ConfirmationOutboxStore(production.model, SECRET, "production", management_enabled=True)
    subscription_store = SubscriptionStore(production.model, confirmation_store=store)
    values = validate_subscription(choices())
    subscription_store.subscribe(values)
    assert host.process() == 0
    assert production.transport.call_count == 1
    assert host.process() == 0
    assert production.transport.call_count == 1
    assert production.model.dispose.call_count == 2
    for call in production.creator.call_args_list:
        assert call.args[0].host == "dpg-synthetic-a"
        assert call.args[0].username == pc.RUNTIME_ROLE
        assert dict(call.args[0].query) == {
            "sslmode": "require", "ssl_min_protocol_version": "TLSv1.2", "sslsni": "1"}
    assert "webhook-token" not in {call.args[0] for call in production.reader.call_args_list}


@pytest.mark.parametrize("change", [{"management_enabled": False}, {"releases_enabled": True},
    {"confirmation_page": "https://evil.example/confirm-email.html"}, {"credential_account": "local-account"},
    {"testing_recipient": "visitor@example.invalid"}])
def test_production_processor_activation_mismatch_before_send(production, change):
    activate(production)
    options = dict(expected_profile="production", enabled=True, management_enabled=True,
                   confirmation_page=ORIGIN + "/confirm-email.html")
    options.update(change)
    assert processor.process_confirmations(**options).status == "unavailable"
    production.transport.assert_not_called()
    production.creator.assert_not_called()


def test_default_off_direct_processor_never_reads_keys(production):
    assert processor.process_confirmations(expected_profile="production").status == "disabled"
    production.reader.assert_not_called()


def test_wsgi_port_single_thread_options_and_cleanup(production, monkeypatch):
    import waitress
    import socket
    # Waitress normalizes even the numeric bind address through getaddrinfo.
    # Supply only that deterministic local normalization; no actual DNS/socket.
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('0.0.0.0', 12345))])
    captured = {}
    def serve(app, **settings):
        captured.update(settings)
        # Exercise the actual pinned dependency's configuration parser offline.
        adjustments = Adjustments(**settings)
        assert adjustments.threads == 1 and adjustments.port == 12345
        assert app.test_client().get("/healthz", base_url=ORIGIN).json == {"status": "ok"}
    monkeypatch.setattr(waitress, "serve", serve)
    monkeypatch.setenv("PORT", "12345")
    assert host.main([]) == 0
    assert captured["expose_tracebacks"] is False
    production.model.dispose.assert_called_once()
    production.transport.assert_not_called()


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port", "１２３", "12\n"])
def test_wsgi_invalid_port_precedes_composition(production, monkeypatch, port):
    monkeypatch.setenv("PORT", port)
    assert host.main([]) == 2
    production.reader.assert_not_called()


def test_startup_failure_private_predicate_and_not_run(production, capsys):
    production.files["oaf-production.toml"] = b'private="synthetic-private-value'
    with pytest.raises(RuntimeError) as exc: host.production_app()
    assert str(exc.value) == "Production application unavailable."
    output = capsys.readouterr().err
    assert "synthetic-private-value" not in output
    assert "production_metadata" in output
    assert "provider_submission" in output and "database_mutation" in output
    production.creator.assert_not_called()


def test_first_failure_survives_wsgi_wrapper_and_cleanup_failure(production, monkeypatch, capsys):
    production.files['oaf-production.toml'] = b'private="synthetic-private-value'
    assert host.main([]) == 2
    output = capsys.readouterr().err
    assert 'production_metadata' in output and 'synthetic-private-value' not in output
    assert 'provider_submission' in output
    production.creator.assert_not_called()
    production.files['oaf-production.toml'] = METADATA.encode()
    import waitress
    monkeypatch.setattr(waitress, 'serve', lambda *a, **kw: None)
    production.model.dispose.side_effect = RuntimeError('synthetic-private-value')
    assert host.main([]) == 2
    assert 'synthetic-private-value' not in capsys.readouterr().err


def test_python_and_cli_rejection_before_config_and_default_port(production, monkeypatch):
    assert host.main(['--private-argument']) == 2
    production.reader.assert_not_called()
    saved = host.sys.version_info
    monkeypatch.setattr(host.sys, 'version_info', (3, 12))
    assert host.main([]) == 2
    production.reader.assert_not_called()
    monkeypatch.setattr(host.sys, 'version_info', saved)
    import waitress
    received = Mock()
    monkeypatch.setattr(waitress, 'serve', received)
    assert host.main([]) == 0
    assert received.call_args.kwargs['port'] == 10000


@pytest.mark.parametrize('arguments', [['process'], ['--unknown-private-option']])
def test_actual_module_invocation_is_off_and_finite(production, monkeypatch, arguments):
    import runpy
    monkeypatch.setattr(host.sys, 'argv', ['oaf_website.production', *arguments])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module('oaf_website.production', run_name='__main__')
    assert exc.value.code == 2
    production.creator.assert_not_called()
    production.transport.assert_not_called()


def test_processor_configuration_failure_is_nonzero_and_private(production, capsys):
    production.files['oaf-production.toml'] = b'private="synthetic-private-value'
    assert host.process() == 2
    assert 'synthetic-private-value' not in capsys.readouterr().err
    production.creator.assert_not_called()


def test_health_accepts_render_probe_host_and_head_only(production):
    client = host.production_app().test_client()
    assert client.get('/healthz', base_url='http://assigned.onrender.com').json == {'status': 'ok'}
    result = client.head('/healthz', base_url='http://assigned.onrender.com')
    assert result.status_code == 200 and result.data == b''
    assert client.post('/healthz', base_url=ORIGIN).status_code == 404
    assert not production.model.statements


def test_protected_file_redirect_empty_and_oversize_rejected(production, monkeypatch, tmp_path):
    import os
    folder = tmp_path / 'protected-extra'
    folder.mkdir()
    path = folder / 'recognition-key'
    monkeypatch.setattr(pc, 'SECRETS_DIR', folder)
    monkeypatch.setattr(pc, 'POSIX', True)
    monkeypatch.setattr(os, 'geteuid', lambda: 1001, raising=False)
    monkeypatch.setattr(os, 'fstat', lambda fd: SimpleNamespace(st_uid=1001, st_mode=0o100600))
    for payload in (b'', b'x'*8193):
        path.write_bytes(payload)
        with pytest.raises(db.DatabaseConfigurationError): REAL_READER('recognition-key', secret=True)
    symlink = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda candidate: candidate == path or symlink(candidate))
    with pytest.raises(db.DatabaseConfigurationError): REAL_READER('recognition-key', secret=True)


def test_protected_read_error_preserves_origin_and_proxy_field_type(production, monkeypatch):
    original = pc.reject('production_protected_file')
    production.reader.side_effect = original
    with pytest.raises(db.DatabaseConfigurationError) as exc:
        pc.read_secret('runtime-db-password')
    assert exc.value is original
    production.reader.side_effect = lambda name, **kw: production.files[name]
    production.files['oaf-production.toml'] = METADATA.replace('["10.20.30.0/24"]', '"not-a-list"').encode()
    with pytest.raises(db.DatabaseConfigurationError): pc.load_production_settings()


def test_brevo_activation_off_and_invalid_feedback_secret_fail_closed(production):
    with pytest.raises(brevo.BrevoConfigurationError):
        brevo.load_brevo_config('production', credential_account=None)
    assert 'brevo-api-key' not in {call.args[0] for call in production.reader.call_args_list}
    with pytest.raises(ValueError): brevo_unsubscribe.BrevoWebhookConfig('production', 'short')


def test_metadata_protected_read_failure_retains_exact_first_failure(production, capsys):
    failure = pc.reject('production_protected_file')
    reference = failure.notification_failure['evidence_ref']
    production.reader.side_effect = failure
    with pytest.raises(db.DatabaseConfigurationError) as exc:
        pc.load_production_settings()
    assert exc.value is failure
    assert host.main([]) == 2
    output = capsys.readouterr().err
    assert reference in output and 'production_protected_file' in output
    production.creator.assert_not_called()
    production.transport.assert_not_called()


def test_checkout_uses_installed_psycopg_connection_info_contract(production):
    from psycopg._connection_info import ConnectionInfo
    physical = SimpleNamespace(host=b'dpg-synthetic-a', ssl_in_use=True, _encoding='utf-8')
    info = ConnectionInfo(physical)
    assert info.host == 'dpg-synthetic-a'
    assert not hasattr(info, 'ssl_in_use')
    @contextmanager
    def cursor():
        yield SimpleNamespace(execute=Mock(), fetchone=lambda: (
            pc.DATABASE, pc.RUNTIME_ROLE, pc.RUNTIME_ROLE, '10.0.0.15', 5432, 17))
    connection = SimpleNamespace(cursor=cursor, rollback=Mock(), info=info, pgconn=physical)
    api._verify_checkout(pc.load_runtime_database(), connection, None, None)
