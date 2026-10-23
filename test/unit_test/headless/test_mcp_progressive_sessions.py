"""Session disclosure cannot grant authority, cross peers, or mix registry snapshots."""
import json

import pytest

from je_auto_control.utils.mcp_server.discovery import ToolIndex, ToolDiscoveryError
from je_auto_control.utils.mcp_server.tools import MCPTool, MCPToolAnnotations


def fixtures():
    return [MCPTool("fixture_" + str(index), "Fixture", {}, lambda: "ok",
                    MCPToolAnnotations(read_only=True)) for index in range(5)]


def request(server, method, params=None):
    return json.loads(server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1,
                                                    "method": method, "params": params or {}})))


def test_enable_is_session_local_and_emits_one_change():
    from je_auto_control.utils.mcp_server.disclosure import ToolView
    events = []
    first = ToolView(lambda: ToolIndex(fixtures()), changed=lambda: events.append("changed"))
    second = ToolView(lambda: ToolIndex(fixtures()))
    assert first.state()["enabled"] == []
    first.enable(["fixture_0"])
    first.enable(["fixture_0"])
    assert first.state()["enabled"] == ["fixture_0"]
    assert second.state()["enabled"] == [] and events == ["changed"]
    assert first.state()["snapshot_id"] != second.state()["snapshot_id"]


def test_cursor_rejects_plugin_changes_and_other_views():
    from je_auto_control.utils.mcp_server.disclosure import ToolView
    tools = fixtures()
    view = ToolView(lambda: ToolIndex(tools), mode="static", initial=[tool.name for tool in tools], page_size=2)
    first = view.list_page()
    cursor = first["nextCursor"]
    other = ToolView(lambda: ToolIndex(tools), mode="static", initial=[tool.name for tool in tools], page_size=2)
    with pytest.raises(ToolDiscoveryError, match="cursor"):
        other.list_page(cursor)
    second = view.list_page(cursor)
    assert len({item["name"] for item in first["tools"] + second["tools"]}) == 4
    assert first["snapshot_id"] == second["snapshot_id"]
    tools.pop()
    with pytest.raises(ToolDiscoveryError, match="cursor"):
        view.list_page(second["nextCursor"])


def test_server_disclosure_cannot_cross_connections_or_bypass_enable():
    from je_auto_control.utils.mcp_server.server import MCPServer
    from je_auto_control.utils.mcp_server.tools._discovery import discovery_tools
    server = MCPServer(tools=discovery_tools() + fixtures())
    server.configure_tool_disclosure("progressive", page_size=10)
    events = []
    with server.connection_scope(connection_id="first", notifier=lambda *event: events.append(event)):
        assert "error" in request(server, "tools/call", {"name": "fixture_0"})
        reply = request(server, "tools/call", {"name": "ac_mcp_tools_enable",
                                               "arguments": {"names": ["fixture_0"]}})
        assert reply["result"]["isError"] is False
        assert "fixture_0" in {tool["name"] for tool in request(server, "tools/list")["result"]["tools"]}
    with server.connection_scope(connection_id="second"):
        assert "fixture_0" not in {tool["name"] for tool in request(server, "tools/list")["result"]["tools"]}
    assert [event[0] for event in events] == ["notifications/tools/list_changed"]
    server.forget_connection("first")
    with server.connection_scope(connection_id="first"):
        assert "error" in request(server, "tools/call", {"name": "fixture_0"})


def test_full_mode_preserves_the_existing_list_shape():
    from je_auto_control.utils.mcp_server.server import MCPServer
    tools = fixtures()
    server = MCPServer(tools=tools)
    assert request(server, "tools/list")["result"] == {"tools": [tool.to_descriptor() for tool in tools]}


def test_readonly_role_and_revocation_apply_to_enable_and_cursors():
    from je_auto_control.utils.mcp_server.disclosure import ToolView
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
    tools = fixtures() + [MCPTool("write", "Mutate", {}, lambda: None)]
    view = ToolView(lambda: ToolIndex(tools), page_size=2)
    with authorization_scope(AuthorizationContext("reader", "viewer")):
        with pytest.raises(ToolDiscoveryError, match="not available"):
            view.enable(["fixture_0", "write"])
        assert view.state()["enabled"] == []
    with authorization_scope(AuthorizationContext("driver", "operator")):
        view.enable([tool.name for tool in tools])
        page = view.list_page()
    with authorization_scope(AuthorizationContext("driver", "viewer")):
        with pytest.raises(ToolDiscoveryError, match="cursor"):
            view.list_page(page["nextCursor"])
        assert "write" not in view.state()["enabled"]


def test_closed_view_cannot_be_revived_by_an_inflight_callback():
    from je_auto_control.utils.mcp_server.disclosure import ToolView
    view = ToolView(lambda: ToolIndex(fixtures()))
    view.close()
    with pytest.raises(ToolDiscoveryError, match="closed"):
        view.enable(["fixture_0"])
    with pytest.raises(ToolDiscoveryError, match="closed"):
        view.list_page()


def test_readonly_ceiling_applies_to_plugins_registered_after_start():
    from je_auto_control.utils.mcp_server.server import MCPServer
    from je_auto_control.utils.mcp_server.tools._discovery import discovery_tools
    server = MCPServer(tools=discovery_tools())
    server.configure_tool_disclosure("progressive", read_only=True)
    calls = []
    server.register_tool(MCPTool("plugin_write", "Mutate", {}, lambda: calls.append(True)))
    result = request(server, "tools/call", {"name": "ac_mcp_tools_enable", "arguments": {"names": ["plugin_write"]}})
    assert result["result"]["isError"] is True
    assert "error" in request(server, "tools/call", {"name": "plugin_write"})
    server.configure_tool_disclosure("full")
    assert "plugin_write" not in {item["name"] for item in request(server, "tools/list")["result"]["tools"]}
    assert "error" in request(server, "tools/call", {"name": "plugin_write"})
    assert calls == []


def test_stateless_requests_use_a_fixed_profile_and_create_no_session_views():
    from je_auto_control.utils.mcp_server.server import MCPServer
    from je_auto_control.utils.mcp_server.tools._discovery import discovery_tools
    server = MCPServer(tools=discovery_tools() + fixtures())
    server.configure_tool_disclosure("progressive", names=["fixture_0"], page_size=1)
    meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {}}
    page = request(server, "tools/list", {"_meta": meta})["result"]
    assert "fixture_0" in {item["name"] for item in page["tools"]}
    assert "fixture_1" not in {item["name"] for item in page["tools"]}
    assert "nextCursor" not in page and server._disclosure_views == {}
    result = request(server, "tools/call", {"_meta": meta, "name": "ac_mcp_tools_enable",
                                          "arguments": {"names": ["fixture_1"]}})
    assert result["result"]["isError"] is True


def test_two_real_http_sessions_keep_separate_views_across_connections():
    import http.client
    from je_auto_control.utils.mcp_server.server import MCPServer
    from je_auto_control.utils.mcp_server.http_transport import HttpMCPServer
    from je_auto_control.utils.mcp_server.tools._discovery import discovery_tools
    bridge = MCPServer(tools=discovery_tools() + fixtures())
    bridge.configure_tool_disclosure("progressive", page_size=10)
    server = HttpMCPServer(bridge, port=0)
    server.start()

    def rpc(method, params=None, session=None):
        connection = http.client.HTTPConnection(*server.address, timeout=5)
        try:
            headers = {"Content-Type": "application/json"}
            if session:
                headers["Mcp-Session-Id"] = session
            connection.request("POST", "/mcp", json.dumps({"jsonrpc": "2.0", "id": 1,
                               "method": method, "params": params or {}}), headers)
            response = connection.getresponse()
            return response.getheader("Mcp-Session-Id"), json.loads(response.read())
        finally:
            connection.close()

    try:
        first, _ = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
        second, _ = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
        assert first and second and first != second
        _, enabled = rpc("tools/call", {"name": "ac_mcp_tools_enable",
                                        "arguments": {"names": ["fixture_0"]}}, first)
        assert enabled["result"]["isError"] is False
        _, first_page = rpc("tools/list", session=first)
        _, second_page = rpc("tools/list", session=second)
        assert "fixture_0" in {item["name"] for item in first_page["result"]["tools"]}
        assert "fixture_0" not in {item["name"] for item in second_page["result"]["tools"]}
        assert first in bridge._disclosure_views and second in bridge._disclosure_views
    finally:
        server.stop()
    assert bridge._disclosure_views == {}


def test_stdio_eof_retires_the_view_and_its_existing_callback():
    import io
    from je_auto_control.utils.mcp_server.server import MCPServer
    server = MCPServer(tools=fixtures())
    server.configure_tool_disclosure("progressive")
    callback = server._build_call_context(1, {}).tool_catalog
    server.serve_stdio(io.StringIO(""), io.StringIO())
    assert server._disclosure_views == {}
    with pytest.raises(ToolDiscoveryError, match="closed"):
        callback().state()
