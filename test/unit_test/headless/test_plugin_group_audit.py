"""Plugin discovery loads only AutoControl's own entry-point group (2026-09-24 audit).

``group`` came from action files and MCP calls, and discovery calls every
entry point it finds: ``AC_list_plugins`` / ``ac_list_plugins`` (annotated
read-only) with ``group="console_scripts"`` ran the ``main()`` of every
installed command-line tool.
"""
from importlib import metadata

import pytest

from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.plugin_sdk import plugin_sdk


@pytest.fixture
def evil_group(monkeypatch):
    ran = []
    point = metadata.EntryPoint("tool", "evilmod:main", "console_scripts")
    monkeypatch.setattr(metadata, "entry_points",
                        lambda group=None: [point] if group == "console_scripts" else [])
    monkeypatch.setattr(metadata.EntryPoint, "load",
                        lambda self: (lambda: ran.append(self.name) or {}))
    return ran


def test_a_foreign_group_is_refused_before_anything_loads(evil_group):
    with pytest.raises(ValueError, match="entry-point group"):
        plugin_sdk.discover_plugins("console_scripts")
    with pytest.raises(ValueError):
        plugin_sdk.load_plugins("console_scripts")
    assert evil_group == []


def test_the_executor_command_refuses_it_too(evil_group):
    executor.execute_action([["AC_list_plugins", {"group": "console_scripts"}],
                             ["AC_load_plugins", {"group": "console_scripts"}]],
                            raise_on_error=False)
    assert evil_group == []


def test_the_commands_group_and_injected_points_still_work():
    assert isinstance(plugin_sdk.discover_plugins(), dict)
    fake = type("Point", (), {"name": "p", "load": lambda self: (lambda: {"AC_x": print})})()
    assert list(plugin_sdk.discover_plugins("any.group", entry_points=[fake])) == ["AC_x"]
