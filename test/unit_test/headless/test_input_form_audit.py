"""Input / form helper defects from the 2026-09-24 audit (fakes only).

The linter called flow-control commands unknown and never looked inside their
bodies, and disagreed with the executor on item shapes; a gamepad click sent
no press and the dpad called an API vgamepad does not have; xclip's error
killed the clipboard poller and a dialog timeout escaped; CUA key names,
double clicks and sideways scrolls were mistranslated; compiled
postconditions had no before frame; the RTF reader ignored the code page and
text symbols; an unknown easing fell back to linear; a negative pause gave
negative delays.
"""
import enum
import subprocess

import pytest

from je_auto_control.utils.action_lint.linter import ActionLinter
from je_auto_control.utils.clipboard_history.clipboard_history import ClipboardHistory
from je_auto_control.utils.clipboard_rich_formats.clipboard_rich_formats import rtf_to_text
from je_auto_control.utils.cua_action import cua_action
from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.file_dialog.file_dialog import FileDialogDriver
from je_auto_control.utils.gamepad import _facade
from je_auto_control.utils.humanize.typing import humanized_key_delays
from je_auto_control.utils.postcondition.postcondition import compile_postcondition
from je_auto_control.utils.tween_drag.tween_drag import tween_points


def _codes(issues):
    return [(issue.code, issue.message) for issue in issues]


def test_block_commands_are_known_and_their_bodies_are_linted():
    issues = ActionLinter().lint_actions(
        [["AC_loop", {"times": 2, "body": [["AC_nope"], ["AC_sleep", {"seconds": 1}]]}]])
    assert [code for code, _m in _codes(issues)] == ["unknown-command"]
    assert "AC_loop.body[0]" in issues[0].message


def test_item_shapes_match_the_executor():
    linter = ActionLinter()
    assert linter.lint_actions([["AC_set_mouse_position", [1, 2]]]) == []
    codes = [issue.code for issue in linter.lint_actions([
        ["AC_set_mouse_position", {"x": 1, "y": 2}, 5], ["AC_set_mouse_position", ""]])]
    assert codes == ["bad-shape", "bad-params"]


class _XUSB(enum.IntFlag):
    XUSB_GAMEPAD_DPAD_UP = 1
    XUSB_GAMEPAD_DPAD_DOWN = 2
    XUSB_GAMEPAD_DPAD_LEFT = 4
    XUSB_GAMEPAD_DPAD_RIGHT = 8
    XUSB_GAMEPAD_A = 0x1000


class _Pad:
    """Like vgamepad's VX360Gamepad: a report of held buttons, sent by update()."""

    def __init__(self):
        self.held, self.reports = 0, []

    def press_button(self, button):
        self.held |= int(button)

    def release_button(self, button):
        self.held &= ~int(button)

    def update(self):
        self.reports.append(self.held)


def _gamepad():
    pad = _facade.VirtualGamepad.__new__(_facade.VirtualGamepad)
    pad._pad, pad._closed = _Pad(), False
    pad._vg = type("VG", (), {"XUSB_BUTTON": _XUSB})
    return pad


def test_a_gamepad_click_sends_a_press_then_a_release(monkeypatch):
    pad = _gamepad()
    monkeypatch.setattr(pad, "_resolve_button", lambda _name: _XUSB.XUSB_GAMEPAD_A)
    pad.click_button("a")
    assert pad._pad.reports == [0x1000, 0]


def test_dpad_diagonals_hold_two_buttons_and_none_releases():
    pad = _gamepad()
    pad.set_dpad("up_left")
    assert pad._pad.reports[-1] == 1 | 4
    pad.set_dpad("down")
    assert pad._pad.reports[-1] == 2
    pad.set_dpad("none")
    assert pad._pad.reports[-1] == 0


def test_a_failing_clipboard_tool_is_a_missed_capture(monkeypatch):
    from je_auto_control.utils.clipboard import clipboard

    def fail():
        raise subprocess.CalledProcessError(1, ["xclip", "-o"])

    monkeypatch.setattr(clipboard, "get_clipboard", fail)
    assert ClipboardHistory().capture_once() is False


def test_a_dialog_timeout_is_not_handled_rather_than_raised(monkeypatch):
    from je_auto_control.wrapper import auto_control_window

    def timeout(_title, timeout=None):
        raise AutoControlActionException("window did not appear")

    monkeypatch.setattr(auto_control_window, "wait_for_window", timeout)
    assert FileDialogDriver().wait_window("Open", 0.1) is False


_WIN32 = {"return": 1, "escape": 1, "ctrl": 1, "control": 1, "next": 1, "back": 1,
          "menu": 1, "lwin": 1, "tab": 1, "s": 1}


def test_cua_keys_resolve_to_this_platforms_names(monkeypatch):
    monkeypatch.setattr(cua_action, "_platform_key_table", lambda: _WIN32)
    command = cua_action.to_ac_command(cua_action.from_openai_cua(
        {"type": "keypress", "keys": ["CTRL", "ENTER"]}))
    assert command == ["AC_hotkey", {"key_code_list": ["ctrl", "return"]}]
    command = cua_action.to_ac_command({"type": "key", "text": "alt+Page_Down+BackSpace"})
    assert command[1]["key_code_list"] == ["menu", "next", "back"]
    assert cua_action.split_key_combo("ctrl++") == ["ctrl", "+"]


def test_a_double_click_clicks_twice():
    command = cua_action.to_ac_command({"type": "double_click", "x": 1, "y": 2})
    assert command[0] == "AC_loop" and command[1]["times"] == 2


def test_scrolls_carry_their_direction(monkeypatch):
    from je_auto_control.wrapper import platform_wrapper
    up = cua_action.to_ac_command(cua_action.from_anthropic(
        {"action": "scroll", "scroll_direction": "up", "scroll_amount": 3}))
    assert up[1] == {"scroll_value": 3, "scroll_direction": "scroll_up"}
    monkeypatch.setattr(platform_wrapper, "special_mouse_keys_table", {"scroll_left": 6})
    left = cua_action.to_ac_command(cua_action.from_anthropic(
        {"action": "scroll", "scroll_direction": "left", "scroll_amount": 3}))
    assert left[1] == {"scroll_value": 3, "scroll_direction": "scroll_left"}
    monkeypatch.setattr(platform_wrapper, "special_mouse_keys_table", None)
    with pytest.raises(AutoControlActionException, match="horizontal"):
        cua_action.to_ac_command(cua_action.from_openai_cua(
            {"type": "scroll", "scroll_x": 5, "scroll_y": 0}))


def test_a_compiled_postcondition_uses_its_before_frame():
    before = [{"name": "Spinner"}]
    assert compile_postcondition({"disappears": {"name": "Spinner"}}, before=before)([])
    assert not compile_postcondition({"appears": {"name": "Spinner"}}, before=before)(before)


def test_rtf_reader_honours_the_code_page_and_text_symbols():
    assert rtf_to_text(r"{\rtf1\ansi\ansicpg936 \'b0\'a1}") == chr(0x554A)
    assert rtf_to_text(r"{\rtf1 x\line y\~z\emdash w}") == "x\ny" + chr(0xA0) + "z" + chr(0x2014) + "w"
    assert rtf_to_text(r"{\rtf1 a\par-b}") == "a\n-b"


def test_an_unknown_easing_is_an_error():
    with pytest.raises(ValueError, match="easing"):
        tween_points((0, 0), (10, 10), 5, "ease-in-out")


def test_a_negative_pause_never_makes_a_negative_delay():
    delays = humanized_key_delays("ab", pause_chance=1, pause_delay=-1, seed=1)
    assert all(delay >= 0 for delay in delays)
