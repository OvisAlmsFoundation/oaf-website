"""Bounded backend-only GraManna interfaces. Configuration is explicitly injected."""

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import re
import sys
from threading import Lock
from time import monotonic
from uuid import UUID

from flask import jsonify, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from .interest_reporting import ENVIRONMENTS, validate_summary
from .notifications import UnsubscribeCapabilities, subscription_response, validate_subscription
from .state_requests import _origin, valid_state

PREFIX = "/api/integrations/v1"
MAX_BODY_BYTES = 1024
HEX_TOKEN = re.compile(r"[0-9a-f]{64}", re.ASCII)
ROUTES = {PREFIX + "/state-requests": ("POST", "submission"),
          PREFIX + "/notifications": ("POST", "submission"),
          PREFIX + "/interest-summary": ("GET", "reporting")}


class IntegrationConfigurationError(ValueError):
    """Fixed-message startup failures contain no injected values."""


@dataclass(frozen=True)
class IntegrationConfig:
    """Inject from protected backend configuration for exactly one environment.

    Credentials are distinct externally provisioned 32-byte random values,
    encoded as lowercase hex. This class never reads or provisions secrets.
    Keep client_id stable across credential rotation. The existing persistent
    recognition_secret supplies the domain-separated visitor-key HMAC.
    """
    environment: str
    client_id: str
    submission_credential: str = field(repr=False)
    reporting_credential: str = field(repr=False)

    def __post_init__(self):
        if (type(self.environment) is not str or self.environment not in ENVIRONMENTS
                or type(self.client_id) is not str
                or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", self.client_id, re.ASCII) is None
                or any(type(value) is not str or HEX_TOKEN.fullmatch(value) is None
                       for value in (self.submission_credential, self.reporting_credential))):
            raise diagnostic_error(IntegrationConfigurationError("Invalid protected integration configuration."), "configuration", "integration_config_fields", stage="startup")
        if hmac.compare_digest(self.submission_credential, self.reporting_credential):
            raise diagnostic_error(IntegrationConfigurationError("Integration permissions require distinct credentials."), "configuration", "integration_credentials_distinct", stage="startup")


def validate_configuration(config, environment, recognition_secret):
    if type(config) is not IntegrationConfig or config.environment != environment:
        raise diagnostic_error(IntegrationConfigurationError("Integration configuration must match the runtime environment."), "configuration", "integration_environment_match", stage="startup")
    if any(hmac.compare_digest(bytes.fromhex(value), recognition_secret)
           for value in (config.submission_credential, config.reporting_credential)):
        raise diagnostic_error(IntegrationConfigurationError("Service credentials must be separate from the persistent key."), "configuration", "integration_key_separation", stage="startup")


def visitor_key(config, secret, token):
    if type(token) is not str or HEX_TOKEN.fullmatch(token) is None:
        raise ValueError("Invalid visitor token.")
    # No IP address, caller-selected identity or cross-domain identity mapping.
    domain = ("oaf-integration-state-browser-v1\0" + config.environment + "\0"
              + config.client_id + "\0").encode("ascii")
    return UUID(bytes=hmac.new(secret, domain + token.encode("ascii"), hashlib.sha256).digest()[:16])


class ServiceLimits:
    """Bounded per-process credential budgets; no visitor/IP tracking or services."""
    def __init__(self, clock=monotonic):
        self.clock, self.lock, self.windows = clock, Lock(), {}

    def allow(self, permission):
        with self.lock:
            now = self.clock()
            start, used = self.windows.get(permission, (now, 0))
            if now - start >= 60:
                start, used = now, 0
            limit = 120 if permission == "submission" else 30
            if used >= limit:
                return False
            self.windows[permission] = (start, used + 1)
            return True


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Repeated JSON field.")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("Invalid JSON constant.")


def register_integrations(app, config, environment, recognition, trusted, allow_local,
                          request_store, subscription_store, reporting_store):
    validate_configuration(config, environment, recognition.secret)
    capabilities = UnsubscribeCapabilities(recognition.secret)
    limits = ServiceLimits()

    def failure(code, message, status, *, predicate):
        retain_failure("integration_request", predicate, sys.exception())
        response = jsonify(status="error", code=code, message=message)
        if status == 401:
            response.headers["WWW-Authenticate"] = 'Bearer realm="oaf-integrations"'
        if status == 429:
            response.headers["Retry-After"] = "60"
        return response, status

    @app.before_request
    def protect_services():
        if not request.path.startswith(PREFIX + "/"):
            return None
        route = ROUTES.get(request.path)
        if route is None:
            return failure("not_found", "Service endpoint unavailable.", 404, predicate="service_route")
        method, permission = route
        if request.method != method:
            return failure("method_not_allowed", "Unsupported service method.", 405, predicate="service_method")
        # Never trust caller-supplied forwarded headers. The deployment must
        # establish HTTPS in the WSGI scheme at its trusted TLS boundary.
        if (_origin(request.host_url) != trusted
                or (not request.is_secure and not (
                    allow_local and environment in {"development", "testing"}
                    and trusted[0] == "http" and trusted[1] in {"localhost", "127.0.0.1", "::1"}
                    and request.remote_addr in {"127.0.0.1", "::1"}))):
            return failure("transport_required", "Use the configured secure service origin.", 403, predicate="service_transport")
        if (any(name in request.headers for name in ("Origin", "Referer", "Cookie"))
                or any(name.lower().startswith("sec-fetch-") for name in request.headers.keys())):
            return failure("backend_only", "Use authenticated backend service access.", 403, predicate="service_backend_only")
        authorization = request.headers.get("Authorization", "")
        match = re.fullmatch(r"Bearer ([0-9a-f]{64})", authorization, re.ASCII)
        supplied = match.group(1) if match else "0" * 64
        expected = (config.submission_credential if permission == "submission"
                    else config.reporting_credential)
        authenticated = hmac.compare_digest(supplied, expected)
        if match is None or not authenticated:
            return failure("unauthorized", "Valid service authorization is required.", 401, predicate="service_bearer")
        if request.query_string:
            return failure("invalid_request", "Service requests do not accept query parameters.", 400, predicate="service_no_query")
        if request.headers.get("Content-Encoding"):
            return failure("invalid_request", "Encoded request bodies are unsupported.", 415, predicate="service_no_encoding")
        # Read at most one extra byte so an unknown-length/chunked body cannot
        # be truncated to a valid JSON prefix and accepted as an in-limit body.
        request.max_content_length = MAX_BODY_BYTES + 1
        if request.content_length is not None and request.content_length > MAX_BODY_BYTES:
            return failure("request_too_large", "Service request exceeds the size limit.", 413, predicate="request_size")
        if not limits.allow(permission):
            return failure("rate_limited", "Service request limit reached. Retry later.", 429, predicate="service_rate_limit")

    def read_body():
        body = request.get_data()
        if len(body) > MAX_BODY_BYTES:
            raise RequestEntityTooLarge
        return body

    def payload():
        if request.mimetype != "application/json":
            return None, failure("invalid_request", "Submit a JSON service request.", 415, predicate="request_json_media_type")
        try:
            # Bounded UTF-8 JSON; reject duplicate keys and nonstandard constants.
            data = json.loads(read_body().decode("utf-8"),
                              object_pairs_hook=_strict_object, parse_constant=_invalid_constant)
            if type(data) is not dict:
                raise ValueError
            return data, None
        except RequestEntityTooLarge:
            return None, failure("request_too_large", "Service request exceeds the size limit.", 413, predicate="request_size")
        except (ValueError, BadRequest, RecursionError):
            return None, failure("invalid_request", "Submit valid service fields.", 400, predicate="service_json_decode")

    @app.post(PREFIX + "/state-requests")
    def integration_state_request():
        data, invalid = payload()
        if invalid is not None:
            return invalid
        if set(data) != {"state", "visitor_token"} or not valid_state(data["state"]):
            return failure("invalid_request", "Select one of the 50 U.S. states and supply a visitor token.", 400, predicate="service_state_fields")
        try:
            key = visitor_key(config, recognition.secret, data["visitor_token"])
        except ValueError:
            return failure("invalid_request", "Supply a valid stable visitor token.", 400, predicate="service_visitor_token")
        try:
            accepted = request_store.submit(data["state"], key)
            if type(accepted) is not bool:
                raise ValueError
        except Exception as exc:
            log_notification_failure(app.logger, "state_persistence", exc, http_status=503)
            return failure("submission_unconfirmed", "Request outcome unconfirmed. Retry with the same state and visitor token.", 503, predicate="state_persistence")
        return jsonify(status="accepted" if accepted else "duplicate", state=data["state"],
                       message="Your state request has been counted. Thank you." if accepted else
                       "This browser has already requested this state. Your request is counted once."), 201 if accepted else 200

    @app.post(PREFIX + "/notifications")
    def integration_notification():
        data, invalid = payload()
        if invalid is not None:
            return invalid
        if set(data) != {"email", "android_launch", "ios_launch", "consent", "token"}:
            return failure("invalid_request", "Supply only mobile preferences, email, consent and receipt token.", 400, predicate="service_signup_fields")
        try:
            values = validate_subscription(dict(data, web_launch=False, state=None))
        except ValueError:
            return failure("invalid_request", "Supply a valid email, mobile preference, consent and receipt token.", 400, predicate="service_signup_validation")
        try:
            subscription_store.subscribe(values)
            response = subscription_response(values, capabilities)
            body = response.get_json()
            if (set(body) != {"status", "message", "unsubscribe_token"}
                    or body["status"] != "received" or type(body["message"]) is not str
                    or capabilities.read(body["unsubscribe_token"]) != values["unsubscribe_digest"]):
                raise ValueError
            return response
        except Exception as exc:
            log_notification_failure(app.logger, "signup_persistence", exc, http_status=503)
            return failure("submission_unconfirmed", "Subscription outcome unconfirmed. Retry with the same receipt token and fields.", 503, predicate="signup_persistence")

    @app.get(PREFIX + "/interest-summary")
    def integration_summary():
        try:
            if read_body():
                return failure("invalid_request", "Reporting does not accept a request body.", 400, predicate="service_summary_no_body")
            result = validate_summary(reporting_store.summary(), environment)
            return jsonify(result)
        except RequestEntityTooLarge:
            return failure("request_too_large", "Service request exceeds the size limit.", 413, predicate="request_size")
        except BadRequest:
            return failure("invalid_request", "Submit a valid service request.", 400, predicate="service_summary_request")
        except Exception as exc:
            log_notification_failure(app.logger, "interest_summary", exc, http_status=503)
            return failure("service_unavailable", "Interest reporting is temporarily unavailable.", 503, predicate="interest_summary")

from .notification_dispatch import log_notification_failure

from .notification_dispatch import retain_failure

from .notification_dispatch import diagnostic_error
