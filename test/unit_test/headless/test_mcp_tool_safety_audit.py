"""Regression tests for the MCP tool-safety defects of the 2026-09-23 audit.

Tool annotations are set by hand, and some were wrong. ``ac_bulkhead_run`` and
``ac_run_chaos`` run action lists but were read-only, so
``JE_AUTOCONTROL_MCP_READONLY`` still ran any command through them. Tools that
write a caller-chosen file were read-only too. Script, trigger and input tools
were non-destructive, so the confirmation gate never asked. Read-only tools
created an SQLite file at any ``db`` path, ``ac_assert_http`` sent DELETE,
``resources/read`` served any file in the root, and an undeclared argument
reached the handler as a ``TypeError`` tool error.
"""
import json
from typing import Any, Dict

import pytest

from je_auto_control.utils.mcp_server.resources import FileSystemProvider
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool, build_default_tool_registry


@pytest.fixture(scope="module")
def registry() -> Dict[str, MCPTool]:
    return {tool.name: tool for tool in build_default_tool_registry(read_only=False, aliases=False)}


_RUN_ACTIONS = ["ac_bulkhead_run", "ac_run_chaos", "ac_run_saga", "ac_skill_run", "ac_run_suite",
                "ac_replay_trace", "ac_run_state_machine", "ac_scheduler_add_job", "ac_trigger_add",
                "ac_hotkey_bind", "ac_load_plugins", "ac_open_path", "ac_observe_add"]
_SEND_INPUT = ["ac_input_sequence", "ac_element_click", "ac_set_field_text", "ac_type_unicode",
               "ac_post_key_to_window", "ac_drag_path"]
_OUTWARD = ["ac_s3_delete", "ac_egress_allow", "ac_lease_secret", "ac_approval_approve",
            "ac_remote_host_start", "ac_usb_acl_set_default", "ac_http_request", "ac_send_email"]


@pytest.mark.parametrize("name", _RUN_ACTIONS + _SEND_INPUT + _OUTWARD)
def test_tools_that_act_are_destructive(registry, name):
    annotations = registry[name].annotations
    assert annotations.destructive and not annotations.read_only


@pytest.mark.parametrize("name", ["ac_export_sarif", "ac_compliance_report", "ac_assert_visual"])
def test_tools_that_write_a_file_are_not_read_only(registry, name):
    assert not registry[name].annotations.read_only


def test_read_only_mode_offers_no_action_runner():
    names = {tool.name for tool in build_default_tool_registry(read_only=True, aliases=False)}
    assert not names & set(_RUN_ACTIONS + _SEND_INPUT + _OUTWARD)


@pytest.mark.parametrize("name, arguments, empty", [
    ("ac_queue_stats", {}, {"new": 0, "in_progress": 0, "success": 0, "failed": 0}),
    ("ac_memory_recall", {"query": "x"}, {"episodes": []}),
    ("ac_memory_recent", {}, {"episodes": []}),
    ("ac_memory_stats", {}, {"episodes": 0}),
    ("ac_checkpoint_status", {"run_id": "r"}, {"checkpoint": None}),
])
def test_read_only_tools_do_not_create_a_database(registry, tmp_path, name, arguments, empty):
    db = tmp_path / "absent.db"
    assert registry[name].invoke({"db": str(db), **arguments}) == empty
    assert not db.exists()


def test_assert_http_only_offers_safe_methods(registry):
    method = registry["ac_assert_http"].input_schema["properties"]["method"]
    assert {value.upper() for value in method["enum"]} == {"GET", "HEAD"}


def _call(server: MCPServer, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    raw = server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }))
    assert raw is not None
    return json.loads(raw)


def _echo_server() -> MCPServer:
    return MCPServer(tools=[MCPTool(
        name="echo", description="echo",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        handler=lambda text="": text)])


@pytest.mark.parametrize("extra", ["bogus", "ctx"])
def test_an_undeclared_argument_is_invalid_params(extra):
    reply = _call(_echo_server(), "echo", {"text": "hi", extra: 1})
    assert reply["error"]["code"] == -32602 and extra in reply["error"]["message"]


def test_declared_arguments_still_work():
    reply = _call(_echo_server(), "echo", {"text": "hi"})
    assert "error" not in reply and reply["result"]["content"][0]["text"] == "hi"


@pytest.mark.parametrize("name", ["creds.txt", "a.json::$DATA", "sub\\a.json", "C:a.json"])
def test_resource_read_serves_only_listed_json_files(tmp_path, name):
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "creds.txt").write_text("secret", encoding="utf-8")
    provider = FileSystemProvider(str(tmp_path))
    assert provider.read(f"autocontrol://files/{name}") is None
    assert provider.read("autocontrol://files/a.json")["text"] == "{}"
