"""Wayland backend for AutoControl (linux_wayland).

Wayland sandboxes synthetic input by design — there is no equivalent to
X11's ``XTEST`` extension that any client can call. To drive a Wayland
session AutoControl has to talk to one of the bridges:

* **wtype** — keyboard input via the ``wlr-virtual-keyboard-v1``
  protocol (works on wlroots compositors: sway, hyprland, river);
* **ydotool** — keyboard + mouse via ``/dev/uinput`` (works on
  GNOME / KDE / wlroots, but the daemon needs uinput permission, and
  it must be **1.0 or newer**: 0.1.x answers this backend's argv with
  exit code 0 and no events, so ``_ydotool_cli`` refuses it);
* **libei** — the compositor's own input-emulation protocol, reached
  through the ``RemoteDesktop`` desktop portal (see ``libei`` and
  ``oeffis``). Preferred where it comes up, since it emits without
  spawning a process per keystroke; falls back to ydotool otherwise;
* **grim** — screenshot via the ``wlr-screencopy`` protocol (wlroots);
  ``gnome-screenshot``, ``spectacle`` and the desktop portal back it up
  (see ``capture`` and ``portal``).

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
    active_backend, select_input_backend,
)
from je_auto_control.linux_wayland.libei import (
    LibeiBackend, LibeiUnavailable, connected_backend, get_default_backend,
)


__all__ = [
    "LibeiBackend", "LibeiUnavailable",
    "WAYLAND_GRIM", "WAYLAND_WTYPE", "WAYLAND_YDOTOOL",
    "active_backend", "binary_path", "connected_backend",
    "get_default_backend", "is_wayland_session",
    "missing_dependencies", "select_display_server",
    "select_input_backend",
]
