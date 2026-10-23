"""Discovery retains authority, connection policy and transport notifications across worker handoff."""
import json
from types import SimpleNamespace

import pytest

from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool, MCPToolAnnotations
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope, current_authorization


@pytest.fixture(autouse=True)
def no_native_error_capture(monkeypatch):
    from je_auto_control.utils.mcp_server import server
    monkeypatch.setattr(server, "_capture_error_screenshot", lambda _name: None)


def test_async_call_keeps_the_callers_role_session_and_roots(tmp_path):
    from je_auto_control.utils.mcp_server._argument_policy import ArgumentPolicy
    from je_auto_control.utils.path_guard.policy import PathPolicy
    policy = None

    def inspect(ctx):
        return {"role": current_authorization().role, "session": ctx.session_id,
                "same_policy": ctx.path_policy is policy}

    server = MCPServer(tools=[MCPTool("fixture", "Inspect authority", {}, inspect,
                                     MCPToolAnnotations(read_only=True))])
    server.argument_policy = ArgumentPolicy(PathPolicy(use_client_roots=True))
    replies = []
    with authorization_scope(AuthorizationContext("reader", "viewer")):
        with server.connection_scope(connection_id="first", concurrent_tools=True, writer=replies.append):
            policy = server._active_argument_policy.path_policy
            policy.set_client_roots([tmp_path])
            assert server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                                  "params": {"name": "fixture"}})) is None
    server._join_workers()
    value = json.loads(json.loads(replies[0])["result"]["content"][0]["text"])
    assert value == {"role": "viewer", "session": server._agent_session + ":first", "same_policy": True}
    server.stop()


def test_async_call_uses_the_enabled_view_from_its_own_session():
    server = MCPServer(tools=[MCPTool("fixture", "Read", {}, lambda: "done", MCPToolAnnotations(read_only=True))])
    server.configure_tool_disclosure("progressive")
    replies = []
    with server.connection_scope(connection_id="first", concurrent_tools=True, writer=replies.append):
        server._session_tool_view().enable(["fixture"])
        server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                       "params": {"name": "fixture"}}))
    server._join_workers()
    reply = json.loads(replies[0])
    assert reply["result"]["isError"] is False
    assert reply["result"]["content"][0]["text"] == "done"
    assert None not in server._disclosure_views
    server.stop()


def test_plugin_list_changes_reach_all_open_http_session_streams_once():
    from je_auto_control.utils.mcp_server.http_transport import HttpMCPServer
    bridge = MCPServer(tools=[])
    host = HttpMCPServer(bridge, port=0)
    host.start()
    try:
        first, second = host.sessions.create(), host.sessions.create()
        left, right = [], []
        assert first.attach_stream(left.append) and second.attach_stream(right.append)
        bridge.register_tool(MCPTool("fixture", "Read", {}, lambda: None, MCPToolAnnotations(read_only=True)))
        assert len(left) == len(right) == 1
        assert json.loads(left[0])["method"] == "notifications/tools/list_changed"
        assert left == right
    finally:
        host.stop()


def test_closed_async_acceptance_does_not_recreate_a_session_view():
    calls, replies = [], []
    server = MCPServer(tools=[MCPTool("fixture", "Read", {}, lambda: calls.append(True),
                                     MCPToolAnnotations(read_only=True))])
    with server.connection_scope(connection_id="first"):
        callback = server._capture_tool_worker(lambda: replies.append(server._build_response(
            1, "tools/call", {"name": "fixture"})))
    server.forget_connection("first")
    with server.connection_scope(connection_id="second"):
        callback()
        assert server._connection_id == "second"
    assert "error" in json.loads(replies[0]) and calls == []
    assert "first" not in server._disclosure_views
    server.stop()


def test_retired_path_policy_cannot_validate_late_arguments(tmp_path):
    from je_auto_control.utils.path_guard.policy import PathPolicy
    from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError
    policy = PathPolicy([tmp_path])
    policy.revoke_managed_origin()
    with pytest.raises(PathNotAllowedError, match="retired"):
        policy.validate(tmp_path / "late.txt", operation="late MCP call")


def test_targeted_http_notifications_are_not_broadcast_or_duplicated():
    from je_auto_control.utils.mcp_server.http_transport import HttpMCPServer
    from je_auto_control.utils.mcp_server.tools._discovery import discovery_tools
    bridge = MCPServer(tools=discovery_tools() + [MCPTool("fixture", "Read", {}, lambda: None,
                                                        MCPToolAnnotations(read_only=True))])
    bridge.configure_tool_disclosure("progressive")
    host = HttpMCPServer(bridge, port=0)
    host.start()
    try:
        first, second = host.sessions.create(), host.sessions.create()
        left, right = [], []
        assert first.attach_stream(left.append) and second.attach_stream(right.append)
        with bridge.connection_scope(connection_id=first.id, notifier=lambda method, params: left.append(
            json.dumps({"jsonrpc": "2.0", "method": method, "params": params}))):
            reply = bridge.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "ac_mcp_tools_enable", "arguments": {"names": ["fixture"]}}}))
            assert json.loads(reply)["result"]["isError"] is False
        assert len(left) == 1 and right == []
    finally:
        host.stop()
    assert bridge._tool_change_sinks == {}


def test_async_stateless_call_uses_a_fixed_view_without_session_enablement():
    from je_auto_control.utils.mcp_server.tools._discovery import discovery_tools
    server = MCPServer(tools=discovery_tools() + [MCPTool("fixture", "Read", {}, lambda: None,
                                                        MCPToolAnnotations(read_only=True))])
    server.configure_tool_disclosure("progressive")
    replies = []
    meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {}}
    with server.connection_scope(concurrent_tools=True, writer=replies.append):
        server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"_meta": meta, "name": "ac_mcp_tools_enable", "arguments": {"names": ["fixture"]}}}))
    server._join_workers()
    assert json.loads(replies[0])["result"]["isError"] is True
    assert server._disclosure_views == {}
    server.stop()


def test_core_discovery_shortcut_still_checks_the_actual_readonly_annotation():
    calls = []
    server = MCPServer(tools=[MCPTool("ac_mcp_tool_search", "Mutating replacement", {}, lambda: calls.append(True))])
    server.configure_tool_disclosure("progressive", read_only=True)
    reply = server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                          "params": {"name": "ac_mcp_tool_search"}}))
    assert "error" in json.loads(reply) and calls == []
    server.stop()


def test_notification_cannot_precede_http_stream_headers(monkeypatch):
    import http.client
    import threading
    from je_auto_control.utils.mcp_server.http_sessions import HttpSession
    from je_auto_control.utils.mcp_server.http_transport import HttpMCPServer
    bridge = MCPServer(tools=[])
    host = HttpMCPServer(bridge, port=0)
    host.start()
    connection = http.client.HTTPConnection(*host.address, timeout=5)
    threads = []
    original = HttpSession.attach_stream

    def attach(session, writer):
        claimed = original(session, writer)
        if claimed:
            started = threading.Event()

            def publish():
                started.set()
                bridge.register_tool(MCPTool("fixture", "Read", {}, lambda: None, MCPToolAnnotations(read_only=True)))

            thread = threading.Thread(target=publish)
            threads.append(thread)
            thread.start()
            assert started.wait(1)
            thread.join(0.1)
        return claimed

    monkeypatch.setattr(HttpSession, "attach_stream", attach)
    try:
        session = host.sessions.create()
        connection.request("GET", "/mcp", headers={"Accept": "text/event-stream", "Mcp-Session-Id": session.id})
        response = connection.getresponse()
        assert response.status == 200
        payload = response.readline().decode("utf-8")
        assert payload.startswith("data: ")
        assert json.loads(payload[6:])["method"] == "notifications/tools/list_changed"
    finally:
        connection.close()
        host.stop()
        for thread in threads:
            thread.join(1)


def _call(server, name, arguments=None):
    return json.loads(server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                                    "params": {"name": name, "arguments": arguments or {}}})))


def test_discovered_call_uses_existing_policy(tmp_path, monkeypatch):
    from je_auto_control.utils.mcp_server._argument_policy import ArgumentPolicy
    from je_auto_control.utils.mcp_server.tools._discovery import discovery_tools
    from je_auto_control.utils.path_guard.policy import PathPolicy
    root = tmp_path / "root"
    root.mkdir()
    calls, confirmations, rate_checks = [], [], []
    tool = MCPTool("fixture", "Read", {"type": "object", "properties": {
        "path": {"type": "string", "format": "path"}, "reference": {"type": "string", "format": "value-ref"}}},
        lambda **values: calls.append(values), MCPToolAnnotations(read_only=True))
    server = MCPServer(tools=discovery_tools() + [tool])
    server.argument_policy = ArgumentPolicy(PathPolicy([root]), ("FIXTURE_ALLOWED",))
    server.configure_tool_disclosure("progressive")
    server._rate_limiter = SimpleNamespace(try_acquire=lambda: rate_checks.append(True) or True)
    confirm = server._maybe_confirm_destructive
    monkeypatch.setattr(server, "_maybe_confirm_destructive", lambda name, item, values: (
        confirmations.append(name), confirm(name, item, values))[-1])
    assert _call(server, "ac_mcp_tools_enable", {"names": ["fixture"]})["result"]["isError"] is False
    assert _call(server, "fixture", {"path": str(root / "ok.txt")})["result"]["isError"] is False
    assert _call(server, "fixture", {"path": str(tmp_path / "denied.txt")})["result"]["isError"] is True
    assert _call(server, "fixture", {"reference": "env://FIXTURE_DENIED"})["result"]["isError"] is True
    assert calls == [{"path": str((root / "ok.txt").resolve())}]
    assert confirmations == ["ac_mcp_tools_enable", "fixture"] and len(rate_checks) == 2
    server.stop()


@pytest.mark.parametrize("role,readonly", [("viewer", False), ("operator", True)])
def test_readonly_forbids_mutating_enable(role, readonly):
    from je_auto_control.utils.mcp_server.tools._discovery import discovery_tools
    calls = []
    server = MCPServer(tools=discovery_tools() + [MCPTool("write", "Mutate", {}, lambda: calls.append(True))])
    server.configure_tool_disclosure("progressive", read_only=readonly)
    with authorization_scope(AuthorizationContext("caller", role)):
        assert _call(server, "ac_mcp_tools_enable", {"names": ["write"]})["result"]["isError"] is True
        assert "error" in _call(server, "write")
    assert calls == []
    server.stop()


def test_removed_tool_cannot_run():
    from je_auto_control.utils.mcp_server.tools._discovery import discovery_tools
    calls = []
    server = MCPServer(tools=discovery_tools() + [MCPTool("fixture", "Read", {}, lambda: calls.append(True),
                                                        MCPToolAnnotations(read_only=True))])
    server.configure_tool_disclosure("progressive")
    assert _call(server, "ac_mcp_tools_enable", {"names": ["fixture"]})["result"]["isError"] is False
    server.unregister_tool("fixture")
    assert "error" in _call(server, "fixture") and calls == []
    server.stop()


def test_plain_client_static_profile():
    from je_auto_control.utils.mcp_server.tools._discovery import discovery_tools
    server = MCPServer(tools=discovery_tools() + [
        MCPTool("selected", "Read", {}, lambda: "selected", MCPToolAnnotations(read_only=True)),
        MCPTool("other", "Read", {}, lambda: "other", MCPToolAnnotations(read_only=True))])
    server.configure_tool_disclosure("static", names=["selected"])
    page = json.loads(server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})))
    assert "selected" in {item["name"] for item in page["result"]["tools"]}
    assert "other" not in {item["name"] for item in page["result"]["tools"]}
    assert _call(server, "selected")["result"]["isError"] is False
    assert "error" in _call(server, "other")
    assert _call(server, "ac_mcp_tools_enable", {"names": ["other"]})["result"]["isError"] is True
    server.stop()
