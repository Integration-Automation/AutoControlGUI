"""Headless tests for Unicode text entry by key events or clipboard. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.text_unicode import (
    plan_paste, plan_unicode_keys, type_unicode, type_unicode_keys,
    type_unicode_text, unicode_code_units,
)
from je_auto_control.utils.text_unicode import text_unicode as tu


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


# --- key injection ---------------------------------------------------------

def test_plan_unicode_keys_is_one_op_per_code_unit():
    assert plan_unicode_keys("a値") == [
        {"op": "unicode_unit", "unit": 97},
        {"op": "unicode_unit", "unit": 0x5024},
    ]
    # astral characters need both surrogates sent separately
    assert plan_unicode_keys("🚀") == [
        {"op": "unicode_unit", "unit": 0xD83D},
        {"op": "unicode_unit", "unit": 0xDE80},
    ]
    assert plan_unicode_keys("") == []


def test_type_unicode_keys_never_touches_the_clipboard():
    # the whole point of the key route: the user's clipboard survives
    events = []
    result = type_unicode_keys("café 🚀", sink=events.append)
    assert {e["op"] for e in events} == {"unicode_unit"}
    assert result["method"] == "keys"
    assert result["ops"] == result["code_units"] == 7


def test_type_unicode_text_picks_keys_when_the_backend_supports_them(monkeypatch):
    monkeypatch.setattr(tu, "unicode_keys_supported", lambda: True)
    events = []
    assert type_unicode_text("値", sink=events.append)["method"] == "keys"
    assert [e["op"] for e in events] == ["unicode_unit"]


def test_type_unicode_text_falls_back_to_paste_without_a_backend(monkeypatch):
    monkeypatch.setattr(tu, "unicode_keys_supported", lambda: False)
    events = []
    assert type_unicode_text("値", sink=events.append)["method"] == "paste"
    assert [e["op"] for e in events] == ["set_clipboard", "hotkey"]


def test_write_falls_back_to_unicode_for_characters_outside_the_key_table():
    # `write` used to raise on the first character missing from the 192-key
    # table — which on a US layout includes `, . / : ? ! _ + @ %` and every CJK
    # character, so a URL or a Chinese sentence failed as a whole.
    from je_auto_control.wrapper import auto_control_keyboard as kb

    sent = []

    class _Backend:
        @staticmethod
        def type_unicode_unit(unit):
            sent.append(unit)

    original = kb.keyboard
    try:
        kb.keyboard = _Backend
        assert kb._write_char_via_unicode("，") is True
    finally:
        kb.keyboard = original
    assert sent == [0xFF0C]


def test_write_sends_newline_and_tab_as_keys_not_characters():
    # U+000A through the Unicode route is dropped by most applications, which
    # silently collapses a multi-line write into one line
    from je_auto_control.wrapper import auto_control_keyboard as kb

    assert kb.WRITE_CONTROL_KEYS["\n"] == "return"
    assert kb.WRITE_CONTROL_KEYS["\r"] == "return"
    assert kb.WRITE_CONTROL_KEYS["\t"] == "tab"
    # Each control character needs *some* key route on this platform, or write()
    # falls through to the space fallback and silently turns a newline into a
    # space. Asserting one spelling is wrong: Windows names backspace "back",
    # X11 names it "backspace" and maps the raw "\b" instead — and write()
    # already copes, because it checks the name against the table before using
    # it. So assert the property that matters, not the spelling.
    for char, name in kb.WRITE_CONTROL_KEYS.items():
        assert (name in kb.keyboard_keys_table
                or char in kb.keyboard_keys_table), (
            f"{char!r} has no key route on this platform: neither {name!r} nor "
            f"the raw character is in keyboard_keys_table, so write() would "
            f"fall through to the space fallback"
        )


def test_write_reports_no_unicode_route_when_the_backend_lacks_one():
    from je_auto_control.wrapper import auto_control_keyboard as kb

    original = kb.keyboard
    try:
        kb.keyboard = object()          # a backend with no unicode entry point
        assert kb._write_char_via_unicode("，") is False
    finally:
        kb.keyboard = original


# --- wiring ---------------------------------------------------------------

def test_executor_adapter_dispatches_via_sink():
    # the executor default dispatch is device-bound; verify the planning the
    # adapter delegates to instead.
    events = []
    type_unicode("値", sink=events.append, modifier="ctrl")
    assert events[-1] == {"op": "hotkey", "keys": ["ctrl", "v"]}


def test_wiring():
    wanted = {"AC_type_unicode", "AC_type_unicode_keys", "AC_type_unicode_text"}
    assert wanted <= set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_type_unicode", "ac_type_unicode_keys",
            "ac_type_unicode_text"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert wanted <= specs


def test_facade_exports():
    for attr in ("type_unicode", "type_unicode_keys", "type_unicode_text",
                 "plan_paste", "plan_unicode_keys", "unicode_code_units",
                 "unicode_keys_supported"):
        assert hasattr(ac, attr) and attr in ac.__all__
