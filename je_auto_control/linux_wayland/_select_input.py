"""Decide whether to use the native libei backend or the CLI shims.

Honours ``JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND``:

* ``libei`` — force the native binding; raise if libei isn't installed.
* ``cli`` — force ``wtype`` / ``ydotool`` shims.
* ``auto`` (default) — use libei; CLI input requires explicit configuration.

Kept separate from :mod:`_detect` so the display-server choice and
the input-pipeline choice can evolve independently.
"""
from __future__ import annotations

import os
from typing import Callable, Mapping, TYPE_CHECKING

from je_auto_control.linux_wayland.permission import WaylandDependencyRequired

if TYPE_CHECKING:
    from je_auto_control.linux_wayland.libei import LibeiBackend


_ENV_OVERRIDE = "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND"
_VALID = frozenset({"auto", "libei", "cli"})


def select_input_backend(environ: Mapping[str, str] | None = None) -> str:
    """Return one of ``"libei"`` or ``"cli"`` based on env + libei probe."""
    env = environ if environ is not None else os.environ
    forced = (env.get(_ENV_OVERRIDE) or "auto").strip().lower()
    if forced not in _VALID:
        forced = "auto"
    if forced == "cli":
        return "cli"
    libei_available = _libei_loadable()
    if not libei_available:
        raise WaylandDependencyRequired(
            "libei is not loadable; install libei or explicitly configure "
            "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=cli",
        )
    return "libei"


def _libei_loadable() -> bool:
    try:
        from je_auto_control.linux_wayland.libei import get_default_backend
        return get_default_backend() is not None
    except (ImportError, OSError, RuntimeError):
        return False


def active_backend() -> LibeiBackend | None:
    """Return a connected libei backend, or None to use the ydotool CLI.

    The single entry point ``keyboard`` and ``mouse`` use. It lives here
    rather than in :mod:`libei` so the dependency runs one way — this module
    decides which input path is wanted, :mod:`libei` only knows how to bring
    one up. None means the operator explicitly selected CLI input. Missing
    dependencies and refused or failed authorization remain typed errors.
    """
    try:
        if select_input_backend() != "libei":
            return None
        from je_auto_control.linux_wayland.libei import connected_backend
        backend = connected_backend()
        if backend is None:
            raise WaylandDependencyRequired("native input is unavailable; explicitly retry or select cli")
        return backend
    except (ImportError, OSError, RuntimeError) as error:
        raise WaylandDependencyRequired("native input failed; install libei or explicitly select cli") from error


def emitted(backend: LibeiBackend, send: Callable[[LibeiBackend], None]) -> bool:
    """Emit on the authorized transport; refusals stop input without fallback."""
    from je_auto_control.linux_wayland.libei import LibeiOutOfBounds, LibeiUnavailable
    from je_auto_control.linux_wayland.permission import WaylandInputUnavailable, WaylandPermissionRequired
    try:
        send(backend)
    except LibeiOutOfBounds as error:
        raise WaylandInputUnavailable(str(error)) from error
    except LibeiUnavailable as error:
        raise WaylandPermissionRequired("input", str(error)) from error
    return True


__all__ = ["active_backend", "emitted", "select_input_backend"]
