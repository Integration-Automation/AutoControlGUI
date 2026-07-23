"""Round-3 net audit: socket + REST request handlers must answer, not drop.

The TCP command server truncated any command that spanned more than one TCP
read and killed its handler thread (leaving the client with a bare EOF) on a
framework error. The REST dispatcher dropped the connection on a sqlite3.Error
from a DB-backed handler. Both must instead reassemble the request and always
send a well-formed response.
"""
import sqlite3

from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException, AutoControlScreenException,
)
from je_auto_control.utils.socket_server import (
    auto_control_socket_server as ss,
)
from je_auto_control.utils.rest_api import rest_server as rs


class _FakeRequest:
    """Minimal socket stand-in: canned recv chunks + captured sendall bytes."""

    def __init__(self, chunks) -> None:
        self._chunks = list(chunks)
        self.sent: list = []

    def settimeout(self, _timeout) -> None:
        """No-op: real sockets expose this; the handler sets a read timeout."""

    def recv(self, _bufsize) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""  # EOF

    def sendall(self, data) -> None:
        self.sent.append(data)


# --- finding 8: socket server ---------------------------------------------

def test_read_command_reassembles_large_message():
    """A >8 KiB command spread across TCP reads must not be truncated."""
    payload = "x" * 20000
    chunks = [payload[i:i + 8192].encode("utf-8")
              for i in range(0, len(payload), 8192)]
    chunks.append(b"\n")  # terminator arrives in a later read
    request = _FakeRequest(chunks)

    result = ss._read_command(request)

    assert result == payload  # full 20 KiB, not the first 8192 bytes


def test_handle_sends_error_and_terminator_on_framework_exc(monkeypatch):
    """An unknown-command framework error must reach the client, not kill the
    handler thread with no reply."""
    def boom(_payload):
        raise AutoControlActionException("unknown command")

    monkeypatch.setattr(ss, "execute_action", boom)

    handler = ss.TCPServerHandler.__new__(ss.TCPServerHandler)
    request = _FakeRequest([b'{"AC_bogus": {}}\n'])
    handler.request = request
    handler.server = object()

    handler.handle()  # must not raise

    joined = b"".join(request.sent)
    assert b"Return_Data_Over_JE" in joined  # terminator always sent
    assert b"unknown command" in joined  # the error text reached the client


# --- finding 9: REST dispatcher -------------------------------------------

class _Gate:
    def check(self, **_kwargs) -> str:
        return "ok"


class _Metrics:
    def __init__(self) -> None:
        self.requests: list = []

    def record_request(self, method, path, status) -> None:
        self.requests.append((method, path, status))

    def record_failed_auth(self) -> None:
        pass


class _Audit:
    def __init__(self) -> None:
        self.logs: list = []

    def log(self, *args, **kwargs) -> None:
        self.logs.append((args, kwargs))


def _make_rest_handler():
    handler = rs._RestRequestHandler.__new__(rs._RestRequestHandler)

    class _Server:
        pass

    server = _Server()
    server.auth_gate = _Gate()
    server.metrics = _Metrics()
    server.audit_log = _Audit()
    handler.server = server
    handler.client_address = ("127.0.0.1", 5555)
    handler.headers = {}
    handler.path = "/history"

    sent: dict = {}

    def fake_send_json(payload, status=200, default=None):
        sent["payload"] = payload
        sent["status"] = status

    handler._send_json = fake_send_json
    return handler, server, sent


def test_dispatch_contains_framework_family():
    """The reparent makes AutoControlException contain the whole family."""
    handler, server, sent = _make_rest_handler()

    def boom(_ctx):
        raise AutoControlScreenException("no display")

    handler._dispatch("GET", {"/history": boom}, body=None)

    assert sent["status"] == 500
    assert sent["payload"] == {"error": "handler crashed"}
    assert any(status == 500 for _, _, status in server.metrics.requests)
    assert server.audit_log.logs  # failure was audited


def test_dispatch_contains_sqlite_error():
    """A DB error from a handler must return 500, not drop the connection."""
    handler, server, sent = _make_rest_handler()

    def boom(_ctx):
        raise sqlite3.OperationalError("database is locked")

    handler._dispatch("GET", {"/history": boom}, body=None)

    assert sent["status"] == 500
    assert any(status == 500 for _, _, status in server.metrics.requests)
