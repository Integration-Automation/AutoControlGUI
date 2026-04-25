"""Tests for the MCP plugin hot-reload watcher."""
import time

from je_auto_control.utils.mcp_server.plugin_watcher import PluginWatcher
from je_auto_control.utils.mcp_server.server import MCPServer


def _write(path, body):
    path.write_text(body, encoding="utf-8")
    # Bump mtime to ensure the watcher picks it up even on coarse FSes.
    now = time.time()
    import os
    os.utime(path, (now, now))


def test_watcher_registers_tools_for_existing_plugins(tmp_path):
    plugin = tmp_path / "demo.py"
    _write(plugin, "def AC_hello(name='world'):\n    return f'hi {name}'\n")
    server = MCPServer(tools=[])
    watcher = PluginWatcher(server, str(tmp_path), poll_seconds=0.1)
    watcher.poll_once()
    assert server._tools.get("plugin_ac_hello") is not None


def test_watcher_picks_up_new_files(tmp_path):
    server = MCPServer(tools=[])
    watcher = PluginWatcher(server, str(tmp_path), poll_seconds=0.1)
    watcher.poll_once()
    plugin = tmp_path / "added.py"
    _write(plugin, "def AC_added():\n    return 'late'\n")
    watcher.poll_once()
    assert "plugin_ac_added" in server._tools


def test_watcher_drops_tools_when_file_removed(tmp_path):
    plugin = tmp_path / "soon.py"
    _write(plugin, "def AC_soon():\n    return 'gone soon'\n")
    server = MCPServer(tools=[])
    watcher = PluginWatcher(server, str(tmp_path), poll_seconds=0.1)
    watcher.poll_once()
    assert "plugin_ac_soon" in server._tools
    plugin.unlink()
    watcher.poll_once()
    assert "plugin_ac_soon" not in server._tools


def test_watcher_reloads_after_mtime_change(tmp_path):
    plugin = tmp_path / "evolving.py"
    _write(plugin, "def AC_evolve():\n    return 1\n")
    server = MCPServer(tools=[])
    watcher = PluginWatcher(server, str(tmp_path), poll_seconds=0.1)
    watcher.poll_once()
    first = server._tools["plugin_ac_evolve"].handler
    # Rewrite with a new function body and bump mtime.
    _write(plugin, "def AC_evolve():\n    return 2\n")
    watcher.poll_once()
    second = server._tools["plugin_ac_evolve"].handler
    assert first is not second


def test_watcher_start_requires_existing_directory(tmp_path):
    server = MCPServer(tools=[])
    watcher = PluginWatcher(server, str(tmp_path / "ghost"))
    try:
        watcher.start()
    except NotADirectoryError:
        pass
    else:
        watcher.stop(timeout=0.5)
        raise AssertionError("expected NotADirectoryError")
