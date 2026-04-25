"""Headless tests for the MCP stdio server.

These tests exercise the JSON-RPC dispatcher directly and via an
in-memory pipe so no real stdin/stdout, no Qt, and no platform
backends are needed.
"""
import io
import json
import os
import threading
from typing import Any, Dict, List

from je_auto_control.utils.mcp_server.context import (
    OperationCancelledError, ToolCallContext,
)
from je_auto_control.utils.mcp_server.prompts import (
    MCPPrompt, MCPPromptArgument, StaticPromptProvider,
    default_prompt_catalogue,
)
from je_auto_control.utils.mcp_server.resources import (
    ChainProvider, FileSystemProvider, MCPResource, ResourceProvider,
)
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
    responses = [_decode(line) for line in out_lines
                  if '"id":' in line and '"method"' not in line]
    assert len(responses) == 2  # initialize + tools/call
    assert responses[-1]["result"]["content"][0]["text"] == "pong"


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


def test_semantic_locator_tools_present_in_default_registry():
    names = {tool.name for tool in build_default_tool_registry()}
    assert {"ac_a11y_list", "ac_a11y_find", "ac_a11y_click",
            "ac_vlm_locate", "ac_vlm_click"}.issubset(names)


def test_a11y_find_tool_returns_none_when_backend_has_no_match(monkeypatch):
    """Find delegates to the headless API; null result must round-trip."""
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    import je_auto_control.utils.accessibility.accessibility_api as api
    monkeypatch.setattr(api, "find_accessibility_element",
                        lambda **_kwargs: None)
    assert by_name["ac_a11y_find"].invoke({"name": "ghost"}) is None


def test_automation_tools_present_in_default_registry():
    names = {tool.name for tool in build_default_tool_registry()}
    assert {
        "ac_scheduler_add_job", "ac_scheduler_remove_job",
        "ac_scheduler_list_jobs", "ac_scheduler_start", "ac_scheduler_stop",
        "ac_trigger_add", "ac_trigger_remove", "ac_trigger_list",
        "ac_trigger_start", "ac_trigger_stop",
        "ac_hotkey_bind", "ac_hotkey_unbind", "ac_hotkey_list",
        "ac_hotkey_daemon_start", "ac_hotkey_daemon_stop",
    }.issubset(names)


def test_scheduler_add_job_round_trips_through_default_scheduler(tmp_path):
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    script = tmp_path / "noop.json"
    script.write_text("[]", encoding="utf-8")
    record = by_name["ac_scheduler_add_job"].invoke({
        "script_path": str(script), "interval_seconds": 60.0,
        "repeat": False, "job_id": "test_mcp_job",
    })
    try:
        assert record["job_id"] == "test_mcp_job"
        assert record["interval_seconds"] == 60.0
        listed = {job["job_id"] for job in
                   by_name["ac_scheduler_list_jobs"].invoke({})}
        assert "test_mcp_job" in listed
    finally:
        by_name["ac_scheduler_remove_job"].invoke({"job_id": "test_mcp_job"})


def test_trigger_add_image_kind_records_trigger(tmp_path):
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    from je_auto_control.utils.triggers.trigger_engine import default_trigger_engine
    script = tmp_path / "noop.json"
    script.write_text("[]", encoding="utf-8")
    image = tmp_path / "hit.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    record = by_name["ac_trigger_add"].invoke({
        "kind": "image", "script_path": str(script),
        "image_path": str(image), "threshold": 0.5,
    })
    try:
        assert record["type"] == "ImageAppearsTrigger"
        assert any(t.trigger_id == record["trigger_id"]
                   for t in default_trigger_engine.list_triggers())
    finally:
        by_name["ac_trigger_remove"].invoke(
            {"trigger_id": record["trigger_id"]}
        )


def test_trigger_add_rejects_unknown_kind(tmp_path):
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    script = tmp_path / "noop.json"
    script.write_text("[]", encoding="utf-8")
    import pytest
    with pytest.raises(ValueError):
        by_name["ac_trigger_add"].invoke({
            "kind": "telepathy", "script_path": str(script),
        })


class _StaticProvider(ResourceProvider):
    """Test double — exposes one fixed resource."""

    def __init__(self, resource: MCPResource, body: str) -> None:
        self._resource = resource
        self._body = body

    def list(self):
        return [self._resource]

    def read(self, uri):
        if uri != self._resource.uri:
            return None
        return {"uri": uri, "mimeType": self._resource.mime_type or "text/plain",
                "text": self._body}


def test_initialize_advertises_resources_capability():
    server = MCPServer(tools=[], resource_provider=ChainProvider([]))
    response = _decode(server.handle_line(_request("initialize", params={})))
    assert "resources" in response["result"]["capabilities"]


def test_resources_list_returns_provider_descriptors():
    resource = MCPResource(uri="autocontrol://demo",
                            name="demo",
                            description="static demo",
                            mime_type="text/plain")
    server = MCPServer(tools=[],
                       resource_provider=_StaticProvider(resource, "hi"))
    response = _decode(server.handle_line(_request("resources/list")))
    descriptors = response["result"]["resources"]
    assert descriptors == [{
        "uri": "autocontrol://demo", "name": "demo",
        "description": "static demo", "mimeType": "text/plain",
    }]


def test_resources_read_returns_provider_content():
    resource = MCPResource(uri="autocontrol://demo", name="demo",
                            mime_type="text/plain")
    server = MCPServer(tools=[],
                       resource_provider=_StaticProvider(resource, "hello"))
    response = _decode(server.handle_line(_request("resources/read", params={
        "uri": "autocontrol://demo",
    })))
    contents = response["result"]["contents"]
    assert contents == [{"uri": "autocontrol://demo",
                          "mimeType": "text/plain", "text": "hello"}]


def test_resources_read_unknown_uri_returns_invalid_params():
    server = MCPServer(tools=[], resource_provider=ChainProvider([]))
    response = _decode(server.handle_line(_request("resources/read", params={
        "uri": "autocontrol://missing",
    })))
    assert response["error"]["code"] == -32602
    assert "Unknown resource" in response["error"]["message"]


def test_filesystem_provider_lists_action_files(tmp_path):
    (tmp_path / "alpha.json").write_text("[]", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("nope", encoding="utf-8")
    (tmp_path / "beta.json").write_text("[]", encoding="utf-8")
    provider = FileSystemProvider(root=str(tmp_path))
    listed = provider.list()
    names = sorted(item.name for item in listed)
    assert names == ["alpha.json", "beta.json"]
    body = provider.read(listed[0].uri)
    assert body is not None
    assert body["mimeType"] == "application/json"


def test_filesystem_provider_rejects_path_traversal(tmp_path):
    (tmp_path / "alpha.json").write_text("[]", encoding="utf-8")
    provider = FileSystemProvider(root=str(tmp_path))
    assert provider.read("autocontrol://files/../etc/passwd") is None
    assert provider.read("autocontrol://files/.hidden") is None


def test_initialize_advertises_prompts_capability():
    server = MCPServer(tools=[],
                       prompt_provider=StaticPromptProvider([]))
    response = _decode(server.handle_line(_request("initialize", params={})))
    assert "prompts" in response["result"]["capabilities"]


def test_prompts_list_returns_descriptors():
    prompt = MCPPrompt(
        name="hello", description="say hi",
        arguments=[MCPPromptArgument("name", required=True)],
        render=lambda args: f"hi {args['name']}",
    )
    server = MCPServer(tools=[],
                       prompt_provider=StaticPromptProvider([prompt]))
    response = _decode(server.handle_line(_request("prompts/list")))
    descriptors = response["result"]["prompts"]
    assert descriptors == [{
        "name": "hello", "description": "say hi",
        "arguments": [{"name": "name", "required": True}],
    }]


def test_prompts_get_renders_message_with_arguments():
    prompt = MCPPrompt(
        name="hello", description="say hi",
        arguments=[MCPPromptArgument("name", required=True)],
        render=lambda args: f"hi {args['name']}",
    )
    server = MCPServer(tools=[],
                       prompt_provider=StaticPromptProvider([prompt]))
    response = _decode(server.handle_line(_request("prompts/get", params={
        "name": "hello", "arguments": {"name": "Jeff"},
    })))
    payload = response["result"]
    assert payload["messages"][0]["content"]["text"] == "hi Jeff"


def test_prompts_get_unknown_name_returns_error():
    server = MCPServer(tools=[],
                       prompt_provider=StaticPromptProvider([]))
    response = _decode(server.handle_line(_request("prompts/get", params={
        "name": "missing",
    })))
    assert response["error"]["code"] == -32602
    assert "Unknown prompt" in response["error"]["message"]


def test_prompts_get_missing_required_arg_returns_error():
    prompt = MCPPrompt(
        name="hello", description="say hi",
        arguments=[MCPPromptArgument("name", required=True)],
        render=lambda args: f"hi {args['name']}",
    )
    server = MCPServer(tools=[],
                       prompt_provider=StaticPromptProvider([prompt]))
    response = _decode(server.handle_line(_request("prompts/get", params={
        "name": "hello", "arguments": {},
    })))
    assert response["error"]["code"] == -32602


def test_default_prompt_catalogue_has_core_templates():
    names = {prompt.name for prompt in default_prompt_catalogue()}
    assert {"automate_ui_task", "record_and_generalize",
            "compare_screenshots", "find_widget",
            "explain_action_file"}.issubset(names)


def test_progress_notifications_are_sent_when_token_provided():
    captured = []

    def slow_handler(seconds, ctx):
        del seconds
        ctx.progress(0.0, total=1.0, message="starting")
        ctx.progress(1.0, total=1.0, message="done")
        return "ok"

    tool = MCPTool(
        name="slow", description="slow",
        input_schema={"type": "object", "properties": {
            "seconds": {"type": "number"}}},
        handler=slow_handler,
    )
    server = MCPServer(tools=[tool])
    server.set_notifier(lambda method, params: captured.append((method, params)))
    response = _decode(server.handle_line(_request("tools/call", params={
        "name": "slow", "arguments": {"seconds": 0.0},
        "_meta": {"progressToken": "tok-1"},
    })))
    assert response["result"]["isError"] is False
    methods = [event[0] for event in captured]
    assert methods == ["notifications/progress",
                       "notifications/progress"]
    assert captured[0][1] == {"progressToken": "tok-1",
                               "progress": 0.0, "total": 1.0,
                               "message": "starting"}


def test_progress_is_no_op_without_token():
    captured = []

    def handler(ctx):
        ctx.progress(0.5, total=1.0)
        return "ok"

    tool = MCPTool(
        name="silent", description="silent",
        input_schema={"type": "object", "properties": {}},
        handler=handler,
    )
    server = MCPServer(tools=[tool])
    server.set_notifier(lambda method, params: captured.append((method, params)))
    response = _decode(server.handle_line(_request("tools/call", params={
        "name": "silent", "arguments": {},
    })))
    assert response["result"]["isError"] is False
    assert captured == []


def test_cancellation_notification_sets_context_flag():
    started = threading.Event()
    proceed = threading.Event()
    seen_cancel = []

    def slow_handler(ctx):
        started.set()
        proceed.wait(timeout=2.0)
        seen_cancel.append(ctx.cancelled)
        ctx.check_cancelled()
        return "ok"

    tool = MCPTool(
        name="cancellable", description="cancellable",
        input_schema={"type": "object", "properties": {}},
        handler=slow_handler,
    )
    server = MCPServer(tools=[tool])

    response_holder = {}

    def run_call():
        response_holder["raw"] = server.handle_line(_request(
            "tools/call", msg_id=42,
            params={"name": "cancellable", "arguments": {}},
        ))

    thread = threading.Thread(target=run_call)
    thread.start()
    assert started.wait(timeout=1.0)
    server.handle_line(json.dumps({
        "jsonrpc": "2.0", "method": "notifications/cancelled",
        "params": {"requestId": 42, "reason": "user clicked stop"},
    }))
    proceed.set()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert seen_cancel == [True]
    decoded = _decode(response_holder["raw"])
    assert decoded["error"]["code"] == -32800


def test_tool_call_context_check_cancelled_raises():
    ctx = ToolCallContext(request_id=7, progress_token=None)
    ctx.check_cancelled()  # not cancelled — no raise
    ctx.cancelled_event.set()
    try:
        ctx.check_cancelled()
    except OperationCancelledError as error:
        assert error.request_id == 7
    else:
        raise AssertionError("expected OperationCancelledError")


def test_request_sampling_round_trips_via_writer():
    """Tool calls sampling; we play the client and reply with a result."""
    captured_lines = []

    def handler(prompt, ctx):
        del ctx
        reply = server.request_sampling(
            messages=[{"role": "user",
                        "content": {"type": "text", "text": prompt}}],
            max_tokens=64,
        )
        return reply["content"]["text"]

    tool = MCPTool(
        name="ask_model", description="ask",
        input_schema={"type": "object", "properties": {
            "prompt": {"type": "string"}}, "required": ["prompt"]},
        handler=handler,
    )
    server = MCPServer(tools=[tool], concurrent_tools=True)
    server.set_writer(captured_lines.append)

    server.handle_line(_request("tools/call", msg_id=10, params={
        "name": "ask_model", "arguments": {"prompt": "ping?"},
    }))

    # The worker is now blocked on sampling; wait for the outbound request.
    deadline = threading.Event()
    for _ in range(200):
        if any('"sampling/createMessage"' in line for line in captured_lines):
            break
        deadline.wait(0.01)
    sampling_lines = [line for line in captured_lines
                       if '"sampling/createMessage"' in line]
    assert sampling_lines, "expected outbound sampling request"
    sampling_request = json.loads(sampling_lines[-1])
    assert sampling_request["method"] == "sampling/createMessage"
    sampling_id = sampling_request["id"]

    server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": sampling_id,
        "result": {"role": "assistant", "model": "test-model",
                    "content": {"type": "text", "text": "pong"}},
    }))

    for _ in range(200):
        if any('"id": 10' in line for line in captured_lines):
            break
        deadline.wait(0.01)
    final_lines = [line for line in captured_lines if '"id": 10' in line]
    assert final_lines, "expected tools/call reply on writer"
    final = json.loads(final_lines[-1])
    assert final["result"]["isError"] is False
    assert final["result"]["content"][0]["text"] == "pong"


def test_request_sampling_without_writer_raises():
    server = MCPServer(tools=[], concurrent_tools=True)
    try:
        server.request_sampling(messages=[
            {"role": "user", "content": {"type": "text", "text": "hi"}}
        ])
    except RuntimeError as error:
        assert "writer" in str(error)
    else:
        raise AssertionError("expected RuntimeError")


def test_initialize_advertises_sampling_capability():
    server = MCPServer(tools=[])
    response = _decode(server.handle_line(_request("initialize", params={})))
    assert "sampling" in response["result"]["capabilities"]


def test_tools_call_rejects_missing_required_field():
    tool = MCPTool(
        name="needs_x", description="needs x",
        input_schema={
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        },
        handler=lambda x: x * 2,
    )
    server = MCPServer(tools=[tool])
    response = _decode(server.handle_line(_request("tools/call", params={
        "name": "needs_x", "arguments": {},
    })))
    assert response["error"]["code"] == -32602
    assert "missing required property 'x'" in response["error"]["message"]


def test_tools_call_rejects_wrong_type():
    tool = MCPTool(
        name="needs_int", description="needs int",
        input_schema={
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        },
        handler=lambda x: x,
    )
    server = MCPServer(tools=[tool])
    response = _decode(server.handle_line(_request("tools/call", params={
        "name": "needs_int", "arguments": {"x": "not-int"},
    })))
    assert response["error"]["code"] == -32602
    assert "expected integer" in response["error"]["message"]


def test_tools_call_rejects_value_outside_enum():
    tool = MCPTool(
        name="enum_only", description="enum",
        input_schema={
            "type": "object",
            "properties": {"mode": {"type": "string",
                                     "enum": ["a", "b"]}},
            "required": ["mode"],
        },
        handler=lambda mode: mode,
    )
    server = MCPServer(tools=[tool])
    response = _decode(server.handle_line(_request("tools/call", params={
        "name": "enum_only", "arguments": {"mode": "c"},
    })))
    assert response["error"]["code"] == -32602


def test_tools_call_passes_valid_args():
    tool = MCPTool(
        name="adder", description="adder",
        input_schema={
            "type": "object",
            "properties": {"x": {"type": "integer"},
                            "y": {"type": "integer"}},
            "required": ["x", "y"],
        },
        handler=lambda x, y: x + y,
    )
    server = MCPServer(tools=[tool])
    response = _decode(server.handle_line(_request("tools/call", params={
        "name": "adder", "arguments": {"x": 1, "y": 2},
    })))
    assert response["result"]["content"][0]["text"] == "3"


def test_initialize_advertises_tools_list_changed():
    server = MCPServer(tools=[])
    response = _decode(server.handle_line(_request("initialize", params={})))
    assert response["result"]["capabilities"]["tools"]["listChanged"] is True


def test_register_tool_emits_list_changed_notification():
    captured = []
    server = MCPServer(tools=[])
    server.set_notifier(lambda method, params: captured.append((method, params)))
    new_tool = MCPTool(
        name="late", description="late",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: "ok",
    )
    server.register_tool(new_tool)
    assert ("notifications/tools/list_changed", {}) in captured


def test_unregister_tool_emits_list_changed_notification():
    tool = MCPTool(
        name="vanish", description="vanish",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: "ok",
    )
    captured = []
    server = MCPServer(tools=[tool])
    server.set_notifier(lambda method, params: captured.append((method, params)))
    assert server.unregister_tool("vanish") is True
    assert ("notifications/tools/list_changed", {}) in captured
    assert server.unregister_tool("vanish") is False


def test_make_plugin_tool_derives_schema_from_signature():
    from je_auto_control.utils.mcp_server.tools.plugin_tools import (
        make_plugin_tool,
    )

    def AC_demo(text: str, count: int = 1) -> str:  # noqa: N802
        """Demo plugin command."""
        return text * count

    tool = make_plugin_tool("AC_demo", AC_demo)
    assert tool.name == "plugin_ac_demo"
    assert tool.description.startswith("Demo plugin command")
    assert tool.input_schema["properties"]["text"] == {"type": "string"}
    assert tool.input_schema["properties"]["count"] == {"type": "integer"}
    assert tool.input_schema.get("required") == ["text"]


def test_register_plugin_tools_adds_to_server_and_notifies():
    from je_auto_control.utils.mcp_server.tools.plugin_tools import (
        register_plugin_tools,
    )

    def AC_one(value: str) -> str:  # noqa: N802
        return value.upper()

    captured = []
    server = MCPServer(tools=[])
    server.set_notifier(lambda method, params: captured.append((method, params)))
    names = register_plugin_tools(server, {"AC_one": AC_one})
    assert names == ["plugin_ac_one"]
    response = _decode(server.handle_line(_request("tools/call", params={
        "name": "plugin_ac_one", "arguments": {"value": "hi"},
    })))
    assert response["result"]["content"][0]["text"] == "HI"
    assert any(method == "notifications/tools/list_changed"
               for method, _ in captured)


def test_diff_screenshots_finds_changed_region(tmp_path):
    pytest = __import__("pytest")
    np = pytest.importorskip("numpy")
    pil_image = pytest.importorskip("PIL.Image")

    base = np.zeros((40, 60, 3), dtype="uint8")
    other = base.copy()
    other[10:20, 30:50, 0] = 255  # paint a 20x10 red rectangle

    path_a = tmp_path / "a.png"
    path_b = tmp_path / "b.png"
    pil_image.fromarray(base).save(path_a)
    pil_image.fromarray(other).save(path_b)

    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    result = by_name["ac_diff_screenshots"].invoke({
        "image_path_a": str(path_a),
        "image_path_b": str(path_b),
        "threshold": 10, "min_box_pixels": 4,
    })
    assert result["size"] == [60, 40]
    assert result["boxes"], "expected at least one diff region"
    # Bounding box should contain the painted rectangle (30..49, 10..19).
    box = result["boxes"][0]
    assert box[0] <= 30 and box[1] <= 10
    assert box[0] + box[2] >= 50
    assert box[1] + box[3] >= 20


def test_diff_screenshots_returns_no_boxes_when_identical(tmp_path):
    pytest = __import__("pytest")
    np = pytest.importorskip("numpy")
    pil_image = pytest.importorskip("PIL.Image")
    img = np.full((20, 20, 3), 200, dtype="uint8")
    path = tmp_path / "same.png"
    pil_image.fromarray(img).save(path)

    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    result = by_name["ac_diff_screenshots"].invoke({
        "image_path_a": str(path), "image_path_b": str(path),
    })
    assert result["boxes"] == []


def test_screen_recording_tools_present_in_default_registry():
    names = {tool.name for tool in build_default_tool_registry()}
    assert {"ac_screen_record_start", "ac_screen_record_stop",
            "ac_screen_record_list"}.issubset(names)


def test_screen_record_start_validates_directory(tmp_path):
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    missing = tmp_path / "nope" / "out.avi"
    try:
        by_name["ac_screen_record_start"].invoke({
            "recorder_name": "rec1", "file_path": str(missing),
        })
    except ValueError as error:
        assert "directory does not exist" in str(error)
    else:
        raise AssertionError("expected ValueError for missing dir")


def test_screen_record_list_starts_empty(monkeypatch):
    """Force a fresh recorder so leftover state from other tests doesn't bleed in."""
    import je_auto_control.utils.mcp_server.tools._handlers as handlers
    monkeypatch.setattr(handlers, "_screen_recorder_singleton", None)
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    assert by_name["ac_screen_record_list"].invoke({}) == []


def test_list_monitors_returns_at_least_one_entry():
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    monitors = by_name["ac_list_monitors"].invoke({})
    assert isinstance(monitors, list)
    assert monitors  # mss always reports at least the virtual desktop
    first = monitors[0]
    assert first["index"] == 0
    assert first["is_combined"] is True
    for key in ("left", "top", "width", "height"):
        assert isinstance(first[key], int)


def test_screenshot_rejects_invalid_monitor_index():
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    try:
        by_name["ac_screenshot"].invoke({"monitor_index": 999})
    except ValueError as error:
        assert "out of range" in str(error)
    else:
        raise AssertionError("expected ValueError for bad monitor index")


def test_clipboard_image_tools_present_in_default_registry():
    names = {tool.name for tool in build_default_tool_registry()}
    assert {"ac_get_clipboard_image", "ac_set_clipboard_image"}.issubset(names)


def test_get_clipboard_image_returns_text_block_when_empty(monkeypatch):
    """When the clipboard has no image, return a clear text fallback."""
    import je_auto_control.utils.mcp_server.tools._handlers as handlers
    import je_auto_control.utils.clipboard.clipboard_image as image_clip
    monkeypatch.setattr(image_clip, "get_clipboard_image", lambda: None)
    result = handlers.get_clipboard_image()
    assert result[0].type == "text"
    assert "does not contain an image" in result[0].text


def test_get_clipboard_image_returns_image_block_when_set(monkeypatch):
    import je_auto_control.utils.mcp_server.tools._handlers as handlers
    import je_auto_control.utils.clipboard.clipboard_image as image_clip
    monkeypatch.setattr(image_clip, "get_clipboard_image",
                         lambda: b"\x89PNG\r\n\x1a\n")
    result = handlers.get_clipboard_image()
    assert result[0].type == "image"
    assert result[0].mime_type == "image/png"


def test_set_clipboard_image_validates_existence(tmp_path):
    by_name = {tool.name: tool for tool in build_default_tool_registry()}
    missing = tmp_path / "nope.png"
    try:
        by_name["ac_set_clipboard_image"].invoke({
            "image_path": str(missing),
        })
    except FileNotFoundError as error:
        assert "image not found" in str(error)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_audit_logger_records_successful_tool_call(tmp_path):
    from je_auto_control.utils.mcp_server.audit import AuditLogger
    audit_path = tmp_path / "audit.jsonl"
    audit = AuditLogger(path=str(audit_path))
    tool = MCPTool(
        name="audited", description="audited",
        input_schema={"type": "object",
                       "properties": {"x": {"type": "integer"}},
                       "required": ["x"]},
        handler=lambda x: x * 2,
    )
    server = MCPServer(tools=[tool], audit_logger=audit)
    server.handle_line(_request("tools/call", params={
        "name": "audited", "arguments": {"x": 21},
    }))
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["tool"] == "audited"
    assert record["status"] == "ok"
    assert record["arguments"] == {"x": 21}
    assert "duration_seconds" in record


def test_audit_logger_records_errors(tmp_path):
    from je_auto_control.utils.mcp_server.audit import AuditLogger

    def raises(x):  # pragma: no cover - called via tool
        del x
        raise ValueError("bad")

    audit = AuditLogger(path=str(tmp_path / "errs.jsonl"))
    tool = MCPTool(
        name="boom", description="boom",
        input_schema={"type": "object",
                       "properties": {"x": {"type": "integer"}},
                       "required": ["x"]},
        handler=raises,
    )
    server = MCPServer(tools=[tool], audit_logger=audit)
    server.handle_line(_request("tools/call", params={
        "name": "boom", "arguments": {"x": 1},
    }))
    record = json.loads(audit.path and open(audit.path, encoding="utf-8").readline())
    assert record["status"] == "error"
    assert "ValueError" in record["error"]


def test_audit_logger_redacts_sensitive_keys(tmp_path):
    from je_auto_control.utils.mcp_server.audit import AuditLogger
    audit = AuditLogger(path=str(tmp_path / "audit.jsonl"))
    tool = MCPTool(
        name="creds", description="creds",
        input_schema={"type": "object",
                       "properties": {"password": {"type": "string"},
                                       "user": {"type": "string"}},
                       "required": ["password", "user"]},
        handler=lambda password, user: "ok",
    )
    server = MCPServer(tools=[tool], audit_logger=audit)
    server.handle_line(_request("tools/call", params={
        "name": "creds",
        "arguments": {"password": "shhh", "user": "jeff"},
    }))
    record = json.loads(open(audit.path, encoding="utf-8").readline())
    assert record["arguments"] == {"password": "<redacted>",
                                     "user": "jeff"}


def test_audit_logger_disabled_when_no_path():
    from je_auto_control.utils.mcp_server.audit import AuditLogger
    audit = AuditLogger(path=None)
    assert audit.enabled is False
    audit.record(tool="x", arguments={}, status="ok",
                  duration_seconds=0.0)  # must not raise


def test_rate_limiter_blocks_when_capacity_exhausted():
    from je_auto_control.utils.mcp_server.rate_limit import RateLimiter
    limiter = RateLimiter(rate_per_sec=0.0001, capacity=2)
    tool = MCPTool(
        name="counted", description="counted",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: "ok",
    )
    server = MCPServer(tools=[tool], rate_limiter=limiter)
    first = _decode(server.handle_line(_request("tools/call", msg_id=1,
        params={"name": "counted", "arguments": {}})))
    second = _decode(server.handle_line(_request("tools/call", msg_id=2,
        params={"name": "counted", "arguments": {}})))
    third = _decode(server.handle_line(_request("tools/call", msg_id=3,
        params={"name": "counted", "arguments": {}})))
    assert first["result"]["isError"] is False
    assert second["result"]["isError"] is False
    assert third["error"]["code"] == -32000
    assert "Rate limit" in third["error"]["message"]


def test_rate_limiter_zero_rate_means_unlimited():
    from je_auto_control.utils.mcp_server.rate_limit import RateLimiter
    limiter = RateLimiter(rate_per_sec=0)
    for _ in range(5):
        assert limiter.try_acquire() is True


def test_initialize_advertises_roots_when_client_supports_it():
    server = MCPServer(tools=[])
    response = _decode(server.handle_line(_request("initialize", params={
        "capabilities": {"roots": {"listChanged": True}},
    })))
    assert "roots" in response["result"]["capabilities"]


def test_initialize_omits_roots_when_client_lacks_capability():
    server = MCPServer(tools=[])
    response = _decode(server.handle_line(_request("initialize", params={
        "capabilities": {},
    })))
    assert "roots" not in response["result"]["capabilities"]


def test_refresh_roots_updates_filesystem_provider(tmp_path):
    from je_auto_control.utils.mcp_server.resources import (
        ChainProvider, FileSystemProvider,
    )
    fs_provider = FileSystemProvider(root=str(tmp_path / "initial"))
    chain = ChainProvider([fs_provider])
    captured_lines = []
    server = MCPServer(tools=[], resource_provider=chain,
                       concurrent_tools=True)
    server.set_writer(captured_lines.append)
    # Simulate client capability so refresh is allowed.
    server._client_capabilities = {"roots": {"listChanged": True}}

    target = tmp_path / "ws"
    target.mkdir()

    def run_refresh():
        server.refresh_roots(timeout=2.0)

    t = threading.Thread(target=run_refresh)
    t.start()
    deadline = threading.Event()
    for _ in range(200):
        if any('"roots/list"' in line for line in captured_lines):
            break
        deadline.wait(0.01)
    request_lines = [line for line in captured_lines
                      if '"roots/list"' in line]
    assert request_lines, "expected outbound roots/list"
    request_id = json.loads(request_lines[-1])["id"]

    file_uri = "file:///" + str(target).replace("\\", "/").lstrip("/")
    server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": request_id,
        "result": {"roots": [{"uri": file_uri, "name": "ws"}]},
    }))
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert os.path.realpath(fs_provider.root) == os.path.realpath(str(target))


def test_initialize_advertises_logging_capability():
    server = MCPServer(tools=[])
    response = _decode(server.handle_line(_request("initialize", params={})))
    assert "logging" in response["result"]["capabilities"]


def test_log_bridge_emits_notification_for_log_record():
    from je_auto_control.utils.mcp_server.log_bridge import MCPLogBridge
    captured = []
    bridge = MCPLogBridge(
        notifier=lambda method, params: captured.append((method, params)),
    )
    import logging
    record = logging.LogRecord(
        name="je_auto_control.tests", level=logging.WARNING,
        pathname=__file__, lineno=10, msg="something %s", args=("happened",),
        exc_info=None,
    )
    bridge.emit(record)
    assert captured
    method, params = captured[0]
    assert method == "notifications/message"
    assert params["level"] == "warning"
    assert params["data"]["message"] == "something happened"


def test_logging_set_level_request_updates_bridge_level():
    from je_auto_control.utils.mcp_server.log_bridge import MCPLogBridge
    server = MCPServer(tools=[], log_bridge=MCPLogBridge())
    response = _decode(server.handle_line(_request("logging/setLevel", params={
        "level": "error",
    })))
    assert response["result"] == {}
    import logging
    assert server._log_bridge.level == logging.ERROR


def test_logging_set_level_rejects_unknown_name():
    server = MCPServer(tools=[])
    response = _decode(server.handle_line(_request("logging/setLevel", params={
        "level": "telepathy",
    })))
    assert response["error"]["code"] == -32602


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
