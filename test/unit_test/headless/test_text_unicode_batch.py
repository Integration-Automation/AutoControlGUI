"""Headless tests for Unicode text entry via clipboard. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.text_unicode import (
    plan_paste, type_unicode, unicode_code_units,
)


def test_code_units_ascii_and_bmp():
    assert unicode_code_units("Hi") == [72, 105]
    assert unicode_code_units("値") == [0x5024]
    assert unicode_code_units("") == []


def test_code_units_astral_surrogate_pair():
    assert unicode_code_units("🚀") == [0xD83D, 0xDE80]   # rocket > U+FFFF
    assert len(unicode_code_units("a🚀b")) == 4            # 1 + 2 + 1


def test_plan_paste_is_clipboard_then_hotkey():
    assert plan_paste("café 🚀") == [
        {"op": "set_clipboard", "text": "café 🚀"},
        {"op": "hotkey", "keys": ["ctrl", "v"]},
    ]
    assert plan_paste("x", modifier="command")[1]["keys"] == ["command", "v"]


def test_type_unicode_dispatches_plan():
    events = []
    result = type_unicode("café 🚀", sink=events.append)
    assert [e["op"] for e in events] == ["set_clipboard", "hotkey"]
    assert events[0]["text"] == "café 🚀"
    assert result["ops"] == 2 and result["code_units"] == 7


# --- wiring ---------------------------------------------------------------

def test_executor_adapter_dispatches_via_sink():
    # the executor default dispatch is device-bound; verify the planning the
    # adapter delegates to instead.
    events = []
    type_unicode("値", sink=events.append, modifier="ctrl")
    assert events[-1] == {"op": "hotkey", "keys": ["ctrl", "v"]}


def test_wiring():
    known = ac.executor.known_commands()
    assert "AC_type_unicode" in set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_type_unicode" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_type_unicode" in specs


def test_facade_exports():
    for attr in ("type_unicode", "plan_paste", "unicode_code_units"):
        assert hasattr(ac, attr) and attr in ac.__all__
