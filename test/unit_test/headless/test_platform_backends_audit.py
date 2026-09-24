"""X11, uinput and macOS backend defects from the 2026-09-24 audit (fakes; nothing reaches the desktop).

uinput typed X keycodes as evdev codes (``a`` sent ``KEY_L``); the X11
send-to-window helpers sent two presses; an unbound key sent keycode 0 and
reported success; recorded wheel events became ``None`` actions; macOS media
keys used the shift flag as the key-down flag; a failing Quartz call was
swallowed; an unknown button posted nothing silently; the event tap was
re-enabled through the wrong handle.
"""
import importlib
import sys
import types

import pytest

from je_auto_control.utils.exception.exceptions import (
    AutoControlKeyboardException, AutoControlMouseException,
)


def test_uinput_types_the_evdev_code_for_an_x_keycode(monkeypatch):
    from je_auto_control.linux_with_x11.uinput import keyboard
    emitted = []
    monkeypatch.setattr(keyboard, "emit", lambda *args: emitted.append(args))
    keyboard.press_key(38)            # X keycode of "a" on an evdev keymap
    keyboard.release_key(38)
    assert emitted == [(keyboard.EV_KEY, 30, 1), (keyboard.EV_KEY, 30, 0)]   # KEY_A
    with pytest.raises(AutoControlKeyboardException):
        keyboard.press_key(3)         # below the X server's reserved range


def _x11_module(name):
    if not sys.platform.startswith("linux"):
        pytest.skip("X11 backend")
    try:
        return importlib.import_module(f"je_auto_control.linux_with_x11.{name}")
    except Exception as error:  # noqa: BLE001  # reason: no X server here; the skip says why
        pytest.skip(f"X11 backend not importable: {error!r}")


class _Window:
    def __init__(self):
        self.sent = []

    def send_event(self, event, propagate=False, event_mask=0):
        self.sent.append((event.type, event_mask))


def test_x11_send_to_window_sends_press_then_release(monkeypatch):
    keyboard = _x11_module("keyboard.x11_linux_keyboard_control")
    mouse = _x11_module("mouse.x11_linux_mouse_control")
    from Xlib import X
    window = _Window()
    for module in (keyboard, mouse):
        monkeypatch.setattr(module.display, "create_resource_object", lambda _kind, _id: window)
        monkeypatch.setattr(module.display, "flush", lambda: None)
    keyboard.send_key_event_to_window(7, 38)
    mouse.send_mouse_event_to_window(7, 1)       # x / y default to None
    assert [kind for kind, _mask in window.sent] == [
        X.KeyPress, X.KeyRelease, X.ButtonPress, X.ButtonRelease]
    assert all(mask for _kind, mask in window.sent)


def test_x11_refuses_an_unbound_keycode():
    keyboard = _x11_module("keyboard.x11_linux_keyboard_control")
    with pytest.raises(AutoControlKeyboardException):
        keyboard.press_key(0)


def test_recorded_wheel_events_are_not_none_actions(monkeypatch):
    record = _x11_module("record.x11_linux_record")
    from queue import Queue
    raw = Queue()
    for event in ((5, 4, 10, 20), (5, 5, 10, 20), (5, 1, 30, 40)):
        raw.put(event)
    monkeypatch.setattr(record, "x11_linux_stop_record", lambda: raw)
    actions = list(record.X11LinuxRecorder().stop_record().queue)
    assert actions == [("AC_mouse_left", 30, 40)]


def test_uinput_scroll_follows_the_sign(monkeypatch):
    mouse = _x11_module("uinput.mouse")
    emitted = []
    monkeypatch.setattr(mouse, "emit", lambda *args: emitted.append(args))
    mouse.scroll(-2, int(mouse.x11_linux_scroll_direction_up))
    mouse.scroll(0, int(mouse.x11_linux_scroll_direction_up))
    assert emitted == [(mouse.EV_REL, mouse.REL_WHEEL, -1)] * 2


def _osx(name):
    if sys.platform != "darwin":
        pytest.skip("macOS backend")
    return importlib.import_module(f"je_auto_control.osx.{name}")


def test_a_media_key_press_and_release_are_different_events(monkeypatch):
    keyboard = _osx("keyboard.osx_keyboard")
    import AppKit
    import Quartz
    posted = []
    monkeypatch.setattr(Quartz, "CGEventPost", lambda _tap, event: posted.append(event))
    keyboard.press_key("key_play", False)
    keyboard.release_key("key_play", False)
    states = [(AppKit.NSEvent.eventWithCGEvent_(event).data1() >> 8) & 0xFF for event in posted]
    assert states == [0xA, 0xB]


def test_a_failing_quartz_call_is_a_keyboard_error(monkeypatch):
    keyboard = _osx("keyboard.osx_keyboard")
    import Quartz

    def refuse(*_args):
        raise ValueError("bad keycode")

    monkeypatch.setattr(Quartz, "CGEventCreateKeyboardEvent", refuse)
    with pytest.raises(AutoControlKeyboardException):
        keyboard.press_key(5, False)


def test_an_unknown_mouse_button_is_refused():
    mouse = _osx("mouse.osx_mouse")
    with pytest.raises(AutoControlMouseException):
        mouse.press_mouse(10, 10, 99)


def test_the_tap_is_re_enabled_through_its_own_handle(monkeypatch):
    listener = _osx("listener.osx_listener")
    import Quartz
    enabled = []
    monkeypatch.setattr(Quartz, "CGEventTapEnable", lambda tap, on: enabled.append((tap, on)))
    tap = listener.OSXInputTap()
    tap._tap = types.SimpleNamespace(name="the tap")
    tap._callback("proxy", Quartz.kCGEventTapDisabledByTimeout, None, None)
    assert enabled == [(tap._tap, True)]
