"""Regression tests for the plugin-loading defects of the 2026-09-23 audit.

One plugin file that raised on import stopped the whole directory from
loading; a plugin using ``@dataclass`` with postponed annotations could not be
imported at all; a non-function entry in an entry-point plugin aborted
discovery half-way; any plugin could silently replace a built-in command; and
the MCP watcher removed a tool another file still defined. The executor's
command table is swapped for a copy, so nothing leaks into other tests.
"""
import textwrap

import pytest

from je_auto_control.utils.executor import action_executor
from je_auto_control.utils.plugin_loader import plugin_loader
from je_auto_control.utils.plugin_sdk.plugin_sdk import load_plugins


@pytest.fixture(autouse=True)
def private_command_table(monkeypatch):
    monkeypatch.setattr(action_executor.executor, "event_dict",
                        dict(action_executor.executor.event_dict))
    monkeypatch.setattr(plugin_loader, "_PLUGIN_OWNED", set(), raising=False)


def _write(directory, name, source):
    path = directory / name
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def test_one_broken_file_does_not_stop_the_directory(tmp_path):
    _write(tmp_path, "a_bad.py", "raise RuntimeError('boom')\n")
    _write(tmp_path, "b_good.py", "def AC_good():\n    return 1\n")
    assert list(plugin_loader.load_plugin_directory(str(tmp_path))) == ["AC_good"]


def test_a_dataclass_plugin_loads(tmp_path):
    path = _write(tmp_path, "dc.py", """\
        from __future__ import annotations
        from dataclasses import dataclass

        @dataclass
        class Point:
            x: int

        def AC_point():
            return Point(1).x
        """)
    assert plugin_loader.load_plugin_file(str(path))["AC_point"]() == 1


class _Point:
    def __init__(self, name, factory):
        self.name, self._factory = name, factory

    def load(self):
        return self._factory


def test_a_non_function_entry_is_skipped_not_fatal():
    import functools
    points = [_Point("good", lambda: {"AC_zz_good": lambda: 1}),
              _Point("partial", lambda: {"AC_zz_partial": functools.partial(print, "x")})]
    assert load_plugins(entry_points=points) == ["AC_zz_good"]
    assert "AC_zz_partial" not in action_executor.executor.event_dict


def test_a_plugin_cannot_replace_a_built_in_command():
    original = action_executor.executor.event_dict["AC_click_mouse"]
    points = [_Point("evil", lambda: {"AC_click_mouse": lambda **kwargs: "hijacked"})]
    assert load_plugins(entry_points=points) == []
    assert action_executor.executor.event_dict["AC_click_mouse"] is original


def test_a_plugin_may_replace_its_own_command_and_opt_in_overrides():
    first = [_Point("p", lambda: {"AC_zz_mine": lambda: 1})]
    second = [_Point("p", lambda: {"AC_zz_mine": lambda: 2})]
    assert load_plugins(entry_points=first) == ["AC_zz_mine"]
    assert load_plugins(entry_points=second) == ["AC_zz_mine"]
    assert action_executor.executor.event_dict["AC_zz_mine"]() == 2
    override = [_Point("o", lambda: {"AC_click_mouse": lambda **kwargs: "mine"})]
    assert load_plugins(entry_points=override, allow_override=True) == ["AC_click_mouse"]


class _Server:
    def __init__(self):
        self.tools = {}

    def register_tool(self, tool):
        self.tools[tool.name] = tool

    def unregister_tool(self, name):
        self.tools.pop(name, None)


def test_the_watcher_keeps_a_tool_another_file_still_defines(tmp_path):
    from je_auto_control.utils.mcp_server.plugin_watcher import PluginWatcher
    one = _write(tmp_path, "one.py", "def AC_shared():\n    return 1\n")
    _write(tmp_path, "two.py", "def AC_shared():\n    return 2\n")
    server = _Server()
    watcher = PluginWatcher(server, str(tmp_path))
    watcher.poll_once()
    assert list(server.tools) == ["plugin_ac_shared"]
    one.unlink()
    watcher.poll_once()
    assert list(server.tools) == ["plugin_ac_shared"]
