"""Anonymous subscriptions, guarded email confirmation and capability-only withdrawal."""

from .notification_dispatch import diagnostic_error

import hashlib
import hmac
import json
import re

from flask import jsonify, request
from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert

from .notification_schema import CONSENT_VERSION, notifications
from .state_request_schema import STATE_CODES

TOKEN = re.compile(r"[0-9a-f]{64}")
LOCAL = re.compile(r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*", re.ASCII)
LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII)
CONFIRMATION_REQUESTED = "If confirmation is needed and permitted, we'll email a link."
CONFIRMED = "Your email is confirmed."
ALREADY_CONFIRMED = "Your email is already confirmed."
LINK_UNAVAILABLE = "This link is unavailable. Request a new confirmation link."
CONFIRMATION_OFF = "Email confirmation is currently unavailable."


class UnsubscribeCapabilities:
    """Regenerable private links for future delivery, without stored bearer tokens."""
    def __init__(self, secret):
        if type(secret) is not bytes or len(secret) < 32:
            raise ValueError("A persistent protected secret of at least 32 bytes is required.")
        self.secret = secret

    def issue(self, digest):
        signature = hmac.new(self.secret, b"oaf-notification-unsubscribe-v1:" + digest.encode("ascii"),
                             hashlib.sha256).hexdigest()
        return digest + "." + signature

    def read(self, token):
        if type(token) is not str or not re.fullmatch(r"[0-9a-f]{64}\.[0-9a-f]{64}", token):
            return None
        digest = token[:64]
        return digest if hmac.compare_digest(self.issue(digest), token) else None


def normalize_email(value):
    # Deliberately support common ASCII mailbox syntax, without DNS/network
    # checks or provider-specific dot/plus rewriting. Never echo supplied input.
    if type(value) is not str or not value.isascii():
        raise diagnostic_error(ValueError("Enter a valid email address using standard letters and symbols."), "normalize_email", "email_ascii", stage="request")
    email = value.strip(" ").lower()
    if len(email) > 254 or email.count("@") != 1:
        raise diagnostic_error(ValueError("Enter a valid email address."), "normalize_email", "email_length_and_separator", stage="request")
    local, domain = email.split("@")
    labels = domain.split(".")
    if (len(local) > 64 or not LOCAL.fullmatch(local) or len(labels) < 2
            or not all(LABEL.fullmatch(label) for label in labels)
            or len(labels[-1]) < 2 or not labels[-1].isalpha()):
        raise diagnostic_error(ValueError("Enter a valid email address."), "normalize_email", "email_mailbox_syntax", stage="request")
    return email


def validate_subscription(data):
    fields = {"email", "web_launch", "android_launch", "ios_launch", "state", "consent", "token"}
    if type(data) is not dict or set(data) != fields:
        raise diagnostic_error(ValueError("Complete the email, preferences and consent fields."), "validate_subscription", "signup_fields", stage="request")
    email = normalize_email(data["email"])
    flags = (data["web_launch"], data["android_launch"], data["ios_launch"])
    if any(type(flag) is not bool for flag in flags):
        raise diagnostic_error(ValueError("Choose valid notification preferences."), "validate_subscription", "signup_preference_types", stage="request")
    state = data["state"]
    if state is not None and (type(state) is not str or state not in STATE_CODES):
        raise diagnostic_error(ValueError("Select one of the 50 U.S. states for availability updates."), "validate_subscription", "signup_state", stage="request")
    if not any(flags) and state is None:
        raise diagnostic_error(ValueError("Choose at least one notification preference."), "validate_subscription", "signup_selection", stage="request")
    if data["consent"] is not True:
        raise diagnostic_error(ValueError("Consent is required to subscribe to the selected announcements."), "validate_subscription", "signup_consent", stage="request")
    if type(data["token"]) is not str or not TOKEN.fullmatch(data["token"]):
        raise diagnostic_error(ValueError("Reload the page and try again."), "validate_subscription", "signup_receipt", stage="request")
    return dict(email=email, web_launch=flags[0], android_launch=flags[1], ios_launch=flags[2],
                state=state, consent_version=CONSENT_VERSION,
                unsubscribe_digest=hashlib.sha256(data["token"].encode("ascii")).hexdigest())


class SubscriptionStore:
    def __init__(self, engine, *, confirmation_store=None, management_store=None):
        if confirmation_store is not None and confirmation_store.engine is not engine:
            raise ValueError("Confirmation must share the subscription engine and transaction.")
        self.engine = engine
        self.confirmation_store = confirmation_store
        if management_store is not None and management_store.engine is not engine:
            raise ValueError("Management must share the subscription engine.")
        self.management_store = management_store

    def subscribe(self, values):
        # Both the permanent receipt PK and the partial active-email unique
        # index arbitrate races. No existing preference or token is replaced.
        statement = insert(notifications).values(**values).on_conflict_do_nothing()
        if self.confirmation_store is not None:
            delivery = self.confirmation_store
            with delivery._transaction() as (connection, now):
                created = connection.execute(statement.returning(notifications.c.unsubscribe_digest)).scalar_one_or_none()
                if created is not None:
                    # Only a genuinely new receipt/lifecycle may reserve work.
                    # A repeat after a lost COMMIT response cannot rotate it.
                    delivery._request_confirmation(connection, now, values["email"])
            return
        with diagnostic_transaction(self.engine) as connection:
            connection.execute(statement)

    def unsubscribe(self, digest):
        if self.management_store is not None:
            return self.management_store.unsubscribe_legacy(digest)
        statement = (update(notifications)
                     .where(notifications.c.unsubscribe_digest == digest,
                            notifications.c.unsubscribed_at.is_(None))
                     .values(unsubscribed_at=func.greatest(func.current_timestamp(), notifications.c.created_at)))
        with diagnostic_transaction(self.engine) as connection:
            connection.execute(statement)


def subscription_response(values, capabilities):
    # Sign only the submitted receipt, never an existing email's private digest.
    return jsonify(status="received", unsubscribe_token=capabilities.issue(values['unsubscribe_digest']),
                   message="Your submission was processed. New subscriptions are saved; existing active preferences stay unchanged.")


def register_notifications(app, store, capabilities, same_origin, valid_csrf, error, *,
                           recognition, browser_cookie_name, secure):
    confirmation = store.confirmation_store

    def payload():
        if not same_origin(mutation=True) or not valid_csrf():
            return None, error("Enable cookies, open this website, and try again.", 403, operation="payload", predicate="request_origin_or_csrf")
        if request.mimetype != "application/json":
            return None, error("Submit the notification form and try again.", 415, operation="payload", predicate="request_json_media_type")
        try:
            from .integrations import _strict_object, _invalid_constant
            return json.loads(request.get_data().decode("utf-8"), object_pairs_hook=_strict_object,
                              parse_constant=_invalid_constant), None
        except (ValueError, UnicodeError, RecursionError):
            return None, error("Submit the notification form and try again.", 400, operation="payload", predicate="request_json_decode")

    from .notification_management import register_management
    register_management(app, store.management_store, payload, error, recognition=recognition,
                        browser_cookie_name=browser_cookie_name, secure=secure)

    @app.post("/api/notifications/confirmation")
    def request_confirmation():
        data, failure = payload()
        if failure is not None:
            return failure
        if confirmation is None:
            return error(CONFIRMATION_OFF, 503, operation="request_confirmation", predicate="confirmation_enabled")
        try:
            if type(data) is not dict or set(data) != {"email"}:
                raise diagnostic_error(ValueError("Enter only your email address."), "request_confirmation", "confirmation_fields", stage="request")
            email = normalize_email(data["email"])
        except ValueError as invalid:
            return error(str(invalid), 400, operation="request_confirmation", predicate="confirmation_input")
        try:
            confirmation.request_confirmation(email)  # Never expose the sensitive return.
        except Exception as exc:
            log_notification_failure(app.logger, "confirmation_reservation", exc, http_status=503)
            return error("We could not confirm this request. Please try again later.", 503, operation="request_confirmation", predicate="confirmation_reservation")
        return jsonify(status="received", message=CONFIRMATION_REQUESTED)

    @app.post("/api/notifications/confirm")
    def confirm():
        data, failure = payload()
        if failure is not None:
            return failure
        if confirmation is None:
            return error(CONFIRMATION_OFF, 503, operation="confirm", predicate="confirmation_enabled")
        if (type(data) is not dict or set(data) != {"token"}
                or type(data["token"]) is not str or not TOKEN.fullmatch(data["token"])):
            return error(LINK_UNAVAILABLE, 400, operation="confirm", predicate="confirmation_token_format")
        try:
            outcome = confirmation.confirm(data["token"])
        except Exception as exc:
            log_notification_failure(app.logger, "confirmation_persistence", exc, http_status=503)
            return error("We could not confirm this action. Please try this link again.", 503, operation="confirm", predicate="confirmation_persistence")
        if outcome not in {"verified", "already_verified"}:
            return error(LINK_UNAVAILABLE, 400, operation="confirm", predicate="confirmation_authority")
        # Keep the successful status compatible with existing confirmation clients.
        already_confirmed = outcome == "already_verified"
        return jsonify(status="confirmed", already_confirmed=already_confirmed,
                       message=ALREADY_CONFIRMED if already_confirmed else CONFIRMED)

    @app.post("/api/notifications")
    def subscribe():
        data, failure = payload()
        if failure is not None:
            return failure
        try:
            values = validate_subscription(data)
        except ValueError as invalid:
            return error(str(invalid), 400, operation="subscribe", predicate="signup_input")
        try:
            store.subscribe(values)
        except Exception as exc:
            log_notification_failure(app.logger, "signup_persistence", exc, http_status=503)
            return error("We could not confirm your subscription. Try again with the same form; duplicates are prevented.", 503, operation="subscribe", predicate="signup_persistence")
        # Same response for a new receipt, active email duplicate or retry.
        # Sign only the caller's receipt, never look up an existing email's token.
        return subscription_response(values, capabilities)

    @app.post("/api/notifications/unsubscribe")
    def unsubscribe():
        data, failure = payload()
        if failure is not None:
            return failure
        digest = capabilities.read(data.get('token')) if type(data) is dict and set(data) == {'token'} else None
        if digest is None:
            return error("Use the complete private unsubscribe link saved when subscribing.", 400, operation="unsubscribe", predicate="unsubscribe_capability")
        try:
            store.unsubscribe(digest)
        except Exception as exc:
            from .notification_dispatch import log_notification_failure
            log_notification_failure(app.logger, "legacy_unsubscribe", exc)
            return error("We could not confirm unsubscribe. Please try this private link again.", 503, operation="unsubscribe", predicate="unsubscribe_persistence")
        return jsonify(status="unsubscribed", message="Any active subscription created with this private link has been unsubscribed.")

from .notification_dispatch import log_notification_failure

from .notification_dispatch import diagnostic_transaction
