"""uinput keyboard backend — same surface as ``x11_linux_keyboard_control``.

AutoControl's keycode tables already speak Linux key codes (the same
``KEY_*`` constants the kernel uses), so the press / release calls
just hand the integer straight through to ``EV_KEY``. ``send_key
_event_to_window`` degrades to a focused-window press because uinput
talks to the kernel HID layer rather than a specific X window.
"""
from __future__ import annotations

from je_auto_control.linux_with_x11.uinput._device import EV_KEY, emit


def press_key(keycode: int) -> None:
    """Hold ``keycode`` (Linux ``KEY_*`` code)."""
    emit(EV_KEY, int(keycode), 1)


def release_key(keycode: int) -> None:
    """Release ``keycode``."""
    emit(EV_KEY, int(keycode), 0)


def send_key_event_to_window(window_id: int, keycode: int) -> None:
    """Press + release; ``window_id`` is ignored at the kernel layer.

    Caller is expected to focus the target window via the standard
    window-manager helpers before calling.
    """
    del window_id
    press_key(int(keycode))
    release_key(int(keycode))
