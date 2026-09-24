"""Thin wrapper around ``facebook-wda`` (WebDriverAgent client).

WebDriverAgent (WDA) is the iOS automation server that Appium and
``facebook-wda`` both talk to. The Python client connects over HTTP
to a WDA instance running on a real device or the iOS Simulator.
We import it lazily so the package stays usable on Windows / Linux
hosts where iOS automation isn't possible.

Setup outside this module:

* Install WDA on the device (``xcodebuild test`` from Facebook's
  WebDriverAgent project, then run ``iproxy`` to forward 8100).
* ``pip install facebook-wda``.
* Point ``IOSDevice(url=...)`` at ``http://127.0.0.1:8100`` (or the
  WDA hub URL when going through Appium / Sauce Labs).
"""
from __future__ import annotations

import functools
import threading
from typing import Any, Callable, Optional, TypeVar

from je_auto_control.utils.exception.exceptions import AutoControlException


class IOSUnavailableError(AutoControlException, RuntimeError):
    """Raised when the ``wda`` SDK is missing or the device can't be reached."""


class IOSDevice:
    """Adapter around ``wda.Client`` with a lazy connection.

    ``url`` is the WebDriverAgent HTTP endpoint
    (default ``http://localhost:8100``). ``handle`` lets tests inject
    a fake client without ever loading the real SDK.
    """

    DEFAULT_URL = "http://localhost:8100"

    def __init__(self, url: Optional[str] = None,
                 handle: Optional[Any] = None) -> None:
        self._url = url or self.DEFAULT_URL
        self._handle = handle
        self._lock = threading.Lock()

    @property
    def url(self) -> str:
        return self._url

    @property
    def handle(self) -> Any:
        """Return the underlying ``wda.Client`` instance (lazy)."""
        return self._resolve_handle()

    def _resolve_handle(self) -> Any:
        with self._lock:
            if self._handle is not None:
                return self._handle
            try:
                import wda
            except ImportError as error:
                raise IOSUnavailableError(
                    "facebook-wda not installed. "
                    "`pip install facebook-wda` and run WebDriverAgent "
                    "on the target device (see the Facebook WDA "
                    "project README).",
                ) from error
            try:
                self._handle = wda.Client(self._url)
            except (OSError, RuntimeError, ValueError, *_sdk_errors()) as error:
                raise IOSUnavailableError(
                    f"could not reach WebDriverAgent at {self._url}: {error}",
                ) from error
            return self._handle


_DEFAULT_DEVICE: Optional[IOSDevice] = None


def default_ios_device() -> IOSDevice:
    """Process-wide default :class:`IOSDevice` (lazy-built)."""
    global _DEFAULT_DEVICE
    if _DEFAULT_DEVICE is None:
        _DEFAULT_DEVICE = IOSDevice()
    return _DEFAULT_DEVICE


def reset_default_ios_device() -> None:
    """Clear the process-wide default — used by tests between cases."""
    global _DEFAULT_DEVICE
    _DEFAULT_DEVICE = None


__all__ = [
    "IOSDevice", "IOSUnavailableError",
    "default_ios_device", "reset_default_ios_device",
]


_Result = TypeVar("_Result")


def _sdk_errors() -> tuple:
    """facebook-wda's base error (an invalid session, a crashed app...), if installed."""
    try:
        from wda import exceptions as wda_exceptions
    except ImportError:
        return ()
    return (wda_exceptions.WDAError,)


def translate_device_errors(function: Callable[..., _Result]) -> Callable[..., _Result]:
    """Re-raise the facebook-wda errors a device call can raise as :class:`IOSUnavailableError`.

    They derive from ``Exception`` alone, so an unreachable or confused device
    escaped ``raise_on_error=False`` and aborted every remaining action.
    """
    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> _Result:
        try:
            return function(*args, **kwargs)
        except (*_sdk_errors(),) as error:
            raise IOSUnavailableError(f"{function.__name__}: {error}") from error
    return wrapper
