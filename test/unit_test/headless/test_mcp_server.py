"""Headless tests for the MCP stdio server.

These tests exercise the JSON-RPC dispatcher directly and via an
in-memory pipe so no real stdin/stdout, no Qt, and no platform
backends are needed.
"""
import io
import json
from typing import Any, Dict, List

from je_auto_control.utils.mcp_server.server import (
    PROTOCOL_VERSION, MCPServer,
)
from je_auto_control.utils.mcp_server.tools import (
    MCPTool, build_default_tool_registry,
)


def _request(method: str, msg_id: int = 1,
             params: Dict[str, Any] = None) -> str:
    payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id,
                               "method": method}
    if params is not None:
        payload["params"] = params
    return json.dumps(payload)


def _decode(line: str) -> Dict[str, Any]:
    return json.loads(line)


def test_initialize_echoes_protocol_version():
    server = MCPServer(tools=[])
    response = _decode(server.handle_line(_request("initialize", params={
        "protocolVersion": "2024-11-05",
        "capabilities": {}, "clientInfo": {"name": "pytest"},
    })))
    result = response["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "je_auto_control"
    assert "tools" in result["capabilities"]


def test_initialize_falls_back_to_server_default():
    server = MCPServer(tools=[])
    response = _decode(server.handle_line(
        _request("initialize", params={})
    ))
    assert response["result"]["protocolVersion"] == PROTOCOL_VERSION


def test_tools_list_returns_registered_tool_descriptors():
    tool = MCPTool(
        name="echo", description="echo args back",
        input_schema={"type": "object", "properties": {}},
        handler=lambda **kwargs: kwargs,
    )
    server = MCPServer(tools=[tool])
    response = _decode(server.handle_line(_request("tools/list")))
    descriptors = response["result"]["tools"]
    assert len(descriptors) == 1
    assert descriptors[0]["name"] == "echo"
    assert descriptors[0]["inputSchema"] == {"type": "object",
                                              "properties": {}}


def test_tools_call_invokes_handler_and_serialises_result():
    tool = MCPTool(
        name="add", description="add two ints",
        input_schema={
            "type": "object",
            "properties": {"a": {"type": "integer"},
                            "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
        handler=lambda a, b: a + b,
    )
    server = MCPServer(tools=[tool])
    response = _decode(server.handle_line(_request("tools/call", params={
        "name": "add", "arguments": {"a": 2, "b": 3},
    })))
    result = response["result"]
    assert result["isError"] is False
    assert result["content"][0]["text"] == "5"


def test_tools_call_unknown_tool_reports_error():
    server = MCPServer(tools=[])
    response = _decode(server.handle_line(_request("tools/call", params={
        "name": "missing", "arguments": {},
    })))
    assert response["error"]["code"] == -32602
    assert "Unknown tool" in response["error"]["message"]


def test_tools_call_handler_exception_returns_is_error():
    def boom(**_kwargs):
        raise ValueError("nope")

    tool = MCPTool(name="boom", description="fail",
                   input_schema={"type": "object", "properties": {}},
                   handler=boom)
    server = MCPServer(tools=[tool])
    response = _decode(server.handle_line(_request("tools/call", params={
        "name": "boom", "arguments": {},
    })))
    result = response["result"]
    assert result["isError"] is True
    assert "ValueError" in result["content"][0]["text"]


def test_unknown_method_returns_method_not_found():
    server = MCPServer(tools=[])
    response = _decode(server.handle_line(_request("does/not/exist")))
    assert response["error"]["code"] == -32601


def test_parse_error_returned_for_bad_json():
    server = MCPServer(tools=[])
    response = _decode(server.handle_line("{not json"))
    assert response["error"]["code"] == -32700
    assert response["id"] is None


def test_notification_initialized_sets_state_and_returns_none():
    server = MCPServer(tools=[])
    notification = json.dumps({"jsonrpc": "2.0",
                                "method": "notifications/initialized"})
    assert server.handle_line(notification) is None
    assert server._initialized is True  # noqa: SLF001  # reason: white-box check


def test_serve_stdio_processes_messages_until_eof():
    tool = MCPTool(name="ping_tool", description="ping",
                   input_schema={"type": "object", "properties": {}},
                   handler=lambda: "pong")
    server = MCPServer(tools=[tool])
    stdin_lines: List[str] = [
        _request("initialize", msg_id=1, params={"protocolVersion": "x"}),
        json.dumps({"jsonrpc": "2.0",
                    "method": "notifications/initialized"}),
        _request("tools/call", msg_id=2,
                  params={"name": "ping_tool", "arguments": {}}),
    ]
    stdin = io.StringIO("\n".join(stdin_lines) + "\n")
    stdout = io.StringIO()
    server.serve_stdio(stdin=stdin, stdout=stdout)
    out_lines = [line for line in stdout.getvalue().splitlines() if line]
    assert len(out_lines) == 2  # initialize + tools/call (notification has no reply)
    last = _decode(out_lines[-1])
    assert last["result"]["content"][0]["text"] == "pong"


def test_default_registry_lists_core_automation_tools():
    names = {tool.name for tool in build_default_tool_registry()}
    expected = {
        "ac_click_mouse", "ac_get_mouse_position", "ac_set_mouse_position",
        "ac_type_text", "ac_press_key", "ac_hotkey",
        "ac_screen_size", "ac_screenshot",
        "ac_locate_image_center", "ac_locate_text",
        "ac_get_clipboard", "ac_set_clipboard",
        "ac_execute_actions", "ac_list_action_commands",
    }
    assert expected.issubset(names)
