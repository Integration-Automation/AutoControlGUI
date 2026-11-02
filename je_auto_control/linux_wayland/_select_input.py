"""Decide whether to use the native libei backend or the CLI shims.

Honours ``JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND``:

* ``libei`` — force the native binding; raise if libei isn't installed.
* ``cli`` — force ``wtype`` / ``ydotool`` shims.
* ``auto`` (default) — use CLI for optional absence, never after authority/session refusal.

Kept separate from :mod:`_detect` so the display-server choice and
the input-pipeline choice can evolve independently.
"""
from __future__ import annotations

import os
from typing import Optional

from je_auto_control.linux_wayland._input_state import raise_if_input_blocked


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
            # pylint: disable-next=import-outside-toplevel  # reason: native backend/error module remains lazy
            from je_auto_control.linux_wayland.libei import LibeiUnavailable
            raise LibeiUnavailable(
                "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=libei but libei is "
                "not loadable; install libei or unset the override", fallback_allowed=False,
            )
        return "libei"
    return "libei" if libei_available else "cli"


def _libei_loadable() -> bool:
    try:
        from je_auto_control.linux_wayland.libei import get_default_backend
        return get_default_backend() is not None
    except (ImportError, OSError, RuntimeError) as error:
        raise_if_input_blocked(error)
        return False


def active_backend():
    """Return a connected libei backend, or None to use the ydotool CLI.

    The single entry point ``keyboard`` and ``mouse`` use. It lives here
    rather than in :mod:`libei` so the dependency runs one way — this module
    decides which input path is wanted, :mod:`libei` only knows how to bring
    one up. None means the optional backend is absent or CLI was selected.
    Explicit permission/session failures propagate.
    """
    try:
        if select_input_backend() != "libei":
            return None
        from je_auto_control.linux_wayland.libei import connected_backend
        backend = connected_backend()
        if backend is None:
            _refuse_required(RuntimeError('the selected libei backend did not connect'))
        return backend
    except (ImportError, OSError, RuntimeError) as error:
        _refuse_required(error)
        return None


def _refuse_required(error: BaseException) -> None:
    """An explicit native choice cannot silently select a different provider."""
    raise_if_input_blocked(error)
    if (os.environ.get(_ENV_OVERRIDE) or 'auto').strip().lower() == 'libei':
        # pylint: disable-next=import-outside-toplevel  # reason: resolve native errors only on a selected native path
        from je_auto_control.linux_wayland.libei import LibeiUnavailable
        raise LibeiUnavailable(str(error), fallback_allowed=False) from error


def emitted(backend, send) -> bool:
    """Run one emission on ``backend``; False means the CLI has to take it.

    Unclassified optional-backend misses retain their legacy auto fallback.
    Explicit native selection and structured permission, pause, revocation or
    protocol failures stop the operation instead of changing input origin.
    """
    from je_auto_control.linux_wayland.libei import LibeiUnavailable
    try:
        send(backend)
    except (LibeiUnavailable, RuntimeError, OSError) as error:
        _refuse_required(error)
        if not isinstance(error, LibeiUnavailable):
            raise
        return False
    return True


__all__ = ["active_backend", "emitted", "select_input_backend"]
