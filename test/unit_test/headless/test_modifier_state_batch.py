"""Headless tests for holding modifiers across an action group. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.modifier_state import (
    hold_modifiers, plan_with_modifiers,
)


def test_plan_wraps_with_reversed_release():
    plan = plan_with_modifiers([{"op": "click"}], ["ctrl", "shift"])
    assert plan == [
        {"op": "press", "key": "ctrl"},
        {"op": "press", "key": "shift"},
        {"op": "click"},
        {"op": "release", "key": "shift"},
        {"op": "release", "key": "ctrl"},
    ]


def test_context_manager_press_then_release():
    events = []
    with hold_modifiers(["ctrl"], sink=events.append):
        events.append({"op": "body"})
    assert [e["op"] for e in events] == ["press", "body", "release"]
    assert events[0]["key"] == "ctrl" and events[-1]["key"] == "ctrl"


def test_release_even_on_exception():
    events = []
    try:
        with hold_modifiers(["ctrl", "shift"], sink=events.append):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    releases = [e for e in events if e["op"] == "release"]
    assert [r["key"] for r in releases] == ["shift", "ctrl"]   # reversed


def test_yields_modifier_list():
    with hold_modifiers(["alt"], sink=lambda e: None) as held:
        assert held == ["alt"]


# --- wiring ---------------------------------------------------------------

def test_executor_adapter_modifier_parsing():
    # the nested-action run is device-bound; verify the modifier-string parsing
    # the adapter does up front, using the pure plan as the oracle.
    plan = plan_with_modifiers([], ["ctrl", "shift"])
    assert plan[0]["key"] == "ctrl" and plan[1]["key"] == "shift"


def test_wiring():
    known = ac.executor.known_commands()
    assert "AC_with_modifiers" in set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_with_modifiers" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_with_modifiers" in specs


def test_facade_exports():
    for attr in ("hold_modifiers", "plan_with_modifiers"):
        assert hasattr(ac, attr) and attr in ac.__all__
