"""An MCP HTTP session belongs to the user who created it.

With RBAC every request was authorised by its own token, but the session id
was honoured for whoever presented it: a second authenticated user who knew
the id could attach to the first user's standing stream, delete the session,
or dispatch into its scope and so read which tools it had enabled. The
shared-token and no-auth servers identify nobody, and keep working as before.

Also here, because they came out of the same file split: ``tool_mode`` on the
HTTP entry points, and a tool registered from the plugin watcher's thread
reaching the sessions' standing streams.

Loopback only, fake tools only.
"""
import http.client
import json
import threading
import time

import pytest

from je_auto_control.utils.mcp_server.disclosure import (
    ENABLE_TOOL, MODE_ENV, STATE_TOOL, ToolDisclosureError, ToolMode,
)
from je_auto_control.utils.mcp_server.http_sessions import (
    SESSION_HEADER, SessionOwnerMismatch, SessionRegistry,
)
from je_auto_control.utils.mcp_server.http_transport import (
    DEFAULT_PATH, HttpMCPServer, start_mcp_http_server,
)
from je_auto_control.utils.mcp_server.plugin_watcher import PluginWatcher
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool
from je_auto_control.utils.mcp_server.tools._base import READ_ONLY, schema
from je_auto_control.utils.rbac import USERS_ENV, Role, UserStore

_WAIT = 10.0
_INITIALIZE = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-06-18", "capabilities": {}}}


@pytest.fixture(autouse=True)
def _no_ambient_configuration(monkeypatch):
    for name in (USERS_ENV, "JE_AUTOCONTROL_MCP_TOKEN", MODE_ENV, "JE_AUTOCONTROL_MCP_READONLY"):
        monkeypatch.delenv(name, raising=False)


def _tool(name):
    return MCPTool(name=name, description=name, annotations=READ_ONLY,
                   handler=lambda: {"ran": name}, input_schema=schema({}))


@pytest.fixture
def users(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.tokens = {name: store.add_user(user_id=name, display_name=name, role=Role.OPERATOR)
                    for name in ("alice", "bob")}
    return store


@pytest.fixture
def serve():
    started = []

    def start(**kwargs):
        kwargs.setdefault("mcp", MCPServer(tools=[_tool("peek"), _tool("look")],
                                           tool_mode=kwargs.pop("mode", None)))
        server = HttpMCPServer(host="127.0.0.1", port=0, **kwargs)
        server.start()
        started.append(server)
        return server

    yield start
    for server in started:
        server.stop(timeout=2.0)


def _request(server, body=None, token=None, session=None, method="POST", accept="application/json"):
    """``(status, session header, parsed body)`` of one request."""
    connection = http.client.HTTPConnection(*server.address, timeout=_WAIT)
    headers = {"Content-Type": "application/json", "Accept": accept}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if session is not None:
        headers[SESSION_HEADER] = session
    try:
        connection.request(method, DEFAULT_PATH, headers=headers,
                           body=None if body is None else json.dumps(body))
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        return response.status, response.getheader(SESSION_HEADER), json.loads(raw) if raw else None
    finally:
        connection.close()


def _call(name, arguments=None, msg_id=2):
    return {"jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}}}


def _open_session(server, token=None):
    status, session, _body = _request(server, _INITIALIZE, token=token)
    assert status == 200
    assert session
    return session


def _open_stream(server, session, token=None):
    """Open the session's standing GET stream; ``(connection, response)``."""
    connection = http.client.HTTPConnection(*server.address, timeout=_WAIT)
    headers = {"Accept": "text/event-stream", SESSION_HEADER: session}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    connection.request("GET", DEFAULT_PATH, headers=headers)
    return connection, connection.getresponse()


def _next_event(response):
    while True:
        raw = response.readline()
        if not raw:
            return None
        line = raw.decode("utf-8").rstrip("\r\n")
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])


# --- the registry ---------------------------------------------------------------------

class _Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_registry_refuses_another_owner_without_touching_the_session():
    clock = _Clock()
    registry = SessionRegistry(clock=clock, idle_timeout=50.0)
    session = registry.create(owner="alice")
    clock.now += 10
    with pytest.raises(SessionOwnerMismatch):
        registry.get(session.id, owner="bob")
    with pytest.raises(SessionOwnerMismatch):
        registry.get(session.id, owner=None)
    assert session.last_seen < clock.now, "a stranger must not keep the session alive"
    assert registry.get(session.id, owner="alice") is session
    assert session.last_seen >= clock.now


def test_registry_refuses_to_terminate_for_another_owner():
    dropped = []
    registry = SessionRegistry(on_drop=dropped.append)
    session = registry.create(owner="alice")
    with pytest.raises(SessionOwnerMismatch):
        registry.terminate(session.id, owner="bob")
    assert dropped == []
    assert not session.closed.is_set()
    assert registry.terminate(session.id, owner="alice") is session
    assert dropped == [session]


def test_registry_lookups_without_an_owner_are_unchanged():
    registry = SessionRegistry()
    owned, anonymous = registry.create(owner="alice"), registry.create()
    assert registry.get(owned.id) is owned
    assert registry.get(anonymous.id, owner=None) is anonymous
    assert set(registry.live()) == {owned, anonymous}
    assert registry.terminate(owned.id) is owned
    assert registry.live() == [anonymous]


# --- RBAC on: the id alone opens nothing -------------------------------------------------

def test_another_user_cannot_post_into_the_session(serve, users):
    server = serve(user_store=users)
    session = _open_session(server, users.tokens["alice"])
    listing = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    status, _session, body = _request(server, listing, users.tokens["bob"], session)
    assert status == 403
    assert "another user" in body["error"]
    status, _session, body = _request(server, listing, users.tokens["alice"], session)
    assert status == 200
    assert {tool["name"] for tool in body["result"]["tools"]} == {"peek", "look"}


def test_another_user_cannot_attach_to_the_stream(serve, users):
    server = serve(user_store=users)
    session = _open_session(server, users.tokens["alice"])
    connection, response = _open_stream(server, session, users.tokens["bob"])
    try:
        assert response.status == 403
        assert not server.sessions.get(session).has_stream
    finally:
        connection.close()
    connection, response = _open_stream(server, session, users.tokens["alice"])
    try:
        assert response.status == 200
    finally:
        connection.close()


def test_another_user_cannot_delete_the_session(serve, users):
    server = serve(user_store=users)
    session = _open_session(server, users.tokens["alice"])
    status, _session, _body = _request(server, token=users.tokens["bob"], session=session,
                                       method="DELETE")
    assert status == 403
    assert server.sessions.get(session) is not None
    status, _session, _body = _request(server, token=users.tokens["alice"], session=session,
                                       method="DELETE")
    assert status == 200
    assert server.sessions.get(session) is None


def test_another_user_cannot_read_the_enabled_tool_view(serve, users):
    server = serve(user_store=users, mode="progressive")
    alice, bob = users.tokens["alice"], users.tokens["bob"]
    session = _open_session(server, alice)
    status, _session, body = _request(server, _call(ENABLE_TOOL, {"names": ["peek"]}), alice, session)
    assert status == 200
    assert body["result"]["isError"] is False
    status, _session, body = _request(server, _call(STATE_TOOL), bob, session)
    assert status == 403
    assert "peek" not in json.dumps(body)
    status, _session, body = _request(
        server, {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, bob, session)
    assert status == 403
    # Bob's own session starts from the core tools, not from what Alice enabled.
    own = _open_session(server, bob)
    status, _session, body = _request(
        server, {"jsonrpc": "2.0", "id": 4, "method": "tools/list"}, bob, own)
    assert status == 200
    assert "peek" not in {tool["name"] for tool in body["result"]["tools"]}


def test_the_same_user_keeps_the_session_across_connections(serve, users):
    server = serve(user_store=users)
    session = _open_session(server, users.tokens["alice"])
    for _attempt in range(2):
        status, echoed, _body = _request(server, {"jsonrpc": "2.0", "id": 5, "method": "ping"},
                                         users.tokens["alice"], session)
        assert status == 200
        assert echoed == session


# --- RBAC off: nobody is identified, so nothing changes -----------------------------------

@pytest.mark.parametrize("token", [None, "shared-token-value"])
def test_without_rbac_the_session_id_works_for_every_caller(serve, token):
    server = serve(auth_token=token)
    session = _open_session(server, token)
    status, _session, body = _request(
        server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, token, session)
    assert status == 200
    assert len(body["result"]["tools"]) == 2
    connection, response = _open_stream(server, session, token)
    try:
        assert response.status == 200
    finally:
        connection.close()
    status, _session, _body = _request(server, token=token, session=session, method="DELETE")
    assert status == 200


# --- tool_mode on the HTTP entry points ---------------------------------------------------

def test_http_server_builds_its_dispatcher_in_the_given_tool_mode():
    assert HttpMCPServer(port=0, tool_mode="progressive").mcp.disclosure.mode is ToolMode.PROGRESSIVE
    assert HttpMCPServer(port=0, tool_mode=ToolMode.STATIC).mcp.disclosure.mode is ToolMode.STATIC
    assert HttpMCPServer(port=0).mcp.disclosure.mode is ToolMode.FULL


def test_tool_mode_none_still_reads_the_environment(monkeypatch):
    monkeypatch.setenv(MODE_ENV, "static")
    assert HttpMCPServer(port=0).mcp.disclosure.mode is ToolMode.STATIC


def test_tool_mode_that_contradicts_a_given_dispatcher_is_refused():
    mcp = MCPServer(tools=[_tool("peek")])
    with pytest.raises(ToolDisclosureError, match="does not match"):
        HttpMCPServer(mcp=mcp, port=0, tool_mode="progressive")
    assert HttpMCPServer(mcp=mcp, port=0, tool_mode="full").mcp is mcp
    with pytest.raises(ToolDisclosureError):
        HttpMCPServer(port=0, tool_mode="everything")


def test_start_mcp_http_server_takes_tool_mode():
    server = start_mcp_http_server(port=0, tool_mode="progressive",
                                   mcp=MCPServer(tools=[_tool("peek")], tool_mode="progressive"))
    try:
        session = _open_session(server)
        _status, _session, body = _request(
            server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session=session)
        names = {tool["name"] for tool in body["result"]["tools"]}
        assert ENABLE_TOOL in names
        assert "peek" not in names
    finally:
        server.stop(timeout=2.0)


# --- a registration from no request at all reaches the sessions ---------------------------

def test_a_tool_registered_from_another_thread_is_announced_on_session_streams(serve):
    server = serve()
    first, second = _open_session(server), _open_session(server)
    streams = [_open_stream(server, first), _open_stream(server, second)]
    try:
        assert all(response.status == 200 for _connection, response in streams)
        worker = threading.Thread(target=server.mcp.register_tool, args=(_tool("late"),))
        worker.start()
        worker.join(_WAIT)
        for _connection, response in streams:
            assert _next_event(response) == {
                "jsonrpc": "2.0", "method": "notifications/tools/list_changed", "params": {}}
    finally:
        for connection, _response in streams:
            connection.close()


def test_the_plugin_watcher_thread_reaches_an_http_session(serve, tmp_path):
    server = serve()
    session = _open_session(server)
    connection, response = _open_stream(server, session)
    watcher = PluginWatcher(server.mcp, str(tmp_path), poll_seconds=0.2)
    watcher.start()
    try:
        assert response.status == 200
        (tmp_path / "late.py").write_text("def AC_late():\n    return 'late'\n", encoding="utf-8")
        event = _next_event(response)
        assert event is not None
        assert event["method"] == "notifications/tools/list_changed"
        _status, _session, body = _request(
            server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session=session)
        assert "plugin_ac_late" in {tool["name"] for tool in body["result"]["tools"]}
    finally:
        watcher.stop(timeout=_WAIT)
        connection.close()


def test_the_requesting_session_is_not_told_twice(serve):
    """A registration made while serving a session reaches that session once."""
    server = serve()
    mcp = server.mcp
    mcp.register_tool(MCPTool(
        name="grow", description="grow", annotations=READ_ONLY, input_schema=schema({}),
        handler=lambda: mcp.register_tool(_tool(f"grown_{time.monotonic_ns()}")) or {"ok": True}))
    session = _open_session(server)
    connection, response = _open_stream(server, session)
    try:
        assert response.status == 200
        status, _session, _body = _request(server, _call("grow"), session=session)
        assert status == 200
        assert _next_event(response)["method"] == "notifications/tools/list_changed"
        # Stopping ends the stream; anything before its end would be a duplicate.
        server.stop(timeout=2.0)
        assert _next_event(response) is None
    finally:
        connection.close()


def test_a_stopped_transport_no_longer_listens_for_registry_changes(serve):
    server = serve()
    mcp = server.mcp
    assert len(mcp._list_changed_listeners) == 1
    server.stop(timeout=2.0)
    assert mcp._list_changed_listeners == []
    mcp.register_tool(_tool("after_stop"))
