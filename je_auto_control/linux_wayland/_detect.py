"""Wayland-session detection and CLI-tool probes.

Imported on every platform — only ``select_display_server`` /
``is_wayland_session`` look at the live environment. Pure stdlib so
the package stays importable in unit tests on Windows / macOS.
"""
from __future__ import annotations

import os
import shutil
from typing import Iterable, List, Optional


WAYLAND_WTYPE = "wtype"
WAYLAND_YDOTOOL = "ydotool"
WAYLAND_GRIM = "grim"

_ENV_OVERRIDE = "JE_AUTOCONTROL_LINUX_DISPLAY_SERVER"


def _normalise(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def is_wayland_session(environ: Optional[dict] = None) -> bool:
    """Return True when the live environment looks like Wayland.

    Honours an ``XDG_SESSION_TYPE`` of ``wayland`` and the
    ``WAYLAND_DISPLAY`` socket name as positive signals.
    """
    env = environ if environ is not None else os.environ
    if _normalise(env.get("XDG_SESSION_TYPE")) == "wayland":
        return True
    return bool(_normalise(env.get("WAYLAND_DISPLAY")))


def select_display_server(environ: Optional[dict] = None) -> str:
    """Pick ``"wayland"`` or ``"x11"`` based on env + override.

    ``JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11|wayland`` forces a
    backend; ``auto`` (default) inspects ``XDG_SESSION_TYPE`` /
    ``WAYLAND_DISPLAY``.
    """
    env = environ if environ is not None else os.environ
    forced = _normalise(env.get(_ENV_OVERRIDE))
    if forced in ("x11", "wayland"):
        return forced
    return "wayland" if is_wayland_session(env) else "x11"


def binary_path(name: str) -> Optional[str]:
    """Return the absolute path to ``name`` if it's on PATH, else None."""
    return shutil.which(name)


def missing_dependencies(required: Iterable[str]) -> List[str]:
    """Return the subset of ``required`` binaries that are NOT on PATH."""
    return [name for name in required if binary_path(name) is None]


__all__ = [
    "WAYLAND_GRIM", "WAYLAND_WTYPE", "WAYLAND_YDOTOOL",
    "binary_path", "is_wayland_session", "missing_dependencies",
    "select_display_server",
]
