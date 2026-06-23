"""Headless tests for clear-then-type field entry. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.field_entry import plan_field_set, set_field_text


def test_default_plan_clears_then_types():
    plan = plan_field_set("hello")
    assert plan == [
        {"op": "hotkey", "keys": ["ctrl", "a"]},
        {"op": "key", "key": "delete"},
        {"op": "type", "text": "hello"},
    ]


def test_paste_plan_uses_clipboard():
    plan = plan_field_set("café 🚀", paste=True)
    ops = [event["op"] for event in plan]
    assert ops == ["hotkey", "key", "set_clipboard", "hotkey"]
    assert plan[2] == {"op": "set_clipboard", "text": "café 🚀"}
    assert plan[-1]["keys"] == ["ctrl", "v"]


def test_clear_none_skips_clear():
    assert plan_field_set("x", clear="none") == [{"op": "type", "text": "x"}]


def test_modifier_override_for_macos():
    plan = plan_field_set("y", modifier="command")
    assert plan[0]["keys"] == ["command", "a"]


def test_unknown_clear_raises():
    try:
        plan_field_set("z", clear="bogus")
    except ValueError as error:
        assert "clear" in str(error)
    else:                                  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_set_field_text_dispatches_plan():
    events = []
    result = set_field_text("hi", sink=events.append)
    assert result["ops"] == 3
    assert [e["op"] for e in events] == ["hotkey", "key", "type"]


# --- wiring ---------------------------------------------------------------

def test_executor_adapter_planning():
    # the executor's default dispatch is device-bound; exercise the adapter
    # planning + JSON-free path by calling the underlying with an injected sink.
    events = []
    set_field_text("v", paste=True, sink=events.append)
    assert events[-1] == {"op": "hotkey", "keys": ["ctrl", "v"]}


def test_wiring():
    known = ac.executor.known_commands()
    assert "AC_set_field_text" in set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_set_field_text" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_set_field_text" in specs


def test_facade_exports():
    for attr in ("plan_field_set", "set_field_text"):
        assert hasattr(ac, attr) and attr in ac.__all__
