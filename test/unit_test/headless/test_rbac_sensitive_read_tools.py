"""Read-only MCP hints do not grant viewers clipboard, local data or credentials."""
import json
import http.client

import pytest

from je_auto_control.utils.mcp_server._authz import FORBIDDEN_CODE
from je_auto_control.utils.mcp_server.http_transport import DEFAULT_PATH, HttpMCPServer
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool, build_default_tool_registry
from je_auto_control.utils.mcp_server.tools._base import READ_ONLY, schema
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.rbac.users import UserStore

SENSITIVE = (
    "ac_get_clipboard", "ac_get_clipboard_image", "ac_get_clipboard_html",
    "ac_get_clipboard_files", "ac_get_clipboard_rtf", "ac_get_clipboard_csv",
    "ac_clipboard_formats", "ac_clip_history_list", "ac_clip_history_search", "ac_assert_clipboard",
    "ac_read_action_file", "ac_load_dotenv", "ac_sql_query", "ac_assert_db",
    "ac_read_workbook", "ac_read_document", "ac_read_presentation", "ac_extract_pdf_text",
    "ac_assert_pdf_text", "ac_load_data", "ac_assert_file", "ac_resolve_ref", "ac_resolve_refs",
    "ac_jwt_encode", "ac_generate_otp", "ac_assert_http", "ac_wait_for_port", "ac_s3_list",
    "ac_assert_all", "ac_assert_any", "ac_assert_eventually", "ac_assert_audio",
    "ac_get_asset", "ac_list_assets", "ac_cas_get", "ac_outbox_pending", "ac_checkpoint_status",
    "ac_memory_recall", "ac_memory_recent", "ac_memory_stats", "ac_queue_stats",
    "ac_rank_tests", "ac_select_tests", "ac_shard_suite", "ac_element_find", "ac_element_list",
    "ac_skill_list", "ac_skill_search", "ac_pending_artifacts", "ac_approval_status",
    "ac_repair_resolved", "ac_repair_pending", "ac_vlm_locate", "ac_self_heal_locate", "ac_describe_screen",
)


def _rpc(server, method, params=None):
    return json.loads(server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params or {},
    })))


@pytest.fixture(scope="module")
def registry():
    return build_default_tool_registry(read_only=False)


def test_default_registry_hides_sensitive_reads_from_viewers(registry):
    server = MCPServer(tools=registry)
    with authorization_scope(AuthorizationContext("viewer", Role.VIEWER)):
        names = {tool["name"] for tool in _rpc(server, "tools/list")["result"]["tools"]}
    assert not names.intersection(SENSITIVE)
    assert {"ac_get_mouse_position", "ac_screen_size", "ac_parse_dotenv", "ac_jwt_decode"} <= names
    # Security classification is separate from readOnlyHint: data reads are
    # still non-mutating and pure parsing of caller-supplied values stays visible.
    assert all(tool.annotations.read_only for tool in registry if tool.name in SENSITIVE)


@pytest.mark.parametrize("name", SENSITIVE)
def test_sensitive_read_call_is_refused_before_handler_invocation(name):
    called = []
    tool = MCPTool(name=name, description="controlled sensitive read", annotations=READ_ONLY,
                   input_schema=schema({}), handler=lambda: called.append(True) or {"ok": True})
    server = MCPServer(tools=[tool])
    for role in Role.all():
        with authorization_scope(AuthorizationContext(role, role)):
            names = [item["name"] for item in _rpc(server, "tools/list")["result"]["tools"]]
            reply = _rpc(server, "tools/call", {"name": name, "arguments": {}})
        if role == Role.VIEWER:
            assert names == []
            assert reply["error"]["code"] == FORBIDDEN_CODE
            assert called == []
        else:
            assert names == [name] and "result" in reply
    assert called == [True, True]


def test_unconfigured_rbac_preserves_sensitive_tools(registry):
    server = MCPServer(tools=registry)
    with authorization_scope(None):
        names = {tool["name"] for tool in _rpc(server, "tools/list")["result"]["tools"]}
    assert set(SENSITIVE) <= names


@pytest.mark.parametrize("name", ["ac_realize_item", "ac_idempotency_begin", "ac_rate_limit"])
def test_state_changes_are_excluded_from_read_only_mode(name, registry):
    tool = next(tool for tool in registry if tool.name == name)
    assert tool.annotations.read_only is False
    assert name not in {tool.name for tool in build_default_tool_registry(read_only=True)}
    with authorization_scope(AuthorizationContext("viewer", Role.VIEWER)):
        names = {item["name"] for item in _rpc(MCPServer(tools=[tool]), "tools/list")["result"]["tools"]}
    assert names == set()


def test_http_user_tokens_cannot_bypass_sensitive_tool_policy(tmp_path):
    store = UserStore(tmp_path / "users.json")
    tokens = {role: store.add_user(user_id=role, display_name=role, role=role) for role in Role.all()}
    called = []
    names = ["ac_sql_query", "ac_get_clipboard", "ac_jwt_encode"]
    tools = [MCPTool(name=name, description=name, annotations=READ_ONLY, input_schema=schema({}),
                     handler=lambda name=name: called.append(name) or {"ok": True}) for name in names]
    server = HttpMCPServer(mcp=MCPServer(tools=tools), host="127.0.0.1", port=0, user_store=store)
    server.start()
    try:
        for role, token in tokens.items():
            for name in names:
                conn = http.client.HTTPConnection(*server.address, timeout=5)
                try:
                    conn.request("POST", DEFAULT_PATH, json.dumps({
                        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": name, "arguments": {}},
                    }), headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
                    response = conn.getresponse()
                    assert response.status == 200
                    reply = json.loads(response.read())
                    if role == Role.VIEWER:
                        assert reply["error"]["code"] == FORBIDDEN_CODE and called == []
                    else:
                        assert "result" in reply
                finally:
                    conn.close()
    finally:
        server.stop()
    assert called == names * 2
