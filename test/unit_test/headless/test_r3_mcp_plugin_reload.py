"""Round-3 regression: plugin hot-reload must survive broken plugins.

``_reload_file`` unregistered the file's existing tools *before* loading and
caught only ``(OSError, ImportError, SyntaxError)`` — a plugin whose module
body raised a runtime error (e.g. ``NameError``) or whose tool construction
failed killed the watcher thread and left the tools vanished. Separately, a
whitespace-only docstring made ``make_plugin_tool`` raise ``IndexError``.
"""
import time

from je_auto_control.utils.mcp_server.plugin_watcher import PluginWatcher
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools.plugin_tools import make_plugin_tool


def _write(path, body):
    import os
    previous = path.stat().st_mtime if path.exists() else 0.0
    path.write_text(body, encoding="utf-8")
    now = max(time.time(), previous + 1.0)
    os.utime(path, (now, now))


def test_broken_reload_keeps_previous_tools_and_watcher_alive(tmp_path):
    plugin = tmp_path / "evolving.py"
    _write(plugin, "def AC_ok():\n    return 'v1'\n")
    server = MCPServer(tools=[])
    watcher = PluginWatcher(server, str(tmp_path), poll_seconds=0.1)
    watcher.poll_once()
    assert "plugin_ac_ok" in server._tools

    # Overwrite with a module that raises at import time (NameError is not in
    # the old narrow catch tuple). poll_once must not raise and must retain
    # the previously-registered tool rather than dropping it.
    _write(plugin, "undefined_symbol_at_module_level\n")
    watcher.poll_once()
    assert "plugin_ac_ok" in server._tools


def test_valid_reload_after_recovery_swaps_tools(tmp_path):
    plugin = tmp_path / "recover.py"
    _write(plugin, "def AC_thing():\n    return 1\n")
    server = MCPServer(tools=[])
    watcher = PluginWatcher(server, str(tmp_path), poll_seconds=0.1)
    watcher.poll_once()
    _write(plugin, "boom_undefined\n")   # broken edit
    watcher.poll_once()
    _write(plugin, "def AC_thing():\n    return 2\n")  # fixed edit
    watcher.poll_once()
    assert server._tools["plugin_ac_thing"].handler() == 2


def test_make_plugin_tool_handles_whitespace_only_docstring():
    def handler():
        return None
    handler.__doc__ = "   \n   \t  "
    tool = make_plugin_tool("AC_ws", handler)
    assert tool.description == "Plugin command 'AC_ws'."


def test_make_plugin_tool_uses_first_docstring_line():
    def handler():
        return None
    handler.__doc__ = "First line summary.\nMore detail."
    tool = make_plugin_tool("AC_doc", handler)
    assert tool.description == "First line summary."
