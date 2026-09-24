"""uinput keyboard backend — same surface as ``x11_linux_keyboard_control``.

The wrapper hands every Linux backend the same keycode table, which holds
X11 keycodes; an X keycode is the evdev ``KEY_*`` code plus 8, so the
press / release calls subtract 8 before ``EV_KEY`` (passed through
unchanged, typing ``a`` sent ``KEY_L``). ``send_key_event_to_window``
degrades to a focused-window press because uinput talks to the kernel HID
layer rather than a specific X window.
"""
from __future__ import annotations

from je_auto_control.linux_with_x11.uinput._device import EV_KEY, emit
from je_auto_control.utils.exception.exceptions import AutoControlKeyboardException

#: X11 keycodes are evdev codes offset by 8 (the X server reserves 0..7).
_X_KEYCODE_OFFSET = 8


def _evdev_code(keycode: int) -> int:
    code = int(keycode) - _X_KEYCODE_OFFSET
    if not 0 < code < 0x300:
        raise AutoControlKeyboardException(f"X keycode {keycode!r} has no evdev key")
    return code


def press_key(keycode: int) -> None:
    """Hold ``keycode`` (an X11 keycode from the wrapper's table)."""
    emit(EV_KEY, _evdev_code(keycode), 1)


def release_key(keycode: int) -> None:
    """Release ``keycode`` (an X11 keycode)."""
    emit(EV_KEY, _evdev_code(keycode), 0)


def send_key_event_to_window(window_id: int, keycode: int) -> None:
    """Press + release; ``window_id`` is ignored at the kernel layer.

    Caller is expected to focus the target window via the standard
    window-manager helpers before calling.
    """
    del window_id
    press_key(int(keycode))
    release_key(int(keycode))
