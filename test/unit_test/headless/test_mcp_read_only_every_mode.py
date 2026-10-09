"""A read-only MCP server stays read-only after it has started, in every tool mode.

Read-only used to be applied once, when the default registry was built. In
the default full mode a mutating tool registered afterwards -- a plugin picked
up by the watcher, ``register_tool`` -- was listed and ran, on a server the
documentation describes as offering only tools that cannot change the machine.
The progressive and static modes already refused it.
"""
import json

import pytest

from je_auto_control.utils.mcp_server.audit import AuditLogger
from je_auto_control.utils.mcp_server.plugin_watcher import PluginWatcher
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool
from je_auto_control.utils.mcp_server.tools._base import DESTRUCTIVE, READ_ONLY, schema

_MODES = ["full", "progressive", "static"]


@pytest.fixture(autouse=True)
def _no_ambient_configuration(monkeypatch):
    for name in ("JE_AUTOCONTROL_MCP_READONLY", "JE_AUTOCONTROL_MCP_TOOL_MODE",
                 "JE_AUTOCONTROL_MCP_TOOL_PROFILE", "JE_AUTOCONTROL_MCP_AUDIT"):
        monkeypatch.delenv(name, raising=False)


class _Tools:
    def __init__(self):
        self.ran = []

    def make(self, name, annotations):
        def handler():
            self.ran.append(name)
            return {"ran": name}
        return MCPTool(name=name, description=name, annotations=annotations, handler=handler,
                       input_schema=schema({}))


def _rpc(server, method, params=None):
    reply = server.handle_line(json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}))
    return json.loads(reply)


def _listed(server):
    return {tool["name"] for tool in _rpc(server, "tools/list")["result"]["tools"]}


def _call(server, name):
    return _rpc(server, "tools/call", {"name": name, "arguments": {}})


@pytest.mark.parametrize("mode", _MODES)
def test_a_mutating_tool_registered_later_is_neither_listed_nor_run(mode):
    tools = _Tools()
    server = MCPServer(tools=[tools.make("look", READ_ONLY)], read_only=True, tool_mode=mode)
    server.register_tool(tools.make("plugin_poke", DESTRUCTIVE))
    assert "plugin_poke" not in _listed(server)
    reply = _call(server, "plugin_poke")
    assert reply["error"]["code"] == -32602
    assert tools.ran == []


def test_full_mode_refusal_says_why_and_is_audited(tmp_path):
    tools = _Tools()
    log = tmp_path / "audit.jsonl"
    server = MCPServer(tools=[tools.make("look", READ_ONLY)], read_only=True,
                       audit_logger=AuditLogger(path=str(log)))
    server.register_tool(tools.make("plugin_poke", DESTRUCTIVE))
    reply = _call(server, "plugin_poke")
    assert "read-only" in reply["error"]["message"]
    row = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert (row["tool"], row["status"]) == ("plugin_poke", "denied")


def test_read_only_tools_keep_working_in_full_mode():
    tools = _Tools()
    server = MCPServer(tools=[tools.make("look", READ_ONLY)], read_only=True)
    server.register_tool(tools.make("plugin_peek", READ_ONLY))
    assert _listed(server) == {"look", "plugin_peek"}
    assert _call(server, "plugin_peek")["result"]["isError"] is False
    assert tools.ran == ["plugin_peek"]


def test_the_environment_flag_is_enforced_the_same_way(monkeypatch):
    monkeypatch.setenv("JE_AUTOCONTROL_MCP_READONLY", "1")
    tools = _Tools()
    server = MCPServer(tools=[tools.make("look", READ_ONLY)])
    server.register_tool(tools.make("plugin_poke", DESTRUCTIVE))
    assert _listed(server) == {"look"}
    assert "error" in _call(server, "plugin_poke")
    assert tools.ran == []


def test_a_server_that_is_not_read_only_is_unchanged():
    tools = _Tools()
    server = MCPServer(tools=[tools.make("look", READ_ONLY)])
    server.register_tool(tools.make("plugin_poke", DESTRUCTIVE))
    assert _listed(server) == {"look", "plugin_poke"}
    assert _call(server, "plugin_poke")["result"]["isError"] is False


def test_a_plugin_the_watcher_loads_cannot_mutate_a_read_only_server(tmp_path):
    marker = tmp_path / "ran.txt"
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "late.py").write_text(
        "def AC_late():\n"
        f"    open({str(marker)!r}, 'w').close()\n"
        "    return 'done'\n", encoding="utf-8")
    server = MCPServer(tools=[_Tools().make("look", READ_ONLY)], read_only=True)
    PluginWatcher(server, str(plugins)).poll_once()
    assert "plugin_ac_late" in server._tools, "the registry still holds it"
    assert _listed(server) == {"look"}
    assert "error" in _call(server, "plugin_ac_late")
    assert not marker.exists()
