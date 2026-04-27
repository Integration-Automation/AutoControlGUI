"""Optional kernel-level (uinput) keyboard / mouse backend for Linux.

Why this exists alongside the X11 (XTest) backend
=================================================

The default Linux backend in ``linux_with_x11/`` uses XTest, which
sits at the X server layer — perfectly fine for normal apps but games
that read input via ``evdev`` (most modern Linux games, especially
SDL2 / Steam ones) ignore XTest events. uinput is the kernel's
synthetic-input gateway: events emitted via ``/dev/uinput`` show up as
a brand-new HID device, indistinguishable from real hardware to
anything reading evdev.

The driver ships with the kernel; the only requirement is that the
running user can write to ``/dev/uinput``. Either load the module
manually (``sudo modprobe uinput``) and add the user to a uinput
group, or use the dedicated ``uinput`` udev rule shown in the
``new_features`` doc.

This package provides:

* :mod:`._device` — :class:`ctypes` wrapper around ``/dev/uinput``.
* :mod:`.keyboard` — same public surface as
  :mod:`x11_linux_keyboard_control`.
* :mod:`.mouse` — same public surface as
  :mod:`x11_linux_mouse_control`.

Set ``JE_AUTOCONTROL_LINUX_BACKEND=uinput`` to use this backend; on
permission failure the platform wrapper falls back to XTest with a
warning so deployments that haven't yet provisioned uinput access
still get a working environment.
"""
from je_auto_control.linux_with_x11.uinput._device import (
    UinputUnavailable, is_available,
)

__all__ = ["UinputUnavailable", "is_available"]
