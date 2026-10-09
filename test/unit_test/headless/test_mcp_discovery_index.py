"""The MCP tool search index: summaries first, one schema on request (plan G1).

Every tool here is a fake whose handler only records that it ran, so nothing
touches the desktop; the registry-wide checks build descriptors and never
invoke a handler.
"""
import json

import pytest

from je_auto_control.utils.mcp_server.discovery import (
    DEFAULT_SEARCH_LIMIT, MAX_SEARCH_LIMIT, ToolDiscoveryError, ToolIndex,
    ToolSummary,
)
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import (
    MCPTool, MCPToolAnnotations, build_default_tool_registry,
)
from je_auto_control.utils.mcp_server.tools._base import MCPToolDescriptor
from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, authorization_scope,
)
from je_auto_control.utils.rbac.users import Capability

_READ = MCPToolAnnotations(read_only=True, idempotent=True)


def _tool(name, description, *, read_only=False, category="", properties=None):
    return MCPTool(
        name=name, description=description,
        input_schema={"type": "object", "properties": properties or {"value": {"type": "string"}}},
        handler=lambda **kwargs: {"ran": name, **kwargs},
        annotations=_READ if read_only else MCPToolAnnotations(),
        category=category,
    )


def _fake_tools():
    return [
        _tool("fx_click", "Click a mouse button at a point. Long tail that is not the summary.",
              category="mouse"),
        _tool("fx_where", "Return the mouse pointer position.", read_only=True, category="mouse"),
        _tool("fx_shot", "Capture the screen to a PNG file.", read_only=True, category="screen",
              properties={"file_path": {"type": "string", "format": "path"}}),
        _tool("fx_type", "Type text with the keyboard.", category="keyboard"),
        _tool("plugin_fx_extra", "A plugin command."),
    ]


def _progressive(tools=None, **kwargs):
    return MCPServer(tools=_fake_tools() if tools is None else tools,
                     tool_mode="progressive", **kwargs)


def _call(server, name, arguments=None, msg_id=1):
    reply = json.loads(server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}}})))
    return reply


def _payload(reply):
    result = reply["result"]
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


# --- the index ----------------------------------------------------------------


def test_search_returns_summary_not_full_schema():
    index = ToolIndex(_fake_tools())
    found = index.search("mouse")
    assert all(isinstance(item, ToolSummary) for item in found)
    search_results = [item.to_dict() for item in found]
    assert [item["name"] for item in search_results] == ["fx_click", "fx_where"]
    assert 'inputSchema' not in search_results[0]
    assert set(search_results[0]) == {
        "name", "summary", "category", "capability", "read_only", "takes_paths"}
    # The summary is the first sentence, not the whole description.
    assert search_results[0]["summary"] == "Click a mouse button at a point."


def test_summary_carries_typed_category_and_capability():
    index = ToolIndex(_fake_tools())
    by_name = {item.name: item for item in index.search("", limit=MAX_SEARCH_LIMIT)}
    assert by_name["fx_click"].capability == Capability.DRIVE_INPUT
    assert by_name["fx_where"].capability == Capability.READ_SCREEN
    assert by_name["fx_shot"].takes_paths is True
    assert by_name["fx_click"].takes_paths is False
    assert by_name["plugin_fx_extra"].category == "plugin"
    assert index.categories() == {"mouse": 2, "screen": 1, "keyboard": 1, "plugin": 1}


def test_search_filters_are_typed():
    index = ToolIndex(_fake_tools())
    assert [item.name for item in index.search("", category="screen")] == ["fx_shot"]
    assert [item.name for item in index.search("", capability=Capability.READ_SCREEN)] == [
        "fx_where", "fx_shot"]
    with pytest.raises(ToolDiscoveryError, match="unknown category"):
        index.search("", category="nope")
    with pytest.raises(ToolDiscoveryError, match="unknown capability"):
        index.search("", capability="root")


@pytest.mark.parametrize("limit", [0, -1, MAX_SEARCH_LIMIT + 1, True, "5", 2.5])
def test_limit_is_bounded(limit):
    index = ToolIndex(_fake_tools())
    with pytest.raises(ToolDiscoveryError):
        index.search("mouse", limit=limit)


def test_default_limit_caps_the_reply():
    tools = [_tool(f"fx_many_{number}", "Many mouse tools.") for number in range(40)]
    index = ToolIndex(tools)
    assert len(index.search("mouse")) == DEFAULT_SEARCH_LIMIT
    assert len(index.search("mouse", limit=MAX_SEARCH_LIMIT)) == 40


def test_query_is_bounded_and_must_be_text():
    index = ToolIndex(_fake_tools())
    with pytest.raises(ToolDiscoveryError):
        index.search("x" * 10_000)
    with pytest.raises(ToolDiscoveryError):
        index.search(None)


def test_an_exact_name_ranks_first():
    index = ToolIndex(_fake_tools() + [_tool("fx_type_fast", "Type text quickly.")])
    assert index.search("fx_type")[0].name == "fx_type"


def test_schema_lookup_is_single_tool():
    index = ToolIndex(_fake_tools())
    selected_tool = "fx_shot"
    schema_reply = index.get_schema(selected_tool)
    assert isinstance(schema_reply, MCPToolDescriptor)
    assert schema_reply.name == selected_tool
    assert schema_reply.to_dict() == _fake_tools()[2].to_descriptor()
    with pytest.raises(ToolDiscoveryError):
        index.get_schema("fx_missing")


# --- the registry is the single source -----------------------------------------


def test_only_authorized_tools_are_indexed():
    server = _progressive()
    hidden_tool = "fx_click"
    with authorization_scope(AuthorizationContext(user_id="v", role="viewer")):
        search_names = [item.name for item in server.disclosure.index().search(
            "", limit=MAX_SEARCH_LIMIT)]
        assert hidden_tool not in search_names
        assert "fx_where" in search_names
        index = server.disclosure.index()
        with pytest.raises(ToolDiscoveryError):
            index.get_schema(hidden_tool)
    # No user store, no RBAC: the same server indexes everything.
    assert hidden_tool in [item.name for item in server.disclosure.index().search(
        "", limit=MAX_SEARCH_LIMIT)]


def test_read_only_mode_indexes_no_mutating_tool():
    server = _progressive(read_only=True)
    names = [item.name for item in server.disclosure.index().search("", limit=MAX_SEARCH_LIMIT)]
    assert names == ["fx_where", "fx_shot"]


def test_index_snapshot_follows_plugin_changes():
    server = _progressive()
    before = server.disclosure.index()
    assert server.disclosure.index() is before  # cached while nothing changed
    server.register_tool(_tool("plugin_fx_late", "Arrived later."))
    after = server.disclosure.index()
    assert after.version > before.version
    assert [item.name for item in after.search("later")] == ["plugin_fx_late"]
    assert before.search("later") == []  # the old snapshot is not mutated
    server.unregister_tool("plugin_fx_late")
    assert server.disclosure.index().search("later") == []


def test_discover_and_schema_tools_go_through_the_dispatcher():
    server = _progressive()
    found = _payload(_call(server, "ac_tools_search", {"query": "mouse", "limit": 1}))
    assert [item["name"] for item in found["tools"]] == ["fx_click"]
    assert found["total"] == 2
    assert found["truncated"] is True
    assert "inputSchema" not in found["tools"][0]
    assert found["tools"][0]["enabled"] is False
    described = _payload(_call(server, "ac_tools_schema", {"name": "fx_shot"}))
    assert described == _fake_tools()[2].to_descriptor()


def test_discover_tool_rejects_bad_input_as_a_tool_error():
    server = _progressive()
    for arguments in ({"query": "mouse", "limit": 9999}, {"query": "mouse", "limit": "3"},
                      {"query": 5}, {"category": "nope"}, {"surprise": 1}):
        result = _call(server, "ac_tools_search", arguments)["result"]
        assert result["isError"] is True, arguments
    assert _call(server, "ac_tools_schema", {"name": "fx_missing"})["result"]["isError"] is True


# --- the real registry ----------------------------------------------------------


def test_every_default_tool_has_a_category_and_the_descriptor_is_unchanged():
    tools = build_default_tool_registry(read_only=False, aliases=True)
    assert all(tool.category for tool in tools)
    assert all("category" not in tool.to_descriptor() for tool in tools)
    index = ToolIndex(tools)
    assert len(index) == len(tools)
    assert "mouse" in index.categories()


def test_search_over_the_real_registry_is_small():
    tools = build_default_tool_registry(read_only=False, aliases=False)
    index = ToolIndex(tools)
    reply = json.dumps([item.to_dict() for item in index.search("screenshot")])
    full = json.dumps([tool.to_descriptor() for tool in tools])
    assert index.search("screenshot")
    assert len(reply) * 20 < len(full)
