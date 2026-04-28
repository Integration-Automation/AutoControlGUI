"""uinput mouse backend — same surface as ``x11_linux_mouse_control``.

The kernel side speaks RELATIVE motion only by default. To emulate
absolute positioning we read the current cursor through the existing
X11 helper and emit the delta — the operator still gets ``set_position
(x, y)`` semantics, just routed through ``/dev/uinput`` so games that
read evdev see the synthetic event.
"""
from __future__ import annotations

from typing import Optional, Tuple

from je_auto_control.linux_with_x11.mouse.x11_linux_mouse_control import (
    position as _x11_position,
    x11_linux_mouse_left, x11_linux_mouse_middle, x11_linux_mouse_right,
    x11_linux_scroll_direction_down, x11_linux_scroll_direction_left,
    x11_linux_scroll_direction_right, x11_linux_scroll_direction_up,
)
from je_auto_control.linux_with_x11.uinput._device import (
    BTN_EXTRA, BTN_LEFT, BTN_MIDDLE, BTN_RIGHT, BTN_SIDE,
    EV_KEY, EV_REL, REL_HWHEEL, REL_WHEEL, REL_X, REL_Y,
    emit, emit_combo,
)

# Re-export the AC scroll direction constants for the wrapper layer.
__all__ = [
    "x11_linux_mouse_left", "x11_linux_mouse_middle", "x11_linux_mouse_right",
    "x11_linux_scroll_direction_up", "x11_linux_scroll_direction_down",
    "x11_linux_scroll_direction_left", "x11_linux_scroll_direction_right",
    "click_mouse", "position", "press_mouse", "release_mouse",
    "scroll", "send_mouse_event_to_window", "set_position",
]


# AC's keyboard table maps to X-server button numbers; uinput uses the
# evdev BTN_* codes. Translate at the wrapper boundary.
_BUTTON_TABLE = {
    int(x11_linux_mouse_left): BTN_LEFT,
    int(x11_linux_mouse_middle): BTN_MIDDLE,
    int(x11_linux_mouse_right): BTN_RIGHT,
    8: BTN_SIDE,
    9: BTN_EXTRA,
}


def _evdev_button(mouse_keycode: int) -> int:
    code = _BUTTON_TABLE.get(int(mouse_keycode))
    if code is None:
        raise ValueError(f"unknown mouse button {mouse_keycode!r}")
    return code


def position() -> Tuple[int, int]:
    """Return the cursor position via the existing X11 helper."""
    return _x11_position()


def set_position(x: int, y: int) -> None:
    """Move to absolute ``(x, y)`` by emitting the relative delta."""
    cur_x, cur_y = position()
    dx = int(x) - int(cur_x)
    dy = int(y) - int(cur_y)
    if dx == 0 and dy == 0:
        return
    emit_combo([
        (EV_REL, REL_X, dx),
        (EV_REL, REL_Y, dy),
    ])


def press_mouse(mouse_keycode: int) -> None:
    """Hold a mouse button."""
    emit(EV_KEY, _evdev_button(mouse_keycode), 1)


def release_mouse(mouse_keycode: int) -> None:
    """Release a mouse button."""
    emit(EV_KEY, _evdev_button(mouse_keycode), 0)


def click_mouse(mouse_keycode: int,
                x: Optional[int] = None,
                y: Optional[int] = None) -> None:
    """Move (when coords given) and press+release in one shot."""
    if x is not None and y is not None:
        set_position(int(x), int(y))
    btn = _evdev_button(mouse_keycode)
    emit_combo([
        (EV_KEY, btn, 1),
        (EV_KEY, btn, 0),
    ])


def scroll(scroll_value: int, scroll_direction: int) -> None:
    """Wheel-scroll; positive scroll_value scrolls in ``direction``."""
    direction = int(scroll_direction)
    magnitude = max(1, abs(int(scroll_value)))
    if direction in (int(x11_linux_scroll_direction_up),
                     int(x11_linux_scroll_direction_down)):
        sign = +1 if direction == int(x11_linux_scroll_direction_up) else -1
        for _ in range(magnitude):
            emit(EV_REL, REL_WHEEL, sign)
    else:
        sign = +1 if direction == int(x11_linux_scroll_direction_right) else -1
        for _ in range(magnitude):
            emit(EV_REL, REL_HWHEEL, sign)


def send_mouse_event_to_window(window_id: int, mouse_keycode: int,
                               x: int = 0, y: int = 0) -> None:
    """Targeted-window degrades to a focused-window click at (x, y)."""
    del window_id
    if x or y:
        set_position(int(x), int(y))
    click_mouse(int(mouse_keycode))
