"""Anonymous subscriptions, explicit consent and capability-only withdrawal."""

import hashlib
import hmac
import re

from flask import jsonify, request
from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from werkzeug.exceptions import BadRequest

from .notification_schema import CONSENT_VERSION, notifications
from .state_request_schema import STATE_CODES

TOKEN = re.compile(r"[0-9a-f]{64}")
LOCAL = re.compile(r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*", re.ASCII)
LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII)


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
        raise ValueError("Enter a valid email address using standard letters and symbols.")
    email = value.strip(" ").lower()
    if len(email) > 254 or email.count("@") != 1:
        raise ValueError("Enter a valid email address.")
    local, domain = email.split("@")
    labels = domain.split(".")
    if (len(local) > 64 or not LOCAL.fullmatch(local) or len(labels) < 2
            or not all(LABEL.fullmatch(label) for label in labels)
            or len(labels[-1]) < 2 or not labels[-1].isalpha()):
        raise ValueError("Enter a valid email address.")
    return email


def validate_subscription(data):
    fields = {"email", "web_launch", "android_launch", "ios_launch", "state", "consent", "token"}
    if type(data) is not dict or set(data) != fields:
        raise ValueError("Complete the email, preferences and consent fields.")
    email = normalize_email(data["email"])
    flags = (data["web_launch"], data["android_launch"], data["ios_launch"])
    if any(type(flag) is not bool for flag in flags):
        raise ValueError("Choose valid notification preferences.")
    state = data["state"]
    if state is not None and (type(state) is not str or state not in STATE_CODES):
        raise ValueError("Select one of the 50 U.S. states for availability updates.")
    if not any(flags) and state is None:
        raise ValueError("Choose at least one notification preference.")
    if data["consent"] is not True:
        raise ValueError("Consent is required to subscribe to the selected announcements.")
    if type(data["token"]) is not str or not TOKEN.fullmatch(data["token"]):
        raise ValueError("Reload the page and try again.")
    return dict(email=email, web_launch=flags[0], android_launch=flags[1], ios_launch=flags[2],
                state=state, consent_version=CONSENT_VERSION,
                unsubscribe_digest=hashlib.sha256(data["token"].encode("ascii")).hexdigest())


class SubscriptionStore:
    def __init__(self, engine):
        self.engine = engine

    def subscribe(self, values):
        # Both the permanent receipt PK and the partial active-email unique
        # index arbitrate races. No existing preference or token is replaced.
        statement = insert(notifications).values(**values).on_conflict_do_nothing()
        with self.engine.begin() as connection:
            connection.execute(statement)

    def unsubscribe(self, digest):
        statement = (update(notifications)
                     .where(notifications.c.unsubscribe_digest == digest,
                            notifications.c.unsubscribed_at.is_(None))
                     .values(unsubscribed_at=func.greatest(func.current_timestamp(), notifications.c.created_at)))
        with self.engine.begin() as connection:
            connection.execute(statement)


def register_notifications(app, store, capabilities, same_origin, valid_csrf, error):
    def payload():
        if not same_origin(mutation=True) or not valid_csrf():
            return None, error("Enable cookies, open this website, and try again.", 403)
        if request.mimetype != "application/json":
            return None, error("Submit the notification form and try again.", 415)
        try:
            return request.get_json(), None
        except BadRequest:
            return None, error("Submit the notification form and try again.", 400)

    @app.post("/api/notifications")
    def subscribe():
        data, failure = payload()
        if failure is not None:
            return failure
        try:
            values = validate_subscription(data)
        except ValueError as invalid:
            return error(str(invalid), 400)
        try:
            store.subscribe(values)
        except Exception:
            app.logger.warning("Notification subscription persistence unavailable.")
            return error("We could not confirm your subscription. Try again with the same form; duplicates are prevented.", 503)
        # Same response for a new receipt, active email duplicate or retry.
        # Sign only the caller's receipt, never look up an existing email's token.
        return jsonify(status="received", unsubscribe_token=capabilities.issue(values['unsubscribe_digest']),
                       message="Your submission was processed. New subscriptions are saved; existing active preferences stay unchanged. No email has been sent.")

    @app.post("/api/notifications/unsubscribe")
    def unsubscribe():
        data, failure = payload()
        if failure is not None:
            return failure
        digest = capabilities.read(data.get('token')) if type(data) is dict and set(data) == {'token'} else None
        if digest is None:
            return error("Use the complete private unsubscribe link saved when subscribing.", 400)
        try:
            store.unsubscribe(digest)
        except Exception:
            app.logger.warning("Notification unsubscribe persistence unavailable.")
            return error("We could not confirm unsubscribe. Please try this private link again.", 503)
        return jsonify(status="unsubscribed", message="Any active subscription created with this private link has been unsubscribed.")
