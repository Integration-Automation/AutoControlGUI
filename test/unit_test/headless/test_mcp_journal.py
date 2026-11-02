"""Journal tools keep RPC errors, progress, permissions and roots explicit."""
import io
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.mcp_server._argument_policy import ArgumentPolicy
from je_auto_control.utils.mcp_server.context import OperationCancelledError, ToolCallContext
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool, build_default_tool_registry
from je_auto_control.utils.mcp_server.tools._base import schema
from je_auto_control.utils.path_guard import PathPolicy
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope


@pytest.fixture(autouse=True)
def no_native_error_capture(monkeypatch):
    monkeypatch.setattr("je_auto_control.utils.mcp_server.server._capture_error_screenshot", lambda _name: None)


def _tool(name):
    return next(tool for tool in build_default_tool_registry(read_only=False, aliases=False) if tool.name == name)


def _rpc(server, name, arguments):
    return json.loads(server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": name, "arguments": arguments}})))


def _data(reply):
    return json.loads(reply["result"]["content"][0]["text"])


def test_tools_expose_capture_and_sensitive_read_hints():
    capture, reader = _tool("ac_journal_capture"), _tool("ac_journal_read")
    assert capture.annotations.destructive and not capture.annotations.read_only
    assert reader.annotations.read_only and reader.annotations.idempotent
    readonly = {tool.name for tool in build_default_tool_registry(read_only=True, aliases=False)}
    assert reader.name in readonly and capture.name not in readonly
    for tool in (capture, reader):
        assert tool.input_schema["properties"]["path"]["format"] == "path"


def test_rpc_capture_read_and_metadata_round_trip(tmp_path):
    path = tmp_path / "rpc.jsonl"
    server = MCPServer(tools=[_tool("ac_journal_capture"), _tool("ac_journal_read")])
    captured = _rpc(server, "ac_journal_capture", {"path": str(path), "variables": {"message": "hello"},
                    "metadata": {"run_id": "rpc", "device_id": "device", "session_id": "session"},
                    "actions": [["AC_get_var", {"name": "message"}]]})
    assert captured["result"]["isError"] is False
    result = _data(captured)
    assert result["run_id"] == "rpc" and result["failed_actions"] == 0
    assert "hello" in result["record"].values()
    reply = _rpc(server, "ac_journal_read", {"path": str(path), "run_id": "rpc", "limit": 1})
    assert reply["result"]["isError"] is False
    events = _data(reply)["events"]
    assert len(events) == 1 and events[0]["status"] == "incomplete"
    assert events[0]["device_id"] == "device" and events[0]["session_id"] == "session"


def test_recorded_failures_are_tool_errors_with_structured_run_metadata(tmp_path, monkeypatch):
    def fail():
        raise ValueError("controlled failure")
    monkeypatch.setitem(ac.executor.event_dict, "AC_mcp_journal_failure", fail)
    path = tmp_path / "failed.jsonl"
    server = MCPServer(tools=[_tool("ac_journal_capture")])
    reply = _rpc(server, "ac_journal_capture", {"path": str(path), "actions": [["AC_mcp_journal_failure"]]})
    assert reply["result"]["isError"] is True
    result = reply["result"]["structuredContent"]
    assert result["failed_actions"] == 1 and result["journal_path"] == str(path.resolve())
    assert result["run_id"] and _data(reply) == result
    assert [event.status for event in ac.read_events(path)] == ["incomplete", "error"]


@pytest.mark.parametrize("name", ["ac_journal_capture", "ac_journal_read"])
def test_viewers_cannot_list_or_call_private_journal_operations(tmp_path, name):
    server = MCPServer(tools=[_tool(name)])
    args = {"path": str(tmp_path / "refused.jsonl")}
    if name.endswith("capture"):
        args["actions"] = [["AC_set_var", {"name": "x", "value": 1}]]
    with authorization_scope(AuthorizationContext("viewer", Role.VIEWER)):
        listed = json.loads(server.handle_line('{"jsonrpc":"2.0","id":2,"method":"tools/list"}'))
        reply = _rpc(server, name, args)
    assert listed["result"]["tools"] == [] and "error" in reply
    assert not (tmp_path / "refused.jsonl").exists()


@pytest.mark.parametrize("name", ["ac_journal_capture", "ac_journal_read"])
def test_server_roots_apply_before_journal_io(tmp_path, name):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    server = MCPServer(tools=[_tool(name)])
    server.argument_policy = ArgumentPolicy(PathPolicy([allowed]))
    args = {"path": str(tmp_path / "outside.jsonl")}
    if name.endswith("capture"):
        args["actions"] = [["AC_set_var", {"name": "x", "value": 1}]]
    assert _rpc(server, name, args)["result"]["isError"] is True
    assert not (tmp_path / "outside.jsonl").exists()


def test_server_passes_its_policy_to_dynamic_nested_captures(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    server = MCPServer(tools=[_tool("ac_journal_capture")])
    server.argument_policy = ArgumentPolicy(PathPolicy([allowed]))
    outside = tmp_path / "outside.jsonl"
    reply = _rpc(server, "ac_journal_capture", {"path": str(allowed / "outer.jsonl"),
                 "variables": {"destination": str(outside)}, "actions": [["AC_journal_capture", {
                 "path": "${destination}", "body": [["AC_set_var", {"name": "x", "value": 1}]]}]]})
    assert reply["result"]["isError"] is True and not outside.exists()
    assert _data(reply)["failed_actions"] == 1


def test_progress_and_cancellation_reach_nested_loop_steps(tmp_path):
    updates = []
    ctx = ToolCallContext(17, progress_token="capture")
    def notify(_method, params):
        updates.append(params["progress"])
        if params["progress"] >= 1:
            ctx.cancelled_event.set()
    ctx.notifier = notify
    path = tmp_path / "cancelled.jsonl"
    with pytest.raises(OperationCancelledError):
        _tool("ac_journal_capture").invoke({"path": str(path), "actions": [["AC_loop", {"times": 3,
               "body": [["AC_set_var", {"name": "x", "value": 1}]]}]]}, ctx=ctx)
    assert updates == [0, 1]
    assert [event.status for event in ac.read_events(path)] == ["incomplete", "incomplete", "ok", "cancelled"]


def test_cancellation_before_capture_has_no_file_effect(tmp_path):
    path = tmp_path / "unused.jsonl"
    ctx = ToolCallContext(18)
    ctx.cancelled_event.set()
    with pytest.raises(OperationCancelledError):
        _tool("ac_journal_capture").invoke({"path": str(path), "actions": [["AC_screen_size"]]}, ctx=ctx)
    assert not path.exists()


def test_read_cancellation_keeps_the_source_unchanged(tmp_path, monkeypatch):
    path = tmp_path / "read.jsonl"
    ac.execute_action_with_journal([["AC_set_var", {"name": "x", "value": 1}]] * 2, path)
    before = path.read_bytes()
    ctx = ToolCallContext(19)
    check = ctx.check_cancelled
    calls = []
    def cancel():
        calls.append(True)
        if len(calls) == 3:
            ctx.cancelled_event.set()
        check()
    monkeypatch.setattr(ctx, "check_cancelled", cancel)
    with pytest.raises(OperationCancelledError):
        _tool("ac_journal_read").invoke({"path": str(path)}, ctx=ctx)
    assert path.read_bytes() == before


@pytest.mark.parametrize("extra", [{"metadata": {"unknown": "value"}}, {"limit": 0}, {"unexpected": 1}])
def test_invalid_fields_are_rejected_before_effects(tmp_path, extra):
    name = "ac_journal_capture" if "metadata" in extra else "ac_journal_read"
    path = tmp_path / "invalid.jsonl"
    args = {"path": str(path), **extra}
    if name.endswith("capture"):
        args["actions"] = [["AC_set_var", {"name": "x", "value": 1}]]
    reply = _rpc(MCPServer(tools=[_tool(name)]), name, args)
    assert reply["result"]["isError"] is True and not path.exists()


def test_explicit_object_results_signal_errors_without_changing_json_data():
    result = ac.MCPToolResult({"value": 3}, is_error=True, error_text="controlled failure")
    assert json.loads(json.dumps(result)) == {"value": 3}
    tool = MCPTool(name="controlled", description="controlled result", input_schema=schema({}), handler=lambda: result)
    reply = _rpc(MCPServer(tools=[tool]), "controlled", {})
    assert reply["result"]["isError"] is True and _data(reply) == {"value": 3}
    plain = MCPTool(name="ordinary", description="ordinary data", input_schema=schema({}),
                    handler=lambda: {"is_error": True})
    assert _rpc(MCPServer(tools=[plain]), "ordinary", {})["result"]["isError"] is False


def test_operator_cannot_hide_administration_inside_capture(tmp_path, monkeypatch):
    effects = []
    monkeypatch.setitem(ac.executor.event_dict, "AC_secret_init", lambda **_kwargs: effects.append(True))
    path = tmp_path / "denied.jsonl"
    server = MCPServer(tools=[_tool("ac_journal_capture")])
    with authorization_scope(AuthorizationContext("operator", Role.OPERATOR)):
        reply = _rpc(server, "ac_journal_capture", {"path": str(path), "actions": [["AC_secret_init", {}]]})
    assert "error" in reply and not effects and not path.exists()


def test_stdio_capture_uses_the_same_typed_journal_result(tmp_path):
    path = tmp_path / "stdio.jsonl"
    request = {"jsonrpc": "2.0", "id": 44, "method": "tools/call", "params": {
        "name": "ac_journal_capture", "arguments": {"path": str(path), "metadata": {"run_id": "stdio"},
        "actions": [["AC_set_var", {"name": "x", "value": 1}]]}}}
    output = io.StringIO()
    server = MCPServer(tools=[_tool("ac_journal_capture")])
    server.serve_stdio(stdin=io.StringIO(json.dumps(request) + "\n"), stdout=output)
    reply = next(json.loads(line) for line in output.getvalue().splitlines() if json.loads(line).get("id") == 44)
    assert reply["result"]["isError"] is False and reply["result"]["structuredContent"]["run_id"] == "stdio"
    assert [event.status for event in ac.read_events(path)] == ["incomplete", "ok"]
