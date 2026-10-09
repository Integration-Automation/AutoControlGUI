"""A plugin may declare a tool read-only; nothing else makes a plugin tool read-only.

Read-only mode is enforced in every tool mode and plugin tools were always
registered as mutating, so a read-only MCP server ran no plugin tool at all.
``mcp_read_only = True`` on the plugin's callable is the opt-in. It is the
plugin author's word -- trusted, not verified -- so it is logged at
registration, and anything but the boolean ``True`` leaves the tool mutating.
"""
import json
import logging

import pytest

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server._authz import visible_tools
from je_auto_control.utils.mcp_server.plugin_watcher import PluginWatcher
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools.plugin_tools import (
    PLUGIN_READ_ONLY_ATTRIBUTE, make_plugin_tool, plugin_declares_read_only,
    register_plugin_tools,
)
from je_auto_control.utils.rbac import (
    AuthorizationContext, Capability, Role, authorization_scope, capability_for_tool,
)

_MODES = ["full", "progressive", "static"]
_PEEK = "plugin_ac_peek"
_POKE = "plugin_ac_poke"


@pytest.fixture(autouse=True)
def _no_ambient_configuration(monkeypatch):
    for name in ("JE_AUTOCONTROL_MCP_READONLY", "JE_AUTOCONTROL_MCP_TOOL_MODE",
                 "JE_AUTOCONTROL_MCP_AUDIT"):
        monkeypatch.delenv(name, raising=False)
    # The static mode offers a fixed profile; name the two plugin tools in it.
    monkeypatch.setenv("JE_AUTOCONTROL_MCP_TOOL_PROFILE", f"{_PEEK},{_POKE}")


@pytest.fixture()
def log_records():
    """Records the framework logger emits (it does not propagate to caplog)."""
    records = []

    class _Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Collect(level=logging.DEBUG)
    autocontrol_logger.addHandler(handler)
    try:
        yield records
    finally:
        autocontrol_logger.removeHandler(handler)


class _Plugin:
    """Two plugin callables that record their calls instead of doing anything."""

    def __init__(self, declaration=True):
        self.ran = []
        ran = self.ran

        def AC_peek():
            """Report something without changing it."""
            ran.append("peek")
            return {"seen": True}

        def AC_poke():
            """Change something."""
            ran.append("poke")
            return {"poked": True}

        setattr(AC_peek, PLUGIN_READ_ONLY_ATTRIBUTE, declaration)
        self.commands = {"AC_peek": AC_peek, "AC_poke": AC_poke}


def _rpc(server, method, params=None):
    reply = server.handle_line(json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}))
    return json.loads(reply)


def _listed(server):
    return {tool["name"] for tool in _rpc(server, "tools/list")["result"]["tools"]}


def _call(server, name, arguments=None):
    return _rpc(server, "tools/call", {"name": name, "arguments": arguments or {}})


def _enable(server, mode, *names):
    if mode == "progressive":
        reply = _call(server, "ac_tools_enable", {"names": list(names)})
        assert "result" in reply, reply


def test_the_attribute_name_is_the_documented_one():
    assert PLUGIN_READ_ONLY_ATTRIBUTE == "mcp_read_only"


def test_a_plugin_tool_is_mutating_by_default():
    def AC_plain():
        return 1

    tool = make_plugin_tool("AC_plain", AC_plain)
    assert tool.annotations.read_only is False
    assert tool.annotations.to_dict()["destructiveHint"] is True
    assert capability_for_tool(tool.name, tool.annotations.read_only) == Capability.DRIVE_INPUT


def test_a_declared_tool_is_read_only_and_claims_nothing_else():
    plugin = _Plugin()
    hints = make_plugin_tool("AC_peek", plugin.commands["AC_peek"]).annotations.to_dict()
    assert hints["readOnlyHint"] is True and hints["destructiveHint"] is False
    assert hints["idempotentHint"] is False, "only read-only was declared"
    assert make_plugin_tool("AC_poke", plugin.commands["AC_poke"]).annotations.read_only is False


@pytest.mark.parametrize("declaration", [
    False, None, 1, 1.0, "true", "True", "yes", ["True"], {"read_only": True}, lambda: True,
])
def test_anything_but_the_boolean_true_is_mutating(declaration):
    plugin = _Plugin(declaration)
    assert plugin_declares_read_only(plugin.commands["AC_peek"]) is False
    assert make_plugin_tool("AC_peek", plugin.commands["AC_peek"]).annotations.read_only is False


def test_a_malformed_declaration_is_logged(log_records):
    plugin = _Plugin("yes")
    make_plugin_tool("AC_peek", plugin.commands["AC_peek"])
    assert any("mcp_read_only" in record.getMessage() and "stays mutating" in record.getMessage()
               for record in log_records)


def test_a_declaration_that_raises_is_mutating(log_records):
    class _Raises:
        @property
        def mcp_read_only(self):
            raise RuntimeError("no")

        def __call__(self):
            return 1

    handler = _Raises()
    assert plugin_declares_read_only(handler) is False
    assert make_plugin_tool("AC_odd", handler).annotations.read_only is False
    assert any("stays mutating" in record.getMessage() for record in log_records)


def test_a_bound_method_carries_its_functions_declaration():
    class _Owner:
        def AC_look(self):
            return 1
        AC_look.mcp_read_only = True

    assert make_plugin_tool("AC_look", _Owner().AC_look).annotations.read_only is True


@pytest.mark.parametrize("mode", _MODES)
def test_a_declared_tool_runs_on_a_read_only_server(mode):
    plugin = _Plugin()
    server = MCPServer(tools=[], read_only=True, tool_mode=mode)
    assert register_plugin_tools(server, plugin.commands) == [_PEEK, _POKE]
    _enable(server, mode, _PEEK)
    listed = _listed(server)
    assert _PEEK in listed and _POKE not in listed
    assert _call(server, _PEEK)["result"]["isError"] is False
    assert _call(server, _POKE)["error"]["code"] == -32602
    assert plugin.ran == ["peek"]


@pytest.mark.parametrize("mode", _MODES)
def test_an_undeclared_plugin_tool_still_does_not_run_read_only(mode):
    plugin = _Plugin(declaration=False)
    server = MCPServer(tools=[], read_only=True, tool_mode=mode)
    register_plugin_tools(server, plugin.commands)
    assert not {_PEEK, _POKE} & _listed(server)
    assert "error" in _call(server, _PEEK) and "error" in _call(server, _POKE)
    assert plugin.ran == []


@pytest.mark.parametrize("mode", _MODES)
def test_a_malformed_declaration_does_not_run_read_only(mode):
    plugin = _Plugin(declaration="true")
    server = MCPServer(tools=[], read_only=True, tool_mode=mode)
    register_plugin_tools(server, plugin.commands)
    assert _PEEK not in _listed(server)
    assert _call(server, _PEEK)["error"]["code"] == -32602
    assert plugin.ran == []


def test_a_server_that_is_not_read_only_offers_both():
    plugin = _Plugin()
    server = MCPServer(tools=[])
    register_plugin_tools(server, plugin.commands)
    assert _listed(server) == {_PEEK, _POKE}
    assert _call(server, _POKE)["result"]["isError"] is False


@pytest.mark.parametrize("mode", _MODES)
def test_a_viewer_may_call_the_declared_tool_and_only_that_one(mode):
    plugin = _Plugin()
    server = MCPServer(tools=[], tool_mode=mode)
    register_plugin_tools(server, plugin.commands)
    with authorization_scope(AuthorizationContext("viewer-user", Role.VIEWER)):
        _enable(server, mode, _PEEK)
        listed = _listed(server)
        peek, poke = _call(server, _PEEK), _call(server, _POKE)
    assert _PEEK in listed and _POKE not in listed
    assert peek["result"]["isError"] is False
    assert "error" in poke
    assert plugin.ran == ["peek"]


def test_the_declared_tool_needs_read_screen_and_a_role_without_it_is_refused():
    plugin = _Plugin()
    tools = [make_plugin_tool(name, handler) for name, handler in plugin.commands.items()]
    peek = tools[0]
    assert capability_for_tool(peek.name, peek.annotations.read_only) == Capability.READ_SCREEN
    with authorization_scope(AuthorizationContext("nobody", "no-such-role")):
        assert visible_tools(tools) == []
    with authorization_scope(AuthorizationContext("op", Role.OPERATOR)):
        assert {tool.name for tool in visible_tools(tools)} == {_PEEK, _POKE}
    server = MCPServer(tools=tools)
    with authorization_scope(AuthorizationContext("nobody", "no-such-role")):
        refused = _call(server, _PEEK)
    assert "error" in refused and plugin.ran == []


def test_registration_logs_which_tools_declared_it(log_records):
    plugin = _Plugin()
    register_plugin_tools(MCPServer(tools=[]), plugin.commands)
    declared = [record.getMessage() for record in log_records
                if "trusted, not verified" in record.getMessage()]
    assert len(declared) == 1 and _PEEK in declared[0] and _POKE not in declared[0]


def test_the_watcher_honours_and_logs_the_declaration(tmp_path, log_records):
    marker = tmp_path / "ran.txt"
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "tools.py").write_text(
        "def AC_peek():\n"
        f"    open({str(marker)!r}, 'w').close()\n"
        "    return 'seen'\n"
        "AC_peek.mcp_read_only = True\n"
        "def AC_poke():\n"
        "    raise AssertionError('a mutating plugin tool ran on a read-only server')\n",
        encoding="utf-8")
    server = MCPServer(tools=[], read_only=True)
    PluginWatcher(server, str(plugins)).poll_once()
    assert _listed(server) == {_PEEK}
    assert _call(server, _PEEK)["result"]["isError"] is False
    assert marker.exists()
    assert "error" in _call(server, _POKE)
    assert any("trusted, not verified" in record.getMessage() and _PEEK in record.getMessage()
               for record in log_records)
