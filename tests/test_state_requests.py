"""Offline HTTP and transactional-model checks; no PostgreSQL/credentials/network."""

import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from html.parser import HTMLParser
from threading import Barrier, Lock
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import URL

from migration_offline import ROOT
from oaf_website import state_requests as api
from oaf_website.database_config import DatabaseConfig, DatabaseConfigurationError
from oaf_website.state_request_schema import STATE_CODES, state_requests

ORIGIN = "https://website.example"
SECRET = b"offline-recognition-secret-32-bytes-only"
COOKIE = "__Host-oaf-state-browser"


class ModelEngine:
    """Serial atomic/commit model, with injected precommit and uncertain failures.

    This verifies HTTP/store lifecycle and emitted SQL. It is not a substitute
    for testing PostgreSQL unique-index waits and isolation after approval.
    """
    def __init__(self):
        self.records = {}
        self.lock = Lock()
        self.failure = None
        self.statements = []

    @contextmanager
    def begin(self):
        with self.lock:
            if self.failure == "connect":
                raise RuntimeError("synthetic-private-connection-details")
            pending = dict(self.records)
            engine = self

            class Connection:
                def execute(self, statement):
                    sql = str(statement.compile(dialect=postgresql.dialect()))
                    engine.statements.append(sql)
                    assert sql.startswith("INSERT INTO oaf_website.state_requests")
                    assert "ON CONFLICT ON CONSTRAINT state_requests_pk DO NOTHING" in sql
                    assert "RETURNING oaf_website.state_requests.state" in sql
                    if engine.failure == "insert":
                        raise RuntimeError("synthetic-private-insert-details")
                    values = statement.compile().params
                    key = (values['state'], values['browser_key'])
                    accepted = key not in pending
                    if accepted:
                        pending[key] = datetime.now(timezone.utc)
                    return SimpleNamespace(scalar_one_or_none=lambda: values['state'] if accepted else None)

            yield Connection()
            if self.failure == "commit":
                raise RuntimeError("synthetic-private-commit-details")
            self.records = pending
            if self.failure == "uncertain":
                raise RuntimeError("synthetic-private-lost-commit-response")

    @contextmanager
    def connect(self):
        with self.lock:
            if self.failure in {"connect", "totals"}:
                raise RuntimeError("synthetic-private-total-details")
            engine = self

            class Connection:
                def execute(self, statement):
                    sql = str(statement.compile(dialect=postgresql.dialect()))
                    engine.statements.append(sql)
                    assert "count(*)" in sql and "GROUP BY oaf_website.state_requests.state" in sql
                    assert "browser_key" not in sql
                    counts = {}
                    for state, _key in engine.records:
                        counts[state] = counts.get(state, 0) + 1
                    return SimpleNamespace(all=lambda: list(counts.items()))

            yield Connection()


def application(engine, secret=SECRET):
    return api._build_app(api.RequestStore(engine), api.BrowserRecognition(secret), ORIGIN)


@pytest.fixture
def setup():
    engine = ModelEngine()
    app = application(engine)
    return engine, app, app.test_client()


def recognize(client):
    response = client.get('/api/state-requests/session', base_url=ORIGIN,
                          headers={"Sec-Fetch-Site": "same-origin"})
    assert response.status_code == 200
    return response.json['csrf_token']


def submit(client, csrf, state="CA", **kwargs):
    headers = kwargs.pop('headers', {"Origin": ORIGIN, "X-CSRF-Token": csrf,
                                     "Sec-Fetch-Site": "same-origin"})
    return client.post('/api/state-requests', json={"state": state}, base_url=kwargs.pop('base_url', ORIGIN),
                       headers=headers, **kwargs)


def totals(client):
    return client.get('/api/state-requests/totals', base_url=ORIGIN)


def test_first_submission_committed_timestamp_and_no_public_identifier(setup):
    engine, app, client = setup
    csrf = recognize(client)
    response = submit(client, csrf)
    assert response.status_code == 201 and response.json['status'] == 'accepted'
    assert set(response.json) == {'status', 'state', 'message'}
    assert len(engine.records) == 1
    assert next(iter(engine.records.values())).tzinfo is timezone.utc
    response = totals(client)
    assert response.json['totals']['CA'] == 1
    assert len(response.json['totals']) == 50
    assert sum(response.json['totals'].values()) == 1
    assert 'browser' not in response.text
    assert response.headers['Cache-Control'] == 'no-store'


def test_duplicate_does_not_replace_timestamp(setup):
    engine, app, client = setup
    csrf = recognize(client)
    submit(client, csrf)
    original = dict(engine.records)
    response = submit(client, csrf)
    assert response.status_code == 200 and response.json['status'] == 'duplicate'
    assert engine.records == original
    assert totals(client).json['totals']['CA'] == 1


def test_different_browsers_and_multiple_states(setup):
    engine, app, first = setup
    second = app.test_client()
    first_csrf, second_csrf = recognize(first), recognize(second)
    assert first_csrf != second_csrf
    assert submit(first, first_csrf, 'CA').status_code == 201
    assert submit(first, first_csrf, 'NY').status_code == 201
    assert submit(second, second_csrf, 'CA').status_code == 201
    counts = totals(first).json['totals']
    assert counts['CA'] == 2 and counts['NY'] == 1 and sum(counts.values()) == 3


@pytest.mark.parametrize('state', ["", " ", "ca", " CA", "DC", "PR", "California", "ZZ", None, 42, True, [], {}])
def test_invalid_and_empty_states_rejected_without_insert(setup, state):
    engine, app, client = setup
    assert submit(client, recognize(client), state).status_code == 400
    assert not engine.records and not engine.statements


def test_all_fifty_states_are_eligible_and_only_once(setup):
    engine, app, client = setup
    csrf = recognize(client)
    for state in STATE_CODES:
        assert submit(client, csrf, state).status_code == 201
        assert submit(client, csrf, state).json['status'] == 'duplicate'
    assert set(totals(client).json['totals'].values()) == {1}


@pytest.mark.parametrize('data,content_type,expected', [
    ('{}', 'application/json', 400), ('null', 'application/json', 400),
    ('[]', 'application/json', 400), ('{', 'application/json', 400),
    ('{"state":"CA","email":"ignored@example.org"}', 'application/json', 400),
    ('state=CA', 'application/x-www-form-urlencoded', 415),
    ('{"state":"CA"}', 'text/plain', 415),
    ('{"state":"' + 'A'*1100 + '"}', 'application/json', 413),
])
def test_request_shape_and_body_limits(setup, data, content_type, expected):
    engine, app, client = setup
    csrf = recognize(client)
    response = client.post('/api/state-requests', base_url=ORIGIN, data=data, content_type=content_type,
                           headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
    assert response.status_code == expected and response.json['status'] == 'error'
    assert not engine.records


@pytest.mark.parametrize('headers', [
    {}, {"Origin": "null"}, {"Origin": "https://evil.example"},
    {"Origin": ORIGIN + '.evil.example'}, {"Origin": ORIGIN + '/path'},
    {"Origin": ORIGIN + ':0'},
    {"Origin": "https://[invalid"}, {"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"},
    {"Origin": ORIGIN, "Sec-Fetch-Site": "same-site"},
    {"Referer": 'https://evil.example/gramanna.html'},
])
def test_origin_safeguards_cannot_trust_caller_host(setup, headers):
    engine, app, client = setup
    headers = dict(headers, **{"X-CSRF-Token": recognize(client)})
    assert submit(client, '', headers=headers).status_code == 403
    assert not engine.records


def test_referer_fallback_and_configured_origin(setup):
    engine, app, client = setup
    csrf = recognize(client)
    assert submit(client, csrf, headers={"Referer": ORIGIN + '/gramanna.html',
                                         "X-CSRF-Token": csrf}).status_code == 201
    assert submit(client, csrf, 'NY', headers={"Origin": "https://attacker.example", "X-CSRF-Token": csrf},
                  base_url="https://attacker.example").status_code == 403


def test_missing_cookie_or_csrf_never_counts_and_session_is_private(setup):
    engine, app, client = setup
    assert submit(client, '0'*64).status_code == 403
    response = client.get('/api/state-requests/session', base_url=ORIGIN)
    cookie = response.headers['Set-Cookie']
    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=Lax' in cookie
    assert 'Path=/' in cookie and 'Domain=' not in cookie
    assert 'Max-Age=31536000' in cookie
    assert set(response.json) == {'csrf_token'}
    assert 'Access-Control-Allow-Origin' not in response.headers
    assert submit(client, '0'*64).status_code == 403
    other = app.test_client()
    assert submit(client, recognize(other)).status_code == 403
    assert not engine.records


@pytest.mark.parametrize('cookie', ['forged', 'f'*300, None])
def test_invalid_recognition_cannot_be_used_to_count(setup, cookie):
    engine, app, client = setup
    csrf = recognize(client)
    if cookie is None:
        client.delete_cookie(COOKIE, domain='website.example')
    else:
        client.set_cookie(COOKIE, cookie, domain='website.example')
    assert submit(client, csrf).status_code == 403
    assert not engine.records
    assert submit(client, recognize(client)).status_code == 201


def test_session_cannot_be_issued_by_cross_site_fetch(setup):
    engine, app, client = setup
    response = client.get('/api/state-requests/session', base_url=ORIGIN,
                          headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403 and 'Set-Cookie' not in response.headers


def test_persistence_and_recognition_across_worker_restart(setup):
    engine, app, first = setup
    csrf = recognize(first)
    submit(first, csrf)
    second = application(engine).test_client()
    second.set_cookie(COOKIE, first.get_cookie(COOKIE, domain='website.example').value, domain='website.example')
    assert recognize(second) == csrf
    assert submit(second, csrf).json['status'] == 'duplicate'
    assert totals(second).json['totals']['CA'] == 1


@pytest.mark.parametrize('failure', ['connect', 'insert', 'commit'])
def test_failed_persistence_is_sanitized_and_does_not_report_success(setup, failure, caplog):
    engine, app, client = setup
    csrf = recognize(client)
    engine.failure = failure
    response = submit(client, csrf)
    assert response.status_code == 503 and response.json['status'] == 'error'
    assert not engine.records
    assert 'synthetic-private' not in response.text + caplog.text
    engine.failure = None
    assert submit(client, csrf).status_code == 201


def test_unconfirmed_commit_deliberate_repeat_converges_without_double_count(setup):
    engine, app, client = setup
    csrf = recognize(client)
    engine.failure = 'uncertain'
    assert submit(client, csrf).status_code == 503
    assert len(engine.records) == 1
    assert len(engine.statements) == 1  # No automatic retry.
    engine.failure = None
    assert submit(client, csrf).json['status'] == 'duplicate'
    assert totals(client).json['totals']['CA'] == 1


def test_totals_failure_does_not_fabricate_zero_or_reverse_acceptance(setup):
    engine, app, client = setup
    assert submit(client, recognize(client)).status_code == 201
    engine.failure = 'totals'
    response = totals(client)
    assert response.status_code == 503 and 'totals' not in response.json
    engine.failure = None
    assert totals(client).json['totals']['CA'] == 1


def test_concurrent_same_browser_duplicates_are_atomic(setup):
    engine, app, client = setup
    csrf = recognize(client)
    cookie = client.get_cookie(COOKIE, domain='website.example').value
    barrier = Barrier(12)
    def attempt(_index):
        peer = app.test_client()
        peer.set_cookie(COOKIE, cookie, domain='website.example')
        barrier.wait(timeout=10)
        return submit(peer, csrf).json['status']
    with ThreadPoolExecutor(max_workers=12) as pool:
        responses = list(pool.map(attempt, range(12)))
    assert responses.count('accepted') == 1 and responses.count('duplicate') == 11
    assert len(engine.records) == 1 and totals(client).json['totals']['CA'] == 1


@pytest.mark.parametrize('origin,local', [('http://website.example', False), ('http://localhost:8000', False),
    ('http://evil.example', True), ('https://website.example/path', False), ('https://website.example?query', False)])
def test_unsafe_runtime_origin_rejected(origin, local):
    with pytest.raises(ValueError):
        api._build_app(None, api.BrowserRecognition(SECRET), origin, allow_insecure_localhost=local)


def test_local_http_cookie_requires_explicit_loopback_opt_in():
    app = api._build_app(None, api.BrowserRecognition(SECRET), 'http://localhost:8000', allow_insecure_localhost=True)
    response = app.test_client().get('/api/state-requests/session', base_url='http://localhost:8000')
    cookie = response.headers['Set-Cookie']
    assert cookie.startswith('oaf-state-browser=') and 'Secure' not in cookie and 'HttpOnly' in cookie


@pytest.mark.parametrize('secret', [None, '', b'', b'a'*31])
def test_missing_or_short_secret_fails_before_credentials(monkeypatch, secret):
    def forbidden(**kwargs):
        pytest.fail('Credential loader must not run')
    monkeypatch.setattr(api, 'load_database_config', forbidden)
    with pytest.raises(ValueError):
        api.create_app(expected_profile='development', recognition_secret=secret, public_origin=ORIGIN)


def test_runtime_factory_only_uses_existing_testing_loader_and_no_startup_connection(monkeypatch):
    config = DatabaseConfig('testing', URL.create('postgresql+psycopg', username='oaf_website_test_app',
                           password='synthetic-only', host='127.0.0.1', port=5432, database='oaf_website_test'))
    loaded, arguments, listeners = [], [], []
    monkeypatch.setattr(api, 'load_testing_database_config', lambda: loaded.append('testing') or config)
    monkeypatch.setattr(api, 'create_engine', lambda *a, **kw: arguments.append((a, kw)) or object())
    monkeypatch.setattr(api.event, 'listen', lambda *a: listeners.append(a))
    app = api.create_app(expected_profile='testing', recognition_secret=SECRET, public_origin=ORIGIN)
    assert loaded == ['testing'] and 'state_requests_engine' in app.extensions
    assert arguments[0][1]['hide_parameters'] is True
    assert arguments[0][1]['connect_args']['require_auth'] == 'scram-sha-256'
    assert listeners[0][1] == 'checkout'


@pytest.mark.parametrize('values', [
    ('oaf_website_dev', 'oaf_website_test_app', 'oaf_website_test_app', '127.0.0.1', 5432, 17),
    ('oaf_website_test', 'oaf_website_test_app', 'postgres', '127.0.0.1', 5432, 17),
    ('oaf_website_test', 'oaf_website_test_app', 'oaf_website_test_app', 'localhost', 5432, 17),
    ('oaf_website_test', 'oaf_website_test_app', 'oaf_website_test_app', '127.0.0.1', 5432, 16),
])
def test_runtime_checkout_identity_rejected(values):
    config = DatabaseConfig('testing', URL.create('postgresql+psycopg', username='oaf_website_test_app',
                           password='synthetic', host='127.0.0.1', port=5432, database='oaf_website_test'))
    @contextmanager
    def cursor():
        yield SimpleNamespace(execute=lambda sql: None, fetchone=lambda: values)
    dbapi = SimpleNamespace(cursor=cursor, rollback=lambda: None)
    with pytest.raises(DatabaseConfigurationError):
        api._verify_checkout(config, dbapi, None, None)


def test_preserved_card_state_registry_and_accessible_activation():
    class Card(HTMLParser):
        def __init__(self):
            super().__init__()
            self.active = False
            self.codes = []
            self.form = None
            self.note = None
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'form' and attrs.get('id') == 'state-request-form':
                self.form = attrs
            if tag == 'select' and attrs.get('id') == 'request-state':
                self.active = True
            if tag == 'option' and self.active and attrs.get('value'):
                self.codes.append(attrs['value'])
            if attrs.get('id') == 'request-note':
                self.note = attrs
        def handle_endtag(self, tag):
            if tag == 'select':
                self.active = False
    card = Card()
    card.feed((ROOT/'gramanna.html').read_text(encoding='utf-8'))
    assert card.codes == list(STATE_CODES) and len(set(card.codes)) == 50
    assert card.form['class'] == 'interface-card state-request'
    assert card.note['role'] == 'status' and card.note['aria-live'] == 'polite'
    assert card.note['aria-atomic'] == 'true'
