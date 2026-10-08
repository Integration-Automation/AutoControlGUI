"""Wayland keyboard listener stub.

Wayland deliberately forbids reading the global key state from an
unprivileged client, so the two hook entry points raise a specific
NotImplementedError rather than pretending.

The supported replacements are narrower than a hook, and live elsewhere:

* a single global *stop* key — :mod:`global_shortcuts`, through the
  GlobalShortcuts portal, which reports only the shortcut that was registered;
* the user's own input, from kernel devices they name — the opt-in
  ``PhysicalRecorder`` in :mod:`input_events`.

The portal's InputCapture interface is not one of them: the compositor decides
when it starts (a pointer crossing a screen edge), so it cannot be a listener
that starts when a script asks.
"""
from __future__ import annotations


def check_key_press(*_args, **_kwargs):
    """Wayland clients cannot read the global key state. Raise explicitly."""
    raise NotImplementedError(
        "Wayland forbids global key-state queries from unprivileged "
        "clients. For a stop key use StopShortcutSession (the "
        "GlobalShortcuts portal); to read your own devices use the opt-in "
        "PhysicalRecorder. The X11 backend "
        "(JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11) sees X11 applications "
        "only under XWayland.",
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
