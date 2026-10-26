"""Existing guard framing/forwarding through memory sockets, never a listener."""
import migration_offline as isolation
isolation.require_early_registration()

import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from oaf_website import webhook_guard as guard

AUTH = b"Bearer synthetic-opaque-bearer"
BODY = b'{"event":"unsubscribed","email":"synthetic@example.invalid"}'


def wire(method=b"POST", path=guard.PATH, auth=AUTH, extra=b""):
    return (method + b" " + path + b" HTTP/1.1\r\nHost: fixture.invalid\r\nAuthorization: "
        + auth + b"\r\nContent-Type: application/json\r\nContent-Length: "
        + str(len(BODY)).encode() + b"\r\n" + extra + b"\r\n" + BODY)


def response(status, body=b"{}", extra=b""):
    return (b"HTTP/1.1 " + str(status).encode() + b" Private reason\r\nContent-Length: "
        + str(len(body)).encode() + b"\r\n" + extra + b"\r\n" + body)


class MemorySocket:
    def __init__(self, incoming):
        self.incoming, self.sent, self.timeouts = io.BytesIO(incoming), bytearray(), []
    def recv(self, size): return self.incoming.read(size)
    def sendall(self, data): self.sent.extend(data)
    def settimeout(self, value): self.timeouts.append(value)
    def __enter__(self): return self
    def __exit__(self, *args): pass


def exchange(monkeypatch, *, incoming=None, upstream=None, failure=None):
    client = MemorySocket(wire() if incoming is None else incoming)
    secured = MemorySocket(response(200) if upstream is None else upstream)
    connect = Mock(return_value=secured, side_effect=failure)
    monkeypatch.setattr(guard.socket, "create_connection", connect)
    wrap = Mock(return_value=secured)
    guard.Handler(client, ("127.0.0.1", 0), SimpleNamespace(context=SimpleNamespace(wrap_socket=wrap)))
    return client, secured, connect, wrap


@pytest.mark.parametrize("failure", [TimeoutError, ConnectionRefusedError, OSError])
def test_transient_failure_is_retryable_with_one_attempt_and_sanitized_evidence(monkeypatch, capsys, failure):
    client, secured, connect, _ = exchange(monkeypatch, failure=failure(AUTH.decode() + BODY.decode()))
    assert bytes(client.sent).startswith(b"HTTP/1.1 429 ")
    connect.assert_called_once_with(guard.UPSTREAM, timeout=guard.TIMEOUT)
    log = capsys.readouterr().out
    assert "upstream_result_unknown_no_retry http_status=429" in log
    assert AUTH.decode() not in log and BODY.decode() not in log


@pytest.mark.parametrize("status", [200, 204, 400, 401, 403, 415, 429, 500, 502, 503, 504, 599])
def test_forwarded_status_policy_and_exact_authenticated_endpoint(monkeypatch, capsys, status):
    client, secured, connect, wrap = exchange(monkeypatch,
        upstream=response(status, b"" if status == 204 else b"{}", b"Retry-After: 60\r\n"))
    public_status = 429 if status >= 500 else status
    assert bytes(client.sent).startswith(b"HTTP/1.1 " + str(public_status).encode() + b" ")
    assert bytes(secured.sent).startswith(b"POST " + guard.PATH + b" HTTP/1.1\r\nHost: localhost\r\n")
    assert b"Authorization: " + AUTH + b"\r\n" in secured.sent and bytes(secured.sent).endswith(BODY)
    assert connect.call_count == 1 and wrap.call_args.kwargs == dict(server_hostname="localhost")
    assert 10 < max(secured.timeouts) <= guard.UPSTREAM_TIMEOUT == 20
    log = capsys.readouterr().out
    if status >= 500: assert f"upstream_http_status={status}" in log
    if status == 429: assert b"Retry-After: 60" in client.sent
    assert AUTH.decode() not in log and BODY.decode() not in log


@pytest.mark.parametrize("upstream", [
    b"NOT HTTP\r\n\r\n", response(200)[:-1], response(200) + b"surplus",
    response(200, extra=b"Retry-After: private.invalid\r\n"),
    b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n",
])
def test_unreadable_upstream_result_is_retryable_without_local_resubmission(monkeypatch, upstream):
    client, _, connect, _ = exchange(monkeypatch, upstream=upstream)
    assert bytes(client.sent).startswith(b"HTTP/1.1 429 ") and connect.call_count == 1


@pytest.mark.parametrize("incoming,status", [
    (wire(method=b"GET"), 405), (wire(path=b"/"), 404),
    (wire(path=guard.PATH + b"?replay=1"), 404), (wire(path=guard.PATH + b"/"), 404),
    (wire(auth=b"Basic private"), 401),
    (wire(extra=b"Authorization: Bearer duplicate\r\n"), 400),
    (wire(extra=b"Transfer-Encoding: chunked\r\n"), 400),
])
def test_guard_rejections_do_not_forward(monkeypatch, incoming, status):
    client, _, connect, _ = exchange(monkeypatch, incoming=incoming)
    assert bytes(client.sent).startswith(b"HTTP/1.1 " + str(status).encode() + b" ")
    connect.assert_not_called()


def test_response_can_arrive_after_database_statement_limit_within_fixed_upstream_deadline(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(guard.time, "monotonic", lambda: clock[0])
    secured = MemorySocket(response(200))
    recv = secured.recv
    def delayed(size):
        if clock[0] == 100.0: clock[0] += 12
        return recv(size)
    secured.recv = delayed
    monkeypatch.setattr(guard.socket, "create_connection", Mock(return_value=secured))
    status, _, _ = guard.forward(SimpleNamespace(wrap_socket=lambda *a, **kw: secured), AUTH, b"application/json", BODY)
    assert status == 200 and min(secured.timeouts) == 8
    assert guard.TIMEOUT == 5 and guard.BIND == ("127.0.0.1", 18765)
    assert guard.UPSTREAM == ("127.0.0.1", 443) and guard.HOSTNAME == "localhost"
