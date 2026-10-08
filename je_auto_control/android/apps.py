"""Android app lifecycle, system dialogs and device extensions over adb.

Lifecycle and file transfer need nothing but ``adb``. Dialog buttons and the
clipboard need the uiautomator2 daemon, because ``adb shell`` can neither read
the widget tree nor reach the clipboard on current Android; without it those
calls raise and say so.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess  # nosec B404  # reason: holds the adb process of a running screen recording
import threading
from time import monotonic, sleep
from typing import Any, Dict, Optional, Sequence

from je_auto_control.android.adb_client import AdbError, AdbUnsupportedError
from je_auto_control.android.client import UIAutomatorDevice, translate_device_errors
from je_auto_control.wrapper.device_context import (
    STATE_AVAILABLE, STATE_NEEDS_DEPENDENCY, AlertNotPresentError, AppState,
    DeviceCapability, DeviceError,
)

_PACKAGE = re.compile(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+")
_COMPONENT = re.compile(r"[A-Za-z0-9_.]+/[A-Za-z0-9_.$]+")
_RESUMED = re.compile(
    r"(?:topResumedActivity|mResumedActivity|ResumedActivity)[=:]\s*ActivityRecord\{\S+ \S+ ([\w.]+)/")
_NEEDS_UI = "uiautomator2 is not installed: pip install uiautomator2"

#: Buttons that accept a system dialog, most specific first.
ACCEPT_BUTTONS = (
    "com.android.permissioncontroller:id/permission_allow_foreground_only_button",
    "com.android.permissioncontroller:id/permission_allow_button",
    "com.android.packageinstaller:id/permission_allow_button",
    "android:id/button1",
)
#: Buttons that dismiss a system dialog.
DISMISS_BUTTONS = (
    "com.android.permissioncontroller:id/permission_deny_button",
    "com.android.packageinstaller:id/permission_deny_button",
    "android:id/button2",
)
DEFAULT_RECORDING_PATH = "/sdcard/autocontrol_recording.mp4"
#: ``screenrecord`` refuses anything longer.
MAX_RECORDING_S = 180
_FINALIZE_TIMEOUT_S = 10.0

#: adb processes of running recordings, by device. A recording is device-side
#: state that outlives the command (and the session) that started it, so the
#: command that stops it has to be able to find it again.
_RECORDINGS: Dict[str, Any] = {}
_RECORDINGS_LOCK = threading.Lock()


def _package(app_id: str) -> str:
    """``app_id`` checked as a package name: it goes into a device shell command."""
    if not isinstance(app_id, str) or not _PACKAGE.fullmatch(app_id):
        raise AdbError(f"not an Android package name: {app_id!r}")
    return app_id


def launch(adb: Any, app_id: str) -> None:
    """Start an app by package (its launcher activity) or by ``package/activity``."""
    if isinstance(app_id, str) and _COMPONENT.fullmatch(app_id):
        out = adb.shell(f"am start -n {app_id}")
        if "Error" in out:
            raise AdbError(f"could not start {app_id}: {out.strip().splitlines()[-1]}")
        return
    package = _package(app_id)
    out = adb.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1")
    if "No activities found" in out or "monkey aborted" in out:
        raise AdbError(f"{package} is not installed or has no launcher activity")


def stop(adb: Any, app_id: str) -> None:
    """Force-stop an app."""
    adb.shell(f"am force-stop {_package(app_id.split('/')[0])}")


def state(adb: Any, app_id: str) -> AppState:
    """Whether the app is installed, running, and in front."""
    package = _package(app_id.split("/")[0])
    code, _out = adb.shell_status(f"pidof {package}")
    if code != 0:
        installed, _path = adb.shell_status(f"pm path {package}")
        return AppState.NOT_RUNNING if installed == 0 else AppState.NOT_INSTALLED
    resumed = _RESUMED.search(adb.shell("dumpsys activity activities"))
    if resumed is not None and resumed.group(1) == package:
        return AppState.FOREGROUND
    return AppState.BACKGROUND


@translate_device_errors
def _press_dialog_button(ui_device: UIAutomatorDevice, buttons: Sequence[str]) -> str:
    handle = ui_device.handle
    for resource_id in buttons:
        button = handle(resourceId=resource_id)
        if button.exists:
            button.click()
            return resource_id
    raise AlertNotPresentError("no system dialog with a matching button is showing")


def answer_dialog(ui_device: Optional[UIAutomatorDevice], accept: bool) -> str:
    """Press the accepting or dismissing button of a system dialog; returns its resource id."""
    if ui_device is None:
        raise AdbUnsupportedError(
            "pressing a dialog button needs the widget tree, which adb alone cannot read",
            reason=_NEEDS_UI,
            alternative="locate the button in a captured frame (find_text / find_image) and tap it")
    return _press_dialog_button(ui_device, ACCEPT_BUTTONS if accept else DISMISS_BUTTONS)


def _existing_file(path: str) -> str:
    resolved = os.path.realpath(os.fspath(path))
    if not os.path.isfile(resolved):
        raise AdbError(f"no such file: {path}")
    return resolved


def _remote_path(path: str) -> str:
    if not isinstance(path, str) or not path.startswith("/") or "\x00" in path:
        raise AdbError(f"a device path must be absolute, got {path!r}")
    return path


class AndroidExtension:
    """Install, files, clipboard and screen recording for one Android device."""

    name = "adb"

    def __init__(self, adb_source: Any, ui_source: Any, device_id: str = "") -> None:
        # Callables, so nothing is built (and no adb is needed) until a feature is used.
        self._adb_source = adb_source
        self._ui_source = ui_source
        self._key = device_id

    @property
    def _adb(self) -> Any:
        return self._adb_source()

    def capability(self, feature: str) -> DeviceCapability:
        """Whether ``feature`` can be used on this device."""
        if feature != "clipboard" or self._ui_source() is not None:
            return DeviceCapability(feature, STATE_AVAILABLE)
        return DeviceCapability(
            feature, STATE_NEEDS_DEPENDENCY, _NEEDS_UI,
            alternative="type the text with type_text instead of pasting it")

    def install_app(self, source: str) -> str:
        """Install (or replace) an APK from the host; returns the path installed."""
        apk = _existing_file(source)
        out = self._adb.run(["install", "-r", apk]).stdout.decode("utf-8", errors="replace")
        if "Success" not in out:
            # adb exits 0 for some refusals and prints "Failure [REASON]".
            raise AdbError(f"install failed: {out.strip().splitlines()[-1] if out.strip() else ''}")
        return apk

    def push_file(self, local_path: str, remote_path: str) -> str:
        """Copy a host file to the device; returns the device path."""
        self._adb.run(["push", _existing_file(local_path), _remote_path(remote_path)])
        return remote_path

    def pull_file(self, remote_path: str, local_path: str) -> str:
        """Copy a device file to the host; returns the host path."""
        target = os.path.realpath(os.fspath(local_path))
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        self._adb.run(["pull", _remote_path(remote_path), target])
        return target

    def _clipboard_device(self) -> UIAutomatorDevice:
        ui_device = self._ui_source()
        if ui_device is None:
            raise AdbUnsupportedError(
                "the clipboard cannot be reached through adb on current Android",
                reason=_NEEDS_UI,
                alternative="type the text with type_text instead of pasting it")
        return ui_device

    def get_clipboard(self) -> str:
        """The device clipboard's text."""
        return _read_clipboard(self._clipboard_device())

    def set_clipboard(self, text: str) -> None:
        """Put ``text`` on the device clipboard."""
        _write_clipboard(self._clipboard_device(), text)

    def start_recording(self, remote_path: str = DEFAULT_RECORDING_PATH,
                        time_limit_s: int = MAX_RECORDING_S) -> str:
        """Start ``screenrecord`` on the device; returns the device path it writes."""
        limit = int(time_limit_s)
        if not 1 <= limit <= MAX_RECORDING_S:
            raise AdbError(f"time_limit_s must be 1..{MAX_RECORDING_S}, got {time_limit_s!r}")
        target = _remote_path(remote_path)
        with _RECORDINGS_LOCK:
            if self._key in _RECORDINGS and _RECORDINGS[self._key].poll() is None:
                raise AdbError("a recording is already running on this device")
            _RECORDINGS[self._key] = self._adb.spawn(
                ["shell", f"screenrecord --time-limit {limit} {shlex.quote(target)}"])
        return target

    def stop_recording(self, local_path: str,
                       remote_path: str = DEFAULT_RECORDING_PATH) -> str:
        """Stop the recording, copy it to the host and delete it from the device."""
        adb = self._adb
        # SIGINT, not SIGKILL: screenrecord has to write the MP4 index on the way out.
        adb.shell_status("pkill -INT screenrecord")
        with _RECORDINGS_LOCK:
            process = _RECORDINGS.pop(self._key, None)
        _wait_finalized(adb, process)
        saved = self.pull_file(remote_path, local_path)
        adb.shell_status(f"rm -f {shlex.quote(_remote_path(remote_path))}")
        return saved


def _wait_finalized(adb: Any, process: Any) -> None:
    """Wait until ``screenrecord`` has exited, so the file it wrote is complete."""
    if process is not None:
        try:
            process.wait(timeout=_FINALIZE_TIMEOUT_S)
        except subprocess.TimeoutExpired as error:
            process.kill()
            raise AdbError("screenrecord did not stop; the recording is incomplete") from error
        return
    # Started by another process: all that can be watched is the device side.
    deadline = monotonic() + _FINALIZE_TIMEOUT_S
    while adb.shell_status("pidof screenrecord")[0] == 0:
        if monotonic() >= deadline:
            raise DeviceError("screenrecord did not stop; the recording is incomplete")
        sleep(0.1)


@translate_device_errors
def _read_clipboard(ui_device: UIAutomatorDevice) -> str:
    return str(ui_device.handle.clipboard or "")


@translate_device_errors
def _write_clipboard(ui_device: UIAutomatorDevice, text: str) -> None:
    if not isinstance(text, str):
        raise TypeError("clipboard text must be a string")
    ui_device.handle.set_clipboard(text)


__all__ = [
    "ACCEPT_BUTTONS", "AndroidExtension", "DEFAULT_RECORDING_PATH", "DISMISS_BUTTONS",
    "MAX_RECORDING_S", "answer_dialog", "launch", "state", "stop",
]
