"""R38 public integration; guarded transactional model and synthetic keys only."""
import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from oaf_website import notifications as api, state_requests as runtime
from oaf_website import confirmation_outbox as outbox
from oaf_website.confirmation_outbox_schema import intents
from oaf_website.notification_delivery import NotificationDeliveryStore
from oaf_website.notification_delivery_schema import verification, limits
from test_notification_delivery import Model, SECRET
from test_notifications import choices, post
from test_state_requests import ORIGIN

REQUEST = '/api/notifications/confirmation'
CONFIRM = '/api/notifications/confirm'


def withdraw(client, csrf, receipt='a'*64):
    digest = hashlib.sha256(receipt.encode('ascii')).hexdigest()
    return post(client, csrf, {'token': api.UnsubscribeCapabilities(SECRET).issue(digest)},
                '/api/notifications/unsubscribe')


def build(model, enabled=True):
    delivery = NotificationDeliveryStore(model, SECRET, 'testing') if enabled else None
    store = api.SubscriptionStore(model, confirmation_store=delivery)
    app = runtime._build_app(None, runtime.BrowserRecognition(SECRET), ORIGIN, subscription_store=store)
    client = app.test_client()
    session = client.get('/api/notifications/session', base_url=ORIGIN)
    assert session.json['confirmation_enabled'] is enabled
    return delivery, store, app, client, session.json['csrf_token']


@pytest.fixture
def setup():
    model = Model()
    return (model, *build(model))


def token(model, delivery):
    row = model.rows(intents)[-1]
    return outbox.capability(delivery, row['subscription'], row['intent'])


def signup(setup, **changes):
    return post(setup[-2], setup[-1], choices(**changes))


def test_new_signup_atomically_reserves_without_sending_or_disclosing(setup, monkeypatch):
    model, delivery, store, app, client, csrf = setup
    forbidden = Mock(side_effect=AssertionError('Public operations cannot process or send'))
    monkeypatch.setattr(outbox.ConfirmationDispatcher, 'process', forbidden)
    monkeypatch.setattr(outbox.BrevoAdapter, 'submit', forbidden)
    response = signup(setup)
    assert response.status_code == 200 and response.json["message"] == "Your submission was processed. New subscriptions are saved; existing active preferences stay unchanged."
    assert len(model.rows(api.notifications)) == len(model.rows(verification)) == len(model.rows(intents)) == 1
    assert len(model.rows(limits)) == 2
    assert model.rows(intents)[0]['status'] == 'pending'
    assert model.rows(verification)[0]['verified_at'] is None
    secret = token(model, delivery)
    assert secret not in response.text + repr(model.records)
    assert post(client, csrf, {'token': secret}, CONFIRM).json == dict(
        status='confirmed', message=api.CONFIRMED, already_confirmed=False)
    forbidden.assert_not_called()
    assert 'RETURNING oaf_website.notifications.unsubscribe_digest' in '\n'.join(model.statements)
    assert 'SELECT pg_catalog.pg_advisory_xact_lock(67210401)' in model.statements


@pytest.mark.parametrize('changed', [dict(), dict(token='b'*64, state='TX', android_launch=True),
                                    dict(email='other@example.invalid')])
def test_duplicate_email_and_receipt_never_replace_any_lifecycle_state(setup, changed):
    model, delivery, store, app, client, csrf = setup
    first = signup(setup)
    original = deepcopy(model.records)
    model.elapse(seconds=61)
    repeated = signup(setup, **changed)
    assert repeated.status_code == first.status_code == 200
    assert repeated.json['message'] == first.json['message']
    assert model.records == original  # Includes quotas, token version and pending intent.


def test_concurrent_signups_create_one_intent_and_only_one_quota_charge(setup):
    model, delivery, store, app, client, csrf = setup
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda n: store.subscribe(api.validate_subscription(choices(token=f'{n:064x}'))), range(16)))
    assert len(model.rows(api.notifications)) == len(model.rows(intents)) == 1
    assert all(row['requests'] == 1 for row in model.rows(limits))


@pytest.mark.parametrize('phase', ['connect', 'execute', 'commit', 'uncertain'])
def test_signup_rollback_or_lost_acknowledgement_converges_without_replacing_intent(setup, phase, caplog):
    model, delivery, store, app, client, csrf = setup
    model.failure = phase
    response = signup(setup)
    assert response.status_code == 503
    assert 'synthetic' not in response.text + caplog.text
    committed = deepcopy(model.records)
    for table in (api.notifications, verification, intents):
        assert len(model.rows(table)) == int(phase == 'uncertain')
    assert len(model.rows(limits)) == (2 if phase == 'uncertain' else 0)
    model.failure = None
    assert signup(setup).status_code == 200
    if phase == 'uncertain': assert model.records == committed
    assert len(model.rows(intents)) == 1


@pytest.mark.parametrize('item', [verification, intents])
def test_reservation_insert_failure_rolls_back_subscription_and_budgets(setup, monkeypatch, item):
    model, delivery, store, app, client, csrf = setup
    original = outbox.insert
    def fail(table):
        if table is item: raise RuntimeError('private@example.invalid token SQL')
        return original(table)
    monkeypatch.setattr(outbox, 'insert', fail)
    assert signup(setup).status_code == 503
    assert all(not rows for rows in model.records.values())


@pytest.mark.parametrize('condition', ['eligible', 'unknown', 'verified', 'suppressed', 'withdrawn', 'cooldown', 'mailbox', 'global'])
def test_valid_request_responses_indistinguishable_and_never_contain_bearer(setup, condition):
    model, delivery, store, app, client, csrf = setup
    address = choices()['email']
    if condition != 'unknown': signup(setup)
    if condition == 'verified': delivery.confirm(token(model, delivery))
    if condition == 'suppressed': delivery.suppress(address, 'complaint')
    if condition == 'withdrawn': withdraw(client, csrf)
    if condition == 'mailbox':
        for _ in range(4):
            model.elapse(seconds=60)
            post(client, csrf, {'email': address}, REQUEST)
    if condition == 'global':
        next(row for row in model.rows(limits) if row['bucket'] == delivery._digest('budget', 'global'))['requests'] = 1000
    if condition != 'cooldown': model.elapse(seconds=60)
    before = len(model.rows(intents))
    response = post(client, csrf, {'email': ' PERSON+UPDATES@EXAMPLE.COM '}, REQUEST)
    assert response.status_code == 200
    assert response.json == dict(status='received', message=api.CONFIRMATION_REQUESTED)
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['Referrer-Policy'] == 'same-origin'
    assert len(model.rows(intents)) == before  # Eligible pending work is coalesced.


@pytest.mark.parametrize('path,data', [(REQUEST, {'email': 'person@example.invalid'}), (CONFIRM, {'token': 'a'*64})])
@pytest.mark.parametrize('headers', [{}, {'Origin': 'https://evil.invalid'}, {'Origin': ORIGIN},
    {'Origin': ORIGIN, 'X-CSRF-Token': '0'*64}, {'Origin': ORIGIN, 'Sec-Fetch-Site': 'cross-site'}])
def test_origin_csrf_required_before_any_persistence(setup, path, data, headers):
    model, delivery, store, app, client, csrf = setup
    assert post(client, csrf, data, path, headers=headers).status_code == 403
    assert not model.statements


@pytest.mark.parametrize('path,body', [
    (REQUEST, '{}'), (REQUEST, 'null'), (REQUEST, '[]'), (REQUEST, '{"email":null}'),
    (REQUEST, '{"email":"bad"}'), (REQUEST, '{"email":"a@example.com","extra":true}'),
    (REQUEST, '{"email":"a@example.com","email":"b@example.com"}'),
    (REQUEST, '{"email":NaN}'), (REQUEST, '{"email":Infinity}'), (REQUEST, b'{"email":"\xff"}'),
    (REQUEST, '{'), (CONFIRM, '{}'), (CONFIRM, 'null'), (CONFIRM, '[]'),
    (CONFIRM, '{"token":null}'), (CONFIRM, '{"token":1}'), (CONFIRM, '{"token":"bad"}'),
    (CONFIRM, '{"token":"'+ 'a'*64 +'","extra":true}'),
    (CONFIRM, '{"token":"'+ 'a'*64 +'","token":"'+ 'b'*64 +'"}'),
])
def test_strict_json_shape_syntax_and_values(setup, path, body):
    model, delivery, store, app, client, csrf = setup
    response = client.post(path, base_url=ORIGIN, data=body, content_type='application/json',
                           headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf})
    assert response.status_code == 400 and not model.statements


@pytest.mark.parametrize('path', [REQUEST, CONFIRM])
def test_method_media_and_size_bounds(setup, path):
    model, delivery, store, app, client, csrf = setup
    assert client.get(path, base_url=ORIGIN).status_code == 405
    headers = {'Origin': ORIGIN, 'X-CSRF-Token': csrf}
    assert client.post(path, base_url=ORIGIN, data='text', headers=headers).status_code == 415
    assert client.post(path, base_url=ORIGIN, data='x'*1025, content_type='application/json', headers=headers).status_code == 413
    assert not model.statements


def test_pending_resend_coalescing_limits_confirmation_repeats_and_stable_timestamp(setup):
    model, delivery, store, app, client, csrf = setup
    signup(setup)
    first = token(model, delivery)
    assert post(client, csrf, {'email': choices()['email']}, REQUEST).status_code == 200
    assert len(model.rows(intents)) == 1
    model.elapse(seconds=60)
    assert post(client, csrf, {'email': choices()['email']}, REQUEST).status_code == 200
    second = token(model, delivery)
    assert second == first and len(model.rows(intents)) == 1
    assert model.rows(intents)[0]['status'] == 'pending'
    assert post(client, csrf, {'token': second}, CONFIRM).json == dict(
        status='confirmed', message=api.CONFIRMED, already_confirmed=False)
    stamp = model.rows(verification)[0]['verified_at']
    model.elapse(seconds=5)
    before = deepcopy(model.records)
    # A fresh browser may recognize a repeat only by presenting the same valid capability.
    _, _, _, repeat_client, repeat_csrf = build(model)
    assert post(repeat_client, repeat_csrf, {'token': second}, CONFIRM).json == dict(
        status='confirmed', message='Your email is already confirmed.', already_confirmed=True)
    assert model.records == before
    assert model.rows(verification)[0]['verified_at'] == stamp


@pytest.mark.parametrize('reason', ['expired', 'future', 'withdrawn', 'suppressed', 'unknown'])
def test_unavailable_lifecycle_never_verifies_and_response_is_sanitized(setup, reason):
    model, delivery, store, app, client, csrf = setup
    signup(setup)
    bearer = token(model, delivery)
    if reason == 'expired': model.elapse(hours=24)
    if reason == 'future': model.elapse(seconds=-1)
    if reason == 'withdrawn': withdraw(client, csrf)
    if reason == 'suppressed': delivery.suppress(choices()['email'], 'hard_bounce')
    if reason == 'unknown': bearer = 'f'*64
    response = post(client, csrf, {'token': bearer}, CONFIRM)
    assert response.status_code == 400 and response.json['message'] == api.LINK_UNAVAILABLE
    assert bearer not in response.text and model.rows(verification)[0]['verified_at'] is None


@pytest.mark.parametrize('path', [REQUEST, CONFIRM])
@pytest.mark.parametrize('phase', ['connect', 'execute', 'commit', 'uncertain'])
def test_public_persistence_failure_sanitized_and_deliberate_repeats_safe(setup, path, phase, caplog):
    model, delivery, store, app, client, csrf = setup
    signup(setup)
    bearer = token(model, delivery)
    data = {'token': bearer} if path == CONFIRM else {'email': choices()['email']}
    model.elapse(seconds=60)
    model.failure = phase
    response = post(client, csrf, data, path)
    assert response.status_code == 503
    assert all(private not in response.text + caplog.text for private in (bearer, 'synthetic', choices()['email']))
    model.failure = None
    before = deepcopy(model.records)
    assert post(client, csrf, data, path).status_code == 200
    if phase == 'uncertain' and path == CONFIRM: assert model.records == before
    assert len(model.rows(intents)) <= 2


def test_unsubscribe_and_new_lifecycle_do_not_revive_original_confirmation(setup):
    model, delivery, store, app, client, csrf = setup
    signup(setup)
    old = token(model, delivery)
    assert withdraw(client, csrf).status_code == 200
    assert withdraw(client, csrf).status_code == 200
    signup(setup)  # Withdrawn receipt never reactivates.
    assert len(model.rows(intents)) == 1
    model.elapse(seconds=60)
    signup(setup, token='b'*64)
    assert len(model.rows(intents)) == 2
    assert post(client, csrf, {'token': old}, CONFIRM).status_code == 400
    assert post(client, csrf, {'token': token(model, delivery)}, CONFIRM).status_code == 200
    assert withdraw(client, csrf).status_code == 200
    assert model.rows(api.notifications)[1]['unsubscribed_at'] is None


@pytest.mark.parametrize('reason', ['cooldown', 'global', 'suppressed'])
def test_new_signup_preserves_existing_quota_and_suppression_policy(setup, reason):
    model, delivery, store, app, client, csrf = setup
    if reason == 'suppressed': delivery.suppress(choices()['email'], 'complaint')
    else:
        post(client, csrf, {'email': choices()['email']}, REQUEST)  # Unknown address consumes budget.
        if reason == 'global':
            next(row for row in model.rows(limits) if row['bucket'] == delivery._digest('budget', 'global'))['requests'] = 1000
    assert signup(setup).status_code == 200
    assert len(model.rows(api.notifications)) == 1
    assert not model.rows(verification) and not model.rows(intents)


def test_default_off_preserves_signup_and_unsubscribe_without_reservations():
    model = Model()
    delivery, store, app, client, csrf = build(model, False)
    response = post(client, csrf, choices())
    before = deepcopy(model.records)
    assert response.json["message"] == "Your submission was processed. New subscriptions are saved; existing active preferences stay unchanged."
    for path, data in [(REQUEST, {'email': choices()['email']}), (CONFIRM, {'token': 'a'*64})]:
        response = post(client, csrf, data, path)
        assert response.status_code == 503 and response.json['message'] == api.CONFIRMATION_OFF
    assert model.records == before
    assert not model.rows(verification) and not model.rows(limits) and not model.rows(intents)
    assert withdraw(client, csrf).status_code == 200


@pytest.mark.parametrize('enabled', [False, True])
def test_factory_activation_is_injected_and_never_connects_or_processes(monkeypatch, enabled):
    model = Model()
    config = SimpleNamespace(profile='testing', url='synthetic-not-connected')
    monkeypatch.setattr(runtime, 'load_testing_database_config', lambda: config)
    monkeypatch.setattr(runtime, 'create_engine', lambda *a, **kw: model)
    monkeypatch.setattr(runtime.event, 'listen', lambda *a: None)
    forbidden = Mock(side_effect=AssertionError('No processor or provider startup'))
    monkeypatch.setattr(outbox.ConfirmationDispatcher, 'process', forbidden)
    monkeypatch.setattr(outbox.BrevoAdapter, 'submit', forbidden)
    options = {'confirmation_enabled': True} if enabled else {}  # Exercise actual default.
    app = runtime.create_app(expected_profile='testing', recognition_secret=SECRET, public_origin=ORIGIN, **options)
    assert not model.statements
    client = app.test_client()
    session = client.get('/api/notifications/session', base_url=ORIGIN).json
    assert session['confirmation_enabled'] is enabled
    assert post(client, session['csrf_token'], choices()).status_code == 200
    assert len(model.rows(intents)) == int(enabled)
    forbidden.assert_not_called()


@pytest.mark.parametrize('enabled', [None, 'true', 1, {}])
def test_invalid_activation_fails_before_config_or_credentials(monkeypatch, enabled):
    forbidden = Mock(side_effect=AssertionError('No credential/config access'))
    monkeypatch.setattr(runtime, 'load_testing_database_config', forbidden)
    with pytest.raises(ValueError):
        runtime.create_app(expected_profile='testing', recognition_secret=SECRET, public_origin=ORIGIN,
                           confirmation_enabled=enabled)
    forbidden.assert_not_called()


def test_separate_engines_cannot_produce_nonatomic_handoff():
    with pytest.raises(ValueError):
        api.SubscriptionStore(Model(), confirmation_store=NotificationDeliveryStore(Model(), SECRET, 'testing'))


def test_turning_off_rejects_previously_valid_tokens_without_mutation(setup):
    model, delivery, store, app, client, csrf = setup
    signup(setup)
    bearer = token(model, delivery)
    before = deepcopy(model.records)
    _, _, _, off_client, off_csrf = build(model, False)
    assert post(off_client, off_csrf, {'token': bearer}, CONFIRM).status_code == 503
    assert model.records == before


@pytest.mark.parametrize('reason', ['expired', 'future', 'withdrawn', 'suppressed', 'unknown', 'superseded'])
def test_successful_confirmation_timestamp_survives_later_unavailable_repeat(setup, reason):
    model, delivery, store, app, client, csrf = setup
    signup(setup)
    bearer = token(model, delivery)
    assert post(client, csrf, {'token': bearer}, CONFIRM).status_code == 200
    stamp = model.rows(verification)[0]['verified_at']
    if reason == 'expired': model.elapse(hours=24)
    if reason == 'future': model.elapse(seconds=-1)
    if reason == 'withdrawn': withdraw(client, csrf)
    if reason == 'suppressed': delivery.suppress(choices()['email'], 'complaint')
    if reason == 'unknown': bearer = 'f'*64
    if reason == 'superseded': model.rows(verification)[0]['token_digest'] = delivery._digest('confirmation', 'f'*64)
    before = deepcopy(model.records)
    response = post(client, csrf, {'token': bearer}, CONFIRM)
    assert response.status_code == 400
    assert response.json == dict(status='error', message=api.LINK_UNAVAILABLE)
    assert model.records == before
    assert model.rows(verification)[0]['verified_at'] == stamp
    before = deepcopy(model.records)
    assert signup(setup, token='b'*64).status_code == 200
    if reason != 'withdrawn': assert model.records == before
