"""Internal transactional adapter. Importing this module never loads keys or sends."""

from dataclasses import dataclass, field
from http.client import HTTPSConnection
import json
import os
import re
import ssl

from .database_config import _validate_environment, _windows_password
from .integrations import _strict_object, _invalid_constant

HOST = "api.brevo.com"
PATH = "/v3/smtp/email"
CONNECT_TIMEOUT = 5
RESPONSE_TIMEOUT = 10
MAX_RESPONSE = 8192
FROM_NAME = "Ovis Alms Foundation"
FROM_EMAIL = "communications@updates.ovisalmsfoundation.org"
REPLY_TO = "contact@ovisalmsfoundation.org"
MESSAGE_ID = re.compile(r"<[A-Za-z0-9_.+:/-]+@[A-Za-z0-9.-]+>", re.ASCII)
OUTCOMES = {"provider_accepted", "provider_rejected", "not_submitted",
            "retryable_rejection", "submission_unknown"}


class BrevoConfigurationError(ValueError):
    """Fixed safe configuration diagnostics; never attach provider exceptions."""


@dataclass(frozen=True)
class BrevoConfig:
    environment: str
    api_key: str = field(repr=False)

    def __post_init__(self):
        if (type(self.environment) is not str or self.environment not in {"development", "testing"}
                or type(self.api_key) is not str
                or re.fullmatch(r"[A-Za-z0-9_-]{16,256}", self.api_key, re.ASCII) is None):
            raise BrevoConfigurationError("Brevo configuration unavailable.")


def load_brevo_config(expected_profile, *, credential_account, environ=None, credential_loader=None):
    """Explicit invocation only; use existing exact-target pinned WinVault loader.

    The owner supplies the existing record's nonsecret account metadata. There is
    no discovery, fallback, keyring plugin selection, env key or production path.
    """
    try:
        environment = dict(os.environ if environ is None else environ)
        _validate_environment(environment, expected_profile)
        if (expected_profile not in {"development", "testing"}
                or type(credential_account) is not str
                or re.fullmatch(r"[A-Za-z0-9@._/-]{1,128}", credential_account, re.ASCII) is None
                or any(name.upper().startswith(("BREVO", "SENDINBLUE")) for name in environment)):
            raise ValueError
        loader = _windows_password if credential_loader is None else credential_loader
        key = loader(f"OAF Website/{expected_profile}/Brevo/ApiKey", credential_account,
                     environment, exact_target=True)
        return BrevoConfig(expected_profile, key)
    except Exception:
        pass
    raise BrevoConfigurationError("Brevo configuration unavailable.") from None


@dataclass(frozen=True)
class ProviderOutcome:
    outcome: str
    message_id: str | None = None

    def __post_init__(self):
        if (self.outcome not in OUTCOMES or self.message_id is not None and (
                self.outcome not in {"provider_accepted", "submission_unknown"} or type(self.message_id) is not str
                or len(self.message_id) > 200 or MESSAGE_ID.fullmatch(self.message_id) is None)):
            raise ValueError("Invalid sanitized provider outcome.")


@dataclass(frozen=True)
class ProviderResponse:
    status: int
    content_type: str
    body: bytes = field(repr=False)


def classify_response(response, api_key):
    """A valid 201 is acceptance only. Every ambiguous response is held, never retried."""
    try:
        if (type(response) is not ProviderResponse or type(response.status) is not int
                or not 100 <= response.status <= 599
                or type(response.body) is not bytes or len(response.body) > MAX_RESPONSE
                or type(response.content_type) is not str
                or response.content_type.lower() not in {
                    "application/json", "application/json;charset=utf-8", "application/json; charset=utf-8"}):
            raise ValueError
        data = json.loads(response.body.decode("utf-8"), object_pairs_hook=_strict_object,
                          parse_constant=_invalid_constant)
        if type(data) is not dict:
            raise ValueError
        if response.status == 201 or set(data) == {"messageId"}:
            if set(data) != {"messageId"} or type(data["messageId"]) is not str or api_key in data["messageId"]:
                raise ValueError
            return ProviderOutcome("provider_accepted" if response.status == 201 else "submission_unknown",
                                   data["messageId"])
        if (set(data) != {"code", "message"} or type(data["code"]) is not str
                or re.fullmatch(r"[a-z_]{1,64}", data["code"], re.ASCII) is None
                or type(data["message"]) is not str or not 1 <= len(data["message"]) <= 2048):
            raise ValueError
        if response.status == 429:
            return ProviderOutcome("retryable_rejection")
        if response.status in {400, 401, 402, 403, 404, 405, 406, 409, 410, 413, 415, 422}:
            return ProviderOutcome("provider_rejected")
    except Exception:
        pass
    return ProviderOutcome("submission_unknown")


class BrevoHTTPS:
    """One POST, no redirects/retries/proxy/netrc/cookies or ambient authorization.

    Connect/TLS must finish before request submission starts. Any failure after
    request() may mean acceptance. Only local close occurs after an acknowledgement.
    Socket timeouts bound connect and response inactivity; response bytes are capped.
    """
    def __call__(self, api_key, body):
        connection = None
        submitting = False
        try:
            # Construct explicitly: create_default_context honors SSLKEYLOGFILE.
            # Do not enable ambient TLS session-key logging or custom CA files.
            if any(name in os.environ for name in ("SSL_CERT_FILE", "SSL_CERT_DIR")):
                return ProviderOutcome("not_submitted")
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_default_certs()
            connection = HTTPSConnection(HOST, 443, timeout=CONNECT_TIMEOUT, context=context)
            connection.connect()
            connection.sock.settimeout(RESPONSE_TIMEOUT)
            submitting = True
            connection.request("POST", PATH, body=body, headers={
                "api-key": api_key, "Content-Type": "application/json", "Accept": "application/json",
                "Accept-Encoding": "identity"})
            response = connection.getresponse()
            # Reject compressed content rather than expanding an unbounded body.
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                return ProviderOutcome("submission_unknown")
            return classify_response(ProviderResponse(response.status,
                response.getheader("Content-Type", ""), response.read(MAX_RESPONSE + 1)), api_key)
        except Exception:
            return ProviderOutcome("submission_unknown" if submitting else "not_submitted")
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass


class BrevoAdapter:
    def __init__(self, config, *, transport=None):
        if type(config) is not BrevoConfig:
            raise BrevoConfigurationError("Brevo configuration unavailable.")
        self.config = config
        self.transport = BrevoHTTPS() if transport is None else transport

    def submit(self, email, message):
        from .notifications import normalize_email
        # Message is produced only by the fixed internal template constructors.
        payload = {"sender": {"name": FROM_NAME, "email": FROM_EMAIL},
                   "replyTo": {"email": REPLY_TO}, "to": [{"email": normalize_email(email)}],
                   "subject": message.subject, "textContent": message.text, "htmlContent": message.html}
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        try:
            outcome = self.transport(self.config.api_key, body)
            if type(outcome) is ProviderResponse:
                return classify_response(outcome, self.config.api_key)
            if type(outcome) is ProviderOutcome and (outcome.message_id is None
                    or self.config.api_key not in outcome.message_id):
                return outcome
        except Exception:
            pass
        return ProviderOutcome("submission_unknown")
