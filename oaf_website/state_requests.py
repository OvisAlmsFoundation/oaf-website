"""Anonymous recognition, authoritative validation and committed-record counting."""

import hashlib
import hmac
import re
import secrets
from urllib.parse import urlsplit
from uuid import UUID

from flask import Flask, jsonify, request
from itsdangerous import BadData, URLSafeSerializer
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import insert
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from .database_config import (
    DatabaseConfigurationError, load_database_config, load_testing_database_config,
)
from .state_request_schema import STATE_CODES, state_requests

COOKIE_AGE = 60 * 60 * 24 * 365


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
        with self.engine.begin() as connection:
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
    if (authenticated != config.url.username or host != config.url.host
            or port != config.url.port or major != 17):
        raise DatabaseConfigurationError("Connected database identity does not match the selected profile.")


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


def _build_app(store, recognition, public_origin, *, allow_insecure_localhost=False):
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

    def error(message, status):
        return jsonify(status="error", message=message), status

    def same_origin(*, mutation=False):
        # Fetch metadata is defense in depth; Origin/Referer and the custom
        # browser-bound CSRF header remain required on mutations.
        site = request.headers.get("Sec-Fetch-Site")
        if site is not None and site != "same-origin":
            return False
        origin = request.headers.get("Origin")
        if origin is not None:
            try:
                parsed = urlsplit(origin)
                return parsed.path == "" and not parsed.query and _origin(origin) == trusted
            except ValueError:
                return False
        referer = request.headers.get("Referer")
        if referer is not None:
            return _origin(referer) == trusted
        return not mutation

    @app.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        return error("Choose one state and try again.", 413)

    @app.get("/api/state-requests/session")
    def browser_session():
        if not same_origin():
            return error("Open the website to request a state.", 403)
        token = recognition.read(request.cookies.get(cookie_name))
        cookie = None
        if token is None:
            token, cookie = recognition.issue()
        response = jsonify(csrf_token=recognition.csrf(token))
        if cookie is not None:
            response.set_cookie(cookie_name, cookie, max_age=COOKIE_AGE,
                                secure=secure, httponly=True, samesite="Lax", path="/")
        return response

    @app.post("/api/state-requests")
    def submit():
        if not same_origin(mutation=True):
            return error("Open the website to request a state.", 403)
        token = recognition.read(request.cookies.get(cookie_name))
        csrf = request.headers.get("X-CSRF-Token", "")
        if (token is None or not re.fullmatch(r"[0-9a-f]{64}", csrf)
                or not hmac.compare_digest(recognition.csrf(token), csrf)):
            return error("Enable cookies, reload the page, and try again.", 403)
        if request.mimetype != "application/json":
            return error("Choose one state and try again.", 415)
        try:
            data = request.get_json()
        except BadRequest:
            return error("Choose one state and try again.", 400)
        if (type(data) is not dict or set(data) != {"state"}
                or type(data["state"]) is not str or data["state"] not in STATE_CODES):
            return error("Select one of the 50 U.S. states.", 400)
        try:
            accepted = store.submit(data["state"], recognition.browser_key(token))
        except Exception:
            # A failed COMMIT response may mean the server committed. Preserve
            # recognition and let a deliberate repeat converge via uniqueness.
            app.logger.warning("State request persistence unavailable.")
            return error("We could not confirm your request. Please try again; a repeat will not add another count.", 503)
        return jsonify(
            status="accepted" if accepted else "duplicate", state=data["state"],
            message=("Your state request has been counted. Thank you." if accepted else
                     "This browser has already requested this state. Your request is counted once."),
        ), 201 if accepted else 200

    @app.get("/api/state-requests/totals")
    def totals():
        try:
            counts = store.totals()
        except Exception:
            app.logger.warning("State request totals unavailable.")
            return error("State totals are temporarily unavailable.", 503)
        return jsonify(totals=counts)

    return app


def create_app(*, expected_profile, recognition_secret, public_origin,
               allow_insecure_localhost=False):
    """Explicit runtime factory. No schema creation, migration or secret fallback.

    Supply one persistent, protected recognition secret to every API worker.
    Serve /api through the public site's origin; no credentialed CORS is enabled.
    """
    recognition = BrowserRecognition(recognition_secret)
    # Validate the origin before any configuration/credential access.
    _build_app(None, recognition, public_origin,
               allow_insecure_localhost=allow_insecure_localhost)
    config = (load_testing_database_config() if expected_profile == "testing" else
              load_database_config(expected_profile=expected_profile))
    engine = create_engine(
        config.url, echo=False, hide_parameters=True, pool_pre_ping=True,
        connect_args={"connect_timeout": 5, "require_auth": "scram-sha-256",
                      "application_name": "oaf_website_state_requests",
                      "options": "-c statement_timeout=10000 -c lock_timeout=5000"},
    )
    event.listen(engine, "checkout", lambda dbapi, record, proxy:
                 _verify_checkout(config, dbapi, record, proxy))
    # Build again with the configured store. No engine connection occurs here.
    app = _build_app(RequestStore(engine), recognition, public_origin,
                     allow_insecure_localhost=allow_insecure_localhost)
    app.extensions["state_requests_engine"] = engine
    return app
