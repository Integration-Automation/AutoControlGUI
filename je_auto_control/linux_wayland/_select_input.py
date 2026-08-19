"""Decide whether to use the native libei backend or the CLI shims.

Honours ``JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND``:

* ``libei`` — force the native binding; raise if libei isn't installed.
* ``cli`` — force ``wtype`` / ``ydotool`` shims.
* ``auto`` (default) — try libei first; fall back to CLI on failure.

Kept separate from :mod:`_detect` so the display-server choice and
the input-pipeline choice can evolve independently.
"""
from __future__ import annotations

import os
from typing import Optional


_ENV_OVERRIDE = "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND"
_VALID = frozenset({"auto", "libei", "cli"})


def select_input_backend(environ: Optional[dict] = None) -> str:
    """Return one of ``"libei"`` or ``"cli"`` based on env + libei probe."""
    env = environ if environ is not None else os.environ
    forced = (env.get(_ENV_OVERRIDE) or "auto").strip().lower()
    if forced not in _VALID:
        forced = "auto"
    if forced == "cli":
        return "cli"
    libei_available = _libei_loadable()
    if forced == "libei":
        if not libei_available:
            raise RuntimeError(
                "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=libei but libei is "
                "not loadable; install libei or unset the override",
            )
        return "libei"
    return "libei" if libei_available else "cli"


def _libei_loadable() -> bool:
    try:
        from je_auto_control.linux_wayland.libei import get_default_backend
        return get_default_backend() is not None
    except (ImportError, OSError, RuntimeError):
        return False


def active_backend():
    """Return a connected libei backend, or None to use the ydotool CLI.

    The single entry point ``keyboard`` and ``mouse`` use. It lives here
    rather than in :mod:`libei` so the dependency runs one way — this module
    decides which input path is wanted, :mod:`libei` only knows how to bring
    one up. None is the answer on any host where libei is absent, the
    portal declines, or the handshake does not complete.
    """
    try:
        if select_input_backend() != "libei":
            return None
        from je_auto_control.linux_wayland.libei import connected_backend
        return connected_backend()
    except (ImportError, OSError, RuntimeError):
        return None


def emitted(backend, send) -> bool:
    """Run one emission on ``backend``; False means the CLI has to take it.

    A backend that finished its handshake can still refuse a single
    emission: the compositor pauses a device, or the session ends between
    two calls. :mod:`libei` is documented as the fast path and never the
    only one, so a refusal falls through to the ``ydotool`` / ``wtype``
    shims here rather than reaching the caller — and if those are missing
    too, *they* raise. Nothing is swallowed; the failure just changes hands.
    """
    from je_auto_control.linux_wayland.libei import LibeiUnavailable
    try:
        send(backend)
    except LibeiUnavailable:
        return False
    return True


__all__ = ["active_backend", "emitted", "select_input_backend"]
