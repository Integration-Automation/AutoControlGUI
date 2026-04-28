"""Optional Interception-driver backend for Windows keyboard / mouse input.

The default Windows backend in ``windows/keyboard`` and ``windows/mouse``
uses ``SendInput`` — fine for most apps, but games that read input via
``GetRawInputData`` ignore synthetic SendInput events. The Interception
driver (https://github.com/oblitum/Interception) is a WHQL-signed
filter driver that injects events at the HID layer, so synthetic input
becomes indistinguishable from a real device.

This package provides:

* :mod:`._dll` — :class:`ctypes` bindings to ``interception.dll``.
* :mod:`.keyboard` — same public surface as
  :mod:`je_auto_control.windows.keyboard.win32_ctype_keyboard_control`.
* :mod:`.mouse` — same public surface as
  :mod:`je_auto_control.windows.mouse.win32_ctype_mouse_control`.

The driver is **not** bundled. It is installed once with admin
privileges via the project's installer. Set
``JE_AUTOCONTROL_WIN32_BACKEND=interception`` to use this backend; if
the DLL or driver is unavailable the platform wrapper falls back to
``SendInput`` with a warning, so deployments with the env var set can
roll the driver out lazily.
"""
from je_auto_control.windows.interception._dll import (
    InterceptionUnavailable, is_available, load_context,
)

__all__ = ["InterceptionUnavailable", "is_available", "load_context"]
