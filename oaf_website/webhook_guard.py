"""OAF webhook guard v1. Source preparation; explicit --serve required to listen.

Python 3.11 standard library only. Shared bounded diagnostics; no stored bearer.
One request per connection, bounded framing, one upstream attempt, no replay.
"""
import argparse
from .notification_dispatch import safe_failure, report_failure
import hashlib
import http
import os
from pathlib import Path
import re
import socket
import socketserver
import ssl
import sys
import time

VERSION = "cloudflare-webhook-guard-step5-repair-20261024"
BIND = ("127.0.0.1", 18765)
UPSTREAM = ("127.0.0.1", 443)
HOSTNAME = "localhost"
PATH = b"/api/notifications/brevo/unsubscribed"
LIMIT = 16 * 1024
HEADER_LIMIT = 16 * 1024
TIMEOUT = 5
# Bound the whole upstream exchange beyond the application's 5s lock/10s
# statement limits. Ingress remains bounded separately; no local retry occurs.
UPSTREAM_TIMEOUT = 20
TOKEN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
BEARER = re.compile(rb"Bearer [A-Za-z0-9._~+/-]+=*")


class Reject(Exception):
    def __init__(self, status=400, predicate="guard_request_framing"):
        self.status = status
        self.notification_failure = safe_failure("request", "webhook_guard", self, predicate=predicate)


def emit(code):
    # Fixed codes, parsed status integers and correlation digests only; no raw HTTP/exception text.
    print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), VERSION, code, flush=True)


def exact_read(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise Reject(predicate="guard_complete_read")
    return data


class Reader:
    """No buffered read-ahead; deadline bounds the whole message, not each byte."""
    def __init__(self, sock, *, deadline=None):
        self.sock = sock
        self.deadline = time.monotonic() + TIMEOUT if deadline is None else deadline
        self.cf_ray_sha256 = "unavailable"

    def read(self, size):
        chunks = bytearray()
        while len(chunks) < size:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            self.sock.settimeout(remaining)
            part = self.sock.recv(size - len(chunks))
            if not part:
                break
            chunks.extend(part)
        return bytes(chunks)


def head(reader):
    data = bytearray()
    while not data.endswith(b"\r\n\r\n"):
        data.extend(exact_read(reader, 1))
        if len(data) > HEADER_LIMIT:
            raise Reject(431, predicate="guard_header_limit")
    lines = bytes(data[:-4]).split(b"\r\n")
    fields = {}
    for line in lines[1:]:
        name, sep, value = line.partition(b":")
        if not sep or not TOKEN.fullmatch(name) or any(c < 32 or c > 126 for c in value):
            raise Reject(predicate="guard_header_syntax")
        name = name.lower()
        if name in fields:  # Also reject duplicate auth, Host, and framing fields.
            raise Reject(predicate="guard_header_unique")
        if name == b"authorization" and value != b" " + value.strip(b" "):
            raise Reject(predicate="guard_authorization_spacing")  # Accepted bearer value is forwarded byte for byte.
        fields[name] = value.strip(b" ")
    return lines[0], fields


def length(fields):
    if any(name in fields for name in (b"transfer-encoding", b"content-encoding", b"expect", b"trailer", b"upgrade")):
        raise Reject(predicate="guard_no_encoding")
    value = fields.get(b"content-length", b"")
    if not re.fullmatch(rb"0|[1-9][0-9]{0,7}", value):
        raise Reject(predicate="guard_content_length")
    size = int(value)
    if size > LIMIT:
        raise Reject(413, predicate="guard_body_limit")
    return size


def request(reader):
    line, fields = head(reader)
    ray = fields.get(b"cf-ray", b"")
    if re.fullmatch(rb"[0-9a-f]{16,32}-[A-Z]{3}", ray):
        reader.cf_ray_sha256 = hashlib.sha256(ray).hexdigest()
    parts = line.split(b" ")
    if len(parts) != 3 or parts[2] not in (b"HTTP/1.0", b"HTTP/1.1"):
        raise Reject(predicate="guard_request_line")
    if parts[0] != b"POST":
        raise Reject(405, predicate="guard_method")
    if parts[1] != PATH:  # No decoding, normalization, query, fragment or absolute URI.
        raise Reject(404, predicate="guard_path")
    if not fields.get(b"host"):
        raise Reject(predicate="guard_host")
    size = length(fields)
    auth = fields.get(b"authorization", b"")
    if not BEARER.fullmatch(auth):
        raise Reject(401, predicate="guard_bearer_format")
    content_type = fields.get(b"content-type", b"")
    if not re.fullmatch(rb"application/json(?:; ?charset=utf-8)?", content_type, re.I):
        raise Reject(415, predicate="guard_media_type")
    return auth, content_type, exact_read(reader, size)


def tls_context(ca_file):
    if "SSLKEYLOGFILE" in os.environ:
        raise ValueError("tls_key_logging_forbidden")
    context = ssl.create_default_context(cafile=str(ca_file))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise ValueError("verified_tls_required")
    return context


def forward(context, auth, content_type, body):
    # Fixed IPv4 destination, with localhost SNI and certificate hostname check.
    # No proxy/env URL interpretation, redirect following, queue or retry loop.
    deadline = time.monotonic() + UPSTREAM_TIMEOUT
    with socket.create_connection(UPSTREAM, timeout=TIMEOUT) as raw:
        with context.wrap_socket(raw, server_hostname=HOSTNAME) as secured:
            secured.settimeout(max(0.001, deadline - time.monotonic()))
            secured.sendall(b"POST " + PATH + b" HTTP/1.1\r\nHost: localhost\r\n"
                           b"Connection: close\r\nAuthorization: " + auth
                           + b"\r\nContent-Type: " + content_type
                           + b"\r\nContent-Length: " + str(len(body)).encode("ascii")
                           + b"\r\n\r\n" + body)
            reader = Reader(secured, deadline=deadline)
            line, fields = head(reader)
            if not re.fullmatch(rb"HTTP/1\.[01] [2-5][0-9]{2} [\x20-\x7e]*", line):
                raise Reject(predicate="guard_upstream_status_line")
            status = int(line.split(b" ")[1])
            size = length(fields)
            if status in (204, 304) and size:
                raise Reject(predicate="guard_upstream_no_body")
            payload = exact_read(reader, size)
            if reader.read(1):  # Require complete close-delimited message; reject surplus.
                raise Reject(predicate="guard_upstream_no_surplus")
            retry = fields.get(b"retry-after")
            if retry is not None and not re.fullmatch(rb"[0-9]{1,8}", retry):
                raise Reject(predicate="guard_upstream_retry_header")
            return status, payload, retry


def respond(sock, status, body=b"", retry=None):
    # No upstream reason phrase or unapproved headers reflected to the public side.
    try:
        phrase = http.HTTPStatus(status).phrase.encode("ascii")
    except ValueError:
        phrase = b"Upstream status"
    sock.settimeout(TIMEOUT)
    sock.sendall(b"HTTP/1.1 " + str(status).encode("ascii") + b" " + phrase
                 + b"\r\nConnection: close\r\nCache-Control: no-store\r\n"
                 b"Content-Type: application/json\r\nContent-Length: "
                 + str(len(body)).encode("ascii")
                 + (b"\r\nRetry-After: " + retry if retry is not None else b"")
                 + b"\r\n\r\n" + body)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        emit("STARTED request_validation")
        reader = Reader(self.request)
        try:
            auth, content_type, body = request(reader)
        except (Reject, OSError) as exc:
            report_failure("webhook_guard", exc, stage="request", predicate="guard_request_framing")
            status = exc.status if isinstance(exc, Reject) else 400
            emit(f"BLOCKED request_validation http_status={status} "
                 f"failure_category=guard_rejected cf_ray_sha256={reader.cf_ray_sha256}")
            try:
                respond(self.request, status)
            except OSError:
                pass
            return
        emit("STARTED upstream_post_once")
        try:
            status, payload, retry = forward(self.server.context, auth, content_type, body)
        except Exception as exc:
            report_failure("webhook_guard", exc, stage="request", predicate="guard_upstream_unknown", side_effects="database_transaction_unacknowledged")
            # Upstream may have committed: do not retry locally. Brevo retries
            # 429 but discards 5xx; the application deduplicates provider retries.
            emit("ERROR upstream_result_unknown_no_retry http_status=429 "
                 f"failure_category=upstream_result_unknown_no_retry cf_ray_sha256={reader.cf_ray_sha256}")
            respond(self.request, 429)
            return
        if status >= 500:
            emit(f"ERROR upstream_transient_failure http_status=429 upstream_http_status={status} "
                 f"failure_category=upstream_failure cf_ray_sha256={reader.cf_ray_sha256}")
            respond(self.request, 429)
            return
        category = ("none" if status < 300 else "upstream_redirect" if status < 400
                    else "upstream_rejected" if status < 500 else "upstream_failure")
        emit(f"PASS upstream_response_validated http_status={status} "
             f"failure_category={category} cf_ray_sha256={reader.cf_ray_sha256}")
        respond(self.request, status, payload, retry)


class Guard(socketserver.TCPServer):
    address_family = socket.AF_INET
    allow_reuse_address = False

    def __init__(self, context):
        self.context = context
        super().__init__(BIND, Handler)

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address):
        emit("ERROR connection_closed_no_retry")  # Suppress traceback/private arguments.


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("Invalid webhook guard arguments.")


def main():
    parser = _Parser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--ca-file", type=Path, help="Explicit approved public PEM trust anchor; no private key")
    try:
        args = parser.parse_args()
    except ValueError as exc:
        report_failure("arguments", exc, predicate="guard_arguments")
        emit("BLOCKED guard_arguments")
        return 2
    if not args.serve:
        emit("SOURCE_ONLY no_listener_started")
        return 0
    if args.ca_file is None or sys.version_info[:2] != (3, 11):
        emit("BLOCKED explicit_ca_and_python311_required")
        return 1
    try:
        emit("STARTED verified_tls_and_exclusive_loopback_bind")
        context = tls_context(args.ca_file)
        with Guard(context) as server:
            emit("PASS listening_127_0_0_1_18765")
            server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        emit("ERROR interrupted_upstream_outcome_unknown_no_retry_listener_closed")
        return 130
    except Exception as exc:
        report_failure("webhook_guard", exc, predicate="guard_startup_runtime")
        emit("ERROR startup_or_runtime_no_retry")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
