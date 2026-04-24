"""Platform backends for the accessibility API."""
import sys
from typing import Optional

from je_auto_control.utils.accessibility.backends.base import (
    AccessibilityBackend,
)
from je_auto_control.utils.accessibility.backends.null_backend import (
    NullAccessibilityBackend,
)

_cached_backend: Optional[AccessibilityBackend] = None


def get_backend() -> AccessibilityBackend:
    """Return (and cache) the best backend for the current platform."""
    global _cached_backend
    if _cached_backend is not None:
        return _cached_backend
    _cached_backend = _build_backend()
    return _cached_backend


def reset_backend_cache() -> None:
    """Force the next ``get_backend()`` call to re-detect."""
    global _cached_backend
    _cached_backend = None


def _build_backend() -> AccessibilityBackend:
    if sys.platform.startswith("win"):
        from je_auto_control.utils.accessibility.backends.windows_backend import (
            WindowsAccessibilityBackend,
        )
        backend = WindowsAccessibilityBackend()
        if backend.available:
            return backend
        return NullAccessibilityBackend(
            "install comtypes to enable Windows UIAutomation support",
        )
    if sys.platform == "darwin":
        from je_auto_control.utils.accessibility.backends.macos_backend import (
            MacOSAccessibilityBackend,
        )
        backend = MacOSAccessibilityBackend()
        if backend.available:
            return backend
        return NullAccessibilityBackend(
            "pyobjc (ApplicationServices, AppKit) is required on macOS",
        )
    return NullAccessibilityBackend(
        f"no accessibility backend for platform {sys.platform!r}",
    )


__all__ = [
    "AccessibilityBackend", "NullAccessibilityBackend",
    "get_backend", "reset_backend_cache",
]
