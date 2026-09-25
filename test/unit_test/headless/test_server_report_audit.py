"""Servers and report helpers at the edges the audit found (loopback only).

Replies that cannot be encoded or serialised, bodies and replies nested too
deeply, a limit SQLite cannot bind, conflicting Content-Length headers,
401 challenges, 405 for a known path's other method, control characters in
access logs, an empty host filter, config-sync ties that never converged, a
duplicated ``+Inf`` bucket and an FPS-only profiler that forgot it ran.
"""
import email.message
import http.client
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from je_auto_control.utils.http_headers import (
    INVALID_CONTENT_LENGTH, log_safe, parse_content_length, wire_json_text,
)
from je_auto_control.utils.rest_api import rest_server as rs
from je_auto_control.utils.rest_api.rest_server import RestApiServer

_DEEP = "[" * 50_000 + "]" * 50_000


@pytest.fixture()
def too_deep(monkeypatch):
    """``json.loads`` raising ``RecursionError`` for ``_DEEP``, as it does on most builds.

    How deep the C parser goes first depends on the build and the stack --
    3.14 on Linux and macOS parsed all 50,000 levels -- so the depth is
    simulated: the handling of the error is what these tests check.
    """
    real = json.loads

    def loads(text, *args, **kwargs):
        head = text[:64]
        if head in ("[" * 64, b"[" * 64):
            raise RecursionError("maximum recursion depth exceeded while decoding a JSON array")
        return real(text, *args, **kwargs)

    monkeypatch.setattr(json, "loads", loads)
_LONE_SURROGATE = chr(0xDCFF)


@pytest.fixture()
def rest():
    server = RestApiServer(host="127.0.0.1", port=0, enable_audit=False)
    server.start()
    yield server
    server.stop(timeout=1.0)


def _call(server, method, path, *, body=None, headers=None, token=True):
    host, port = server.address
    conn = http.client.HTTPConnection(host, port, timeout=5)
    try:
        conn.putrequest(method, path)
        for name, value in (headers or {}).items():
            conn.putheader(name, value)
        if token:
            conn.putheader("Authorization", f"Bearer {server.token}")
        if body is not None and not any(n.lower() == "content-length" for n in (headers or {})):
            conn.putheader("Content-Length", str(len(body)))
        conn.endheaders(body)
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


# --- REST replies ------------------------------------------------------------------------------

def test_a_reply_holding_a_lone_surrogate_is_sent(rest, monkeypatch):
    monkeypatch.setitem(rs._GET_ROUTES, "/jobs", lambda ctx: (200, {"name": _LONE_SURROGATE}))  # noqa: SLF001
    status, _, raw = _call(rest, "GET", "/jobs")
    assert status == 200 and json.loads(raw) == {"name": _LONE_SURROGATE}


def test_a_reply_that_cannot_be_serialised_is_a_500(rest, monkeypatch):
    circular = {}
    circular["self"] = circular
    monkeypatch.setitem(rs._GET_ROUTES, "/jobs", lambda ctx: (200, circular))  # noqa: SLF001
    status, _, raw = _call(rest, "GET", "/jobs")
    assert status == 500 and "serialisable" in json.loads(raw)["error"]


def test_a_history_limit_too_large_for_sqlite_is_answered(rest):
    status, _, raw = _call(rest, "GET", "/history?limit=" + "9" * 40)
    assert status == 200 and isinstance(json.loads(raw)["runs"], list)


def test_a_body_nested_too_deeply_is_a_400(rest, too_deep):
    status, _, raw = _call(rest, "POST", "/execute", body=_DEEP.encode(),
                           headers={"Content-Type": "application/json"})
    assert status == 400 and json.loads(raw) == {"error": "invalid JSON"}


def test_conflicting_content_lengths_are_a_400(rest):
    host, port = rest.address
    conn = http.client.HTTPConnection(host, port, timeout=5)
    try:
        conn.putrequest("POST", "/execute")
        conn.putheader("Authorization", f"Bearer {rest.token}")
        conn.putheader("Content-Length", "2")
        conn.putheader("Content-Length", "40")
        conn.endheaders(b"[]")
        response = conn.getresponse()
        assert response.status == 400
        assert json.loads(response.read()) == {"error": "invalid Content-Length"}
    finally:
        conn.close()


# --- REST status codes -------------------------------------------------------------------------

def test_a_known_path_with_the_other_method_is_a_405_with_allow(rest):
    status, headers, _ = _call(rest, "GET", "/execute")
    assert status == 405 and headers["Allow"] == "POST"
    status, headers, _ = _call(rest, "POST", "/health", body=b"{}")
    assert status == 405 and headers["Allow"] == "GET"
    status, _, _ = _call(rest, "GET", "/nope")
    assert status == 404


def test_a_401_carries_a_bearer_challenge(rest):
    _, headers, _ = _call(rest, "GET", "/jobs", token=False)
    assert headers["WWW-Authenticate"] == 'Bearer realm="autocontrol"'
    status, headers, _ = _call(rest, "GET", "/jobs", token=False,
                               headers={"Authorization": "Bearer wrong"})
    assert status == 401 and 'error="invalid_token"' in headers["WWW-Authenticate"]


def test_the_access_log_escapes_control_characters(rest, monkeypatch):
    lines = []

    class _Recorder:
        @staticmethod
        def info(message, *args):
            lines.append(message % args)

        error = warning = debug = info

    monkeypatch.setattr(rs, "autocontrol_logger", _Recorder())
    host, port = rest.address
    with socket.create_connection((host, port), timeout=5) as conn:
        # http.client refuses to send these; a hostile client does not.
        # A valid request line: a \r would split it, and the stdlib's 400
        # for a malformed one logs it with %r, escaped either way.
        conn.sendall(b"GET /health\x1b[2J\x08 HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        while conn.recv(65536):
            pass
    access = [line for line in lines if "rest-api 127.0.0.1" in line]
    assert access and not any(ch in line for line in access for ch in "\x1b\x08")
    assert any("\\x1b[2J\\x08" in line for line in access)


# --- shared helpers ------------------------------------------------------------------------------

def test_parse_content_length_reads_every_copy():
    message = email.message.Message()
    message["Content-Length"] = "5"
    message["Content-Length"] = "5"
    assert parse_content_length(message) == 5
    message["Content-Length"] = "6"
    assert parse_content_length(message) == INVALID_CONTENT_LENGTH


def test_log_safe_and_wire_json_text():
    assert log_safe("a\nb\\c\x85") == "a\\x0ab\\\\c\\x85"
    assert wire_json_text({"a": "中"}) == '{"a": "中"}'
    text = wire_json_text({"a": _LONE_SURROGATE})
    assert text.encode("utf-8") and json.loads(text) == {"a": _LONE_SURROGATE}


# --- socket, MCP, webhook ------------------------------------------------------------------------

def test_the_socket_server_answers_a_command_nested_too_deeply(too_deep):
    from je_auto_control.utils.socket_server.auto_control_socket_server import _is_complete
    assert _is_complete((_DEEP + "\n").encode()) is True


def test_mcp_answers_a_line_nested_too_deeply_and_a_lone_surrogate(too_deep):
    from je_auto_control.utils.mcp_server._protocol import _result_response
    from je_auto_control.utils.mcp_server.http_transport import _is_initialize
    from je_auto_control.utils.mcp_server.prompts import StaticPromptProvider
    from je_auto_control.utils.mcp_server.resources import ChainProvider
    from je_auto_control.utils.mcp_server.server import MCPServer
    server = MCPServer(tools=[], resource_provider=ChainProvider([]),
                       prompt_provider=StaticPromptProvider([]))
    assert json.loads(server.handle_line(_DEEP))["error"]["code"] == -32700
    assert _is_initialize(_DEEP) is False
    assert _result_response(1, {"name": _LONE_SURROGATE}).encode("utf-8")


def test_mcp_http_answers_missing_and_wrong_tokens_401_with_a_challenge():
    from je_auto_control.utils.mcp_server.http_transport import DEFAULT_PATH, HttpMCPServer
    from je_auto_control.utils.mcp_server.prompts import StaticPromptProvider
    from je_auto_control.utils.mcp_server.resources import ChainProvider
    from je_auto_control.utils.mcp_server.server import MCPServer
    server = HttpMCPServer(mcp=MCPServer(tools=[], resource_provider=ChainProvider([]),
                                         prompt_provider=StaticPromptProvider([])),
                           host="127.0.0.1", port=0, auth_token="secret")
    server.start()
    try:
        host, port = server.address
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
        for auth, error in ((None, False), ("Bearer wrong", True)):
            conn = http.client.HTTPConnection(host, port, timeout=5)
            headers = {"Content-Type": "application/json"}
            if auth:
                headers["Authorization"] = auth
            conn.request("POST", DEFAULT_PATH, body=body, headers=headers)
            response = conn.getresponse()
            challenge = response.getheader("WWW-Authenticate") or ""
            response.read()
            conn.close()
            assert response.status == 401 and challenge.startswith("Bearer realm=")
            assert ('error="invalid_token"' in challenge) is error
    finally:
        server.stop(timeout=1.0)


def test_a_webhook_body_nested_too_deeply_is_not_json(too_deep):
    from je_auto_control.utils.triggers.webhook_server import _maybe_parse_json
    assert _maybe_parse_json("application/json", _DEEP) is None


# --- clients reading a reply nested too deeply ---------------------------------------------------

class _DeepReply(BaseHTTPRequestHandler):
    def _reply(self):
        body = _DEEP.encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_PUT = _reply

    def log_message(self, format, *args):  # noqa: A002  # pylint: disable=redefined-builtin  # reason: stdlib override
        return


@pytest.fixture()
def deep_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _DeepReply)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % server.server_address[1]  # NOSONAR loopback test server
    server.shutdown()
    server.server_close()


def test_clients_turn_a_reply_nested_too_deeply_into_their_own_error(deep_server, tmp_path, too_deep):
    from je_auto_control.utils.admin.admin_client import AdminConsoleClient
    from je_auto_control.utils.config_sync.client import ConfigSyncClient, ConfigSyncError
    from je_auto_control.utils.remote_desktop.signaling_client import SignalingError, _request
    admin = AdminConsoleClient(persist_path=tmp_path / "hosts.json", timeout_s=5)
    admin.add_host("h", deep_server, "tok")
    [status] = admin.poll_all()
    assert status.healthy is False and "nested too deeply" in status.error
    with pytest.raises(ConfigSyncError):
        ConfigSyncClient(deep_server, user_id="u").fetch()
    with pytest.raises(SignalingError):
        _request("GET", deep_server + "/x")


def test_an_empty_host_filter_runs_on_no_host(tmp_path, monkeypatch):
    from je_auto_control.utils.admin.admin_client import AdminConsoleClient
    admin = AdminConsoleClient(persist_path=tmp_path / "hosts.json")
    admin.add_host("h", "http://127.0.0.1:9", "tok")  # NOSONAR never contacted
    called = []
    monkeypatch.setattr(admin, "_execute_one", lambda *a: called.append(a))
    assert admin.broadcast_execute([["AC_sleep", {"seconds": 0}]], labels=[]) == []
    assert admin.poll_all(labels=[]) == [] and called == []


# --- config sync, metrics, profiler --------------------------------------------------------------

def _bucket(combo, stamp=100.0, **extra):
    from je_auto_control.utils.config_sync.client import ConfigBucket
    bucket = ConfigBucket(user_id="u")
    bucket.sections["hotkeys"] = {"hk1": {"combo": combo, "last_modified": stamp, **extra}}
    return bucket


def test_a_config_sync_tie_converges_and_is_reported():
    from je_auto_control.utils.config_sync.client import merge_buckets
    a, b = _bucket("ctrl+a"), _bucket("ctrl+b")
    merged_ab, conflicts_ab = merge_buckets(a, b)
    merged_ba, conflicts_ba = merge_buckets(b, a)
    assert merged_ab.sections["hotkeys"] == merged_ba.sections["hotkeys"]
    assert len(conflicts_ab) == len(conflicts_ba) == 1
    tombstone = _bucket("ctrl+a")
    tombstone.sections["hotkeys"]["hk1"] = {"deleted": True, "last_modified": 100.0}
    merged, _ = merge_buckets(_bucket("ctrl+z"), tombstone, now=100.0)
    assert merged.sections["hotkeys"]["hk1"].get("deleted") is True
    assert merge_buckets(_bucket("same"), _bucket("same"))[1] == []


def test_a_histogram_given_inf_renders_one_inf_bucket():
    import math

    from je_auto_control.utils.observability.metrics import Histogram
    histogram = Histogram("latency", "help", buckets=(1.0, math.inf))
    histogram.observe(0.5)
    assert histogram.render().count('le="+Inf"') == 1
    with pytest.raises(ValueError):
        Histogram("bad", "help", buckets=(1.0, math.nan))


def test_an_fps_only_profiler_knows_it_is_running():
    from je_auto_control.utils.profiler.resource_profiler import ResourceProfiler
    profiler = ResourceProfiler()
    profiler._psutil = profiler._proc = None  # noqa: SLF001
    profiler.start()
    profiler.tick_frame()
    assert profiler.is_running
    profiler.start()
    assert len(profiler._frames) == 1  # noqa: SLF001
    profiler.stop()
    assert not profiler.is_running
