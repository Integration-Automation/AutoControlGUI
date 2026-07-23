"""Round-3 platform regression tests: Windows mouse backend.

Headless — no real mouse/keyboard input is dispatched. The backend layer
(``_send_stroke`` / ``PostMessageW``) is monkeypatched or exercised only
through pure helpers, so nothing touches the OS input APIs.

Covers audit findings:
* #1 ``mouse_keys_table`` must be built from the *selected* backend.
* #2 Interception ``scroll`` must scale a notch count by ``WHEEL_DELTA``.
* #7 ``send_mouse_event_to_window`` must post WM_* messages, not the
  SendInput button tuple.
* #8 ``SendInput.argtypes`` typo (``arg_types``) must be corrected.
"""
import ctypes
import sys
from ctypes import wintypes

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform not in ("win32", "cygwin", "msys"),
    reason="Windows input backend modules only import on Windows.",
)


def test_finding1_mouse_keys_table_built_from_selected_backend():
    """The table reflects the selected backend's flag tuples, not the
    import-time SendInput globals."""
    from je_auto_control.wrapper import _platform_windows as pw
    from je_auto_control.windows.interception import mouse as interception_mouse
    from je_auto_control.windows.mouse import win32_ctype_mouse_control as sendinput_mouse

    table = pw._build_mouse_keys_table(interception_mouse)
    # Built from the module handed in — Interception constants, not SendInput.
    assert table["mouse_left"] == interception_mouse.win32_mouse_left
    assert table["mouse_right"] == interception_mouse.win32_mouse_right
    # Interception bitmasks differ from SendInput dwFlags: proves the
    # distinction the bug erased.
    assert interception_mouse.win32_mouse_left != sendinput_mouse.win32_mouse_left
    assert table["mouse_left"] != sendinput_mouse.win32_mouse_left
    # The live module table matches whatever backend it actually selected.
    assert pw.mouse_keys_table["mouse_left"] == pw.mouse.win32_mouse_left


def test_finding2_interception_scroll_scales_by_wheel_delta(monkeypatch):
    """One notch must move one notch: rolling == value * 120."""
    from je_auto_control.windows.interception import mouse as interception_mouse

    captured = {}

    def _fake_send(state, *, flags=0, x=0, y=0, rolling=0):
        captured["state"] = state
        captured["rolling"] = rolling

    monkeypatch.setattr(interception_mouse, "_send_stroke", _fake_send)
    interception_mouse.scroll(3)
    assert captured["state"] == interception_mouse.MOUSE_WHEEL
    assert captured["rolling"] == 3 * 120


def test_finding7_window_message_translation_not_raw_tuple():
    """The window path resolves a button tuple into integer WM_* messages."""
    from je_auto_control.utils.exception.exceptions import AutoControlException
    from je_auto_control.windows.mouse import win32_ctype_mouse_control as sendinput_mouse

    down, up = sendinput_mouse._resolve_window_messages(sendinput_mouse.win32_mouse_left)
    assert down == (sendinput_mouse.WM_LBUTTONDOWN, sendinput_mouse.MK_LBUTTON)
    assert up == (sendinput_mouse.WM_LBUTTONUP, 0)
    # A window message is an int — never the SendInput dwFlags tuple.
    assert isinstance(down[0], int)
    assert down[0] != sendinput_mouse.win32_mouse_left

    right_down, _ = sendinput_mouse._resolve_window_messages(sendinput_mouse.win32_mouse_right)
    assert right_down[0] == sendinput_mouse.WM_RBUTTONDOWN

    with pytest.raises(AutoControlException):
        sendinput_mouse._resolve_window_messages((9, 9, 9))


def test_finding8_sendinput_argtypes_applied():
    """The ``argtypes`` (not ``arg_types``) attribute must be set."""
    from je_auto_control.windows.core.utils import win32_ctype_input as mod

    assert mod.user32.SendInput.argtypes == (wintypes.UINT, ctypes.c_void_p, ctypes.c_int)
