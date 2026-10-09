"""Session-local tool disclosure and paged ``tools/list`` (plan G2).

Fake tools only. The HTTP half runs a real ``HttpMCPServer`` on a loopback
port, because "two sessions do not see each other's tools" is a statement
about session ids and connections, not about a dict.
"""
import http.client
import json

import pytest

from je_auto_control.utils.mcp_server.disclosure import (
    CORE_TOOL_NAMES, SNAPSHOT_META, DisclosureResult, ToolDisclosureError,
    ToolMode, ToolPage, ToolView, resolve_mode,
)
from je_auto_control.utils.mcp_server.http_sessions import SESSION_HEADER
from je_auto_control.utils.mcp_server.http_transport import DEFAULT_PATH, HttpMCPServer
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import (
    MCPTool, MCPToolAnnotations, build_default_tool_registry,
)

_LIST_CHANGED = "notifications/tools/list_changed"


def _tool(name, *, read_only=False, category="fake"):
    return MCPTool(
        name=name, description=f"Fake tool {name}.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: name,
        annotations=MCPToolAnnotations(read_only=read_only), category=category,
    )


def _tools(count=6):
    return [_tool(f"fx_{number:03d}") for number in range(count)]


def _rpc(server, method, params=None, msg_id=1):
    return json.loads(server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}})))


def _names(reply):
    return [tool["name"] for tool in reply["result"]["tools"]]


def _call(server, name, arguments=None):
    reply = _rpc(server, "tools/call", {"name": name, "arguments": arguments or {}})
    result = reply["result"]
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


def _all_pages(server):
    names, cursor, pages = [], None, 0
    while True:
        reply = _rpc(server, "tools/list", {"cursor": cursor} if cursor else {})
        names.extend(_names(reply))
        pages += 1
        cursor = reply["result"].get("nextCursor")
        if cursor is None:
            return names, pages


# --- mode selection ---------------------------------------------------------------


def test_full_mode_is_compatible(monkeypatch):
    monkeypatch.delenv("JE_AUTOCONTROL_MCP_TOOL_MODE", raising=False)
    registry = build_default_tool_registry(read_only=False)
    server = MCPServer(tools=registry)
    assert server.disclosure.mode is ToolMode.FULL
    reply = _rpc(server, "tools/list")
    full_names = _names(reply)
    registry_names = [tool.name for tool in registry]
    assert full_names == registry_names
    # Byte for byte what the server answered before the mode existed: one
    # page, no cursor, no _meta, and a cursor argument is ignored as it was.
    expected = {"tools": [tool.to_descriptor() for tool in registry]}
    assert reply["result"] == expected
    assert json.dumps(reply["result"]) == json.dumps(expected)
    assert _rpc(server, "tools/list", {"cursor": "anything"})["result"] == expected
    assert not any(name in server._tools for name in CORE_TOOL_NAMES)


def test_mode_comes_from_the_environment_and_rejects_typos(monkeypatch):
    monkeypatch.setenv("JE_AUTOCONTROL_MCP_TOOL_MODE", "progressive")
    assert MCPServer(tools=_tools()).disclosure.mode is ToolMode.PROGRESSIVE
    assert MCPServer(tools=_tools(), tool_mode="full").disclosure.mode is ToolMode.FULL
    monkeypatch.setenv("JE_AUTOCONTROL_MCP_TOOL_MODE", "progresive")
    with pytest.raises(ToolDisclosureError):
        resolve_mode(None)
    monkeypatch.setenv("JE_AUTOCONTROL_MCP_TOOL_MODE", "")
    assert resolve_mode(None) is ToolMode.FULL


def test_progressive_session_starts_with_the_core_only():
    server = MCPServer(tools=_tools(), tool_mode="progressive")
    reply = _rpc(server, "tools/list")
    assert _names(reply) == list(CORE_TOOL_NAMES)
    assert "nextCursor" not in reply["result"]
    assert isinstance(reply["result"]["_meta"][SNAPSHOT_META], str)


# --- enabling ---------------------------------------------------------------------


def test_enable_adds_to_the_list_and_reports_what_happened():
    server = MCPServer(tools=_tools(), tool_mode="progressive")
    outcome = _call(server, "ac_tools_enable", {"names": ["fx_001", "fx_404", "fx_001"]})
    assert outcome["enabled"] == ["fx_001"]
    assert outcome["unavailable"] == ["fx_404"]
    assert _names(_rpc(server, "tools/list")) == list(CORE_TOOL_NAMES) + ["fx_001"]
    again = _call(server, "ac_tools_enable", {"names": ["fx_001"]})
    assert again["enabled"] == []
    assert again["already_enabled"] == ["fx_001"]
    assert _call(server, "ac_tools_disable", {"names": ["fx_001"]})["disabled"] == ["fx_001"]
    assert _names(_rpc(server, "tools/list")) == list(CORE_TOOL_NAMES)


def test_enable_accepts_a_category():
    tools = _tools(3) + [_tool("fx_other", category="other")]
    server = MCPServer(tools=tools, tool_mode="progressive")
    outcome = _call(server, "ac_tools_enable", {"names": ["category:fake"]})
    assert outcome["enabled"] == ["fx_000", "fx_001", "fx_002"]
    assert _call(server, "ac_tools_enable", {"names": ["category:nope"]})["unavailable"] == [
        "category:nope"]


def test_enable_emits_list_changed():
    server = MCPServer(tools=_tools(), tool_mode="progressive")
    sent = []
    server.set_notifier(lambda method, params: sent.append(method))
    outcome = _call(server, "ac_tools_enable", {"names": ["fx_001", "fx_002"]})
    list_changed_count = sent.count(_LIST_CHANGED)
    assert list_changed_count == 1
    assert outcome["list_changed_sent"] is True
    # Enabling what is already enabled changes nothing, so it says nothing.
    _call(server, "ac_tools_enable", {"names": ["fx_001"]})
    assert sent.count(_LIST_CHANGED) == 1
    _call(server, "ac_tools_disable", {"names": ["fx_001"]})
    assert sent.count(_LIST_CHANGED) == 2


def test_enable_without_a_channel_says_the_client_must_list_again():
    server = MCPServer(tools=_tools(), tool_mode="progressive")
    outcome = _call(server, "ac_tools_enable", {"names": ["fx_001"]})
    assert outcome["list_changed_sent"] is False


def test_view_api_returns_typed_results():
    server = MCPServer(tools=_tools(), tool_mode="progressive")
    view = server.disclosure.view_for("session-a")
    assert isinstance(view, ToolView)
    result = view.enable(["fx_002"])
    assert isinstance(result, DisclosureResult)
    assert result.enabled == ("fx_002",)
    page = view.list_page(None)
    assert isinstance(page, ToolPage)
    assert page.next_cursor is None
    assert page.snapshot_id
    assert [tool.name for tool in page.tools] == list(CORE_TOOL_NAMES) + ["fx_002"]
    with pytest.raises(ToolDisclosureError):
        view.enable("fx_003")  # a bare string is not a list of names
    with pytest.raises(ToolDisclosureError):
        view.enable([f"fx_{number}" for number in range(10_000)])


def test_enable_is_session_local():
    server = MCPServer(tools=_tools(), tool_mode="progressive")
    tool = "fx_003"
    with server.connection_scope(connection_id="session-a"):
        _call(server, "ac_tools_enable", {"names": [tool]})
        assert tool in _names(_rpc(server, "tools/list"))
    other_session = server.disclosure.view_for("session-b")
    assert tool not in other_session.visible_names
    with server.connection_scope(connection_id="session-b"):
        assert tool not in _names(_rpc(server, "tools/list"))
        refused = _rpc(server, "tools/call", {"name": tool, "arguments": {}})
        assert refused["error"]["code"] == -32602
    # stdio's one implicit session is a third, separate view.
    assert tool not in _names(_rpc(server, "tools/list"))


def test_a_session_is_reclaimed_when_it_ends():
    server = MCPServer(tools=_tools(), tool_mode="progressive")
    with server.connection_scope(connection_id="session-a"):
        _call(server, "ac_tools_enable", {"names": ["fx_001"]})
    assert server.disclosure.session_count == 1
    server.forget_connection("session-a")
    assert server.disclosure.session_count == 0
    with server.connection_scope(connection_id="session-a"):
        assert "fx_001" not in _names(_rpc(server, "tools/list"))


# --- pagination -------------------------------------------------------------------


def _paged_server(count=7, page_size=3):
    server = MCPServer(tools=_tools(count), tool_mode="progressive")
    server.disclosure.page_size = page_size
    _call(server, "ac_tools_enable", {"names": ["category:fake"]})
    return server


def test_list_pages_cover_the_view_exactly_once():
    server = _paged_server()
    names, pages = _all_pages(server)
    assert names == list(CORE_TOOL_NAMES) + [f"fx_{number:03d}" for number in range(7)]
    assert pages == 4


def test_cursor_snapshot_survives_plugin_change():
    server = _paged_server()
    first = _rpc(server, "tools/list")
    snapshot = first["result"]["_meta"][SNAPSHOT_META]
    cursor = first["result"]["nextCursor"]
    # A plugin arrives and another leaves between two pages.
    server.register_tool(_tool("plugin_fx_new"))
    server.unregister_tool("fx_005")
    _call(server, "ac_tools_enable", {"names": ["plugin_fx_new"]})
    names = _names(first)
    while cursor is not None:
        page = _rpc(server, "tools/list", {"cursor": cursor})
        assert page["result"]["_meta"][SNAPSHOT_META] == snapshot
        names.extend(_names(page))
        cursor = page["result"].get("nextCursor")
    # The original snapshot, whole: no page mixes the two registries.
    assert names == list(CORE_TOOL_NAMES) + [f"fx_{number:03d}" for number in range(7)]
    fresh, _pages = _all_pages(server)
    assert "plugin_fx_new" in fresh
    assert "fx_005" not in fresh
    assert _rpc(server, "tools/list")["result"]["_meta"][SNAPSHOT_META] != snapshot


def test_stale_and_malformed_cursors_fail_explicitly():
    server = _paged_server()
    cursor = _rpc(server, "tools/list")["result"]["nextCursor"]
    for bad in ("", "not-a-cursor", cursor[:-2] + "zz", cursor + "AAAA", 7, ["x"]):
        reply = _rpc(server, "tools/list", {"cursor": bad})
        assert reply["error"]["code"] == -32602, bad
    # Enough newer snapshots push the first one out; its cursor then fails
    # instead of silently paging a different list.
    for number in range(server.disclosure.view_for(None).max_snapshots + 1):
        server.register_tool(_tool(f"fx_churn_{number}"))
        _rpc(server, "tools/list")
    assert _rpc(server, "tools/list", {"cursor": cursor})["error"]["code"] == -32602


def test_a_cursor_belongs_to_its_session():
    server = _paged_server()
    cursor = _rpc(server, "tools/list")["result"]["nextCursor"]
    with server.connection_scope(connection_id="session-b"):
        assert _rpc(server, "tools/list", {"cursor": cursor})["error"]["code"] == -32602


# --- over HTTP --------------------------------------------------------------------


def _post(port, payload, session_id=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/json"}
    if session_id is not None:
        headers[SESSION_HEADER] = session_id
    try:
        connection.request("POST", DEFAULT_PATH, body=json.dumps(payload), headers=headers)
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        return response.status, response.getheader(SESSION_HEADER), body
    finally:
        connection.close()


def _open_session(port):
    status, session_id, _body = _post(port, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {}}})
    assert status == 200
    assert session_id
    return session_id


def _http_names(port, session_id):
    _status, _sid, body = _post(port, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                                session_id)
    return [tool["name"] for tool in json.loads(body)["result"]["tools"]]


def test_two_http_sessions_do_not_share_enabled_tools():
    mcp = MCPServer(tools=_tools(), tool_mode="progressive")
    transport = HttpMCPServer(mcp=mcp, port=0)
    transport.start()
    try:
        port = transport.address[1]
        first, second = _open_session(port), _open_session(port)
        _post(port, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "ac_tools_enable", "arguments": {"names": ["fx_002"]}}},
              first)
        assert "fx_002" in _http_names(port, first)
        assert "fx_002" not in _http_names(port, second)
        status, _sid, body = _post(port, {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "fx_002", "arguments": {}}}, second)
        assert status == 200
        assert json.loads(body)["error"]["code"] == -32602
        assert mcp.disclosure.session_count == 2
        # Ending the session releases its view.
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.request("DELETE", DEFAULT_PATH, headers={SESSION_HEADER: first})
            assert connection.getresponse().status == 200
        finally:
            connection.close()
        assert mcp.disclosure.session_count == 1
        transport.stop()
        assert mcp.disclosure.session_count == 0
    finally:
        transport.stop()
