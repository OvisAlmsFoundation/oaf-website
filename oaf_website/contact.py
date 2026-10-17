"""Bounded General Contact requests; no database, subscriptions or shared API writes."""

import hashlib
import hmac
import json
from threading import Lock
from time import monotonic

from flask import jsonify, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from .contact_mail import DeliveryUnavailable
from .notifications import normalize_email

MAX_REQUEST_BYTES = 32768
MAX_MESSAGE_CHARS = 6000
MAX_WORDS = 200
RATE_WINDOW = 600
DUPLICATE_WINDOW = 900
MAX_GUARD_ENTRIES = 4096
SUCCESS = "Your message has been accepted for sending. Thank you."
UNAVAILABLE = "We could not send your message. Please try again later."
UNCERTAIN = "We could not confirm whether your message was accepted. Please wait 15 minutes before trying again."


def validate_contact(data):
    if type(data) is not dict or set(data) != {"email", "message"}:
        raise ValueError("Complete only the email address and message fields.")
    if type(data["email"]) is not str or len(data["email"]) > 254:
        raise ValueError("Enter a valid email address (maximum 254 characters).")
    email = normalize_email(data["email"])
    message = data["message"]
    if type(message) is not str or not message.strip():
        raise ValueError("Enter a message.")
    if len(message) > MAX_MESSAGE_CHARS:
        raise ValueError("Keep your message within 6,000 characters and 200 words.")
    if len(message.split()) > MAX_WORDS:
        raise ValueError("Keep your message within 200 words.")
    if any((ord(c) < 32 and c not in "\t\r\n") or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in message):
        raise ValueError("Remove unsupported control characters from your message.")
    return email, message.strip()


class ContactGuard:
    """Thread-safe, bounded, process-local limits and duplicate suppression.

    Store keyed digests and states only. Restart/worker boundaries are explicit
    limitations; no database or external rate-limit infrastructure is added.
    """
    def __init__(self, secret, *, clock=monotonic):
        self.secret, self.clock = secret, clock
        self.lock = Lock()
        self.rates, self.submissions = {}, {}

    def digest(self, purpose, values):
        value = json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        return hmac.new(self.secret, b"oaf-contact-v1:" + purpose + b":" + value, hashlib.sha256).digest()

    def _prune(self):
        now = self.clock()
        for entries in (self.rates, self.submissions):
            for key, (expiry, _) in list(entries.items()):
                if expiry <= now:
                    del entries[key]
        return now

    def allow(self, browser, remote_addr):
        keys = [(self.digest(b"browser", [browser]), 5),
                (self.digest(b"address", [remote_addr]), 5), (b"global", 60)]
        with self.lock:
            now = self._prune()
            if len(self.rates) + sum(key not in self.rates for key, _ in keys) > MAX_GUARD_ENTRIES:
                return False
            if any(self.rates.get(key, (0, 0))[1] >= limit for key, limit in keys):
                return False
            for key, _ in keys:
                expiry, count = self.rates.get(key, (now + RATE_WINDOW, 0))
                self.rates[key] = expiry, count + 1
            return True

    def begin(self, browser, email, message):
        key = self.digest(b"submission", [browser, email, message])
        with self.lock:
            now = self._prune()
            if key in self.submissions:
                return key, self.submissions[key][1]
            if len(self.submissions) >= MAX_GUARD_ENTRIES:
                return key, "full"
            self.submissions[key] = now + DUPLICATE_WINDOW, "pending"
            return key, "new"

    def finish(self, key, state):
        with self.lock:
            if state == "unavailable":
                self.submissions.pop(key, None)
            else:
                self.submissions[key] = self.clock() + DUPLICATE_WINDOW, state


def register_contact(app, recognition, cookie_name, same_origin, valid_csrf, error, *, sender=None):
    guard = ContactGuard(recognition.secret)
    app.extensions["contact_guard"] = guard
    # Reuse the existing cookie issuance and browser CSRF contract.
    app.add_url_rule("/api/contact/session", "contact_session", app.view_functions["browser_session"], methods=["GET"])

    @app.before_request
    def contact_size_limit():
        if request.path == "/api/contact":
            # Per-request override preserves the 1 KiB State/notification contracts.
            request.max_content_length = MAX_REQUEST_BYTES

    @app.post("/api/contact")
    def submit_contact():
        if not same_origin(mutation=True):
            return error("Open the website to send a message.", 403)
        if not valid_csrf():
            return error("Enable cookies, reload the page, and try again.", 403)
        browser = recognition.read(request.cookies.get(cookie_name))
        # Ignore user-supplied forwarding headers; use the server's peer address.
        if not guard.allow(browser, request.remote_addr):
            response, status = error("Too many contact attempts. Please wait 10 minutes and try again.", 429)
            response.headers["Retry-After"] = str(RATE_WINDOW)
            return response, status
        if request.mimetype != "application/json":
            return error("Submit the contact form as JSON.", 415)
        try:
            data = request.get_json()
        except RequestEntityTooLarge:
            return error("Keep your message within 6,000 characters and 200 words.", 413)
        except BadRequest:
            return error("Complete the email address and message fields.", 400)
        try:
            email, message = validate_contact(data)
        except ValueError as invalid:
            return error(str(invalid), 400)
        key, state = guard.begin(browser, email, message)
        if state == "accepted":
            return jsonify(status="accepted", message=SUCCESS)
        if state == "uncertain":
            return error(UNCERTAIN, 503)
        if state in {"pending", "full"}:
            return error("Please wait before sending this message again.", 409 if state == "pending" else 429)
        try:
            if sender is None:
                raise DeliveryUnavailable()
            sender(email, message)
        except DeliveryUnavailable:
            guard.finish(key, "unavailable")
            app.logger.warning("Contact mail unavailable.")
            return error(UNAVAILABLE, 503)
        except Exception:
            # Includes an unexpected sender failure: never retry an uncertain send.
            guard.finish(key, "uncertain")
            app.logger.warning("Contact mail acceptance uncertain.")
            return error(UNCERTAIN, 503)
        guard.finish(key, "accepted")
        return jsonify(status="accepted", message=SUCCESS)
