"""Legacy key-state compatibility; Wayland stop uses an explicitly granted portal shortcut.

InputCapture is not an ordinary desktop-wide observation hook. Physical event
capture uses selected Linux nodes with existing read ACLs, not an automatic
privilege change. No backend selector can convert an existing Wayland session
into an X11 desktop. See api.wayland_input for raw recording and portal stop.
"""
from __future__ import annotations

from typing import Any

from je_auto_control.linux_wayland.input_events import RecordingUnavailable


def check_key_press(*_args: Any, **_kwargs: Any) -> None:
    """Reject unsupported desktop-wide key-state observation with actionable recovery."""
    raise RecordingUnavailable('Wayland has no ordinary global key-state query; '
                               'request a StopShortcutSession for stopping control')


def hook_keyboard(*_args: Any, **_kwargs: Any) -> None:
    """Reject a legacy global hook; raw recording requires explicit physical device selection."""
    raise RecordingUnavailable('Wayland has no ordinary global keyboard hook')


def check_key_is_press(keycode: int | None = None) -> bool:
    """Return False for the legacy polling contract; this does not provide a stop grant."""
    del keycode
    return False


__all__ = ['check_key_is_press', 'check_key_press', 'hook_keyboard']
