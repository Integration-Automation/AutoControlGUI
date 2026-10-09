"""Disclosure changes availability only: the existing gates still decide (plan G3).

Fake tools whose handlers record that they ran. Nothing here drives the
desktop, and the benchmark is run against a small fake registry.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from je_auto_control.utils.mcp_server import __main__ as mcp_cli
from je_auto_control.utils.mcp_server._argument_policy import ArgumentPolicy
from je_auto_control.utils.mcp_server.audit import AuditLogger
from je_auto_control.utils.mcp_server.disclosure import (
    CORE_TOOL_NAMES, DEFAULT_PROFILE, ToolDisclosureError, ToolMode,
)
from je_auto_control.utils.mcp_server.rate_limit import RateLimiter
from je_auto_control.utils.mcp_server.server import MCPServer, start_mcp_stdio_server
from je_auto_control.utils.mcp_server.tools import MCPTool, MCPToolAnnotations
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, authorization_scope,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATELESS_META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
}


class _Recorder:
    """Fake tools that only note which of them ran."""

    def __init__(self) -> None:
        self.ran = []

    def tool(self, name, *, read_only=False, properties=None, category="fake"):
        def handler(**kwargs):
            self.ran.append((name, kwargs))
            return {"ran": name}
        return MCPTool(
            name=name, description=f"Fake tool {name}.",
            input_schema={"type": "object", "properties": properties or {}},
            handler=handler, annotations=MCPToolAnnotations(read_only=read_only),
            category=category,
        )

    def tools(self):
        return [
            self.tool("fx_write", properties={"file_path": {"type": "string", "format": "path"}}),
            self.tool("fx_read", read_only=True),
            self.tool("fx_click"),
        ]


def _rpc(server, method, params=None, msg_id=1):
    return json.loads(server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}})))


def _call(server, name, arguments=None, meta=None):
    params = {"name": name, "arguments": arguments or {}}
    if meta is not None:
        params["_meta"] = meta
    return _rpc(server, "tools/call", params)


def _names(reply):
    return [tool["name"] for tool in reply["result"]["tools"]]


def _enable(server, *names):
    result = _call(server, "ac_tools_enable", {"names": list(names)})["result"]
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


# --- every call still goes through the existing gates -------------------------------


def test_discovered_call_uses_existing_policy(tmp_path, monkeypatch):
    recorder = _Recorder()
    server = MCPServer(tools=recorder.tools(), tool_mode="progressive")
    policy_checks = []
    real_prepare = server._prepare_tool_call

    def spying_prepare(params):
        policy_checks.append(params.get("name"))
        return real_prepare(params)
    monkeypatch.setattr(server, "_prepare_tool_call", spying_prepare)
    server.argument_policy = ArgumentPolicy(PathPolicy(roots=[tmp_path]))
    _enable(server, "fx_write")
    inside = _call(server, "fx_write", {"file_path": str(tmp_path / "ok.txt")})
    assert inside["result"]["isError"] is False
    outside = _call(server, "fx_write", {"file_path": str(tmp_path.parent / "escape.txt")})
    assert outside["result"]["isError"] is True
    undeclared = _call(server, "fx_write", {"surprise": 1})
    assert undeclared["result"]["isError"] is True
    expected_checks = ["ac_tools_enable", "fx_write", "fx_write", "fx_write"]
    assert policy_checks == expected_checks
    # Only the call inside the root ran, and with the canonical path.
    assert [name for name, _kwargs in recorder.ran] == ["fx_write"]
    assert Path(recorder.ran[0][1]["file_path"]) == (tmp_path / "ok.txt").resolve()


def test_a_tool_that_is_not_enabled_is_refused_before_it_runs(tmp_path):
    recorder = _Recorder()
    audit_path = tmp_path / "audit.jsonl"
    server = MCPServer(tools=recorder.tools(), tool_mode="progressive",
                       audit_logger=AuditLogger(str(audit_path)))
    reply = _call(server, "fx_click")
    assert reply["error"]["code"] == -32602
    assert "ac_tools_enable" in reply["error"]["message"]
    assert recorder.ran == []
    entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [(entry["tool"], entry["status"]) for entry in entries] == [("fx_click", "denied")]


def test_rbac_is_checked_for_search_enable_and_call():
    recorder = _Recorder()
    server = MCPServer(tools=recorder.tools(), tool_mode="progressive")
    with authorization_scope(AuthorizationContext(user_id="v", role="viewer")):
        outcome = _enable(server, "fx_click", "fx_read")
        assert outcome["enabled"] == ["fx_read"]
        assert outcome["unavailable"] == ["fx_click"]
        assert "fx_click" not in _names(_rpc(server, "tools/list"))
        # The role refusal is the existing one, with its own code.
        assert _call(server, "fx_click")["error"]["code"] == -32003
        assert _call(server, "ac_tools_schema", {"name": "fx_click"})["result"]["isError"] is True
        assert _call(server, "fx_read")["result"]["isError"] is False
    assert recorder.ran == [("fx_read", {})]


def test_a_tool_enabled_by_an_operator_is_not_open_to_a_viewer_on_the_same_session():
    recorder = _Recorder()
    server = MCPServer(tools=recorder.tools(), tool_mode="progressive")
    with authorization_scope(AuthorizationContext(user_id="o", role="operator")):
        assert _enable(server, "fx_click")["enabled"] == ["fx_click"]
    with authorization_scope(AuthorizationContext(user_id="v", role="viewer")):
        assert "fx_click" not in _names(_rpc(server, "tools/list"))
        assert _call(server, "fx_click")["error"]["code"] == -32003
    assert recorder.ran == []


def test_rate_limit_still_applies_to_an_enabled_tool():
    recorder = _Recorder()
    server = MCPServer(tools=recorder.tools(), tool_mode="progressive",
                       rate_limiter=RateLimiter(rate_per_sec=0.001, capacity=2))
    _enable(server, "fx_click")                       # first token
    assert "result" in _call(server, "fx_click")      # second token
    assert _call(server, "fx_click")["error"]["code"] == -32000


# --- read-only ---------------------------------------------------------------------


def test_readonly_forbids_mutating_enable():
    recorder = _Recorder()
    server = MCPServer(tools=recorder.tools(), tool_mode="progressive", read_only=True)
    # A plugin registers a mutating tool on the live, read-only server.
    server.register_tool(recorder.tool("plugin_fx_mutate"))
    outcome = _enable(server, "fx_click", "plugin_fx_mutate", "fx_read")
    assert outcome["enabled"] == ["fx_read"]
    assert outcome["unavailable"] == ["fx_click", "plugin_fx_mutate"]
    listed = _names(_rpc(server, "tools/list"))
    mutating_tool_visible = "fx_click" in listed or "plugin_fx_mutate" in listed
    assert mutating_tool_visible is False
    assert _call(server, "plugin_fx_mutate")["error"]["code"] == -32602
    assert recorder.ran == []
    # The core stays usable: a read-only session can still search and enable.
    assert listed == list(CORE_TOOL_NAMES) + ["fx_read"]


def test_read_only_argument_reaches_the_stdio_entry_point(monkeypatch):
    served = []
    monkeypatch.setattr(MCPServer, "serve_stdio", lambda self: served.append(self))
    server = start_mcp_stdio_server(read_only=True, tool_mode="progressive")
    assert served == [server]
    assert server.disclosure.mode is ToolMode.PROGRESSIVE
    assert server.disclosure.read_only is True
    assert all(tool.annotations.read_only for tool in server._tools.values())


# --- plugins -----------------------------------------------------------------------


def test_removed_tool_cannot_run():
    recorder = _Recorder()
    server = MCPServer(tools=recorder.tools(), tool_mode="progressive")
    server.register_tool(recorder.tool("plugin_fx_gone"))
    _enable(server, "plugin_fx_gone")
    assert server.unregister_tool("plugin_fx_gone") is True
    assert "plugin_fx_gone" not in _names(_rpc(server, "tools/list"))
    assert _call(server, "plugin_fx_gone")["error"]["code"] == -32602
    # The same name coming back is a new tool: the session has to ask again.
    server.register_tool(recorder.tool("plugin_fx_gone"))
    assert _call(server, "plugin_fx_gone")["error"]["code"] == -32602
    removed_tool_executed = any(name == "plugin_fx_gone" for name, _kwargs in recorder.ran)
    assert removed_tool_executed is False
    _enable(server, "plugin_fx_gone")
    assert _call(server, "plugin_fx_gone")["result"]["isError"] is False


def test_the_core_tools_cannot_be_shadowed_or_removed():
    recorder = _Recorder()
    server = MCPServer(tools=recorder.tools(), tool_mode="progressive")
    shadow = recorder.tool("ac_tools_enable")
    with pytest.raises(ToolDisclosureError):
        server.register_tool(shadow)
    with pytest.raises(ToolDisclosureError):
        server.unregister_tool("ac_tools_search")
    assert _names(_rpc(server, "tools/list")) == list(CORE_TOOL_NAMES)


# --- clients that cannot follow a changing list -------------------------------------


def test_plain_client_static_profile(monkeypatch):
    recorder = _Recorder()
    monkeypatch.setenv("JE_AUTOCONTROL_MCP_TOOL_PROFILE", "fx_read, category:nope, fx_click")
    server = MCPServer(tools=recorder.tools(), tool_mode="static")
    sent = []
    server.set_notifier(lambda method, params: sent.append(method))
    assert _names(_rpc(server, "tools/list")) == ["fx_read", "fx_click"]
    assert not any(name in server._tools for name in CORE_TOOL_NAMES)
    assert _call(server, "fx_read")["result"]["isError"] is False
    assert _call(server, "fx_write")["error"]["code"] == -32602
    assert sent == []


def test_static_profile_defaults_to_the_common_tools(monkeypatch):
    monkeypatch.delenv("JE_AUTOCONTROL_MCP_TOOL_PROFILE", raising=False)
    recorder = _Recorder()
    tools = recorder.tools() + [recorder.tool(name) for name in DEFAULT_PROFILE[:3]]
    server = MCPServer(tools=tools, tool_mode="static")
    assert _names(_rpc(server, "tools/list")) == list(DEFAULT_PROFILE[:3])


def test_a_stateless_request_gets_the_static_profile_in_progressive_mode(monkeypatch):
    monkeypatch.setenv("JE_AUTOCONTROL_MCP_TOOL_PROFILE", "fx_read")
    recorder = _Recorder()
    server = MCPServer(tools=recorder.tools(), tool_mode="progressive")
    _enable(server, "fx_click")  # the handshake-era stdio session
    listed = _rpc(server, "tools/list", {"_meta": _STATELESS_META})
    # 2026-07-28 has no session to keep an enabled set in.
    assert _names(listed) == ["fx_read"]
    assert listed["result"]["resultType"] == "complete"
    assert _call(server, "fx_read", meta=_STATELESS_META)["result"]["isError"] is False
    assert _call(server, "fx_click", meta=_STATELESS_META)["error"]["code"] == -32602
    assert _call(server, "ac_tools_enable", {"names": ["fx_click"]},
                 meta=_STATELESS_META)["error"]["code"] == -32602
    # The session's own view is untouched: core, its profile, what it enabled.
    assert _names(_rpc(server, "tools/list")) == list(CORE_TOOL_NAMES) + ["fx_read", "fx_click"]


def test_protocol_negotiation_and_cancel_are_unchanged_by_the_mode():
    recorder = _Recorder()
    server = MCPServer(tools=recorder.tools(), tool_mode="progressive")
    for version in ("2024-11-05", "2025-06-18", "2025-11-25"):
        reply = _rpc(server, "initialize", {"protocolVersion": version, "capabilities": {}})
        assert reply["result"]["protocolVersion"] == version
        assert reply["result"]["capabilities"]["tools"] == {"listChanged": True}
    # A cancel for a call that is not running is ignored, as before.
    assert server.handle_line(json.dumps({
        "jsonrpc": "2.0", "method": "notifications/cancelled",
        "params": {"requestId": 99}})) is None


def test_stdio_loop_serves_one_implicit_session_and_reclaims_it():
    import io
    recorder = _Recorder()
    server = MCPServer(tools=recorder.tools(), tool_mode="progressive")
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-11-25", "capabilities": {}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "ac_tools_enable", "arguments": {"names": ["fx_read"]}}},
    ]
    stdout = io.StringIO()
    server.serve_stdio(stdin=io.StringIO("".join(json.dumps(line) + "\n" for line in lines)),
                       stdout=stdout)
    written = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert sum(1 for message in written
               if message.get("method") == "notifications/tools/list_changed") == 1
    assert server.disclosure.session_count == 0  # the loop ended, so did its session


# --- the CLI and the benchmark ------------------------------------------------------


def test_cli_lists_what_a_new_progressive_session_sees(capsys, monkeypatch):
    monkeypatch.delenv("JE_AUTOCONTROL_MCP_TOOL_PROFILE", raising=False)
    mcp_cli.main(["--list-tools", "--tool-mode", "progressive", "--read-only"])
    listed = json.loads(capsys.readouterr().out)
    assert [tool["name"] for tool in listed] == list(CORE_TOOL_NAMES)


def test_cli_passes_the_mode_to_the_server(monkeypatch):
    seen = {}
    monkeypatch.setattr(mcp_cli, "start_mcp_stdio_server",
                        lambda **kwargs: seen.update(kwargs))
    mcp_cli.main(["--tool-mode", "progressive"])
    assert seen == {"read_only": None, "tool_mode": "progressive"}
    seen.clear()
    # Without the flag the call is the one it always was.
    mcp_cli.main([])
    assert seen == {"read_only": None}


def _load_benchmark():
    spec = importlib.util.spec_from_file_location(
        "mcp_discovery_benchmark", _REPO_ROOT / "benchmarks" / "mcp_discovery.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_benchmark_reports_the_four_figures_for_both_modes():
    recorder = _Recorder()
    report = _load_benchmark().measure(tools=recorder.tools(), rounds=2)
    assert set(report["modes"]) == {"full", "progressive"}
    for figures in report["modes"].values():
        assert {"count", "json_bytes", "handshake_ms", "search_ms"} <= set(figures)
    assert report["modes"]["full"]["count"] == 3
    assert report["modes"]["progressive"]["count"] == len(CORE_TOOL_NAMES)
    assert report["modes"]["full"]["search_ms"] is None  # full mode has no search tool
    assert report["modes"]["progressive"]["search_ms"] >= 0
