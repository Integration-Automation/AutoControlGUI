"""iOS app lifecycle, alerts and the part of the extension surface WebDriverAgent has.

WebDriverAgent can launch, terminate and query apps, answer alerts and set the
pasteboard. It has no endpoint for installing an app, moving files or
recording the screen: those need a host-side tool, and are reported as a
missing dependency here rather than imitated.
"""
from __future__ import annotations

from typing import Any, Optional

from je_auto_control.ios.client import IOSDevice, default_ios_device, translate_device_errors
from je_auto_control.wrapper.device_context import (
    STATE_AVAILABLE, STATE_NEEDS_DEPENDENCY, STATE_UNSUPPORTED, AlertNotPresentError,
    AppState, DeviceCapability, DeviceUnsupportedError,
)

#: ``XCUIApplicationState``: 0 unknown, 1 not running, 2 suspended, 3 background, 4 foreground.
_APP_STATES = {2: AppState.BACKGROUND, 3: AppState.BACKGROUND, 4: AppState.FOREGROUND}
NEEDS_ADAPTER = ("WebDriverAgent has no API for this; it needs a host-side adapter "
                 "(for example tidevice, pymobiledevice3 or Appium) registered with "
                 "register_mobile_extension('ios', ...)")
_NO_PASTEBOARD_READ = ("this facebook-wda build cannot read the pasteboard "
                       "(WebDriverAgent only allows it while WDA itself is in front)")


def _bundle(app_id: str) -> str:
    if not isinstance(app_id, str) or not app_id.strip():
        raise ValueError("bundle id must be a non-empty string")
    return app_id


@translate_device_errors
def launch(app_id: str, *, device: Optional[IOSDevice] = None) -> None:
    """Launch (or bring to the front) the app with bundle id ``app_id``."""
    (device or default_ios_device()).handle.app_launch(_bundle(app_id))


@translate_device_errors
def stop(app_id: str, *, device: Optional[IOSDevice] = None) -> None:
    """Terminate the app with bundle id ``app_id``."""
    (device or default_ios_device()).handle.app_terminate(_bundle(app_id))


@translate_device_errors
def state(app_id: str, *, device: Optional[IOSDevice] = None) -> AppState:
    """Whether the app is running and in front.

    WebDriverAgent reports an app that is not installed as not running, so
    this never answers ``NOT_INSTALLED``.
    """
    reply = (device or default_ios_device()).handle.app_state(_bundle(app_id))
    value: Any = reply.get("value") if isinstance(reply, dict) else getattr(reply, "value", reply)
    try:
        return _APP_STATES.get(int(value), AppState.NOT_RUNNING)
    except (TypeError, ValueError):
        return AppState.NOT_RUNNING


@translate_device_errors
def answer_alert(accept: bool, *, device: Optional[IOSDevice] = None) -> str:
    """Accept or dismiss the alert that is showing; returns its text."""
    alert = (device or default_ios_device()).handle.alert
    if not alert.exists:
        raise AlertNotPresentError("no alert is showing")
    text = str(alert.text or "")
    if accept:
        alert.accept()
    else:
        alert.dismiss()
    return text


class WdaExtension:
    """What WebDriverAgent offers of the extension surface: the pasteboard."""

    name = "wda"

    def __init__(self, device_source: Any) -> None:
        # A callable, so no client is built until a feature is used.
        self._device_source = device_source

    def capability(self, feature: str) -> DeviceCapability:
        """Whether ``feature`` can be used through WebDriverAgent."""
        if feature == "clipboard":
            return DeviceCapability(
                feature, STATE_AVAILABLE,
                "set only: reading the pasteboard is allowed only while WDA is in front")
        if feature in ("install", "files", "recording"):
            return DeviceCapability(feature, STATE_NEEDS_DEPENDENCY, NEEDS_ADAPTER)
        return DeviceCapability(feature, STATE_UNSUPPORTED, f"unknown feature {feature!r}")

    def _missing(self, feature: str) -> DeviceUnsupportedError:
        return DeviceUnsupportedError(
            f"{feature} is not available on iOS through WebDriverAgent",
            reason=NEEDS_ADAPTER,
            alternative="register an adapter with register_mobile_extension('ios', factory)")

    def install_app(self, source: str) -> str:
        """Not available through WebDriverAgent."""
        raise self._missing("install")

    def push_file(self, local_path: str, remote_path: str) -> str:
        """Not available through WebDriverAgent."""
        raise self._missing("files")

    def pull_file(self, remote_path: str, local_path: str) -> str:
        """Not available through WebDriverAgent."""
        raise self._missing("files")

    def start_recording(self, remote_path: str = "", time_limit_s: int = 0) -> str:
        """Not available through WebDriverAgent."""
        raise self._missing("recording")

    def stop_recording(self, local_path: str, remote_path: str = "") -> str:
        """Not available through WebDriverAgent."""
        raise self._missing("recording")

    def set_clipboard(self, text: str) -> None:
        """Put ``text`` on the device pasteboard."""
        _set_pasteboard(self._device_source(), text)

    def get_clipboard(self) -> str:
        """The pasteboard's text, where this facebook-wda build can read it."""
        return _get_pasteboard(self._device_source())


@translate_device_errors
def _set_pasteboard(device: IOSDevice, text: str) -> None:
    if not isinstance(text, str):
        raise TypeError("clipboard text must be a string")
    device.handle.set_clipboard(text)


@translate_device_errors
def _get_pasteboard(device: IOSDevice) -> str:
    reader = getattr(device.handle, "get_clipboard", None)
    if not callable(reader):
        raise DeviceUnsupportedError(
            "the pasteboard cannot be read on this device", reason=_NO_PASTEBOARD_READ,
            alternative="read the text from the screen (find_text) or the page source")
    return str(reader() or "")


__all__ = ["NEEDS_ADAPTER", "WdaExtension", "answer_alert", "launch", "state", "stop"]
