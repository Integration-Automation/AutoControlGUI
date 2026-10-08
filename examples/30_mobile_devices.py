"""Drive Android and iOS devices through isolated device sessions.

One :class:`DeviceContext` names one device; :func:`open_device` turns it into
a session that owns its own transport, timeout and cancellation. Nothing in a
session reads a process-wide default, so two workers of a device matrix cannot
reach each other's phone by leaving an argument out::

    context = ac.DeviceContext("android", "emulator-5554", timeout_s=20)
    with ac.open_device(context) as session:
        print(ac.device_setup_report(session).to_dict())   # sends no input
        frame = session.capture()                           # a DeviceFrame
        x, y = frame.locate_image("login_button.png")       # answers in device points
        session.perform(ac.Tap(x, y))
        session.type_text("hello")

iOS is the same with ``ac.DeviceContext("ios", "http://127.0.0.1:8100")`` (a
WebDriverAgent URL). Gestures are ``Tap``, ``LongPress``, ``Swipe``, ``Drag``
and ``Pinch``; app lifecycle is ``ac.launch_app`` / ``stop_app`` /
``app_state`` / ``wait_for_app``.

**Check a setup before blaming a script.** ``device_setup_report`` says which
backend and version answered and gives every capability a state --
``available``, ``needs_permission`` (accept the USB-debugging prompt),
``needs_dependency`` (install the ADB Keyboard IME for non-ASCII text, or the
``uiautomator2`` extra for multi-touch) or ``unsupported`` -- with the reason.

Every operation is also an ``AC_android_*`` / ``AC_ios_*`` command and an MCP
tool, generated from one table::

    ac.run_mobile_command("AC_android_tap", {"x": 540, "y": 960, "serial": "emulator-5554"})
    ac.mobile_capability_matrix()      # which commands deliver what, per platform

What has no mobile counterpart (windows, mouse buttons, hotkeys, the desktop
accessibility tree) is listed there too, with the alternative.

Requirements for a real device: Android needs ``adb`` on ``PATH`` and USB
debugging authorised; iOS needs a running WebDriverAgent and
``pip install je_auto_control[ios]``. Neither can be verified without the
hardware -- ``--validate`` replaces the transport with an offline stand-in
that answers the adb commands the session builds, so it proves which commands
are sent and nothing about a phone. Without the flag the script prints the
setup report of the device you name and sends it no input unless ``--tap`` is
given.
"""
import argparse
import io
import subprocess  # nosec B404  # reason: only for the CompletedProcess type; nothing is spawned
import sys
from typing import Any, List, Optional, Sequence

import je_auto_control as ac
# Subclassed below to build the offline transport; a real run never imports it.
from je_auto_control.android.adb_client import AdbClient

_SERIAL = "emulator-5554"
_SIZE = (1080, 1920)
_INPUT_COMMANDS = ("input ", "am broadcast", "am start", "monkey ")


def _blank_png() -> bytes:
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", _SIZE, (20, 20, 20)).save(buffer, format="PNG")
    return buffer.getvalue()


class OfflineAdb(AdbClient):
    """The real client with the one method that spawns ``adb`` replaced.

    Every other method -- ``tap``, ``text``, ``screencap_png``, ``version`` --
    is the production code, so the argv recorded here is what a device would
    receive. No process is started.
    """

    def __init__(self, serial: str) -> None:
        super().__init__(adb_path="adb (offline)", default_serial=serial)
        self.sent: List[str] = []

    def run(self, args: Sequence[str], **_options: Any) -> "subprocess.CompletedProcess[bytes]":
        """Answer one adb invocation from canned replies."""
        self.sent.append(" ".join(args))
        return subprocess.CompletedProcess(list(args), 0, self._reply(list(args)), b"")

    def _reply(self, args: List[str]) -> bytes:
        if args[:1] == ["devices"]:
            return f"List of devices attached\n{self.default_serial}\tdevice\n".encode()
        if args[:1] == ["version"]:
            return b"Android Debug Bridge version 1.0.41\nVersion 35.0.2-12147458\n"
        if args[:2] == ["exec-out", "screencap"]:
            return _blank_png()
        replies = {
            "wm size": f"Physical size: {_SIZE[0]}x{_SIZE[1]}\n",
            "dumpsys input": "  SurfaceOrientation: 0\n",
            "getprop ro.build.version.release": "14\n",
            "settings get secure default_input_method":
                "com.google.android.inputmethod.latin/.LatinIME\n",
        }
        command = args[1] if args[:1] == ["shell"] and len(args) > 1 else ""
        return next((text for prefix, text in replies.items()
                     if command.startswith(prefix)), "").encode()

    @property
    def input_sent(self) -> List[str]:
        """The shell commands that would have acted on a device."""
        return [line[len("shell "):] for line in self.sent
                if line.startswith("shell ") and line[len("shell "):].startswith(_INPUT_COMMANDS)]


def show_report(report: ac.DeviceSetupReport) -> None:
    """Print a setup report: what answered, and each capability's state."""
    print(f"{report.platform} {report.device_id}: backend {report.backend}"
          f" {report.backend_version} / OS {report.os_version} -> {report.state}")
    for name, capability in report.capabilities.items():
        reason = f" -- {capability.reason}" if capability.reason else ""
        print(f"  {name:<14} {capability.state}{reason}")


def validate() -> int:
    """Open a session over the offline transport and check what it would send."""
    adb = OfflineAdb(_SERIAL)
    context = ac.DeviceContext("android", _SERIAL, timeout_s=5, label="offline pixel")
    with ac.open_device(context, adb=adb) as session:
        report = ac.device_setup_report(session)
        show_report(report)
        probing = list(adb.input_sent)             # a probe must not touch the device
        frame = session.capture()
        print(f"captured {frame.pixel_size} px as {frame.to_dict()['point_size']} points,"
              f" scale {frame.scale:g}")
        session.perform(ac.Tap(540, 960))
        session.perform(ac.Swipe(540, 1500, 540, 500, duration_s=0.2))
        session.type_text("hello")
        # A bound session is what address-less mobile commands target.
        with ac.use_device(session):
            ac.run_mobile_command("AC_android_tap", {"x": 10, "y": 20})
    print("sent to the device:", adb.input_sent)

    matrix = ac.mobile_capability_matrix()
    for row in matrix["capabilities"]:
        print(f"  {row['capability']:<14} android={len(row['android'])} ios={len(row['ios'])} command(s)")
    print(f"  {len(matrix['desktop_only'])} desktop-only feature(s) documented with an alternative")

    problems = []
    if probing:
        problems.append(f"the setup report sent input: {probing}")
    if report.state != "available" or report.backend != "adb":
        problems.append(f"unexpected setup report: {report.to_dict()}")
    wanted = ["input tap 540 960", "input swipe 540 1500 540 500 200", "input tap 10 20"]
    missing = [command for command in wanted if command not in adb.input_sent]
    if missing:
        problems.append(f"not sent: {missing}")
    if not any(command.startswith("input text") for command in adb.input_sent):
        problems.append("type_text sent no input text command")
    if session.connected:
        problems.append("the session was not closed on leaving the with block")
    for problem in problems:
        print(f"FAILED: {problem}")
    print("validate:", "failed" if problems else "ok")
    return 1 if problems else 0


def real_device(platform: str, device_id: str, tap: Optional[List[int]]) -> int:
    """Print the setup report of a real device; tap only when asked to."""
    with ac.open_device(ac.DeviceContext(platform, device_id)) as session:
        report = ac.device_setup_report(session)
        show_report(report)
        if tap is None:
            return 0
        if report.state != "available":
            print(f"not tapping: input is {report.state} ({report.reason})")
            return 1
        session.perform(ac.Tap(tap[0], tap[1]))
        print(f"tapped {tap[0]},{tap[1]}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Parse the command line; see the module docstring."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--validate", action="store_true",
                        help="use an offline transport; no adb, no device")
    parser.add_argument("--platform", choices=("android", "ios"), default="android")
    parser.add_argument("--device", default="",
                        help="adb serial or WebDriverAgent URL (empty: the only one attached)")
    parser.add_argument("--tap", nargs=2, type=int, metavar=("X", "Y"),
                        help="REAL INPUT: tap this point on the device")
    args = parser.parse_args(argv)
    if args.validate:
        return validate()
    return real_device(args.platform, args.device, args.tap)


if __name__ == "__main__":
    sys.exit(main())
