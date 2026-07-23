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


def check_key_is_press(keycode: int | None = None) -> bool:
    """Best-effort key-state query; on Wayland this always reports ``False``.

    Every other backend exposes ``check_key_is_press`` and the wrapper's
    critical-exit watcher calls it on a timer. Wayland cannot read the
    global key state from an unprivileged client, so rather than omitting
    the name (which would ``AttributeError`` and kill the critical-exit
    thread) this reports ``False`` — the panic key is inert on Wayland,
    but callers degrade gracefully instead of crashing.

    :param keycode: key to query; ignored because no query is possible.
    :return: always ``False``.
    """
    del keycode
    return False


__all__ = ["check_key_is_press", "check_key_press", "hook_keyboard"]
