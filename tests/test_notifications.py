"""Offline subscription HTTP, privacy and transactional lifecycle checks."""

import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from threading import Lock
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert, Update

from oaf_website import notifications as api
from oaf_website.state_requests import BrowserRecognition, _build_app
from test_state_requests import ORIGIN, SECRET


class SubscriptionEngine:
    """Atomic in-memory model, not evidence of PostgreSQL index/isolation behavior."""
    def __init__(self):
        self.records = {}
        self.lock = Lock()
        self.failure = None
        self.statements = []

    @contextmanager
    def begin(self):
        with self.lock:
            if self.failure == 'connect':
                raise RuntimeError('private@example.com synthetic connection error')
            pending = deepcopy(self.records)
            engine = self

            class Connection:
                def execute(self, statement):
                    sql = str(statement.compile(dialect=postgresql.dialect()))
                    engine.statements.append(sql)
                    values = statement.compile().params
                    if engine.failure == 'execute':
                        raise RuntimeError('private@example.com synthetic SQL error')
                    if isinstance(statement, Insert):
                        assert 'ON CONFLICT DO NOTHING' in sql and 'RETURNING' not in sql
                        digest = values['unsubscribe_digest']
                        if digest not in pending and not any(r['email'] == values['email'] and
                                                            r['unsubscribed_at'] is None for r in pending.values()):
                            pending[digest] = dict(values, created_at=datetime.now(timezone.utc), unsubscribed_at=None)
                    elif isinstance(statement, Update):
                        assert 'unsubscribed_at IS NULL' in sql and 'greatest(CURRENT_TIMESTAMP' in sql
                        assert 'email' not in sql
                        record = pending.get(values['unsubscribe_digest_1'])
                        if record and record['unsubscribed_at'] is None:
                            record['unsubscribed_at'] = datetime.now(timezone.utc)
                    else:
                        raise AssertionError('Unexpected query')
                    return SimpleNamespace()

            yield Connection()
            if self.failure == 'commit':
                raise RuntimeError('private@example.com synthetic commit rejection')
            self.records = pending
            if self.failure == 'uncertain':
                raise RuntimeError('private@example.com synthetic lost commit response')


def choices(**overrides):
    return dict(dict(email='Person+updates@Example.com', web_launch=True, android_launch=False,
                     ios_launch=False, state=None, consent=True, token='a'*64), **overrides)


@pytest.fixture
def setup():
    engine = SubscriptionEngine()
    app = _build_app(None, BrowserRecognition(SECRET), ORIGIN, subscription_store=api.SubscriptionStore(engine))
    client = app.test_client()
    csrf = client.get('/api/notifications/session', base_url=ORIGIN).json['csrf_token']
    return engine, app, client, csrf


def post(client, csrf, data, path='/api/notifications', **options):
    return client.post(path, base_url=ORIGIN, json=data,
                       headers=options.pop('headers', {'Origin': ORIGIN, 'X-CSRF-Token': csrf,
                                                      'Sec-Fetch-Site': 'same-origin'}), **options)


def withdraw(client, csrf, token='a'*64):
    digest = hashlib.sha256(token.encode()).hexdigest()
    return post(client, csrf, {'token': api.UnsubscribeCapabilities(SECRET).issue(digest)}, '/api/notifications/unsubscribe')


def test_saved_preferences_consent_digest_timestamp_and_private_response(setup):
    engine, app, client, csrf = setup
    response = post(client, csrf, choices(android_launch=True, ios_launch=True, state='CA'))
    assert response.status_code == 200
    assert set(response.json) == {'status', 'message', 'unsubscribe_token'}
    assert 'No email has been sent.' in response.json['message']
    record = next(iter(engine.records.values()))
    assert record['email'] == 'person+updates@example.com'
    assert record['web_launch'] and record['android_launch'] and record['ios_launch'] and record['state'] == 'CA'
    assert record['consent_version'] == api.CONSENT_VERSION and record['unsubscribed_at'] is None
    assert record['created_at'].tzinfo is timezone.utc
    assert record['unsubscribe_digest'] == hashlib.sha256(('a'*64).encode()).hexdigest()
    assert 'a'*64 not in repr(record)
    assert 'person+updates@example.com' not in response.text and 'unsubscribe_digest' not in response.text
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'


def test_duplicate_same_and_other_browser_never_overwrite_or_disclose(setup):
    engine, app, client, csrf = setup
    first = post(client, csrf, choices())
    original = deepcopy(engine.records)
    second = post(client, csrf, choices(email=' PERSON+updates@example.com ', token='b'*64, state='TX'))
    assert first.status_code == second.status_code == 200
    assert first.json['message'] == second.json['message'] and first.json['status'] == second.json['status']
    assert api.UnsubscribeCapabilities(SECRET).read(second.json['unsubscribe_token']) not in engine.records
    assert engine.records == original
    other = app.test_client()
    other_csrf = other.get('/api/notifications/session', base_url=ORIGIN).json['csrf_token']
    assert post(other, other_csrf, choices(token='c'*64)).json['message'] == first.json['message']
    assert withdraw(other, other_csrf, 'c'*64).status_code == 200
    assert engine.records == original


def test_unsubscribe_idempotent_resubscribe_fresh_consent_old_token_cannot_affect_new(setup):
    engine, app, client, csrf = setup
    post(client, csrf, choices())
    first = withdraw(client, csrf)
    snapshot = deepcopy(engine.records)
    assert next(iter(snapshot.values()))['unsubscribed_at'] is not None
    assert withdraw(client, csrf).json == first.json and engine.records == snapshot
    # Replaying the old receipt cannot restore withdrawn consent.
    post(client, csrf, choices())
    assert engine.records == snapshot
    post(client, csrf, choices(token='b'*64, web_launch=False, state='TX'))
    assert len(engine.records) == 2
    assert sum(r['unsubscribed_at'] is None for r in engine.records.values()) == 1
    withdraw(client, csrf)
    assert [r['state'] for r in engine.records.values() if r['unsubscribed_at'] is None] == ['TX']
    withdraw(client, csrf, 'b'*64)
    post(client, csrf, choices())
    assert all(r['unsubscribed_at'] is not None for r in engine.records.values())


def test_unknown_and_known_tokens_have_same_withdrawal_response_and_get_never_mutates(setup):
    engine, app, client, csrf = setup
    post(client, csrf, choices())
    before = deepcopy(engine.records)
    assert client.get('/api/notifications/unsubscribe', base_url=ORIGIN).status_code == 405
    assert engine.records == before
    unknown = withdraw(client, csrf, 'f'*64)
    known = withdraw(client, csrf)
    assert unknown.json == known.json and unknown.status_code == known.status_code == 200
    for path in ['/api/notifications', '/api/notifications/subscribers', '/api/notifications/totals']:
        assert client.get(path, base_url=ORIGIN).status_code in {404, 405}


@pytest.mark.parametrize('email', [None, 4, [], {}, '', 'a', 'a@@example.com', 'a@localhost',
    '.a@example.com', 'a..b@example.com', 'a.@example.com', 'a@-example.com', 'a@example-.com',
    'a@exam_ple.com', 'a@example.c', 'a@example.123', 'a\n@example.com', 'a@example.com\r\n',
    'é@example.com', '"a b"@example.com', 'a'*65+'@example.com', 'a@'+('b'*64)+'.com',
    'a@'+'.'.join(['b'*63]*4)+'.com'])
def test_invalid_email_rejected_without_persistence_or_reflection(setup, email):
    engine, app, client, csrf = setup
    response = post(client, csrf, choices(email=email))
    assert response.status_code == 400 and not engine.records


@pytest.mark.parametrize('change', [dict(web_launch=1), dict(android_launch='true'), dict(ios_launch=None),
    dict(web_launch=False), dict(consent=False), dict(consent=1), dict(consent='yes'), dict(state=''),
    dict(state='ca'), dict(state='DC'), dict(state=42), dict(state=[]), dict(token='f'*63),
    dict(token='F'*64), dict(token=None), dict(token={'email': 'private@example.com'})])
def test_preferences_consent_state_and_capability_validated_on_server(setup, change):
    engine, app, client, csrf = setup
    assert post(client, csrf, choices(**change)).status_code == 400
    assert not engine.records


@pytest.mark.parametrize('state', api.STATE_CODES)
def test_each_authorized_state_without_launch_preferences(setup, state):
    engine, app, client, csrf = setup
    assert post(client, csrf, choices(web_launch=False, state=state)).status_code == 200
    assert next(iter(engine.records.values()))['state'] == state


@pytest.mark.parametrize('data', [None, [], 'text', {}, dict(choices(), extra='private@example.com')])
def test_exact_json_shape(setup, data):
    engine, app, client, csrf = setup
    if data is None:
        response = client.post('/api/notifications', base_url=ORIGIN, data='null', content_type='application/json',
                               headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf})
    else:
        response = post(client, csrf, data)
    assert response.status_code == 400 and not engine.records


@pytest.mark.parametrize('path', ['/api/notifications', '/api/notifications/unsubscribe'])
@pytest.mark.parametrize('headers', [{}, {'Origin': 'https://other.example'}, {'Origin': ORIGIN},
    {'Origin': ORIGIN, 'X-CSRF-Token': '0'*64}, {'Origin': ORIGIN, 'Sec-Fetch-Site': 'cross-site'}])
def test_origin_and_browser_csrf_required(setup, path, headers):
    engine, app, client, csrf = setup
    assert post(client, csrf, choices(), path, headers=headers).status_code == 403
    assert not engine.records


def test_content_type_malformed_body_and_size_limits(setup):
    engine, app, client, csrf = setup
    headers = {'Origin': ORIGIN, 'X-CSRF-Token': csrf}
    assert client.post('/api/notifications', base_url=ORIGIN, data='email=a@example.com', headers=headers).status_code == 415
    assert client.post('/api/notifications', base_url=ORIGIN, data='{', content_type='application/json', headers=headers).status_code == 400
    assert client.post('/api/notifications', base_url=ORIGIN, data='x'*1025, content_type='application/json', headers=headers).status_code == 413
    assert not engine.records


@pytest.mark.parametrize('phase', ['connect', 'execute', 'commit', 'uncertain'])
@pytest.mark.parametrize('withdrawal', [False, True])
def test_failures_sanitized_and_deliberate_repeat_converges(setup, caplog, phase, withdrawal):
    engine, app, client, csrf = setup
    if withdrawal:
        post(client, csrf, choices())
    engine.failure = phase
    response = withdraw(client, csrf) if withdrawal else post(client, csrf, choices())
    assert response.status_code == 503
    assert 'private@example.com' not in response.text + caplog.text
    assert 'synthetic' not in response.text + caplog.text
    if not withdrawal:
        assert len(engine.records) == (1 if phase == 'uncertain' else 0)
    engine.failure = None
    assert (withdraw(client, csrf) if withdrawal else post(client, csrf, choices())).status_code == 200
    assert len(engine.records) == 1
    assert (next(iter(engine.records.values()))['unsubscribed_at'] is not None) == withdrawal


def test_concurrent_model_duplicate_emails_and_token_reuse(setup):
    engine, app, client, csrf = setup
    store = api.SubscriptionStore(engine)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda n: store.subscribe(api.validate_subscription(choices(token=f'{n:064x}'))), range(32)))
    assert len(engine.records) == 1
    # Reusing a receipt for another mailbox cannot create another row.
    digest = next(iter(engine.records))
    original_token = next(f'{n:064x}' for n in range(32) if hashlib.sha256(f'{n:064x}'.encode()).hexdigest() == digest)
    store.subscribe(api.validate_subscription(choices(email='different@example.com', token=original_token)))
    assert len(engine.records) == 1


@pytest.mark.parametrize('token', [None,42,{},'a'*64,'a'*64+'.'+'b'*64,'f'*129,'a'*64+'.'+'b'*63])
def test_unsigned_tampered_and_malformed_unsubscribe_tokens_cannot_mutate(setup, token):
    engine, app, client, csrf = setup
    post(client, csrf, choices())
    before = deepcopy(engine.records)
    response = post(client, csrf, {'token':token}, '/api/notifications/unsubscribe')
    assert response.status_code == 400 and engine.records == before


def test_links_recreated_for_future_delivery_and_restart_without_stored_bearer(setup):
    engine, app, client, csrf = setup
    response = post(client, csrf, choices())
    digest = next(iter(engine.records))
    capabilities = api.UnsubscribeCapabilities(SECRET)
    assert capabilities.issue(digest) == response.json['unsubscribe_token']
    assert capabilities.read(response.json['unsubscribe_token']) == digest
    assert api.UnsubscribeCapabilities(b'different-protected-secret-32-bytes').read(response.json['unsubscribe_token']) is None
    assert capabilities.issue(digest) not in repr(engine.records)
    restarted = _build_app(None, BrowserRecognition(SECRET), ORIGIN, subscription_store=api.SubscriptionStore(engine))
    other = restarted.test_client()
    other_csrf = other.get('/api/notifications/session', base_url=ORIGIN).json['csrf_token']
    assert post(other, other_csrf, {'token':capabilities.issue(digest)}, '/api/notifications/unsubscribe').status_code == 200
    assert engine.records[digest]['unsubscribed_at'] is not None
