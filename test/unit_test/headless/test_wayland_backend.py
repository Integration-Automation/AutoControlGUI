"""Headless tests for the Wayland backend skeleton.

All tests run on any host because:

* detection uses ``os.environ`` so we inject a fake dict;
* every CLI invocation is patched out, so neither wtype/ydotool/grim
  needs to be installed to validate the dispatch logic.
"""
import subprocess
from unittest.mock import patch

import pytest

from je_auto_control.linux_wayland import (
    _detect, keyboard as wayland_keyboard, mouse as wayland_mouse,
    screen as wayland_screen,
)
from je_auto_control.linux_wayland.keymap import keyboard_keys_table
from je_auto_control.utils.exception.exceptions import AutoControlException


# === Detection ==============================================================

def test_is_wayland_session_reads_session_type():
    env = {"XDG_SESSION_TYPE": "wayland"}
    assert _detect.is_wayland_session(env) is True


def test_is_wayland_session_reads_wayland_display():
    env = {"WAYLAND_DISPLAY": "wayland-0"}
    assert _detect.is_wayland_session(env) is True


def test_is_wayland_session_false_for_x11():
    env = {"XDG_SESSION_TYPE": "x11"}
    assert _detect.is_wayland_session(env) is False


def test_select_display_server_auto_picks_wayland():
    env = {"XDG_SESSION_TYPE": "wayland"}
    assert _detect.select_display_server(env) == "wayland"


def test_select_display_server_override_x11_wins_over_env():
    env = {
        "XDG_SESSION_TYPE": "wayland",
        "JE_AUTOCONTROL_LINUX_DISPLAY_SERVER": "x11",
    }
    assert _detect.select_display_server(env) == "x11"


def test_select_display_server_override_wayland_on_x11_session():
    env = {
        "XDG_SESSION_TYPE": "x11",
        "JE_AUTOCONTROL_LINUX_DISPLAY_SERVER": "wayland",
    }
    assert _detect.select_display_server(env) == "wayland"


def test_select_display_server_invalid_override_falls_through():
    env = {
        "XDG_SESSION_TYPE": "x11",
        "JE_AUTOCONTROL_LINUX_DISPLAY_SERVER": "garbage",
    }
    assert _detect.select_display_server(env) == "x11"


def test_missing_dependencies_returns_absent_names():
    with patch.object(_detect.shutil, "which",
                      side_effect=lambda name: None if name == "missing"
                      else "/usr/bin/" + name):
        assert _detect.missing_dependencies(
            ["wtype", "missing", "grim"],
        ) == ["missing"]


# === Keymap ================================================================

def test_keymap_includes_enter_and_alpha_and_digits():
    assert keyboard_keys_table["enter"] == 28
    assert keyboard_keys_table["a"] == keyboard_keys_table["A"]
    assert keyboard_keys_table["0"] == 11
    assert keyboard_keys_table["1"] == 2


def test_keymap_function_keys_present():
    assert keyboard_keys_table["f1"] == 59
    assert keyboard_keys_table["f12"] == 88
    assert keyboard_keys_table["f24"] == 194


# === Keyboard dispatch =====================================================

def _fake_run(captured):
    def runner(argv, **_kwargs):
        captured.append(list(argv))
        # CompletedProcess is a *constructor* (not a process spawn);
        # used here to mock subprocess.run's return value.
        # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
        result = subprocess.CompletedProcess(argv, 0, b"", b"")
        return result
    return runner


def test_press_key_invokes_ydotool_with_keydown_suffix():
    captured: list = []
    with patch.object(wayland_keyboard, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_keyboard.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_keyboard.press_key(28)
    assert captured == [["/usr/bin/ydotool", "key", "28:1"]]


def test_release_key_invokes_ydotool_with_keyup_suffix():
    captured: list = []
    with patch.object(wayland_keyboard, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_keyboard.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_keyboard.release_key(28)
    assert captured == [["/usr/bin/ydotool", "key", "28:0"]]


def test_write_invokes_wtype_with_text():
    captured: list = []
    with patch.object(wayland_keyboard, "binary_path",
                      return_value="/usr/bin/wtype"), \
         patch.object(wayland_keyboard.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_keyboard.write("hello")
    assert captured == [["/usr/bin/wtype", "--", "hello"]]


def test_hotkey_chord_presses_in_order_releases_reverse():
    captured: list = []
    with patch.object(wayland_keyboard, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_keyboard.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_keyboard.hotkey([29, 46])  # ctrl + c
    assert captured == [[
        "/usr/bin/ydotool", "key",
        "29:1", "46:1", "46:0", "29:0",
    ]]


def test_keyboard_raises_clear_error_when_ydotool_missing():
    with patch.object(wayland_keyboard, "binary_path", return_value=None):
        with pytest.raises(AutoControlException, match="ydotool"):
            wayland_keyboard.press_key(28)


def test_keyboard_raises_when_wtype_missing():
    with patch.object(wayland_keyboard, "binary_path", return_value=None):
        with pytest.raises(AutoControlException, match="wtype"):
            wayland_keyboard.write("hi")


def test_press_key_rejects_non_integer():
    with pytest.raises(ValueError):
        wayland_keyboard.press_key("28")  # type: ignore[arg-type]


def test_press_key_rejects_non_positive():
    with pytest.raises(ValueError):
        wayland_keyboard.press_key(0)


def test_send_key_event_to_window_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        wayland_keyboard.send_key_event_to_window(1234, 28)


# === Mouse dispatch =========================================================

def test_set_position_invokes_ydotool_mousemove():
    captured: list = []
    with patch.object(wayland_mouse, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_mouse.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_mouse.set_position(120, 240)
    assert captured == [[
        "/usr/bin/ydotool", "mousemove", "--absolute",
        "-x", "120", "-y", "240",
    ]]


def test_click_mouse_can_move_first():
    captured: list = []
    with patch.object(wayland_mouse, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_mouse.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_mouse.click_mouse(wayland_mouse.wayland_mouse_left,
                                   x=10, y=20)
    assert captured[0][1] == "mousemove"
    assert captured[1][1] == "click"


def test_press_mouse_sets_hold_bit():
    captured: list = []
    with patch.object(wayland_mouse, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_mouse.subprocess, "run",
                      side_effect=_fake_run(captured)):
        wayland_mouse.press_mouse(wayland_mouse.wayland_mouse_left)
    # 0xC0 | 0x40 = 0xC0 (hold bit already set); confirm hex format.
    assert captured[-1][-1].startswith("0x")


def test_position_query_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        wayland_mouse.position()


def test_send_mouse_to_window_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        wayland_mouse.send_mouse_event_to_window()


def test_mouse_raises_when_ydotool_missing():
    with patch.object(wayland_mouse, "binary_path", return_value=None):
        with pytest.raises(AutoControlException, match="ydotool"):
            wayland_mouse.set_position(0, 0)


# === Screen dispatch ========================================================

def test_screenshot_calls_grim_with_path():
    captured: list = []
    # CompletedProcess constructor used to mock subprocess.run.
    with patch.object(wayland_screen, "binary_path",
                      return_value="/usr/bin/grim"), \
         patch.object(wayland_screen.subprocess, "run",
                      # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                      side_effect=lambda argv, **kw: (captured.append(argv)
                       or subprocess.CompletedProcess(argv, 0, b"", b""))):
        wayland_screen.screenshot("out.png")
    assert captured == [["/usr/bin/grim", "out.png"]]


def test_screenshot_passes_screen_region():
    captured: list = []
    with patch.object(wayland_screen, "binary_path",
                      return_value="/usr/bin/grim"), \
         patch.object(wayland_screen.subprocess, "run",
                      side_effect=lambda argv, **kw: (captured.append(argv)
                       or subprocess.CompletedProcess(argv, 0, b"", b""))):
        wayland_screen.screenshot("out.png", screen_region=[10, 20, 110, 220])
    assert captured == [[
        "/usr/bin/grim", "-g", "10,20 100x200", "out.png",
    ]]


def test_screen_size_uses_wlr_randr_when_available():
    with patch.object(wayland_screen, "binary_path",
                      side_effect=lambda name: "/usr/bin/" + name), \
         patch.object(
            wayland_screen.subprocess, "run",
            return_value=subprocess.CompletedProcess(
                ["wlr-randr"], 0, b" HDMI-A-1 1920x1080@60.000Hz\n", b"",
            ),
        ):
        assert wayland_screen.screen_size() == (1920, 1080)


def test_screenshot_raises_when_grim_missing():
    with patch.object(wayland_screen, "binary_path", return_value=None):
        with pytest.raises(AutoControlException, match="grim"):
            wayland_screen.screenshot("out.png")


# === Listener / record stubs ===============================================

def test_listener_raises_not_implemented():
    from je_auto_control.linux_wayland import listener
    with pytest.raises(NotImplementedError):
        listener.check_key_press()
    with pytest.raises(NotImplementedError):
        listener.hook_keyboard()


def test_recorder_raises_not_implemented():
    from je_auto_control.linux_wayland.record import wayland_recorder
    with pytest.raises(NotImplementedError):
        wayland_recorder.record()
    with pytest.raises(NotImplementedError):
        wayland_recorder.stop_record()


# === Wrapper module skeleton ==============================================

def test_platform_wayland_wrapper_exports_expected_names():
    from je_auto_control.wrapper import _platform_wayland as wrapper
    for name in ("keyboard", "keyboard_check", "keyboard_keys_table",
                  "mouse", "mouse_keys_table", "special_mouse_keys_table",
                  "screen", "recorder"):
        assert hasattr(wrapper, name)
    assert wrapper.mouse_keys_table["mouse_left"] == \
        wayland_mouse.wayland_mouse_left
