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
    if sys.platform.startswith("linux"):
        from je_auto_control.utils.accessibility.backends.linux_backend import (
            LinuxAccessibilityBackend,
        )
        backend = LinuxAccessibilityBackend()
        if backend.available:
            return backend
        # AT-SPI is a bus, not a library, so "not installed" and "installed
        # but nothing is bridged to it" look the same from here. Name both.
        return NullAccessibilityBackend(
            "no AT-SPI accessibility bus. Install and start at-spi2-core, and "
            "enable the toolkit bridge (GTK_MODULES=gail:atk-bridge, "
            "QT_ACCESSIBILITY=1)",
        )
    return NullAccessibilityBackend(
        f"no accessibility backend for platform {sys.platform!r}",
    )


__all__ = [
    "AccessibilityBackend", "NullAccessibilityBackend",
    "get_backend", "reset_backend_cache",
]
