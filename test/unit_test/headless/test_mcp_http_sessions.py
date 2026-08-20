"""Headless tests for MCP session identity over the HTTP transport.

Two halves. The registry half is pure and drives an injected clock. The
transport half runs a real ``HttpMCPServer`` over real sockets, because the
thing worth proving — that a destructive tool can be confirmed over HTTP —
only exists once a session id, a standing GET stream and three separate
connections are all in play at once.
"""
import http.client
import json
import logging
import threading

import pytest

from je_auto_control.utils.mcp_server.http_sessions import (
    SESSION_HEADER, SessionRegistry, session_id_from_headers,
)
from je_auto_control.utils.mcp_server.http_transport import (
    DEFAULT_PATH, HttpMCPServer, _MCPHttpHandler,
)
from je_auto_control.utils.mcp_server.prompts import StaticPromptProvider
from je_auto_control.utils.mcp_server.resources import ChainProvider
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool, MCPToolAnnotations


class _Clock:
    """Manual monotonic clock."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# --- registry ---------------------------------------------------------------


def test_created_sessions_are_distinct_and_resolvable():
    registry = SessionRegistry(clock=_Clock())
    first, second = registry.create(), registry.create()
    assert first.id != second.id
    assert registry.get(first.id) is first
    assert registry.get(second.id) is second
    assert len(registry) == 2


def test_unknown_and_blank_session_ids_resolve_to_none():
    registry = SessionRegistry(clock=_Clock())
    assert registry.get("nope") is None
    assert registry.get("") is None
    assert registry.get(None) is None


def test_idle_sessions_are_swept_and_announced():
    clock = _Clock()
    dropped = []
    registry = SessionRegistry(clock=clock, idle_timeout=100.0,
                                on_drop=dropped.append)
    session = registry.create()
    clock.now += 50.0
    assert registry.get(session.id) is session  # touched, so still live
    clock.now += 60.0                            # 60 < 100 since the touch
    assert registry.get(session.id) is session
    clock.now += 101.0
    assert registry.get(session.id) is None
    assert [item.id for item in dropped] == [session.id]
    assert session.closed.is_set()


def test_capacity_evicts_the_least_recently_seen():
    clock = _Clock()
    dropped = []
    registry = SessionRegistry(clock=clock, max_sessions=2,
                                idle_timeout=0, on_drop=dropped.append)
    first, second = registry.create(), registry.create()
    clock.now += 1.0
    registry.get(second.id)          # second is now the fresher of the two
    clock.now += 1.0
    third = registry.create()
    assert [item.id for item in dropped] == [first.id]
    assert registry.get(first.id) is None
    assert registry.get(second.id) is second
    assert registry.get(third.id) is third


def test_terminate_and_terminate_all_announce_once():
    dropped = []
    registry = SessionRegistry(clock=_Clock(), on_drop=dropped.append)
    first, second = registry.create(), registry.create()
    assert registry.terminate(first.id) is first
    assert registry.terminate(first.id) is None
    registry.terminate_all()
    assert [item.id for item in dropped] == [first.id, second.id]
    assert second.closed.is_set()
    assert len(registry) == 0


def test_a_failing_drop_hook_does_not_break_the_caller():
    def boom(_session):
        raise RuntimeError("hook exploded")

    registry = SessionRegistry(clock=_Clock(), on_drop=boom)
    session = registry.create()
    assert registry.terminate(session.id) is session  # no exception escapes


def test_only_one_stream_attaches_per_session():
    registry = SessionRegistry(clock=_Clock())
    session = registry.create()
    first, second = (lambda _payload: None), (lambda _payload: None)
    assert session.attach_stream(first) is True
    assert session.has_stream is True
    assert session.attach_stream(second) is False
    session.detach_stream(second)                    # not the owner — no-op
    assert session.stream_writer is first
    session.detach_stream(first)
    assert session.has_stream is False


def test_session_id_header_is_read_case_insensitively():
    assert session_id_from_headers({"Mcp-Session-Id": " abc "}) == "abc"
    assert session_id_from_headers({"Mcp-Session-Id": "   "}) is None
    assert session_id_from_headers({}) is None
    assert session_id_from_headers(None) is None


# --- transport --------------------------------------------------------------


def _destructive_tool(ran):
    return MCPTool(
        name="zap", description="destructive probe",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: ran.append(1) or "RAN",
        annotations=MCPToolAnnotations(destructive=True, read_only=False),
    )


@pytest.fixture()
def live_server(monkeypatch):
    """A real HttpMCPServer carrying one destructive tool, gate armed."""
    monkeypatch.setenv("JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE", "1")
    ran = []
    server = HttpMCPServer(mcp=MCPServer(
        tools=[_destructive_tool(ran)], resource_provider=ChainProvider([]),
        prompt_provider=StaticPromptProvider([]),
    ), host="127.0.0.1", port=0)
    server.start()
    try:
        yield server, ran
    finally:
        server.stop(timeout=2.0)


def _connect(server):
    host, port = server.address
    return http.client.HTTPConnection(host, port, timeout=20)


def _post(conn, payload, session_id=None, accept="application/json"):
    headers = {"Content-Type": "application/json", "Accept": accept}
    if session_id is not None:
        headers[SESSION_HEADER] = session_id
    conn.request("POST", DEFAULT_PATH, body=json.dumps(payload),
                 headers=headers)
    response = conn.getresponse()
    body = response.read().decode("utf-8")
    return response, body


_INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {"elicitation": {}},
        "clientInfo": {"name": "probe", "version": "1"},
    },
}
_CALL = {
    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
    "params": {"name": "zap", "arguments": {}},
}


def _initialize(server):
    """Run initialize on its own connection; return the minted session id."""
    conn = _connect(server)
    try:
        response, _body = _post(conn, _INIT)
        assert response.status == 200
        session_id = response.getheader(SESSION_HEADER)
        assert session_id, "initialize must mint a session id"
        return session_id
    finally:
        conn.close()


def _read_sse_event(response):
    """Read one SSE event's data payload, skipping comments and blanks.

    The connection's socket timeout is what bounds this, so a stream that
    never carries the expected event fails the test instead of hanging it.
    """
    while True:
        raw = response.readline()
        if not raw:
            return None
        line = raw.decode("utf-8").rstrip("\r\n")
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])


def test_initialize_mints_a_session_id(live_server):
    server, _ran = live_server
    session_id = _initialize(server)
    assert server.sessions.get(session_id) is not None


def test_capabilities_survive_a_new_connection_when_the_id_is_echoed(
        live_server):
    server, _ran = live_server
    session_id = _initialize(server)
    # A second, entirely separate TCP connection.
    conn = _connect(server)
    try:
        with server.mcp.connection_scope(connection_id=session_id):
            assert "elicitation" in server.mcp._client_capabilities
    finally:
        conn.close()


def test_unknown_session_id_is_refused(live_server):
    server, _ran = live_server
    conn = _connect(server)
    try:
        response, _body = _post(conn, _CALL, session_id="not-a-session")
        assert response.status == 404
    finally:
        conn.close()


def test_delete_terminates_the_session(live_server):
    server, _ran = live_server
    session_id = _initialize(server)
    conn = _connect(server)
    try:
        conn.request("DELETE", DEFAULT_PATH,
                     headers={SESSION_HEADER: session_id})
        assert conn.getresponse().read() is not None
        conn.close()
        conn = _connect(server)
        response, _body = _post(conn, _CALL, session_id=session_id)
        assert response.status == 404
    finally:
        conn.close()


def test_get_without_sse_accept_is_rejected(live_server):
    server, _ran = live_server
    session_id = _initialize(server)
    conn = _connect(server)
    try:
        conn.request("GET", DEFAULT_PATH, headers={
            SESSION_HEADER: session_id, "Accept": "application/json",
        })
        assert conn.getresponse().status == 405
    finally:
        conn.close()


def test_get_stream_without_a_session_is_rejected(live_server):
    server, _ran = live_server
    conn = _connect(server)
    try:
        conn.request("GET", DEFAULT_PATH,
                     headers={"Accept": "text/event-stream"})
        assert conn.getresponse().status == 404
    finally:
        conn.close()


def test_destructive_confirmation_round_trips_over_http(live_server):
    """The whole point of session identity: a decline blocks the tool.

    Three connections, as a real Streamable HTTP client would use: one that
    initialized, one holding the standing GET stream, and one carrying the
    tools/call. The elicitation goes out on the stream and its reply comes
    back on a fourth — none of which shared a socket with the handshake.
    """
    server, ran = live_server
    session_id = _initialize(server)

    stream_conn = _connect(server)
    stream_conn.request("GET", DEFAULT_PATH, headers={
        SESSION_HEADER: session_id, "Accept": "text/event-stream",
    })
    stream = stream_conn.getresponse()
    assert stream.status == 200

    call_result = {}

    def run_call():
        conn = _connect(server)
        try:
            _response, body = _post(conn, _CALL, session_id=session_id)
            call_result["body"] = body
        finally:
            conn.close()

    caller = threading.Thread(target=run_call, daemon=True)
    caller.start()
    try:
        prompt = _read_sse_event(stream)
        assert prompt is not None, "expected elicitation on the stream"
        assert prompt["method"] == "elicitation/create"

        reply_conn = _connect(server)
        try:
            response, _body = _post(reply_conn, {
                "jsonrpc": "2.0", "id": prompt["id"],
                "result": {"action": "decline"},
            }, session_id=session_id)
            assert response.status == 202
        finally:
            reply_conn.close()

        caller.join(timeout=20.0)
        assert not caller.is_alive()
    finally:
        stream_conn.close()

    payload = json.loads(call_result["body"])
    assert payload["error"]["code"] == -32000
    assert "declined" in payload["error"]["message"]
    assert ran == [], "a declined destructive tool must not run"


def test_accepting_the_confirmation_runs_the_tool(live_server):
    server, ran = live_server
    session_id = _initialize(server)

    stream_conn = _connect(server)
    stream_conn.request("GET", DEFAULT_PATH, headers={
        SESSION_HEADER: session_id, "Accept": "text/event-stream",
    })
    stream = stream_conn.getresponse()
    call_result = {}

    def run_call():
        conn = _connect(server)
        try:
            _response, body = _post(conn, _CALL, session_id=session_id)
            call_result["body"] = body
        finally:
            conn.close()

    caller = threading.Thread(target=run_call, daemon=True)
    caller.start()
    try:
        prompt = _read_sse_event(stream)
        reply_conn = _connect(server)
        try:
            _post(reply_conn, {
                "jsonrpc": "2.0", "id": prompt["id"],
                "result": {"action": "accept", "content": {}},
            }, session_id=session_id)
        finally:
            reply_conn.close()
        caller.join(timeout=20.0)
    finally:
        stream_conn.close()

    payload = json.loads(call_result["body"])
    assert payload["result"]["isError"] is False
    assert ran == [1]


def test_second_stream_on_one_session_is_refused(live_server):
    server, _ran = live_server
    session_id = _initialize(server)
    first = _connect(server)
    first.request("GET", DEFAULT_PATH, headers={
        SESSION_HEADER: session_id, "Accept": "text/event-stream",
    })
    assert first.getresponse().status == 200
    second = _connect(server)
    try:
        second.request("GET", DEFAULT_PATH, headers={
            SESSION_HEADER: session_id, "Accept": "text/event-stream",
        })
        assert second.getresponse().status == 409
    finally:
        second.close()
        first.close()


def test_evicting_an_abandoned_session_is_not_logged_as_a_warning(caplog):
    """Every initialize mints a session; churning through them is routine.

    A client that ignores the header leaves a session behind on every
    handshake. Warning on each eviction would put one line per request in
    the log of any busy sessionless server, which buries the case that does
    matter: a session someone was holding.
    """
    clock = _Clock()
    registry = SessionRegistry(clock=clock, max_sessions=1, idle_timeout=0)
    registry.create()
    with caplog.at_level(logging.INFO):
        registry.create()
    assert not [record for record in caplog.records
                if record.levelno >= logging.WARNING]
    assert any("never used after initialize" in record.getMessage()
               for record in caplog.records)


def test_evicting_a_session_in_use_warns(caplog):
    clock = _Clock()
    registry = SessionRegistry(clock=clock, max_sessions=1, idle_timeout=0)
    held = registry.create()
    clock.now += 1.0
    registry.get(held.id)          # touched, so no longer an abandoned shell
    with caplog.at_level(logging.INFO):
        registry.create()
    warnings = [record for record in caplog.records
                if record.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert "evicting a live session" in warnings[0].getMessage()


def test_an_sse_post_can_carry_its_own_confirmation(live_server):
    """A session'd SSE POST is promptable without a standing GET stream.

    The response stream is itself a server-to-client channel, so the
    elicitation goes down the same socket the call arrived on. The reply
    still comes back as a separate POST, because the client is busy reading
    this one.
    """
    server, ran = live_server
    session_id = _initialize(server)

    conn = _connect(server)
    conn.request("POST", DEFAULT_PATH, body=json.dumps(_CALL), headers={
        "Content-Type": "application/json", "Accept": "text/event-stream",
        SESSION_HEADER: session_id,
    })
    stream = conn.getresponse()
    try:
        prompt = _read_sse_event(stream)
        assert prompt is not None and prompt["method"] == "elicitation/create"

        reply_conn = _connect(server)
        try:
            _post(reply_conn, {
                "jsonrpc": "2.0", "id": prompt["id"],
                "result": {"action": "decline"},
            }, session_id=session_id)
        finally:
            reply_conn.close()

        final = _read_sse_event(stream)
        assert final["error"]["code"] == -32000
        assert "declined" in final["error"]["message"]
    finally:
        conn.close()
    assert ran == []


class _RecordingReader:
    """Stands in for a handler's ``rfile``, remembering every read."""

    def __init__(self, chunks=b""):
        self.reads = []
        self._buffer = chunks

    def read(self, size):
        self.reads.append(size)
        chunk, self._buffer = self._buffer[:size], self._buffer[size:]
        return chunk


class _VanishedReader:
    """An ``rfile`` whose peer is already gone."""

    def read(self, _size):
        raise ConnectionAbortedError(10053, "connection aborted")


def _bare_handler(*, consumed, reader, length="10"):
    """A handler instance with no socket, for the body-drain logic alone."""
    handler = _MCPHttpHandler.__new__(_MCPHttpHandler)
    handler._body_consumed = consumed
    handler.rfile = reader
    handler.headers = {"Content-Length": length}
    return handler


def test_drain_is_skipped_once_the_body_has_been_read():
    """A 4xx raised after _read_body must not go looking for more body.

    It would find the *next* request's bytes, or nothing at all, and block
    on the socket until the 30s read timeout — pinning the worker for every
    unknown-session 404 and every duplicate-stream 409.
    """
    reader = _RecordingReader(b"leftover!!")
    handler = _bare_handler(consumed=True, reader=reader)
    handler._drain_body()
    assert reader.reads == []


def test_drain_still_runs_when_the_body_was_never_read():
    reader = _RecordingReader(b"0123456789")
    handler = _bare_handler(consumed=False, reader=reader)
    handler._drain_body()
    assert reader.reads, "an unread body is still drained"


def test_drain_survives_a_peer_that_vanished():
    handler = _bare_handler(consumed=False, reader=_VanishedReader())
    handler._drain_body()  # must not raise: courtesy to a peer that has gone
