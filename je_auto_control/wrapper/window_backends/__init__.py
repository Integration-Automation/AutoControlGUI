"""Per-platform window-management backends.

Window management was Windows-only for the project's whole life: the facade
branched on ``sys.platform`` and raised ``NotImplementedError`` everywhere
else, which left 23 ``AC_*`` commands and their MCP tools dead on macOS and
Linux. This is the seam that replaces that branch, following the same shape
the accessibility, OCR and vision subsystems already use — abstract base,
concrete implementations, null fallback — so a platform without one still
imports.

Selection is cached because probing opens an X connection or a Quartz query,
and the answer cannot change inside a process.
"""
import sys
from typing import Optional

from je_auto_control.wrapper.window_backends.base import WindowManageBackend
from je_auto_control.wrapper.window_backends.null_backend import NullWindowBackend

_cached_backend: Optional[WindowManageBackend] = None


def get_backend() -> WindowManageBackend:
    """Return (and cache) the best window backend for this platform."""
    global _cached_backend
    if _cached_backend is None:
        _cached_backend = _build_backend()
    return _cached_backend


def reset_backend_cache() -> None:
    """Force the next :func:`get_backend` call to re-detect."""
    global _cached_backend
    _cached_backend = None


def _build_backend() -> WindowManageBackend:
    if sys.platform in ("win32", "cygwin", "msys"):
        from je_auto_control.wrapper.window_backends.windows_backend import (
            WindowsWindowBackend,
        )
        return WindowsWindowBackend()
    if sys.platform == "darwin":
        from je_auto_control.wrapper.window_backends.macos_backend import (
            MacOSWindowBackend,
        )
        backend = MacOSWindowBackend()
        if backend.available:
            return backend
        return NullWindowBackend(
            "pyobjc (Quartz, AppKit) is required for macOS window management")
    if sys.platform in ("linux", "linux2"):
        from je_auto_control.wrapper.window_backends.x11_backend import (
            X11WindowBackend,
        )
        backend = X11WindowBackend()
        if backend.available:
            return backend
        # Wayland deliberately does not let a client enumerate or move other
        # applications' windows; that is a protocol decision, not a gap here.
        return NullWindowBackend(
            "no X display. Wayland does not expose other windows to a client, "
            "so run under X11 or XWayland for window management")
    return NullWindowBackend(f"no window backend for platform {sys.platform!r}")


__all__ = [
    "NullWindowBackend", "WindowManageBackend",
    "get_backend", "reset_backend_cache",
]
