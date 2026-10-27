"""Anonymous recognition, authoritative validation and committed-record counting."""

import hashlib
import hmac
import re
import sys
import secrets
from urllib.parse import urlsplit
from uuid import UUID

from flask import Flask, jsonify, request, g
from itsdangerous import BadData, URLSafeSerializer
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import insert
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from .database_config import (
    DatabaseConfigurationError, load_database_config, load_testing_database_config,
)
from .state_request_schema import STATE_CODES, state_requests

COOKIE_AGE = 60 * 60 * 24 * 365


def valid_state(value):
    return type(value) is str and value in STATE_CODES


class BrowserRecognition:
    def __init__(self, secret):
        if type(secret) is not bytes or len(secret) < 32:
            raise ValueError("A persistent recognition secret of at least 32 bytes is required.")
        self.secret = secret
        self.serializer = URLSafeSerializer(
            secret, salt="oaf-state-browser-v1",
            signer_kwargs={"digest_method": hashlib.sha256},
        )

    def read(self, cookie):
        if not cookie or len(cookie) > 256:
            return None
        try:
            token = self.serializer.loads(cookie)
        except BadData:
            return None
        return token if type(token) is str and re.fullmatch(r"[0-9a-f]{64}", token) else None

    def issue(self):
        token = secrets.token_hex(32)
        return token, self.serializer.dumps(token)

    def csrf(self, token):
        return hmac.new(self.secret, b"oaf-state-csrf-v1:" + token.encode(), hashlib.sha256).hexdigest()

    def browser_key(self, token):
        return UUID(bytes=hashlib.sha256(b"oaf-state-key-v1:" + token.encode()).digest()[:16])


class RequestStore:
    def __init__(self, engine):
        self.engine = engine

    def submit(self, state, browser_key):
        # No preliminary SELECT and no counter update. PostgreSQL arbitrates
        # competing inserts, including different workers, in its unique index.
        statement = (insert(state_requests).values(state=state, browser_key=browser_key)
                     .on_conflict_do_nothing(constraint="state_requests_pk")
                     .returning(state_requests.c.state))
        with diagnostic_transaction(self.engine) as connection:
            accepted = connection.execute(statement).scalar_one_or_none() is not None
        # Return only after the transaction context acknowledges COMMIT.
        return accepted

    def totals(self):
        statement = select(state_requests.c.state, func.count()).group_by(state_requests.c.state)
        with self.engine.connect() as connection:
            counts = dict(connection.execute(statement).all())
        return {state: counts.get(state, 0) for state in STATE_CODES}


def _verify_checkout(config, dbapi_connection, connection_record, connection_proxy):
    """Check every physical/pool checkout before any application query."""
    with dbapi_connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), current_user, session_user, "
                       "pg_catalog.host(pg_catalog.inet_server_addr()), "
                       "pg_catalog.inet_server_port(), "
                       "pg_catalog.current_setting('server_version_num')::int / 10000")
        database, effective, authenticated, host, port, major = cursor.fetchone()
    dbapi_connection.rollback()
    config.verify_connection_identity(database, effective)
    for valid, predicate in ((authenticated == config.url.username, "database_authenticated_identity"),
            (host == config.url.host, "database_server_address"), (port == config.url.port, "database_server_port"),
            (major == 17, "database_server_version")):
        if not valid:
            raise diagnostic_error(DatabaseConfigurationError("Connected database identity does not match the selected profile."),
                "database_checkout", predicate, stage="startup")


def _origin(value):
    try:
        parts = urlsplit(value)
        if (parts.scheme not in {"http", "https"} or not parts.hostname
                or parts.username or parts.password or parts.fragment):
            return None
        port = parts.port
        host = parts.hostname.lower()
        return parts.scheme, host, port if port is not None else (443 if parts.scheme == "https" else 80)
    except (ValueError, TypeError):
        return None


def _build_app(store, recognition, public_origin, *, allow_insecure_localhost=False,
               subscription_store=None, integration_config=None, reporting_store=None,
               environment=None, contact_sender=None, brevo_webhook_config=None, release_store=None):
    trusted = _origin(public_origin)
    parts = urlsplit(public_origin)
    if (trusted is None or parts.path not in {"", "/"} or parts.query
            or (trusted[0] != "https" and not (
                allow_insecure_localhost and trusted[1] in {"127.0.0.1", "localhost", "::1"}))):
        raise ValueError("An explicit HTTPS public origin is required; local HTTP needs explicit opt-in.")
    secure = trusted[0] == "https"
    cookie_name = "__Host-oaf-state-browser" if secure else "oaf-state-browser"
    app = Flask(__name__, static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=1024)
    def safe_uncaught(exc_info):
        log_notification_failure(app.logger, "http_request", exc_info[1], http_status=500)
    app.log_exception = safe_uncaught

    @app.before_request
    def webhook_body_limit():
        # Only this authenticated provider route accepts the larger Brevo shape.
        if request.path == "/api/notifications/brevo/unsubscribed":
            request.max_content_length = 16384

    from .notification_dispatch import retain_failure, report_request_failure, log_notification_failure

    def error(message, status, *, operation="http_request", predicate="http_rejection"):
        retain_failure(operation, predicate, sys.exception())
        return jsonify(status="error", message=message), status

    def same_origin(*, mutation=False):
        # Fetch metadata is defense in depth; Origin/Referer and the custom
        # browser-bound CSRF header remain required on mutations.
        site = request.headers.get("Sec-Fetch-Site")
        if site is not None and site != "same-origin":
            retain_failure("http_request", "request_fetch_site")
            return False
        origin = request.headers.get("Origin")
        if origin is not None:
            try:
                parsed = urlsplit(origin)
                valid = parsed.path == "" and not parsed.query and _origin(origin) == trusted
                if not valid: retain_failure("http_request", "request_origin")
                return valid
            except ValueError:
                retain_failure("http_request", "request_origin")
                return False
        referer = request.headers.get("Referer")
        if referer is not None:
            valid = _origin(referer) == trusted
            if not valid: retain_failure("http_request", "request_referer")
            return valid
        if mutation: retain_failure("http_request", "request_origin_missing")
        return not mutation

    def valid_csrf():
        token = recognition.read(request.cookies.get(cookie_name))
        csrf = request.headers.get("X-CSRF-Token", "")
        valid = (token is not None and re.fullmatch(r"[0-9a-f]{64}", csrf) is not None
                 and hmac.compare_digest(recognition.csrf(token), csrf))
        if not valid:
            retain_failure("http_request", "csrf_browser_missing" if token is None else
                           "csrf_header_format" if re.fullmatch(r"[0-9a-f]{64}", csrf) is None else "csrf_signature")
        return valid

    @app.after_request
    def private_response(response):
        report_request_failure(response, app.logger)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = ("no-referrer" if request.path.startswith("/api/notifications/manage")
            or request.path in {"/manage-notifications.html", "/api/notifications/brevo/unsubscribed"} else "same-origin")
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        if request.path.startswith("/api/notifications"):
            return error("Submit only the email, preferences and consent fields.", 413, operation="too_large", predicate="request_size")
        return error("Choose one state and try again.", 413, operation="too_large", predicate="request_size")

    @app.get("/api/notifications/session")
    @app.get("/api/state-requests/session")
    def browser_session():
        if not same_origin():
            return error("Open the website to request a state.", 403, operation="browser_session", predicate="request_origin")
        token = recognition.read(request.cookies.get(cookie_name))
        cookie = None
        if token is None:
            token, cookie = recognition.issue()
        body = dict(csrf_token=recognition.csrf(token))
        if request.path == "/api/notifications/session":
            body["confirmation_enabled"] = (subscription_store is not None
                                            and subscription_store.confirmation_store is not None)
            body["management_enabled"] = (subscription_store is not None
                                          and subscription_store.management_store is not None)
        response = jsonify(body)
        if cookie is not None:
            response.set_cookie(cookie_name, cookie, max_age=COOKIE_AGE,
                                secure=secure, httponly=True, samesite="Lax", path="/")
        return response

    @app.post("/api/state-requests")
    def submit():
        if not same_origin(mutation=True):
            return error("Open the website to request a state.", 403, operation="submit", predicate="request_origin")
        token = recognition.read(request.cookies.get(cookie_name))
        csrf = request.headers.get("X-CSRF-Token", "")
        if not valid_csrf():
            return error("Enable cookies, reload the page, and try again.", 403, operation="submit", predicate="request_csrf")
        if request.mimetype != "application/json":
            return error("Choose one state and try again.", 415, operation="submit", predicate="request_json_media_type")
        try:
            data = request.get_json()
        except BadRequest:
            return error("Choose one state and try again.", 400, operation="submit", predicate="request_json_decode")
        if (type(data) is not dict or set(data) != {"state"}
                or not valid_state(data["state"])):
            return error("Select one of the 50 U.S. states.", 400, operation="submit", predicate="request_state")
        try:
            accepted = store.submit(data["state"], recognition.browser_key(token))
        except Exception as exc:
            # A failed COMMIT response may mean the server committed. Preserve
            # recognition and let a deliberate repeat converge via uniqueness.
            log_notification_failure(app.logger, "state_persistence", exc, http_status=503)
            return error("We could not confirm your request. Please try again; a repeat will not add another count.", 503, operation="submit", predicate="state_persistence")
        return jsonify(
            status="accepted" if accepted else "duplicate", state=data["state"],
            message=("Your state request has been counted. Thank you." if accepted else
                     "This browser has already requested this state. Your request is counted once."),
        ), 201 if accepted else 200

    @app.get("/api/state-requests/totals")
    def totals():
        try:
            counts = store.totals()
        except Exception as exc:
            log_notification_failure(app.logger, "state_totals_query", exc, http_status=503)
            return error("State totals are temporarily unavailable.", 503, operation="totals", predicate="state_totals_query")
        return jsonify(totals=counts)

    from .contact import register_contact
    register_contact(app, recognition, cookie_name, same_origin, valid_csrf, error,
                     sender=contact_sender)
    if subscription_store is not None:
        from .notifications import UnsubscribeCapabilities, register_notifications
        register_notifications(app, subscription_store, UnsubscribeCapabilities(recognition.secret),
                               same_origin, valid_csrf, error, recognition=recognition,
                               browser_cookie_name=cookie_name, secure=secure)
        from .brevo_unsubscribe import register_brevo_unsubscribe, validate_webhook_config
        if brevo_webhook_config is not None:
            validate_webhook_config(brevo_webhook_config, environment)
        register_brevo_unsubscribe(app, subscription_store.management_store, brevo_webhook_config, error)
    if integration_config is not None:
        from .integrations import register_integrations
        register_integrations(app, integration_config, environment, recognition, trusted,
                              allow_insecure_localhost, store, subscription_store, reporting_store, release_store)
    return app


def create_app(*, expected_profile, recognition_secret, public_origin,
               allow_insecure_localhost=False, integration_config=None, confirmation_enabled=False,
               management_enabled=False, brevo_webhook_config=None, releases_enabled=False):
    """Explicit runtime factory. No schema creation, migration or secret fallback.

    Supply one persistent, protected recognition secret to every API worker.
    Serve /api through the public site's origin; no credentialed CORS is enabled.
    Optional IntegrationConfig is injected from protected backend configuration;
    its environment must match the verified runtime profile. None disables the
    service routes. No additional environment-variable allowlist is introduced.
    confirmation_enabled must be explicitly True to enable reservation/confirmation;
    it never constructs a provider adapter or starts outbox processing.
    """
    from .notification_dispatch import report_failure
    engine = None
    operation = "application_startup"
    try:
        if type(confirmation_enabled) is not bool:
            raise ValueError("Email confirmation activation must be an explicit boolean.")
        if type(management_enabled) is not bool:
            raise ValueError("Notification management activation must be an explicit boolean.")
        if type(releases_enabled) is not bool:
            raise ValueError("Release activation must be an explicit boolean.")
        if releases_enabled and (not management_enabled or integration_config is None or integration_config.release_credential is None):
            raise ValueError("Release intake requires separate protected approval authorization.")
        if brevo_webhook_config is not None:
            from .brevo_unsubscribe import validate_webhook_config
            validate_webhook_config(brevo_webhook_config, expected_profile)
            if not management_enabled:
                raise ValueError("Webhook processing requires notification management activation.")
        recognition = BrowserRecognition(recognition_secret)
        # Validate the origin before any configuration/credential access.
        _build_app(None, recognition, public_origin,
                   allow_insecure_localhost=allow_insecure_localhost)
        if integration_config is not None:
            from .integrations import validate_configuration
            validate_configuration(integration_config, expected_profile, recognition.secret)
        operation = "database_configuration"
        config = (load_testing_database_config() if expected_profile == "testing" else
                  load_database_config(expected_profile=expected_profile))
        operation = "engine"
        engine = create_engine(
            config.url, echo=False, hide_parameters=True, pool_pre_ping=True,
            connect_args={"connect_timeout": 5, "require_auth": "scram-sha-256",
                          "application_name": "oaf_website_state_requests",
                          "options": "-c statement_timeout=10000 -c lock_timeout=5000"},
        )
        event.listen(engine, "checkout", lambda dbapi, record, proxy:
                     _verify_checkout(config, dbapi, record, proxy))
        # Build again with the configured store. No engine connection occurs here.
        from .notifications import SubscriptionStore
        from .interest_reporting import InterestSummaryStore
        from .contact_mail import ConfiguredSMTP
        confirmation = None
        if confirmation_enabled:
            from .notification_delivery import NotificationDeliveryStore
            confirmation = NotificationDeliveryStore(engine, recognition.secret, config.profile,
                                                     management_enabled=management_enabled)
        management = None
        if management_enabled:
            from .notification_management import NotificationManagementStore
            management = NotificationManagementStore(engine, recognition.secret, config.profile)
        release = None
        if releases_enabled:
            from .notification_delivery import NotificationDeliveryStore
            release = NotificationDeliveryStore(engine, recognition.secret, config.profile,
                management_enabled=management_enabled, releases_enabled=True)
        operation = "application_startup"
        app = _build_app(RequestStore(engine), recognition, public_origin,
                         allow_insecure_localhost=allow_insecure_localhost,
                         subscription_store=SubscriptionStore(engine, confirmation_store=confirmation,
                                                              management_store=management),
                         integration_config=integration_config, environment=config.profile,
                         reporting_store=InterestSummaryStore(engine, config.profile)
                         if integration_config is not None else None,
                         contact_sender=ConfiguredSMTP(config.profile), brevo_webhook_config=brevo_webhook_config,
                         release_store=release)
        app.extensions["state_requests_engine"] = engine
        return app
    except Exception as exc:
        first = report_failure(operation, exc)
        if engine is not None:
            try:
                engine.dispose()
            except Exception as cleanup:
                report_failure("dispose", cleanup, first_failure=first)
        raise

from .notification_dispatch import diagnostic_transaction

from .notification_dispatch import diagnostic_error
