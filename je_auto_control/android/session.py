"""One Android device as a :class:`DeviceSession`: its own adb client and widget daemon."""
from __future__ import annotations

from importlib.util import find_spec
from typing import Any, Callable, Dict, Optional, Tuple

from je_auto_control.android import apps as android_apps
from je_auto_control.android import input as android_input
from je_auto_control.android.adb_client import AdbClient, AdbError
from je_auto_control.android.client import UIAutomatorDevice
from je_auto_control.android.input import ADB_KEYBOARD_IME, current_input_method
from je_auto_control.android.screen import capture_frame
from je_auto_control.wrapper.device_context import (
    CAPABILITY_NAMES, STATE_AVAILABLE, STATE_NEEDS_DEPENDENCY, STATE_NEEDS_PERMISSION,
    AppState, DeviceCapability, DeviceContext, DeviceError, DeviceSession, Drag,
    LongPress, Pinch, Swipe, Tap, bound_session,
)
from je_auto_control.wrapper.device_frame import DeviceFrame
from je_auto_control.wrapper.mobile_extensions import EXTENSION_FEATURES, mobile_extension

#: Capabilities plain ``adb`` provides once the device is authorised.
_ADB_CAPABILITIES = ("input", "screenshot", "app_lifecycle")
#: Capabilities that need the uiautomator2 daemon on top of adb.
_UI_CAPABILITIES = ("ui_tree", "multi_touch", "alerts")
_NEEDS_UI = "uiautomator2 is not installed: pip install uiautomator2"
_UNAUTHORIZED = ("the device has not authorised this host: accept the USB debugging "
                 "prompt on the device, then check `adb devices`")


class AndroidSession(DeviceSession):
    """An Android device addressed by adb serial.

    The adb client and the uiautomator2 wrapper are built on first use and
    belong to this session alone; one handed in by the caller is used but not
    owned.
    """

    def __init__(self, context: DeviceContext, *, adb: Optional[Any] = None,
                 ui_device: Optional[UIAutomatorDevice] = None) -> None:
        super().__init__(context)
        self._adb = adb
        self._ui_device = ui_device
        self._ui_injected = ui_device is not None

    @property
    def adb(self) -> Any:
        """This session's :class:`AdbClient`, bound to the context's serial."""
        self.check_usable()
        with self._state_lock:
            if self._adb is None:
                self._adb = AdbClient(
                    adb_path=self.context.adb_path,
                    default_serial=self.device_id or None,
                    timeout_s=self.context.timeout_s,
                )
            return self._adb

    @property
    def ui_device(self) -> UIAutomatorDevice:
        """This session's uiautomator2 wrapper (connects on first use of its handle)."""
        self.check_usable()
        with self._state_lock:
            if self._ui_device is None:
                self._ui_device = UIAutomatorDevice(serial=self.device_id or None)
            return self._ui_device

    @property
    def has_ui_automator(self) -> bool:
        """Whether the uiautomator2 path can be used (installed, or handed in)."""
        return self._ui_injected or find_spec("uiautomator2") is not None

    def capabilities(self) -> Dict[str, DeviceCapability]:
        """What this device can do right now; only ``adb devices`` and a settings read are sent."""
        return self.invoke("capabilities", self._probe)

    def _probe(self) -> Dict[str, DeviceCapability]:
        blocker = self._blocker()
        if blocker is not None:
            state, reason = blocker
            return {name: DeviceCapability(name, state, reason) for name in CAPABILITY_NAMES}
        found = {name: DeviceCapability(name, STATE_AVAILABLE) for name in _ADB_CAPABILITIES}
        for name in _UI_CAPABILITIES:
            found[name] = self._ui_capability(name)
        found["unicode_text"] = self._unicode_capability()
        extension = mobile_extension(self)
        for name in EXTENSION_FEATURES:
            found[name] = extension.capability(name)
        return {name: found[name] for name in CAPABILITY_NAMES}

    def _blocker(self) -> Optional[Tuple[str, str]]:
        """Why nothing can be used: ``(state, reason)``, or ``None`` when adb sees the device."""
        try:
            state = self.adb.device_state()
        except DeviceError as error:
            return STATE_NEEDS_DEPENDENCY, str(error)
        if state == "device":
            return None
        if state in ("unauthorized", "no permissions"):
            return STATE_NEEDS_PERMISSION, _UNAUTHORIZED
        name = self.device_id or "(default)"
        if not state:
            return STATE_NEEDS_DEPENDENCY, (
                f"no device {name!r} is attached: start the emulator or connect the "
                "device, then check `adb devices`")
        return STATE_NEEDS_DEPENDENCY, f"device {name!r} is {state}, not ready"

    def _ui_capability(self, name: str) -> DeviceCapability:
        if self.has_ui_automator:
            return DeviceCapability(name, STATE_AVAILABLE)
        return DeviceCapability(name, STATE_NEEDS_DEPENDENCY, _NEEDS_UI)

    def _unicode_capability(self) -> DeviceCapability:
        name = "unicode_text"
        if self.has_ui_automator:
            return DeviceCapability(name, STATE_AVAILABLE)
        try:
            ime = current_input_method(self.adb)
        except AdbError as error:
            return DeviceCapability(name, STATE_NEEDS_DEPENDENCY, str(error))
        if ime == ADB_KEYBOARD_IME:
            return DeviceCapability(name, STATE_AVAILABLE)
        return DeviceCapability(
            name, STATE_NEEDS_DEPENDENCY,
            "`adb shell input text` carries printable ASCII only; other text needs "
            "uiautomator2 on the host or the ADBKeyBoard IME selected on the device",
            alternative="ASCII text works without either")

    def _ui_or_none(self) -> Optional[UIAutomatorDevice]:
        """The uiautomator2 wrapper when that path can be used, else ``None``."""
        return self.ui_device if self.has_ui_automator else None

    def launch_app(self, app_id: str) -> None:
        """Launch a package's launcher activity, or a ``package/activity`` component."""
        self.invoke("launch_app", lambda: android_apps.launch(self.adb, app_id))

    def stop_app(self, app_id: str) -> None:
        """Force-stop a package."""
        self.invoke("stop_app", lambda: android_apps.stop(self.adb, app_id))

    def app_state(self, app_id: str) -> AppState:
        """Whether a package is installed, running, and in front."""
        return self.invoke("app_state", lambda: android_apps.state(self.adb, app_id))

    def answer_alert(self, accept: bool) -> str:
        """Press the accepting or dismissing button of a system dialog (needs uiautomator2)."""
        return self.invoke("answer_alert", lambda: android_apps.answer_dialog(
            self._ui_or_none(), accept))

    def builtin_extension(self) -> android_apps.AndroidExtension:
        """Install, files, clipboard and recording over adb / uiautomator2."""
        return android_apps.AndroidExtension(
            lambda: self.adb, self._ui_or_none, self.device_id)

    def capture(self) -> DeviceFrame:
        """The current screen, upright, in the coordinates ``input tap`` takes."""
        return self.invoke("capture", lambda: capture_frame(self.adb, self.device_id))

    def type_text(self, text: str) -> None:
        """Type ``text`` through a path that can carry it, or raise (see ``android.input``)."""
        self.invoke("type_text", lambda: android_input.type_text(
            self.adb, text, ui_device=self._ui_or_none()))

    def press_key(self, key: str) -> None:
        """Send a keycode (``KEYCODE_HOME``, ``BACK``, or a number)."""
        self.invoke("press_key", lambda: self.adb.key_event(key))

    def _gesture_handlers(self) -> Dict[type, Callable[[Any], None]]:
        adb = self.adb
        ui_device = self._ui_or_none()
        return {
            Tap: lambda g: android_input.tap(adb, g),
            LongPress: lambda g: android_input.long_press(adb, g),
            Swipe: lambda g: android_input.swipe(adb, g),
            Drag: lambda g: android_input.drag(adb, g, ui_device=ui_device),
            Pinch: lambda g: android_input.pinch(adb, g, ui_device=ui_device),
        }

    def _release(self) -> None:
        self._adb = None
        if not self._ui_injected:
            self._ui_device = None


def bound_android_session(serial: Optional[str] = None) -> Optional[AndroidSession]:
    """The Android session bound by ``use_device`` when ``serial`` addresses it."""
    session = bound_session("android", serial)
    return session if isinstance(session, AndroidSession) else None


__all__ = ["AndroidSession", "bound_android_session"]
