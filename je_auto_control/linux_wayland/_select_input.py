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


__all__ = ["select_input_backend"]
