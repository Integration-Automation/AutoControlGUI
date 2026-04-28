"""Virtual gamepad backend (Windows ViGEmBus driver).

Used for games that don't accept synthetic keyboard / mouse but read
gamepad input — driving a virtual Xbox 360 / DualShock 4 controller
that ViGEmBus exposes to the OS as a real HID device.

Public surface (kept stable so the executor + MCP wrapper can rely on
it):

* :class:`VirtualGamepad` — context manager that owns one virtual
  controller for its lifetime.
* :func:`default_gamepad` — process-wide singleton, lazily created on
  first use.
* :class:`GamepadUnavailable` — raised when ViGEmBus or ``vgamepad``
  is missing.

The real implementation is delegated to the ``vgamepad`` package
(https://github.com/yannbouteiller/vgamepad). We don't ship that as a
hard dep; install with ``pip install vgamepad`` after installing the
ViGEmBus driver. The facade layer adapts ``vgamepad``'s constants to
the friendly string names AutoControl uses everywhere else
(``button=A``, ``stick=left``, ...).
"""
from je_auto_control.utils.gamepad._facade import (
    DPAD_DIRECTIONS, GAMEPAD_BUTTONS, GamepadUnavailable, VirtualGamepad,
    default_gamepad, is_available, reset_default_gamepad,
)

__all__ = [
    "DPAD_DIRECTIONS", "GAMEPAD_BUTTONS",
    "GamepadUnavailable", "VirtualGamepad",
    "default_gamepad", "is_available", "reset_default_gamepad",
]
