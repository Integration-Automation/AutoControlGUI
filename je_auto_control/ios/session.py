"""One iOS device as a :class:`DeviceSession`: its own WebDriverAgent client."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from je_auto_control.ios import apps as ios_apps
from je_auto_control.ios import input as ios_input
from je_auto_control.ios.client import IOSDevice, translate_device_errors
from je_auto_control.ios.screen import capture_frame
from je_auto_control.wrapper.device_context import (
    CAPABILITY_NAMES, STATE_AVAILABLE, STATE_NEEDS_DEPENDENCY,
    AppState, DeviceCapability, DeviceContext, DeviceError, DeviceSession, Drag,
    LongPress, Pinch, Swipe, Tap, bound_session,
)
from je_auto_control.wrapper.device_frame import DeviceFrame
from je_auto_control.wrapper.mobile_extensions import EXTENSION_FEATURES, mobile_extension

#: Capabilities WebDriverAgent itself provides.
_WDA_CAPABILITIES = ("input", "unicode_text", "multi_touch", "screenshot", "ui_tree",
                     "app_lifecycle", "alerts")


@translate_device_errors
def _wda_status(handle: Any) -> Dict[str, Any]:
    """``GET /status`` — a read; nothing is sent to the app under test."""
    return dict(handle.status() or {})


class IOSSession(DeviceSession):
    """An iOS device addressed by its WebDriverAgent URL.

    The client is built on first use and belongs to this session alone; an
    :class:`IOSDevice` handed in by the caller is used but not owned. Closing
    the session never terminates an app or deletes a remote WDA session: it
    releases the local client only.
    """

    def __init__(self, context: DeviceContext, *,
                 device: Optional[IOSDevice] = None) -> None:
        super().__init__(context)
        self._device = device
        self._injected = device is not None

    @property
    def device(self) -> IOSDevice:
        """This session's :class:`IOSDevice`, bound to the context's URL."""
        self.check_usable()
        with self._state_lock:
            if self._device is None:
                self._device = IOSDevice(url=self.device_id or None)
            return self._device

    def status(self) -> Dict[str, Any]:
        """WebDriverAgent's ``/status`` document."""
        return self.invoke("status", lambda: _wda_status(self.device.handle))

    def capabilities(self) -> Dict[str, DeviceCapability]:
        """What this device can do right now; only ``GET /status`` is sent."""
        return self.invoke("capabilities", self._probe)

    def _probe(self) -> Dict[str, DeviceCapability]:
        blocker = self._blocker()
        if blocker is not None:
            state, reason = blocker
            return {name: DeviceCapability(name, state, reason) for name in CAPABILITY_NAMES}
        found = {name: DeviceCapability(name, STATE_AVAILABLE) for name in _WDA_CAPABILITIES}
        extension = mobile_extension(self)
        for name in EXTENSION_FEATURES:
            found[name] = extension.capability(name)
        return {name: found[name] for name in CAPABILITY_NAMES}

    def _blocker(self) -> Optional[Tuple[str, str]]:
        """Why nothing can be used: ``(state, reason)``, or ``None`` when WDA answers."""
        try:
            _wda_status(self.device.handle)
        except (DeviceError, OSError) as error:
            return STATE_NEEDS_DEPENDENCY, str(error)
        return None

    def capture(self) -> DeviceFrame:
        """The current screen, upright, with its pixel-to-point mapping."""
        return self.invoke("capture", lambda: capture_frame(device=self.device))

    def type_text(self, text: str) -> None:
        """Type ``text`` into the focused field (WebDriverAgent carries Unicode)."""
        self.invoke("type_text", lambda: ios_input.type_text(text, device=self.device))

    def press_key(self, key: str) -> None:
        """Press a hardware key (``"home"``, ``"volumeUp"``, ``"volumeDown"``)."""
        self.invoke("press_key", lambda: ios_input.press_key(key, device=self.device))

    def _gesture_handlers(self) -> Dict[type, Callable[[Any], None]]:
        device = self.device
        return {
            Tap: lambda g: ios_input.tap(g.x, g.y, device=device),
            LongPress: lambda g: ios_input.long_press(g.x, g.y, g.duration_s, device=device),
            Swipe: lambda g: ios_input.swipe(g.x1, g.y1, g.x2, g.y2, g.duration_s,
                                             device=device),
            Drag: lambda g: ios_input.drag(g.x1, g.y1, g.x2, g.y2, g.hold_s, device=device),
            Pinch: lambda g: ios_input.pinch(g.scale, g.duration_s, device=device),
        }

    def launch_app(self, app_id: str) -> None:
        """Launch (or bring to the front) the app with this bundle id."""
        self.invoke("launch_app", lambda: ios_apps.launch(app_id, device=self.device))

    def stop_app(self, app_id: str) -> None:
        """Terminate the app with this bundle id."""
        self.invoke("stop_app", lambda: ios_apps.stop(app_id, device=self.device))

    def app_state(self, app_id: str) -> AppState:
        """Whether the app is running and in front."""
        return self.invoke("app_state", lambda: ios_apps.state(app_id, device=self.device))

    def answer_alert(self, accept: bool) -> str:
        """Accept or dismiss the alert that is showing; returns its text."""
        return self.invoke("answer_alert", lambda: ios_apps.answer_alert(
            accept, device=self.device))

    def builtin_extension(self) -> ios_apps.WdaExtension:
        """What WebDriverAgent offers of install / files / clipboard / recording."""
        return ios_apps.WdaExtension(lambda: self.device)

    def _release(self) -> None:
        if not self._injected:
            self._device = None


def bound_ios_session(url: Optional[str] = None) -> Optional[IOSSession]:
    """The iOS session bound by ``use_device`` when ``url`` addresses it."""
    session = bound_session("ios", url)
    return session if isinstance(session, IOSSession) else None


__all__ = ["IOSSession", "bound_ios_session"]
