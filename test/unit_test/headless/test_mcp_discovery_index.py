"""Tool discovery uses the live registry and never expands the caller's authority."""
import json

import pytest

from je_auto_control.utils.mcp_server.tools import MCPTool, MCPToolAnnotations
from je_auto_control.utils.mcp_server.discovery import ToolDiscoveryError
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope


def catalog():
    return [
        MCPTool("ac_read", "Read a document", {"type": "object"}, lambda: None,
                MCPToolAnnotations(read_only=True)),
        MCPTool("ac_click", "Click a document", {"type": "object"}, lambda: None),
        MCPTool("ac_agent_target", "Register host target", {"type": "object"}, lambda: None),
    ]


def test_search_returns_summary_not_full_schema():
    from je_auto_control.utils.mcp_server.discovery import ToolIndex
    index = ToolIndex(catalog())
    results = index.search("document")
    assert {item["name"] for item in results} == {"ac_read", "ac_click"}
    assert all("inputSchema" not in item and "capability" in item and "category" in item for item in results)


def test_only_authorized_tools_are_indexed():
    from je_auto_control.utils.mcp_server.discovery import ToolIndex
    index = ToolIndex(catalog())
    with authorization_scope(AuthorizationContext("reader", "viewer")):
        assert [item["name"] for item in index.search("")] == ["ac_read"]
        with pytest.raises(ToolDiscoveryError, match="not available"):
            index.get_schema("ac_click")
    with authorization_scope(AuthorizationContext("driver", "operator")):
        assert "ac_agent_target" not in {item["name"] for item in index.search("")}


def test_schema_lookup_is_single_tool_and_detached():
    from je_auto_control.utils.mcp_server.discovery import ToolIndex
    tools = catalog()
    index = ToolIndex(tools)
    tools[0].input_schema["changed"] = True
    descriptor = index.get_schema("ac_read")
    assert descriptor["name"] == "ac_read" and "changed" not in descriptor["inputSchema"]
    descriptor["inputSchema"]["corrupt"] = True
    assert "corrupt" not in index.get_schema("ac_read")["inputSchema"]
    assert index.snapshot_id == ToolIndex(catalog()).snapshot_id
    assert index.snapshot_id != ToolIndex(tools).snapshot_id


@pytest.mark.parametrize("query,limit", [(None, 1), ("x" * 257, 1), ("", 0), ("", 51), ("", True)])
def test_search_rejects_unbounded_inputs(query, limit):
    from je_auto_control.utils.mcp_server.discovery import ToolIndex
    with pytest.raises(ToolDiscoveryError, match="query|limit"):
        ToolIndex(catalog()).search(query, limit=limit)


def test_mcp_discovery_uses_the_server_registry_including_plugins():
    from je_auto_control.utils.mcp_server.server import MCPServer
    from je_auto_control.utils.mcp_server.tools._discovery import discovery_tools
    server = MCPServer(tools=discovery_tools() + catalog())
    server.register_tool(MCPTool("fixture_plugin", "Special fixture", {}, lambda: None))
    reply = json.loads(server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "ac_mcp_tool_search", "arguments": {"query": "fixture"}}})))
    result = json.loads(reply["result"]["content"][0]["text"])
    assert [item["name"] for item in result] == ["fixture_plugin"]
    server.unregister_tool("fixture_plugin")
    reply = json.loads(server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "ac_mcp_tool_schema", "arguments": {"name": "fixture_plugin"}}})))
    assert reply["result"]["isError"] is True


def test_public_discovery_and_executor_share_the_api():
    import je_auto_control as ac
    from je_auto_control.api import core
    assert core.search_mcp_tools is ac.search_mcp_tools
    result = ac.executor.execute_one("AC_mcp_tool_search", {"query": "ac_mcp_tool_schema"})
    assert result[0]["name"] == "ac_mcp_tool_schema"
    descriptor = ac.executor.execute_one("AC_mcp_tool_schema", {"name": "ac_mcp_tool_search"})
    assert descriptor["name"] == "ac_mcp_tool_search"


def test_readonly_registry_filters_both_search_and_schema():
    from je_auto_control.utils.mcp_server.discovery import search_mcp_tools, get_mcp_tool_schema
    assert search_mcp_tools("ac_click_mouse", read_only=True) == []
    with pytest.raises(ToolDiscoveryError, match="not available"):
        get_mcp_tool_schema("ac_click_mouse", read_only=True)


def test_queries_refresh_a_store_backed_role(tmp_path):
    from je_auto_control.utils.mcp_server.discovery import ToolIndex
    from je_auto_control.utils.rbac.users import UserStore
    from je_auto_control.utils.rbac.authorization import AuthorizationError
    store = UserStore(tmp_path / "users.json")
    store.add_user(user_id="driver", display_name="Driver", role="operator")
    index = ToolIndex(catalog())
    with authorization_scope(AuthorizationContext("driver", "admin", store_path=str(store.path))):
        assert "ac_agent_target" not in {item["name"] for item in index.search("")}
        store.remove_user("driver")
        with pytest.raises(AuthorizationError):
            index.search("")
        with pytest.raises(AuthorizationError):
            index.get_schema("ac_read")


def test_schema_discovery_does_not_bypass_the_argument_root_policy(tmp_path):
    from je_auto_control.utils.mcp_server.server import MCPServer
    from je_auto_control.utils.mcp_server.tools._discovery import discovery_tools
    from je_auto_control.utils.mcp_server._argument_policy import ArgumentPolicy
    from je_auto_control.utils.path_guard.policy import PathPolicy
    calls = []
    tool = MCPTool("fixture_read", "Read a rooted path", {"type": "object", "properties": {
        "path": {"type": "string", "format": "path"}}}, lambda path: calls.append(path),
        MCPToolAnnotations(read_only=True))
    root = tmp_path / "allowed"
    root.mkdir()
    server = MCPServer(tools=discovery_tools() + [tool])
    server.argument_policy = ArgumentPolicy(PathPolicy((str(root),)))
    for name, arguments, error in (("ac_mcp_tool_schema", {"name": "fixture_read"}, False),
                                   ("fixture_read", {"path": str(tmp_path / "outside.txt")}, True)):
        reply = json.loads(server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": name, "arguments": arguments}})))
        assert reply["result"]["isError"] is error
    assert calls == []
