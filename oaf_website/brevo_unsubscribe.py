"""One authenticated transactional event; no provider API or reconciliation worker."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hmac
import json
import os
import re

from flask import jsonify, request
from sqlalchemy import select

from .database_config import _validate_environment, _windows_password
from .notification_delivery_schema import events, deliveries, attempts, suppressions
from .confirmation_outbox_schema import intents, confirmation_attempts
from .notification_management_schema import notifications, changes
from .notifications import normalize_email
from .notification_dispatch import safe_failure, log_notification_failure

WEBHOOK_PATH = "/api/notifications/brevo/unsubscribed"
ALLOWED_FIELDS = {"event", "email", "message-id", "ts", "ts_event", "id", "date", "subject",
                  "X-Mailin-custom", "template_id", "tag", "tags", "ts_epoch", "sending_ip",
                  "user_agent", "device_used", "mirror_link", "contact_id",
                  "link", "sender_email", "source", "uuid"}


@dataclass(frozen=True)
class BrevoWebhookConfig:
    environment: str
    token: str = field(repr=False)

    def __post_init__(self):
        if (self.environment not in {"testing", "development"} or type(self.token) is not str
                or re.fullmatch(r"[A-Za-z0-9_-]{32,256}", self.token, re.ASCII) is None):
            raise diagnostic_error(ValueError("Protected webhook configuration unavailable."), "webhook_configuration", "webhook_token_format", stage="startup")


def validate_webhook_config(config, environment):
    if type(config) is not BrevoWebhookConfig or config.environment != environment:
        raise diagnostic_error(ValueError("Webhook configuration must match the runtime environment."), "webhook_configuration", "webhook_environment_match", stage="startup")


def load_brevo_webhook_config(expected_profile, *, credential_account, environ=None, credential_loader=None):
    """Explicit protected loading only. Never provision or print the bearer."""
    try:
        environment = dict(os.environ if environ is None else environ)
        _validate_environment(environment, expected_profile)
        if (expected_profile not in {"testing", "development"} or type(credential_account) is not str
                or re.fullmatch(r"[A-Za-z0-9@._/-]{1,128}", credential_account, re.ASCII) is None
                or any(n.upper().startswith(("BREVO", "SENDINBLUE")) for n in environment)):
            raise diagnostic_error(ValueError(), "webhook_configuration", "webhook_credential_metadata", stage="startup")
        loader = _windows_password if credential_loader is None else credential_loader
        value = loader(f"OAF Website/{expected_profile}/Brevo/UnsubscribeWebhook", credential_account,
                       environment, exact_target=True)
        return BrevoWebhookConfig(expected_profile, value)
    except Exception as exc:
        first = safe_failure("startup", "webhook_configuration", exc, predicate="webhook_credential_read")
    failure = ValueError("Protected webhook configuration unavailable.")
    failure.notification_failure = first
    report_failure("webhook_configuration", failure)
    raise failure from None


def _failure(context, predicate, exc=None, *, field_names=None):
    """Fixed codes and bounded sanitized field names; never payload values."""
    failure = ValueError("Invalid event.")
    failure.notification_failure = safe_failure(
        "notifications", "brevo_unsubscribe", exc, context=context, predicate=predicate,
        preserve=False, field_names=field_names)
    return failure


def message_identity(value):
    if type(value) is not str:
        raise _failure("webhook_event", "webhook_message_id_text")
    if len(value) > 200:
        raise _failure("webhook_event", "webhook_message_id_length")
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1]
    if re.fullmatch(r"[A-Za-z0-9_.+:/-]+@[A-Za-z0-9.-]+", value, re.ASCII) is None:
        raise _failure("webhook_event", "webhook_message_id_format")
    return value


def event_payload(data):
    def invalid(predicate):
        return _failure("webhook_event", predicate)

    if type(data) is not dict:
        raise invalid("webhook_event_object")
    if not {"event", "email", "message-id", "ts_event"} <= set(data):
        raise invalid("webhook_required_fields")
    if not set(data) <= ALLOWED_FIELDS:
        raise _failure("webhook_event", "webhook_allowed_fields",
                       field_names=set(data) - ALLOWED_FIELDS)
    if data["event"] != "unsubscribed":
        raise invalid("webhook_event_name")
    for name in ("ts_event", "ts", "id", "template_id", "contact_id", "ts_epoch"):
        if name not in data:
            continue
        if type(data[name]) is not int:
            raise invalid("webhook_" + name + "_integer")
        valid_range = 0 < data[name] <= 253402300799 if name in {"ts_event", "ts"} else data[name] >= 0
        if not valid_range:
            raise invalid("webhook_" + name + "_range")
    # Deterministic order, fixed field codes; never retain supplied keys/values.
    for name, code in (("date", "date"), ("subject", "subject"), ("X-Mailin-custom", "custom"),
                       ("tag", "tag"), ("sending_ip", "sending_ip"), ("user_agent", "user_agent"),
                       ("device_used", "device_used"), ("mirror_link", "mirror_link")):
        if name in data:
            if type(data[name]) is not str:
                raise invalid("webhook_" + code + "_text")
            if len(data[name]) > 8192:
                raise invalid("webhook_" + code + "_length")
    if "tags" in data:
        if type(data["tags"]) is not list:
            raise invalid("webhook_tags_array")
        if len(data["tags"]) > 50:
            raise invalid("webhook_tags_count")
        for tag in data["tags"]:
            if type(tag) is not str:
                raise invalid("webhook_tags_text")
            if len(tag) > 256:
                raise invalid("webhook_tags_length")
    try:
        email = normalize_email(data["email"])
    except ValueError as exc:
        raise _failure("webhook_event", "webhook_email_format", exc) from None
    identity = message_identity(data["message-id"])
    times = {}
    for name, value in (("event", data["ts_event"]), ("original", data.get("ts", data["ts_event"]))):
        try:
            times[name] = datetime.fromtimestamp(value, timezone.utc)
        except (ValueError, OverflowError, OSError) as exc:
            raise _failure("webhook_event", "webhook_" + name + "_time_supported", exc) from None
    # id is the provider webhook definition identity, never a delivery identity.
    # Observed link/sender_email/source/uuid are optional opaque metadata. Their
    # values are never read, retained, or used as authority or fallback identity.
    return dict(email=email, message_id=identity, event_at=times["event"], original_at=times["original"])


def process_unsubscribe(store, event, *, diagnostics=None):
    def reject(predicate, outcome="rejected"):
        if diagnostics is not None and not diagnostics:
            diagnostics.append(_failure("webhook_correlation", predicate))
        return outcome

    identity = event["message_id"]
    variants = (identity, "<" + identity + ">")
    with store._transaction() as (connection, now):
        if event["event_at"] > now + timedelta(minutes=5):
            return reject("webhook_event_not_future")
        if event["original_at"] > event["event_at"]:
            return reject("webhook_time_order")
        candidates = {}
        # Review both parent and attempt persistence. Matching only email or a
        # webhook id can never authorize withdrawal. Any contradictory match fails.
        for parent_table, attempt_table, kind in ((intents, confirmation_attempts, "confirmation"),
                                                  (deliveries, attempts, "release")):
            parent_key = ("intent",) if kind == "confirmation" else ("event_id", "subscription")
            parents = list(connection.execute(select(parent_table).where(
                parent_table.c.provider_message_id.in_(variants))).mappings())
            matching_attempts = list(connection.execute(select(attempt_table).where(
                attempt_table.c.provider_message_id.in_(variants))).mappings())
            for attempt in matching_attempts:
                key = {n: attempt[n] for n in parent_key}
                parent = store._get(connection, parent_table, **key)
                if parent is None:
                    return reject("webhook_attempt_parent_present")
                if not any(all(p[n] == parent[n] for n in parent_key) for p in parents):
                    parents.append(parent)
            for parent in parents:
                key = {n: parent[n] for n in parent_key}
                expected = store._get(connection, attempt_table, **key, attempt=parent["attempts"])
                # Preserve short circuit order and the existing submitting retry.
                predicate = None
                if parent["status"] != "accepted":
                    predicate = "webhook_parent_accepted"
                elif parent["outcome"] != "provider_accepted":
                    predicate = "webhook_parent_outcome"
                elif parent["provider_message_id"] not in variants:
                    predicate = "webhook_parent_message"
                elif parent["accepted_at"] is None:
                    predicate = "webhook_parent_accepted_at"
                elif expected is None:
                    predicate = "webhook_attempt_present"
                elif expected["outcome"] != "provider_accepted":
                    predicate = "webhook_attempt_outcome"
                elif expected["provider_message_id"] not in variants:
                    predicate = "webhook_attempt_message"
                elif expected["submitting_at"] is None:
                    predicate = "webhook_attempt_submitting_at"
                elif expected["finished_at"] is None:
                    predicate = "webhook_attempt_finished_at"
                elif expected["finished_at"] != parent["accepted_at"]:
                    predicate = "webhook_acceptance_time_match"
                elif expected["finished_at"] < expected["submitting_at"]:
                    predicate = "webhook_attempt_time_order"
                elif any(a["attempt"] != expected["attempt"] for a in matching_attempts
                         if all(a[n] == parent[n] for n in parent_key)):
                    predicate = "webhook_latest_attempt_match"
                if predicate is not None:
                    return reject(predicate, "retry" if parent["status"] == "submitting" else "rejected")
                if kind == "release":
                    release = store._get(connection, events, event_id=parent["event_id"])
                    if release is None:
                        return reject("webhook_release_present")
                    if release["environment"] != store.environment:
                        return reject("webhook_release_environment")
                send_key = (kind, *(parent[n] for n in parent_key), expected["attempt"])
                candidates[send_key] = (parent["subscription"], expected["submitting_at"])
        if not candidates:
            # A callback can race the accepted-outcome commit. Brevo retries 429,
            # but discards 5xx. Finite provider retry does not guarantee delivery.
            return reject("webhook_accepted_message_present", "retry")
        if len(candidates) != 1:
            return reject("webhook_accepted_message_unique")
        subscription, submitting_at = next(iter(candidates.values()))
        subscriber = store._get(connection, notifications, unsubscribe_digest=subscription)
        if subscriber is None:
            return reject("webhook_subscriber_present")
        if subscriber["email"] != event["email"]:
            return reject("webhook_recipient_match")
        if event["original_at"].timestamp() < int(submitting_at.timestamp()):
            return reject("webhook_original_after_submission")
        if event["event_at"].timestamp() < int(submitting_at.timestamp()):
            return reject("webhook_event_after_submission")
        mailbox = store._digest("mailbox", event["email"])
        action = store._digest("brevo-unsubscribed", store.environment + ":" + identity + ":" + mailbox)
        if store._get(connection, changes, action_digest=action) is not None:
            return "processed"
        # Already withdrawn original lifecycles still retain the event receipt and
        # permanent provider block. Never touch a newer lifecycle's consent.
        store._change(connection, now, subscriber, action, action, "brevo",
                      message_id=identity, event_at=event["event_at"])
        store._insert(connection, suppressions, dict(mailbox_digest=mailbox, reason="provider_block", created_at=now))
        return "processed"


def register_brevo_unsubscribe(app, store, config, error):
    def reject(context, predicate, message, status, exc=None):
        log_notification_failure(app.logger, "brevo_unsubscribe", _failure(context, predicate, exc), http_status=status)
        return error(message, status)

    @app.post(WEBHOOK_PATH)
    def brevo_unsubscribe():
        if config is None:
            return reject("webhook_configuration", "webhook_config_present", "Webhook unavailable.", 429)
        if store is None:
            return reject("webhook_configuration", "webhook_store_present", "Webhook unavailable.", 429)
        authorization = request.headers.get("Authorization", "")
        if not request.is_secure:
            return reject("webhook_authentication", "webhook_https", "Unauthorized webhook.", 401)
        if request.query_string:
            return reject("webhook_authentication", "webhook_no_query", "Unauthorized webhook.", 401)
        if not authorization.isascii():
            return reject("webhook_authentication", "webhook_authorization_ascii", "Unauthorized webhook.", 401)
        if not hmac.compare_digest(authorization, "Bearer " + config.token):
            return reject("webhook_authentication", "webhook_authorization_match", "Unauthorized webhook.", 401)
        if request.mimetype != "application/json":
            return reject("webhook_media_type", "webhook_json_media_type", "Invalid event.", 415)
        try:
            from .integrations import _strict_object, _invalid_constant

            def strict_object(pairs):
                try:
                    return _strict_object(pairs)
                except ValueError as exc:
                    raise _failure("webhook_json", "webhook_json_unique_keys", exc) from None

            def invalid_constant(value):
                try:
                    return _invalid_constant(value)
                except ValueError as exc:
                    raise _failure("webhook_json", "webhook_json_finite_constants", exc) from None

            data = json.loads(request.get_data().decode("utf-8"), object_pairs_hook=strict_object,
                              parse_constant=invalid_constant)
            event = event_payload(data)
        except (ValueError, UnicodeError, RecursionError, OverflowError, OSError) as exc:
            failure = exc if getattr(exc, "notification_failure", None) is not None else _failure(
                "webhook_json", "webhook_json_decode", exc)
            log_notification_failure(app.logger, "brevo_unsubscribe", failure, http_status=400)
            return error("Invalid event.", 400)
        diagnostics = []
        try:
            outcome = process_unsubscribe(store, event, diagnostics=diagnostics)
        except Exception as exc:
            # A later transaction failure must not replace an earlier rejection.
            if diagnostics:
                transaction = getattr(exc, "notification_failure", None)
                first = diagnostics[0].notification_failure
                if transaction is not None:
                    first["side_effects"] = transaction["side_effects"]
                    exc.notification_transaction_failure = transaction
                else:
                    first["side_effects"] = "database_transaction_unacknowledged"
                exc.notification_failure = first
            log_notification_failure(app.logger, "brevo_unsubscribe", exc, http_status=429)
            return error("Event processing unavailable.", 429)
        if outcome == "retry":
            log_notification_failure(app.logger, "brevo_unsubscribe", diagnostics[0], http_status=429)
            return error("Event processing unavailable.", 429)
        if outcome == "rejected":
            log_notification_failure(app.logger, "brevo_unsubscribe", diagnostics[0], http_status=400)
            return error("Invalid event correlation.", 400)
        return jsonify(status="processed")

from .notification_dispatch import diagnostic_error, report_failure
