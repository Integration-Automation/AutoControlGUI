"""Wayland backend for AutoControl (linux_wayland).

Wayland sandboxes synthetic input by design — there is no equivalent to
X11's ``XTEST`` extension that any client can call. To drive a Wayland
session AutoControl has to talk to one of the bridges:

* **wtype** — keyboard input via the ``wlr-virtual-keyboard-v1``
  protocol (works on wlroots compositors: sway, hyprland, river);
* **ydotool** — keyboard + mouse via ``/dev/uinput`` (works on
  GNOME / KDE / wlroots, but the daemon needs uinput permission);
* **grim** — screenshot via the ``wlr-screencopy`` protocol (wlroots);
  ``gnome-screenshot`` is used as a fallback on GNOME / KDE.

Each helper module probes for the matching binary lazily, so importing
this package on a non-Linux host (e.g. CI on Windows / macOS) does not
fail. ``platform_wrapper.py`` picks this backend over the X11 one when
``XDG_SESSION_TYPE=wayland`` or ``WAYLAND_DISPLAY`` is set, with a
graceful fall-through to X11 (XWayland) when the CLI tools are
missing.
"""
from je_auto_control.linux_wayland._detect import (
    WAYLAND_GRIM, WAYLAND_WTYPE, WAYLAND_YDOTOOL,
    binary_path, is_wayland_session, missing_dependencies,
    select_display_server,
)
from je_auto_control.linux_wayland._select_input import (
    select_input_backend,
)
from je_auto_control.linux_wayland.libei import (
    LibeiBackend, LibeiUnavailable, get_default_backend,
)


__all__ = [
    "LibeiBackend", "LibeiUnavailable",
    "WAYLAND_GRIM", "WAYLAND_WTYPE", "WAYLAND_YDOTOOL",
    "binary_path", "get_default_backend", "is_wayland_session",
    "missing_dependencies", "select_display_server",
    "select_input_backend",
]
