"""Mouse input via the Interception driver.

Public surface mirrors :mod:`win32_ctype_mouse_control` so the
platform wrapper can swap modules at import time:

* Button-flag tuples ``win32_mouse_left`` / ``_middle`` / ``_right`` /
  ``_x1`` / ``_x2`` reuse the original variable names but carry the
  Interception flag bits instead of the SendInput dwFlags.
* :func:`set_position` / :func:`position` go through ``user32`` exactly
  like the SendInput backend — the cursor coordinate APIs in the
  Interception driver are stroke-based and would force callers to
  poll, which would break the contract callers already rely on.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import windll, wintypes
from typing import Optional, Tuple

from je_auto_control.utils.exception.exception_tags import (
    windows_import_error_message,
)
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.windows.interception._dll import (
    InterceptionMouseStroke, InterceptionUnavailable,
    MOUSE_BUTTON4_DOWN, MOUSE_BUTTON4_UP,
    MOUSE_BUTTON5_DOWN, MOUSE_BUTTON5_UP,
    MOUSE_LEFT_DOWN, MOUSE_LEFT_UP,
    MOUSE_MIDDLE_DOWN, MOUSE_MIDDLE_UP,
    MOUSE_MOVE_ABSOLUTE, MOUSE_RIGHT_DOWN, MOUSE_RIGHT_UP,
    MOUSE_WHEEL,
    default_mouse_device, load_context,
)
from je_auto_control.windows.screen.win32_screen import size

if sys.platform not in ("win32", "cygwin", "msys"):
    raise AutoControlException(windows_import_error_message)


# Button tuples — same shape as the SendInput backend
# (release_flag, press_flag, mouse_data) so the wrapper can swap
# modules without touching dispatch tables.
win32_mouse_left: Tuple[int, int, int] = (MOUSE_LEFT_UP, MOUSE_LEFT_DOWN, 0)
win32_mouse_middle: Tuple[int, int, int] = (MOUSE_MIDDLE_UP, MOUSE_MIDDLE_DOWN, 0)
win32_mouse_right: Tuple[int, int, int] = (MOUSE_RIGHT_UP, MOUSE_RIGHT_DOWN, 0)
win32_mouse_x1: Tuple[int, int, int] = (MOUSE_BUTTON4_UP, MOUSE_BUTTON4_DOWN, 0)
win32_mouse_x2: Tuple[int, int, int] = (MOUSE_BUTTON5_UP, MOUSE_BUTTON5_DOWN, 0)

_user32 = windll.user32
_get_cursor_pos = _user32.GetCursorPos
_set_cursor_pos = _user32.SetCursorPos


def _to_absolute(x: int, y: int) -> Tuple[int, int]:
    """Convert raw screen coords to the 0–65535 range Interception wants."""
    width, height = size()
    if width <= 0 or height <= 0:
        return 0, 0
    return 65535 * x // width, 65535 * y // height


def _send_stroke(state: int, *, flags: int = 0,
                 x: int = 0, y: int = 0, rolling: int = 0) -> None:
    """Push one mouse stroke through the Interception driver."""
    dll, ctx = load_context()
    stroke = InterceptionMouseStroke(
        state=state & 0xFFFF,
        flags=flags & 0xFFFF,
        rolling=rolling,
        x=int(x),
        y=int(y),
        information=0,
    )
    sent = dll.interception_send(
        ctx, default_mouse_device(),
        ctypes.byref(stroke), 1,
    )
    if sent != 1:
        raise InterceptionUnavailable(
            "interception_send returned 0 — the device id "
            f"{default_mouse_device()!r} is likely wrong; set "
            "JE_AUTOCONTROL_INTERCEPTION_MOUSE to a valid id (11–20)."
        )


def position() -> Optional[Tuple[int, int]]:
    """Return ``(x, y)`` cursor position via ``GetCursorPos``."""
    point = wintypes.POINT()
    if _get_cursor_pos(ctypes.byref(point)):
        return point.x, point.y
    return None


def set_position(x: int, y: int) -> None:
    """Set the cursor via the absolute-move stroke (driver-level move)."""
    abs_x, abs_y = _to_absolute(int(x), int(y))
    _send_stroke(0, flags=MOUSE_MOVE_ABSOLUTE, x=abs_x, y=abs_y)
    # GetCursorPos still reflects the move because the driver's
    # absolute path goes through the OS — but call the Win32
    # SetCursorPos as a belt-and-braces fallback when the driver is
    # configured to ignore mouse-only injection (rare).
    _set_cursor_pos(int(x), int(y))


def press_mouse(press_button: Tuple[int, int, int]) -> None:
    """Press a mouse button using the supplied (up, down, data) tuple."""
    _send_stroke(press_button[1])


def release_mouse(release_button: Tuple[int, int, int]) -> None:
    """Release a mouse button using the supplied (up, down, data) tuple."""
    _send_stroke(release_button[0])


def click_mouse(mouse_keycode: Tuple[int, int, int],
                x: Optional[int] = None,
                y: Optional[int] = None) -> None:
    """Move (when coords given), press and release in one shot."""
    if x is not None and y is not None:
        set_position(int(x), int(y))
    press_mouse(mouse_keycode)
    release_mouse(mouse_keycode)


def scroll(scroll_value: int, x: int = 0, y: int = 0) -> None:
    """Wheel-scroll via the driver. ``x``/``y`` are kept for API parity."""
    del x, y  # Interception scroll is delivered to the focused window
    _send_stroke(MOUSE_WHEEL, rolling=int(scroll_value))


def mouse_event(event: int, x: int, y: int, dw_data: int = 0) -> None:
    """Free-form stroke for callers that already speak Interception flags."""
    _send_stroke(event, x=int(x), y=int(y), rolling=int(dw_data))


def send_mouse_event_to_window(window, mouse_keycode: int,
                               x: int = 0, y: int = 0):
    """Targeted-window injection — degraded to focused-window for the driver.

    Interception talks to the kernel HID stack, not a single window
    handle. Caller is expected to focus the window first via the
    standard window-manager helpers; we then perform a regular
    set+click.
    """
    del window
    if x or y:
        set_position(int(x), int(y))
    _send_stroke(int(mouse_keycode))
