"""Headless tests for canonical computer-use action mapping. No Qt."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.cua_action import (
    canonical_action, from_anthropic, from_openai_cua, to_ac_command,
)
from je_auto_control.utils.exception.exceptions import AutoControlActionException


def test_canonical_action_drops_none():
    assert canonical_action("click", x=1, y=2, text=None) == {"type": "click",
                                                              "x": 1, "y": 2}


def test_from_anthropic_click_key_scroll():
    assert from_anthropic({"action": "left_click", "coordinate": [100, 200]}) == {
        "type": "click", "x": 100, "y": 200}
    assert from_anthropic({"action": "key", "text": "ctrl+s"}) == {
        "type": "key", "text": "ctrl+s"}
    scroll = from_anthropic({"action": "scroll", "coordinate": [10, 20],
                             "scroll_direction": "down", "scroll_amount": 3})
    assert scroll["type"] == "scroll" and scroll["amount"] == 3


def test_from_openai_click_button_and_keypress():
    assert from_openai_cua({"type": "click", "x": 5, "y": 6,
                            "button": "right"})["type"] == "right_click"
    assert from_openai_cua({"type": "keypress", "keys": ["ctrl", "c"]}) == {
        "type": "key", "text": "ctrl+c"}


def test_to_ac_command_click_key_scroll():
    assert to_ac_command({"type": "click", "x": 100, "y": 200}) == [
        "AC_click_mouse", {"mouse_keycode": "mouse_left", "x": 100, "y": 200}]
    assert to_ac_command({"type": "key", "text": "ctrl+s"}) == [
        "AC_hotkey", {"key_code_list": ["ctrl", "s"]}]
    assert to_ac_command({"type": "type", "text": "hi"}) == [
        "AC_write", {"write_string": "hi"}]
    assert to_ac_command({"type": "scroll", "x": 1, "y": 2, "scroll_y": 120}) == [
        "AC_mouse_scroll", {"scroll_value": -120, "x": 1, "y": 2}]


def test_to_ac_command_applies_scale():
    assert to_ac_command({"type": "move", "x": 50, "y": 60},
                         scale=lambda x, y: (x * 2, y * 2)) == [
        "AC_set_mouse_position", {"x": 100, "y": 120}]


def test_to_ac_command_unsupported_raises():
    with pytest.raises(AutoControlActionException):
        to_ac_command({"type": "wait"})


def test_round_trip_anthropic_to_ac():
    canonical = from_anthropic({"action": "right_click", "coordinate": [7, 8]})
    assert to_ac_command(canonical) == [
        "AC_click_mouse", {"mouse_keycode": "mouse_right", "x": 7, "y": 8}]


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_cua_command" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_cua_command" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_cua_command" in specs


def test_executor_normalizes_and_maps():
    from je_auto_control.utils.executor.action_executor import _cua_command
    result = _cua_command({"action": "left_click", "coordinate": [3, 4]},
                          source="anthropic")
    assert result["command"] == ["AC_click_mouse",
                                 {"mouse_keycode": "mouse_left", "x": 3, "y": 4}]


def test_facade_exports():
    for attr in ("canonical_action", "from_anthropic", "from_openai_cua",
                 "to_ac_command"):
        assert hasattr(ac, attr) and attr in ac.__all__
