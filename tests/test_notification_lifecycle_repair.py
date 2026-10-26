"""Connected Flask/store/adapter journeys with real projected SQLAlchemy rows."""
import migration_offline as isolation
isolation.require_early_registration()

from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
import json
import re
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.dml import Insert

from oaf_website import notification_management as management, state_requests as runtime
from oaf_website import confirmation_outbox as outbox, brevo_unsubscribe as webhook
from oaf_website.notification_delivery import NotificationDeliveryStore
from oaf_website.notification_delivery_schema import verification, suppressions, limits
from oaf_website.notification_management_schema import notifications, intents, changes
from oaf_website.notifications import SubscriptionStore
from test_notification_delivery import Model, SECRET, subscribe
from test_notifications import choices, post
from test_state_requests import ORIGIN
from test_brevo import CONFIG, PAGE, response
from test_brevo_unsubscribe import BEARER
from test_notification_management import PREFERENCES, SESSION_COOKIE


def build():
    model = Model()
    manager = management.NotificationManagementStore(model, SECRET, "testing")
    delivery = NotificationDeliveryStore(model, SECRET, "testing", management_enabled=True)
    app = runtime._build_app(None, runtime.BrowserRecognition(SECRET), ORIGIN,
        subscription_store=SubscriptionStore(model, confirmation_store=delivery, management_store=manager),
        environment="testing", brevo_webhook_config=webhook.BrevoWebhookConfig("testing", BEARER))
    client = app.test_client()
    csrf = client.get("/api/notifications/session", base_url=ORIGIN).json["csrf_token"]
    processor = outbox.ConfirmationOutboxStore(model, SECRET, "testing", management_enabled=True)
    return SimpleNamespace(model=model, manager=manager, delivery=delivery, app=app, client=client,
                           csrf=csrf, processor=processor, sent=[])


def signup(c, number=1):
    reply = post(c.client, c.csrf, choices(email="subscriber1@example.invalid", token=f"{number:064x}"))
    assert reply.status_code == 200
    return reply.json["unsubscribe_token"]


def send_confirmation(c):
    def transport(key, body):
        c.sent.append(json.loads(body))
        return response(body=json.dumps({"messageId": f"<repair-{len(c.sent)}@provider.invalid>"}).encode())
    result = outbox.ConfirmationDispatcher(c.processor, CONFIG, PAGE, transport=transport).process()
    assert result.status == "processed" and result.processed == 1
    body = c.sent[-1]
    token = re.search(r"#confirm-email=([0-9a-f]{64})", body["textContent"]).group(1)
    manage = re.search(r"#manage=(m2\.[^\s]+)", body["textContent"]).group(1)
    assert token in body["htmlContent"] and manage in body["htmlContent"]
    return token, manage


def genuine_shaped_event(c):
    accepted = next(row for row in c.model.rows(intents) if row["status"] == "accepted")
    stamp = int(c.model.now.timestamp())
    return {"event": "unsubscribed", "email": "subscriber1@example.invalid", "id": 123,
        "date": "2026-10-15 12:00:00", "ts": stamp, "message-id": accepted["provider_message_id"].strip("<>"),
        "ts_event": stamp, "subject": "Synthetic lifecycle", "X-Mailin-custom": "", "template_id": 0,
        "tag": '["transactionalTag"]', "tags": ["transactionalTag"], "ts_epoch": stamp * 1000,
        "sending_ip": "192.0.2.1", "user_agent": "Synthetic fixture", "device_used": "DESKTOP",
        "mirror_link": "https://example.invalid/synthetic-preview", "contact_id": 0}


def callback(c, data):
    return c.client.post(webhook.WEBHOOK_PATH, base_url=ORIGIN, json=data,
                         headers={"Authorization": "Bearer " + BEARER})


@pytest.mark.parametrize("withdrawal", ["website", "brevo"])
def test_signup_confirmation_preferences_withdrawal_audit_suppression_fresh_consent(withdrawal):
    c = build()
    primary = subscribe(c.model, 99, email="foundation@example.invalid")
    primary_before = deepcopy(next(r for r in c.model.rows(notifications) if r["unsubscribe_digest"] == primary))
    signup(c)
    token, manage = send_confirmation(c)
    assert post(c.client, c.csrf, {"token": token}, "/api/notifications/confirm").json["status"] == "confirmed"
    opened = post(c.client, c.csrf, {"token": manage}, "/api/notifications/manage")
    assert opened.json["status"] == "preferences"
    saved = post(c.client, c.csrf, dict(action="a"*64, revision=0, preferences=PREFERENCES),
                 "/api/notifications/manage/save")
    assert saved.json == dict(status="saved", revision=1)
    assert post(c.client, c.csrf, {}, "/api/notifications/manage").json["preferences"]["state"] == "CA"
    if withdrawal == "website":
        body = dict(action="b"*64, revision=1)
        receipt = post(c.client, c.csrf, body, "/api/notifications/manage/withdrawal-receipt").json["receipt"]
        result = post(c.client, c.csrf, body, "/api/notifications/manage/save")
        assert result.json == dict(status="unsubscribed", revision=2)
        assert c.client.get_cookie(SESSION_COOKIE, domain="website.example") is None
        snapshot = deepcopy(c.model.records)
        assert post(c.client, c.csrf, dict(body, receipt=receipt),
                    "/api/notifications/manage/withdrawal-ack").json == result.json
        assert c.model.records == snapshot
    else:
        event = genuine_shaped_event(c)
        assert callback(c, event).json == dict(status="processed")
        snapshot = deepcopy(c.model.records)
        assert callback(c, dict(event, id=999)).json == dict(status="processed")
        assert c.model.records == snapshot
    old = deepcopy(next(r for r in c.model.rows(notifications) if r["email"] == "subscriber1@example.invalid"))
    assert old["unsubscribed_at"] is not None and len(c.model.rows(changes)) == 2
    assert len(c.model.rows(suppressions)) == int(withdrawal == "brevo")
    c.model.elapse(seconds=60)
    signup(c, 2)
    assert len([r for r in c.model.rows(notifications) if r["email"] == old["email"]]) == 2
    assert next(r for r in c.model.rows(notifications) if r["unsubscribe_digest"] == old["unsubscribe_digest"]) == old
    assert c.delivery.confirm(token) == "unavailable"
    if withdrawal == "website":
        fresh, _ = send_confirmation(c)
        assert fresh != token and c.delivery.confirm(fresh) == "verified"
    else:
        assert len(c.model.rows(intents)) == 1
        assert c.model.rows(suppressions)[0]["reason"] == "provider_block"
        assert c.processor.candidates(20) == []
    assert next(r for r in c.model.rows(notifications) if r["unsubscribe_digest"] == primary) == primary_before


def test_unverified_valid_link_is_withdrawal_only_and_never_discloses_preferences():
    c = build(); signup(c); token, manage = send_confirmation(c)
    opened = post(c.client, c.csrf, {"token": manage}, "/api/notifications/manage")
    assert opened.status_code == 200 and opened.json["status"] == "withdrawal_only"
    assert "preferences" not in opened.json and "token" not in opened.json
    assert c.client.get_cookie(SESSION_COOKIE, domain="website.example") is None
    body = dict(token=manage, action="a"*64, revision=0)
    assert post(c.client, c.csrf, dict(body, preferences=PREFERENCES),
                "/api/notifications/manage/save").status_code == 400
    receipt = post(c.client, c.csrf, body, "/api/notifications/manage/withdrawal-receipt")
    assert receipt.status_code == 200
    assert post(c.client, c.csrf, body, "/api/notifications/manage/save").json["status"] == "unsubscribed"
    assert c.model.rows(verification)[0]["verified_at"] is None
    assert c.delivery.confirm(token) == "unavailable"


@pytest.mark.parametrize("invalid", ["expired", "forged", "wrong_environment", "stale_revision"])
def test_invalid_links_cannot_view_prepare_or_save(invalid):
    c = build(); signup(c); _, manage = send_confirmation(c)
    if invalid == "expired": c.model.elapse(days=30)
    if invalid == "forged": manage = manage[:-1] + ("0" if manage[-1] != "0" else "1")
    if invalid == "wrong_environment": manage = manage.replace(".testing.", ".development.")
    if invalid == "stale_revision": c.manager.unsubscribe_legacy(c.model.rows(notifications)[0]["unsubscribe_digest"])
    snapshot = deepcopy(c.model.records)
    for path, body in (
        ("/manage", dict(token=manage)),
        ("/manage/withdrawal-receipt", dict(token=manage, action="a"*64, revision=0)),
        ("/manage/save", dict(token=manage, action="a"*64, revision=0)),
    ):
        reply = post(c.client, c.csrf, body, "/api/notifications" + path)
        assert reply.status_code in (400, 409)
        assert reply.json.get("status") != "unsubscribed"
    assert c.model.records == snapshot


def test_delivered_confirmation_remains_usable_while_replacement_is_pending():
    c = build(); signup(c); old, _ = send_confirmation(c)
    delivered = deepcopy(c.model.rows(verification)[0])
    c.model.elapse(seconds=60)
    for _ in range(3):
        assert post(c.client, c.csrf, {"email": "subscriber1@example.invalid"},
                    "/api/notifications/manage/recovery").status_code == 200
        c.model.elapse(seconds=60)
    assert len(c.model.rows(intents)) == 2
    assert c.model.rows(intents)[1]["status"] == "pending" and c.model.rows(intents)[1]["attempts"] == 0
    assert c.model.rows(verification)[0] == delivered
    assert c.delivery.confirm(old) == "verified"
    verified = deepcopy(c.model.rows(verification)[0])
    transport = Mock()
    assert outbox.ConfirmationDispatcher(c.processor, CONFIG, PAGE, transport=transport).process().processed == 0
    transport.assert_not_called()
    assert c.model.rows(verification)[0] == verified


@pytest.mark.parametrize("outcome", ["provider_accepted", "retryable_rejection", "submission_unknown"])
def test_replacement_authority_changes_only_with_eligible_accepted_outcome(outcome):
    c = build(); signup(c); old, _ = send_confirmation(c)
    original = deepcopy(c.model.rows(verification)[0])
    c.model.elapse(seconds=60)
    replacement = c.delivery.request_confirmation("subscriber1@example.invalid")
    record = c.model.rows(intents)[-1]
    assert c.delivery.confirm(replacement) == "unavailable"
    claim = c.processor.claim_confirmation(record["intent"])
    assert c.processor.prepare_confirmation(record["intent"], claim, PAGE)
    assert c.model.rows(verification)[0] == original
    assert c.processor.confirmation_outcome(record["intent"], claim, outcome, "<replacement@provider.invalid>")
    if outcome == "provider_accepted":
        assert c.delivery.confirm(old) == "unavailable"
        assert c.delivery.confirm(replacement) == "verified"
        assert c.model.rows(verification)[0]["expires_at"] == record["created_at"] + timedelta(hours=24)
    else:
        assert c.model.rows(verification)[0] == original
        assert c.delivery.confirm(old) == "verified"


@pytest.mark.parametrize("intervention", ["confirmed", "withdrawn", "suppressed", "expired"])
def test_acceptance_cannot_revive_revoked_or_expired_authority(intervention):
    c = build(); signup(c); old, _ = send_confirmation(c); c.model.elapse(seconds=60)
    replacement = c.delivery.request_confirmation("subscriber1@example.invalid")
    record = c.model.rows(intents)[-1]
    claim = c.processor.claim_confirmation(record["intent"])
    assert c.processor.prepare_confirmation(record["intent"], claim, PAGE)
    if intervention == "confirmed": assert c.delivery.confirm(old) == "verified"
    if intervention == "withdrawn": c.manager.unsubscribe_legacy(record["subscription"])
    if intervention == "suppressed": c.manager.suppress("subscriber1@example.invalid", "provider_block")
    if intervention == "expired": c.model.elapse(hours=24)
    preserved = deepcopy(c.model.rows(verification))
    assert c.processor.confirmation_outcome(record["intent"], claim, "provider_accepted", "<r@provider.invalid>")
    assert c.model.rows(verification) == preserved
    assert c.delivery.confirm(replacement) == "unavailable"


def test_recovery_coalescing_keeps_original_expiry_limits_and_uncertainty_hold():
    c = build(); signup(c); token, _ = send_confirmation(c)
    assert c.delivery.confirm(token) == "verified"
    c.model.elapse(seconds=60); c.manager.request_recovery("subscriber1@example.invalid")
    record = deepcopy(c.model.rows(intents)[-1])
    c.model.elapse(seconds=60); c.manager.request_recovery("subscriber1@example.invalid")
    assert c.model.rows(intents)[-1] == record and len(c.model.rows(intents)) == 2
    claim = c.processor.claim_confirmation(record["intent"])
    assert c.processor.prepare_confirmation(record["intent"], claim, PAGE)
    assert c.processor.confirmation_outcome(record["intent"], claim, "submission_unknown")
    c.model.elapse(seconds=60); c.manager.request_recovery("subscriber1@example.invalid")
    assert len(c.model.rows(intents)) == 2 and c.processor.candidates(20) == []
    mailbox = next(r for r in c.model.rows(limits) if r["bucket"] == c.manager._digest("mailbox", "subscriber1@example.invalid"))
    assert mailbox["requests"] == 4
    c.model.elapse(hours=24); c.manager.request_recovery("subscriber1@example.invalid")
    assert len(c.model.rows(intents)) == 3
    assert c.model.rows(intents)[1]["status"] == "uncertain"  # Never reused.
    assert c.model.rows(intents)[-1]["intent"] != record["intent"]


def test_expired_delivered_link_stays_expired_and_replacement_keeps_its_own_request_deadline():
    c = build(); signup(c); old, _ = send_confirmation(c)
    c.model.elapse(seconds=60)
    replacement = c.delivery.request_confirmation("subscriber1@example.invalid")
    requested = c.model.now
    c.model.elapse(hours=24, seconds=-30)
    assert c.delivery.confirm(old) == "unavailable"
    delivered, _ = send_confirmation(c)
    assert delivered == replacement
    assert c.model.rows(verification)[0]["expires_at"] == requested + timedelta(hours=24)
    c.model.elapse(seconds=30)
    assert c.delivery.confirm(replacement) == "unavailable"


def test_concurrent_resends_reserve_one_replacement_without_rotating_delivered_authority():
    from concurrent.futures import ThreadPoolExecutor
    c = build(); signup(c); old, _ = send_confirmation(c); c.model.elapse(seconds=60)
    original = deepcopy(c.model.rows(verification)[0])
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: c.delivery.request_confirmation("subscriber1@example.invalid"), range(8)))
    assert sum(result is not None for result in results) == 1
    assert len(c.model.rows(intents)) == 2 and c.model.rows(verification)[0] == original
    assert c.delivery.confirm(old) == "verified"


@contextmanager
def audit_failure(model, *, rollback_failure=False):
    begin = model.begin
    @contextmanager
    def failing():
        try:
            with begin() as connection:
                execute = connection.execute
                def run(statement):
                    if isinstance(statement, Insert) and statement.table.name == changes.name:
                        driver = type("SyntheticDriver", (Exception,), {"sqlstate": "23514"})("PRIVATE SQL VALUE")
                        raise IntegrityError("PRIVATE SQL", {"token": "PRIVATE PARAM"}, driver, hide_parameters=True)
                    return execute(statement)
                connection.execute = run
                yield connection
        except IntegrityError:
            if rollback_failure: raise RuntimeError("PRIVATE ROLLBACK") from None
            raise
    model.begin = failing
    try: yield
    finally: model.begin = begin


@pytest.mark.parametrize("path", ["website", "legacy", "brevo"])
@pytest.mark.parametrize("rollback_failure", [False, True])
def test_originating_failure_survives_rollback_and_public_responses_stay_private(path, rollback_failure, caplog):
    c = build(); legacy = signup(c); _, manage = send_confirmation(c)
    snapshot = deepcopy(c.model.records)
    body = dict(token=manage, revision=0, action="a"*64)
    with audit_failure(c.model, rollback_failure=rollback_failure):
        if path == "website": reply = post(c.client, c.csrf, body, "/api/notifications/manage/save")
        elif path == "legacy": reply = post(c.client, c.csrf, {"token": legacy}, "/api/notifications/unsubscribe")
        else: reply = callback(c, genuine_shaped_event(c))
    assert reply.status_code == (429 if path == "brevo" else 503)
    assert c.model.records == snapshot
    logs = [record.message for record in caplog.records if record.message.startswith("Notification operation failed: ")]
    assert len(logs) == 1
    diagnostic = json.loads(logs[0].split(": ", 1)[1])
    first = diagnostic["first_failure"]
    assert first["operation"] == "audit_insert" and first["exception_class"] == "IntegrityError"
    assert first["sqlstate"] == "23514"
    assert first["side_effects"] == ("database_rollback_uncertain" if rollback_failure else "database_rolled_back")
    if rollback_failure: assert diagnostic["rollback_failure"]["exception_class"] == "RuntimeError"
    for private in ("PRIVATE", manage, legacy, BEARER, "subscriber1@example.invalid"):
        assert private not in caplog.text and private not in reply.text
    if path == "website": result = post(c.client, c.csrf, body, "/api/notifications/manage/save")
    elif path == "legacy": result = post(c.client, c.csrf, {"token": legacy}, "/api/notifications/unsubscribe")
    else: result = callback(c, genuine_shaped_event(c))
    assert result.status_code == 200 and len(c.model.rows(changes)) == 1


@pytest.mark.parametrize("phase", ["commit", "uncertain"])
def test_commit_failure_reports_uncertainty_and_acknowledges_only_a_committed_action(phase, caplog):
    c = build(); signup(c); _, manage = send_confirmation(c)
    body = dict(token=manage, action="a"*64, revision=0)
    receipt = post(c.client, c.csrf, body, "/api/notifications/manage/withdrawal-receipt").json["receipt"]
    c.model.failure = phase
    assert post(c.client, c.csrf, body, "/api/notifications/manage/save").status_code == 503
    c.model.failure = None
    assert '"operation": "transaction_commit"' in caplog.text
    assert '"side_effects": "database_commit_uncertain"' in caplog.text
    acknowledgment = post(c.client, c.csrf, dict(receipt=receipt, action="a"*64, revision=0),
                          "/api/notifications/manage/withdrawal-ack")
    assert acknowledgment.status_code == (200 if phase == "uncertain" else 400)
    assert len(c.model.rows(changes)) == int(phase == "uncertain")
