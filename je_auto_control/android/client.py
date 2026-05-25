"""Thin lazy wrapper around ``uiautomator2.Device``.

The ADB-based path in :mod:`adb_client` handles tap / swipe / text /
screenshot via raw ``adb shell`` commands. ``uiautomator2`` adds what
``adb shell`` cannot: a live widget tree, blocking ``wait`` for an
element, and bounding-rect introspection. We keep it in a separate
class so the cheap adb-only path stays available when the daemon
isn't installed.
"""
from __future__ import annotations

import threading
from typing import Any, Optional


class UIAutomatorUnavailableError(RuntimeError):
    """Raised when the ``uiautomator2`` SDK or a target device is missing."""


class UIAutomatorDevice:
    """Adapter around ``uiautomator2.Device`` with lazy connection.

    Construct with an optional ``serial`` (the adb device serial as
    reported by ``adb devices``). When omitted, ``uiautomator2``
    selects the first attached device. The underlying
    ``uiautomator2.Device`` is built on first attribute access so
    importing this module never triggers an adb scan.
    """

    def __init__(self, serial: Optional[str] = None,
                 handle: Optional[Any] = None) -> None:
        self._serial = serial
        self._handle = handle
        self._lock = threading.Lock()

    @property
    def serial(self) -> Optional[str]:
        return self._serial

    @property
    def handle(self) -> Any:
        """Return the underlying ``uiautomator2.Device`` instance.

        Lazily connects on first call. Subsequent calls reuse the
        handle so the daemon-side session survives across operations.
        """
        return self._resolve_handle()

    def _resolve_handle(self) -> Any:
        with self._lock:
            if self._handle is not None:
                return self._handle
            try:
                import uiautomator2 as u2
            except ImportError as error:
                raise UIAutomatorUnavailableError(
                    "uiautomator2 not installed. "
                    "`pip install uiautomator2` and ensure adb sees the "
                    "device (`adb devices`).",
                ) from error
            try:
                self._handle = u2.connect(self._serial)
            except (OSError, RuntimeError, ValueError) as error:
                raise UIAutomatorUnavailableError(
                    f"could not connect to Android device "
                    f"{self._serial or '(default)'}: {error}",
                ) from error
            return self._handle


_DEFAULT_DEVICE: Optional[UIAutomatorDevice] = None


def default_ui_device() -> UIAutomatorDevice:
    """Process-wide default :class:`UIAutomatorDevice` (lazy-built)."""
    global _DEFAULT_DEVICE
    if _DEFAULT_DEVICE is None:
        _DEFAULT_DEVICE = UIAutomatorDevice()
    return _DEFAULT_DEVICE


def reset_default_ui_device() -> None:
    """Clear the process-wide default — used by tests between cases."""
    global _DEFAULT_DEVICE
    _DEFAULT_DEVICE = None


__all__ = [
    "UIAutomatorDevice", "UIAutomatorUnavailableError",
    "default_ui_device", "reset_default_ui_device",
]
