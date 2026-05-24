"""Wayland keyboard listener stub.

Wayland deliberately forbids reading the global key state from an
unprivileged client. Hooking would require either the libei input
capture protocol (not yet stable across compositors) or a kernel-level
listener via ``/dev/input/event*`` (root-only). For now, raise a
specific NotImplementedError so callers can fall back to the X11
backend if they need key listening.
"""
from __future__ import annotations


def check_key_press(*_args, **_kwargs):
    """Wayland clients cannot read the global key state. Raise explicitly."""
    raise NotImplementedError(
        "Wayland forbids global key-state queries from unprivileged "
        "clients. Use the X11 backend "
        "(JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11), libei capture, or "
        "an evdev reader (requires root).",
    )


def hook_keyboard(*_args, **_kwargs):
    """Wayland clients cannot install a global key hook."""
    raise NotImplementedError(
        "Wayland forbids global key hooks. See check_key_press for "
        "fallback options.",
    )


__all__ = ["check_key_press", "hook_keyboard"]
