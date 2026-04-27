"""Keyboard input via the Interception driver.

Public surface mirrors :mod:`win32_ctype_keyboard_control` so the
platform wrapper can swap modules at import time without touching
callers.
"""
from __future__ import annotations

import ctypes
import sys

from je_auto_control.utils.exception.exception_tags import (
    windows_import_error_message,
)
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.windows.interception._dll import (
    KEY_DOWN, KEY_E0, KEY_UP, InterceptionKeyStroke,
    InterceptionUnavailable, default_keyboard_device, load_context,
    vk_to_scancode,
)

if sys.platform not in ("win32", "cygwin", "msys"):
    raise AutoControlException(windows_import_error_message)


def _send_stroke(scancode: int, *, key_up: bool, extended: bool) -> None:
    """Push one keystroke through the Interception driver."""
    dll, ctx = load_context()
    state = (KEY_UP if key_up else KEY_DOWN) | (KEY_E0 if extended else 0)
    stroke = InterceptionKeyStroke(
        code=scancode & 0xFFFF,
        state=state,
        information=0,
    )
    sent = dll.interception_send(
        ctx, default_keyboard_device(),
        ctypes.byref(stroke), 1,
    )
    if sent != 1:
        raise InterceptionUnavailable(
            "interception_send returned 0 — the device id "
            f"{default_keyboard_device()!r} is likely wrong; set "
            "JE_AUTOCONTROL_INTERCEPTION_KEYBOARD to a valid id "
            "(1–10)."
        )


def press_key(keycode: int) -> None:
    """Press ``keycode`` (a Win32 VK code) via the Interception driver."""
    scancode, extended = vk_to_scancode(int(keycode))
    _send_stroke(scancode, key_up=False, extended=extended)


def release_key(keycode: int) -> None:
    """Release ``keycode`` (a Win32 VK code) via the Interception driver."""
    scancode, extended = vk_to_scancode(int(keycode))
    _send_stroke(scancode, key_up=True, extended=extended)


def send_key_event_to_window(window: str, keycode: int) -> None:
    """Inject a press+release pair for ``window``.

    Interception talks to the kernel HID stack, not a single window —
    so the targeted-window contract degrades to "press at the focused
    window". Caller is expected to focus the window first via the
    standard window-manager helpers.
    """
    del window  # see docstring; kept for API parity with SendInput backend
    press_key(int(keycode))
    release_key(int(keycode))
