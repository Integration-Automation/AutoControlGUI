"""Fake ADB host and fake WebDriverAgent client for the mobile tests.

No ``adb`` binary, emulator, iPhone or WebDriverAgent exists on a CI runner
(or on the machine these tests were written on), so the mobile code is driven
against these doubles:

* :class:`FakeAdbHost` stands in for ``subprocess.run`` inside
  ``android.adb_client``. It parses the real argv the client builds — so the
  ``-s <serial>`` routing, the shell quoting and the exit-code handling are the
  production code's — and answers from one :class:`FakeAndroidDevice` per
  serial.
* :class:`FakeWda` stands in for ``wda.Client``. It records every call and
  keeps just enough state (apps, alert, clipboard, orientation) to answer.

They prove the code sends the commands it means to send. They do not prove a
real device accepts them.
"""
from __future__ import annotations

import base64
import io
import shlex
import subprocess
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"
DEFAULT_IME = "com.google.android.inputmethod.latin/.LatinIME"

#: Shell command prefixes that put input into the device.
_INPUT_PREFIXES = ("input ", "am broadcast", "am start", "am force-stop", "monkey ",
                   "pm ", "screenrecord", "pkill")


def png_bytes(width: int, height: int, color: Tuple[int, int, int] = (0, 0, 0),
              patch: Optional[Tuple[int, int, int, int]] = None) -> bytes:
    """A PNG of ``width`` x ``height``; ``patch`` is a white ``(x, y, w, h)`` block."""
    from PIL import Image
    image = Image.new("RGB", (width, height), color)
    if patch is not None:
        x, y, w, h = patch
        image.paste(Image.new("RGB", (w, h), (255, 255, 255)), (x, y))
        # A dark dot inside the block, so a template of it has structure to match.
        image.paste(Image.new("RGB", (max(1, w // 3), max(1, h // 3)), (10, 40, 90)),
                    (x + w // 4, y + h // 4))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class FakeAndroidDevice:
    """State of one pretend Android device."""

    def __init__(self, serial: str, *, state: str = "device",
                 size: Tuple[int, int] = (1080, 1920), rotation: int = 0,
                 ime: str = DEFAULT_IME) -> None:
        self.serial = serial
        self.state = state
        self.size = size
        self.rotation = rotation
        self.ime = ime
        self.shell_commands: List[str] = []
        self.typed: List[str] = []
        self.running: set = set()
        self.installed: set = set()
        self.files: Dict[str, bytes] = {}
        self.screen: Optional[bytes] = None
        self.recording = False
        self.gate: Optional[threading.Event] = None
        #: False imitates an old ``input`` build without ``draganddrop``.
        self.has_draganddrop = True

    @property
    def device_id(self) -> str:
        """The serial, under the name a device context uses."""
        return self.serial

    @property
    def input_calls(self) -> List[str]:
        """Every shell command that would have acted on the device."""
        return [command for command in self.shell_commands
                if command.startswith(_INPUT_PREFIXES)]

    def screencap(self) -> bytes:
        """The current screen as PNG, in the display's current orientation."""
        if self.screen is not None:
            return self.screen
        width, height = self.size
        if self.rotation % 2:
            width, height = height, width
        return png_bytes(width, height)

    def shell(self, command: str) -> Tuple[int, str]:
        """Answer one ``adb shell`` command: ``(exit code, stdout)``."""
        self.shell_commands.append(command)
        if self.gate is not None:
            self.gate.wait(5)
        for prefix, handler in self._handlers():
            if command.startswith(prefix):
                return handler(command)
        return 0, ""

    def _handlers(self) -> List[Tuple[str, Callable[[str], Tuple[int, str]]]]:
        return [
            ("settings get secure default_input_method", lambda _c: (0, self.ime + "\n")),
            ("wm size", lambda _c: (0, f"Physical size: {self.size[0]}x{self.size[1]}\n")),
            ("dumpsys input", lambda _c: (0, f"  SurfaceOrientation: {self.rotation}\n")),
            ("getprop ro.build.version.release", lambda _c: (0, "14\n")),
            ("am broadcast -a ADB_INPUT_B64", self._ime_broadcast),
            ("input text ", self._input_text),
            ("input draganddrop ", self._draganddrop),
            ("monkey -p ", self._launch),
            ("am force-stop ", self._stop),
            ("pidof ", self._pidof),
            ("dumpsys activity activities", self._resumed),
            ("pkill -INT screenrecord", self._stop_recording),
            ("rm ", lambda _c: (0, "")),
        ]

    def _ime_broadcast(self, command: str) -> Tuple[int, str]:
        # The reply is the same whether or not an IME received it, as on a device.
        if self.ime == ADB_KEYBOARD_IME:
            payload = shlex.split(command)[-1]
            self.typed.append(base64.b64decode(payload).decode("utf-8"))
        return 0, "Broadcasting: Intent { act=ADB_INPUT_B64 }\nBroadcast completed: result=0\n"

    def _input_text(self, command: str) -> Tuple[int, str]:
        # What ``input text`` does: %s becomes a space, non-ASCII is dropped, exit 0.
        raw = shlex.split(command)[2].replace("%s", " ")
        self.typed.append("".join(char for char in raw if " " <= char <= "~"))
        return 0, ""

    def _draganddrop(self, _command: str) -> Tuple[int, str]:
        if self.has_draganddrop:
            return 0, ""
        return 0, "Error: Unknown command: draganddrop\nUsage: input [<source>] <command>\n"

    def _launch(self, command: str) -> Tuple[int, str]:
        package = shlex.split(command)[2]
        if package not in self.installed:
            return 0, "** No activities found to run, monkey aborted.\n"
        self.running.add(package)
        self.foreground = package
        return 0, "Events injected: 1\n"

    def _stop(self, command: str) -> Tuple[int, str]:
        package = shlex.split(command)[-1]
        self.running.discard(package)
        if getattr(self, "foreground", "") == package:
            self.foreground = ""
        return 0, ""

    def _pidof(self, command: str) -> Tuple[int, str]:
        package = shlex.split(command)[-1]
        return (0, "4242\n") if package in self.running else (1, "")

    def _resumed(self, _command: str) -> Tuple[int, str]:
        package = getattr(self, "foreground", "")
        if not package:
            return 0, ""
        return 0, f"    topResumedActivity=ActivityRecord{{1 u0 {package}/.Main t7}}\n"

    def _stop_recording(self, _command: str) -> Tuple[int, str]:
        self.recording = False
        return 0, ""


class FakeAdbHost:
    """Replacement for ``subprocess.run`` in ``android.adb_client``."""

    def __init__(self) -> None:
        self.devices: Dict[str, FakeAndroidDevice] = {}
        self.calls: List[Tuple[Optional[str], List[str]]] = []
        self.host_files: Dict[str, bytes] = {}
        self._lock = threading.Lock()

    def add(self, serial: str, **kwargs: Any) -> FakeAndroidDevice:
        """Attach a device and return it."""
        device = FakeAndroidDevice(serial, **kwargs)
        self.devices[serial] = device
        return device

    def calls_for(self, serial: str) -> List[List[str]]:
        """The adb argv (after ``-s serial``) of every call addressed to ``serial``."""
        return [args for target, args in self.calls if target == serial]

    def run(self, cmd: List[str], **_kwargs: Any) -> subprocess.CompletedProcess:
        """Answer one adb invocation."""
        serial, args = self._split(cmd)
        with self._lock:
            self.calls.append((serial, list(args)))
        if args[:1] == ["devices"]:
            return self._done(0, self._listing())
        if args[:1] == ["version"]:
            return self._done(0, "Android Debug Bridge version 1.0.41\nVersion 35.0.2-12147458\n")
        device = self._target(serial)
        if isinstance(device, subprocess.CompletedProcess):
            return device
        return self._dispatch(device, args)

    def _dispatch(self, device: FakeAndroidDevice,
                  args: List[str]) -> subprocess.CompletedProcess:
        if args[0] == "shell":
            code, out = device.shell(args[1])
            return self._done(code, out)
        if args[:2] == ["exec-out", "screencap"]:
            return self._done(0, device.screencap())
        if args[0] == "install":
            device.installed.add(args[-1])
            return self._done(0, "Performing Streamed Install\nSuccess\n")
        if args[0] == "push":
            device.files[args[2]] = self.host_files.get(args[1], b"")
            return self._done(0, "1 file pushed\n")
        if args[0] == "pull":
            if args[1] not in device.files:
                return self._done(1, "", f"adb: error: failed to stat remote object '{args[1]}'")
            self.host_files[args[2]] = device.files[args[1]]
            return self._done(0, "1 file pulled\n")
        return self._done(0, "")

    def _target(self, serial: Optional[str]) -> Any:
        if serial is None:
            ready = list(self.devices.values())
            if len(ready) != 1:
                return self._done(1, "", "adb: more than one device/emulator")
            return ready[0]
        device = self.devices.get(serial)
        if device is None:
            return self._done(1, "", f"adb: device '{serial}' not found")
        if device.state == "unauthorized":
            return self._done(
                1, "", "adb: device unauthorized.\nThis adb server's $ADB_VENDOR_KEYS is not set")
        if device.state != "device":
            return self._done(1, "", f"adb: device {device.state}")
        return device

    def _listing(self) -> str:
        lines = ["List of devices attached"]
        lines.extend(f"{d.serial}\t{d.state} product:fake model:Fake_{d.serial} transport_id:1"
                     for d in self.devices.values())
        return "\n".join(lines) + "\n"

    @staticmethod
    def _split(cmd: List[str]) -> Tuple[Optional[str], List[str]]:
        rest = list(cmd[1:])
        if rest[:1] == ["-s"]:
            return rest[1], rest[2:]
        return None, rest

    @staticmethod
    def _done(code: int, out: Any, err: str = "") -> subprocess.CompletedProcess:
        stdout = out if isinstance(out, bytes) else str(out).encode("utf-8")
        # nosemgrep  # reason: a CompletedProcess value object, no process is started
        return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout,
                                           stderr=err.encode("utf-8"))


class FakeU2Object:
    """What ``device(**selector)`` returns."""

    def __init__(self, owner: "FakeU2", selector: Dict[str, Any]) -> None:
        self._owner = owner
        self._selector = selector

    @property
    def exists(self) -> bool:
        return self._selector.get("resourceId") in self._owner.buttons

    def click(self) -> None:
        self._owner.record("click", **self._selector)
        self._owner.buttons.discard(self._selector.get("resourceId"))

    def gesture(self, start1: Any, start2: Any, end1: Any, end2: Any,
                steps: int = 100) -> None:
        self._owner.record("gesture", start1=start1, start2=start2, end1=end1,
                           end2=end2, steps=steps)


class FakeU2:
    """Replacement for ``uiautomator2.Device``."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.typed: List[str] = []
        self.buttons: set = set()
        self.clipboard = ""

    def record(self, op: str, **details: Any) -> None:
        """Note one call."""
        self.calls.append({"op": op, **details})

    def __call__(self, **selector: Any) -> FakeU2Object:
        return FakeU2Object(self, selector)

    def send_keys(self, text: str, clear: bool = False) -> None:
        self.record("send_keys", clear=clear)
        self.typed.append(text)

    def drag(self, sx: int, sy: int, ex: int, ey: int, duration: float = 0.5) -> None:
        self.record("drag", sx=sx, sy=sy, ex=ex, ey=ey, duration=duration)

    def set_clipboard(self, text: str, label: Optional[str] = None) -> None:
        self.record("set_clipboard", label=label)
        self.clipboard = text


class FakeWdaAlert:
    """The ``client.alert`` object."""

    def __init__(self, owner: "FakeWda") -> None:
        self._owner = owner

    @property
    def exists(self) -> bool:
        return self._owner.alert_text is not None

    @property
    def text(self) -> str:
        return self._owner.alert_text or ""

    def accept(self) -> None:
        self._owner.record("alert.accept")
        self._owner.alert_text = None

    def dismiss(self) -> None:
        self._owner.record("alert.dismiss")
        self._owner.alert_text = None


class FakeWdaElement:
    """What a selector resolves to."""

    def __init__(self, owner: "FakeWda") -> None:
        self._owner = owner

    def pinch(self, scale: float, velocity: float) -> None:
        self._owner.record("pinch", scale=scale, velocity=velocity)


class FakeWda:
    """Replacement for ``wda.Client``: records calls, keeps a little state."""

    def __init__(self, *, points: Tuple[int, int] = (390, 844), scale: int = 3,
                 orientation: str = "PORTRAIT") -> None:
        self.points = points
        self.scale = scale
        self.orientation = orientation
        self.calls: List[Dict[str, Any]] = []
        self.typed: List[str] = []
        self.app_states: Dict[str, int] = {}
        self.alert_text: Optional[str] = None
        self.clipboard = ""
        self.screen: Optional[bytes] = None
        self.gate: Optional[threading.Event] = None
        self.alert = FakeWdaAlert(self)

    def record(self, op: str, **details: Any) -> None:
        """Note one call."""
        self.calls.append({"op": op, **details})

    @property
    def input_calls(self) -> List[Dict[str, Any]]:
        """Every call that would have acted on the device."""
        passive = {"status", "window_size", "screenshot", "orientation", "app_state", "select"}
        return [call for call in self.calls if call["op"] not in passive]

    def __call__(self, **selectors: Any) -> FakeWdaElement:
        self.record("select", **selectors)
        return FakeWdaElement(self)

    def status(self) -> Dict[str, Any]:
        self.record("status")
        return {"build": {"productBundleIdentifier": "com.facebook.WebDriverAgentRunner",
                          "version": "8.5.2"},
                "os": {"name": "iOS", "version": "17.4"}, "ready": True}

    def window_size(self) -> Tuple[int, int]:
        self.record("window_size")
        width, height = self.points
        if self.orientation != "PORTRAIT":
            width, height = height, width
        return width, height

    def screenshot(self, *args: Any, **kwargs: Any) -> Any:
        self.record("screenshot")
        from PIL import Image
        if self.screen is not None:
            image = Image.open(io.BytesIO(self.screen))
        else:
            width, height = self.window_size()
            image = Image.new("RGB", (width * self.scale, height * self.scale))
        if args and isinstance(args[0], str):
            image.save(args[0], format="PNG")
        return image

    def tap(self, x: int, y: int) -> None:
        if self.gate is not None:
            self.gate.wait(5)
        self.record("tap", x=x, y=y)

    def tap_hold(self, x: int, y: int, duration: float) -> None:
        self.record("tap_hold", x=x, y=y, duration=duration)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: float) -> None:
        self.record("swipe", x1=x1, y1=y1, x2=x2, y2=y2, duration=duration)

    def send_keys(self, text: str) -> None:
        self.record("send_keys", text=text)
        self.typed.append(text)

    def press(self, name: str) -> None:
        self.record("press", name=name)

    def app_launch(self, bundle_id: str, **_kwargs: Any) -> None:
        self.record("app_launch", bundle_id=bundle_id)
        self.app_states[bundle_id] = 4

    def app_terminate(self, bundle_id: str) -> None:
        self.record("app_terminate", bundle_id=bundle_id)
        self.app_states[bundle_id] = 1

    def app_state(self, bundle_id: str) -> Dict[str, Any]:
        self.record("app_state", bundle_id=bundle_id)
        return {"value": self.app_states.get(bundle_id, 1)}

    def set_clipboard(self, content: str, *_args: Any) -> None:
        self.record("set_clipboard")
        self.clipboard = content
