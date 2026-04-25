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
    MCPContent, MCPTool, MCPToolAnnotations, build_default_tool_registry,
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


def test_tool_descriptor_includes_annotations():
    annotations = MCPToolAnnotations(title="Echo", read_only=True,
                                      idempotent=True)
    tool = MCPTool(
        name="echo", description="echo",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: "ok",
        annotations=annotations,
    )
    descriptor = tool.to_descriptor()
    assert descriptor["annotations"] == {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
        "title": "Echo",
    }


def test_read_only_annotation_forces_destructive_false():
    """Per spec, destructiveHint is meaningful only if readOnlyHint is false."""
    annotations = MCPToolAnnotations(read_only=True, destructive=True)
    assert annotations.to_dict()["destructiveHint"] is False


def test_default_tool_registry_marks_safe_tools_read_only():
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    assert by_name["ac_get_mouse_position"].annotations.read_only is True
    assert by_name["ac_screen_size"].annotations.read_only is True
    assert by_name["ac_list_action_commands"].annotations.read_only is True
    # Side-effecting tools must NOT claim read-only.
    assert by_name["ac_click_mouse"].annotations.read_only is False
    assert by_name["ac_type_text"].annotations.read_only is False


def test_read_only_registry_drops_destructive_tools():
    safe = build_default_tool_registry(read_only=True)
    assert safe, "expected at least one read-only tool"
    assert all(tool.annotations.read_only for tool in safe)
    safe_names = {tool.name for tool in safe}
    assert "ac_click_mouse" not in safe_names
    assert "ac_type_text" not in safe_names
    assert "ac_execute_actions" not in safe_names
    # Pure observers must survive.
    assert {"ac_get_mouse_position", "ac_screen_size",
            "ac_list_action_commands"}.issubset(safe_names)


def test_read_only_env_var_is_honored(monkeypatch):
    monkeypatch.setenv("JE_AUTOCONTROL_MCP_READONLY", "1")
    safe = build_default_tool_registry()
    assert all(tool.annotations.read_only for tool in safe)


def test_read_only_env_var_disabled_when_unset(monkeypatch):
    monkeypatch.delenv("JE_AUTOCONTROL_MCP_READONLY", raising=False)
    full = build_default_tool_registry()
    assert any(not tool.annotations.read_only for tool in full)


def test_mcp_content_image_block_serialises_to_mcp_shape():
    content = MCPContent.image_block("AAAA", mime_type="image/jpeg")
    assert content.to_dict() == {
        "type": "image", "data": "AAAA", "mimeType": "image/jpeg",
    }


def test_mcp_content_text_block_serialises_to_mcp_shape():
    assert MCPContent.text_block("hello").to_dict() == {
        "type": "text", "text": "hello",
    }


def test_tools_call_returns_image_content_when_handler_yields_image():
    image_payload = MCPContent.image_block("ZmFrZQ==")  # base64 "fake"
    tool = MCPTool(
        name="snap", description="snap",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: image_payload,
    )
    server = MCPServer(tools=[tool])
    response = _decode(server.handle_line(_request("tools/call", params={
        "name": "snap", "arguments": {},
    })))
    blocks = response["result"]["content"]
    assert blocks == [{"type": "image", "data": "ZmFrZQ==",
                       "mimeType": "image/png"}]


def test_tools_call_passes_through_multi_content_lists():
    payload = [MCPContent.image_block("Zm9v"),
               MCPContent.text_block("saved: /tmp/x.png")]
    tool = MCPTool(
        name="snap2", description="snap2",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: payload,
    )
    server = MCPServer(tools=[tool])
    response = _decode(server.handle_line(_request("tools/call", params={
        "name": "snap2", "arguments": {},
    })))
    blocks = response["result"]["content"]
    assert len(blocks) == 2
    assert blocks[0]["type"] == "image"
    assert blocks[1]["type"] == "text"


def test_recording_tools_present_in_default_registry():
    names = {tool.name for tool in build_default_tool_registry()}
    assert {
        "ac_record_start", "ac_record_stop",
        "ac_read_action_file", "ac_write_action_file",
        "ac_trim_actions", "ac_adjust_delays", "ac_scale_coordinates",
    }.issubset(names)


def test_trim_actions_tool_returns_subset(tmp_path):
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    actions = [["AC_a", {}], ["AC_b", {}], ["AC_c", {}], ["AC_d", {}]]
    trimmed = by_name["ac_trim_actions"].invoke(
        {"actions": actions, "start": 1, "end": 3}
    )
    assert trimmed == [["AC_b", {}], ["AC_c", {}]]


def test_scale_coordinates_tool_scales_x_y():
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    actions = [["AC_click_mouse", {"x": 100, "y": 200,
                                     "mouse_keycode": "mouse_left"}]]
    scaled = by_name["ac_scale_coordinates"].invoke(
        {"actions": actions, "x_factor": 2.0, "y_factor": 0.5}
    )
    assert scaled[0][1]["x"] == 200
    assert scaled[0][1]["y"] == 100


def test_write_and_read_action_file_round_trip(tmp_path):
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    target = tmp_path / "actions.json"
    actions = [["AC_click_mouse", {"mouse_keycode": "mouse_left"}]]
    saved_path = by_name["ac_write_action_file"].invoke(
        {"file_path": str(target), "actions": actions}
    )
    assert target.exists()
    loaded = by_name["ac_read_action_file"].invoke({"file_path": saved_path})
    assert loaded == actions


def test_drag_and_send_tools_present_in_default_registry():
    names = {tool.name for tool in build_default_tool_registry()}
    assert {"ac_drag", "ac_send_key_to_window",
            "ac_send_mouse_to_window"}.issubset(names)


def test_drag_tool_calls_press_move_release_in_order(monkeypatch):
    """ac_drag must press at the start, move, then release at the end."""
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    calls = []

    def fake_set(x, y):
        calls.append(("set", int(x), int(y)))
        return (int(x), int(y))

    def fake_press(keycode, x=None, y=None):
        calls.append(("press", keycode, x, y))
        return (keycode, x, y)

    def fake_release(keycode, x=None, y=None):
        calls.append(("release", keycode, x, y))
        return (keycode, x, y)

    import je_auto_control.wrapper.auto_control_mouse as mouse_module
    monkeypatch.setattr(mouse_module, "set_mouse_position", fake_set)
    monkeypatch.setattr(mouse_module, "press_mouse", fake_press)
    monkeypatch.setattr(mouse_module, "release_mouse", fake_release)

    result = by_name["ac_drag"].invoke({
        "start_x": 10, "start_y": 20,
        "end_x": 100, "end_y": 200,
        "mouse_keycode": "mouse_left",
    })
    assert result == [100, 200]
    sequence = [step[0] for step in calls]
    # set start → press → set end → release
    assert sequence == ["set", "press", "set", "release"]
    assert calls[0][1:] == (10, 20)
    assert calls[2][1:] == (100, 200)


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
