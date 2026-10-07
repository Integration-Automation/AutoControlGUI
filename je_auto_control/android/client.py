"""Thin lazy wrapper around ``uiautomator2.Device``.

The ADB-based path in :mod:`adb_client` handles tap / swipe / text /
screenshot via raw ``adb shell`` commands. ``uiautomator2`` adds what
``adb shell`` cannot: a live widget tree, blocking ``wait`` for an
element, and bounding-rect introspection. We keep it in a separate
class so the cheap adb-only path stays available when the daemon
isn't installed.
"""
from __future__ import annotations

import functools
from typing import Any, Callable, Optional, ParamSpec, TypeVar, cast

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.wrapper._mobile_binding import bound_device
from je_auto_control.wrapper._mobile_client_owner import LazyMobileHandle
from je_auto_control.wrapper._mobile_sdk import android_handle, dispose_android
from je_auto_control.wrapper._mobile_sdk_protocols import AndroidSDK


class UIAutomatorUnavailableError(AutoControlException, RuntimeError):
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
                 handle: Optional[Any] = None, *, timeout_s: Optional[float] = None,
                 _guard: Optional[Callable[[], None]] = None) -> None:
        self._serial = serial
        self._timeout_s = timeout_s
        self._guard = _guard
        self._owner = LazyMobileHandle(handle, _guard, dispose_android if _guard is not None else None)

    @property
    def serial(self) -> Optional[str]:
        """The configured ADB serial; does not connect to the device."""
        return self._serial

    @property
    def handle(self) -> AndroidSDK:
        """Return the underlying ``uiautomator2.Device`` instance.

        Lazily connects on first call. Subsequent calls reuse the
        handle so the daemon-side session survives across operations.
        """
        return cast(AndroidSDK, self._resolve_handle())

    def _resolve_handle(self) -> Any:
        return self._owner.get(self._connect_handle)

    def _connect_handle(self) -> Any:
        try:
            import uiautomator2 as u2
        except ImportError as error:
            raise UIAutomatorUnavailableError(
                "uiautomator2 not installed. `pip install uiautomator2` "
                "and ensure adb sees the device (`adb devices`).",
            ) from error
        try:
            if self._guard is None:
                return u2.connect(self._serial)
            return android_handle(u2, self._serial or '', self._timeout_s or 10, self._guard)
        except (OSError, RuntimeError, ValueError) + _sdk_errors() as error:
            raise UIAutomatorUnavailableError(
                f"could not connect to Android device {self._serial or '(default)'}: {error}",
            ) from error

    def close(self) -> None:
        """Close this client; an explicit owner also disposes its own started helper."""
        self._owner.close()


_DEFAULT_DEVICE: Optional[UIAutomatorDevice] = None


def default_ui_device() -> UIAutomatorDevice:
    """Current explicit binding, or the compatible lazy process default."""
    session = bound_device('android')
    if session is not None:
        return session.adapter('uiautomator2')
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


_Result = TypeVar("_Result")
_Parameters = ParamSpec("_Parameters")


def _sdk_errors() -> tuple[type[BaseException], ...]:
    """``adbutils.AdbError`` (no device, or several without a serial) and
    uiautomator2's base error, whichever are installed."""
    errors = []
    try:
        import adbutils
        errors.append(adbutils.AdbError)
    except ImportError:
        pass
    try:
        from uiautomator2 import exceptions as u2_exceptions
        errors.append(u2_exceptions.BaseException)
    except (ImportError, AttributeError):
        pass
    return tuple(errors)


def translate_device_errors(function: Callable[_Parameters, _Result]) -> Callable[_Parameters, _Result]:
    """Re-raise the adbutils / uiautomator2 errors a device call can raise as :class:`UIAutomatorUnavailableError`.

    They derive from ``Exception`` alone, so an unreachable or confused device
    escaped ``raise_on_error=False`` and aborted every remaining action.
    """
    @functools.wraps(function)
    def wrapper(*args: _Parameters.args, **kwargs: _Parameters.kwargs) -> _Result:
        try:
            return function(*args, **kwargs)
        except _sdk_errors() as error:
            raise UIAutomatorUnavailableError(f"{function.__name__}: {error}") from error
    return wrapper
