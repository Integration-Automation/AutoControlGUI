"""Headless tests for the plugin SDK (entry-point discovery of AC_* commands).
The entry-point source is injected, so no real plugin is installed. Pure
stdlib; no Qt imports."""
import je_auto_control as ac
from je_auto_control.utils.plugin_sdk import discover_plugins, load_plugins


class _FakeEP:
    """Minimal stand-in for an importlib.metadata EntryPoint."""

    def __init__(self, name, factory):
        self.name = name
        self._factory = factory

    def load(self):
        return self._factory


def _good_factory():
    return {"AC_plugin_demo": lambda: {"ok": True}}


def _broken_factory():
    raise ImportError("missing dependency")


def test_discover_merges_command_mappings():
    eps = [_FakeEP("demo", _good_factory)]
    commands = discover_plugins(entry_points=eps)
    assert "AC_plugin_demo" in commands
    assert callable(commands["AC_plugin_demo"])


def test_discover_skips_broken_plugins():
    eps = [_FakeEP("bad", _broken_factory), _FakeEP("ok", _good_factory)]
    commands = discover_plugins(entry_points=eps)
    assert list(commands) == ["AC_plugin_demo"]      # broken one skipped


def test_discover_empty_when_no_entry_points():
    assert discover_plugins(entry_points=[]) == {}


def test_load_registers_into_executor():
    eps = [_FakeEP("demo", lambda: {"AC_plugin_loaded": lambda: {"v": 1}})]
    loaded = load_plugins(entry_points=eps)
    assert loaded == ["AC_plugin_loaded"]
    assert "AC_plugin_loaded" in ac.executor.known_commands()
    # the registered command is callable through the executor
    rec = ac.execute_action([["AC_plugin_loaded", {}]])
    assert any("'v': 1" in str(v) for v in rec.values())


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_list_plugins", "AC_load_plugins"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_list_plugins", "ac_load_plugins"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_list_plugins", "AC_load_plugins"} <= cmds


def test_facade_exports():
    for attr in ("discover_plugins", "load_plugins", "COMMANDS_GROUP"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
