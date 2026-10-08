"""AdbClient — thin wrapper around the ``adb`` CLI for Android automation."""
from __future__ import annotations

import re
import shlex
import shutil
import subprocess  # nosec B404  # reason: required to invoke the adb binary
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from je_auto_control.wrapper.device_context import (
    DeviceError, DevicePermissionError, DeviceTimeoutError, DeviceUnavailableError,
    DeviceUnsupportedError,
)

_DEFAULT_TIMEOUT_S = 30.0


class AdbError(DeviceError):
    """Raised when adb returns a non-zero exit code."""


class AdbNotAvailable(DeviceUnavailableError):
    """Raised when the adb binary isn't on PATH and no path was supplied."""


class AdbTimeoutError(AdbError, DeviceTimeoutError):
    """Raised when adb did not answer within the client's timeout."""


class AdbUnauthorizedError(AdbError, DevicePermissionError):
    """Raised when the device has not authorised this host for USB debugging."""


class AdbDeviceMissingError(AdbError, DeviceUnavailableError):
    """Raised when the addressed device is offline or not attached."""


class AdbUnsupportedError(AdbError, DeviceUnsupportedError):
    """Raised when adb on this device cannot do what was asked."""


def adb_text_safe(value: str) -> bool:
    """Whether ``adb shell input text`` delivers ``value`` unchanged.

    It maps characters through the key character map, so only printable ASCII
    arrives; and it turns every ``%s`` into a space with no escape for it.
    """
    return "%s" not in value and all(" " <= char <= "~" for char in value)


#: adb's own wording for a refused or absent device, mapped to the typed error.
#: Anchored on "device": a shell's "sh: foo: not found" is not a missing device.
_STDERR_ERRORS = (
    (re.compile(r"device unauthorized|no permissions"), AdbUnauthorizedError),
    (re.compile(r"device (?:'[^']*' )?not found|device offline|no devices/emulators found"
                r"|more than one device"), AdbDeviceMissingError),
)


def _exit_error(args: Sequence[str], returncode: int, stderr: str) -> AdbError:
    """The typed error for a non-zero adb exit."""
    lowered = stderr.lower()
    kind = next((error for pattern, error in _STDERR_ERRORS if pattern.search(lowered)),
                AdbError)
    return kind(f"{_describe(args)} exited {returncode}: {stderr}")


@dataclass
class AndroidDevice:
    """One device row from ``adb devices -l``."""
    serial: str
    state: str
    model: str = ""
    product: str = ""
    transport_id: Optional[str] = None

    def is_ready(self) -> bool:
        return self.state == "device"


def _describe(args: Sequence[str]) -> str:
    """The adb subcommand, for an error message: never its arguments.

    ``adb shell input text <text>`` put the typed text -- a filled-in
    ``${secrets.*}`` value -- into the exception, the run record and the log.
    """
    if not args:
        return "adb"
    return f"adb {args[0]}" + (" ..." if len(args) > 1 else "")


class AdbClient:
    """Wrap the ``adb`` binary so the rest of AutoControl never shells out.

    Pass ``adb_path`` to point at a non-default binary (e.g. on Windows
    you might want to use a portable ``platform-tools/adb.exe`` rather
    than the system PATH lookup). ``default_serial`` lets every method
    skip the explicit ``serial`` kwarg when only one device is attached.
    """

    def __init__(self, *, adb_path: Optional[str] = None,
                 default_serial: Optional[str] = None,
                 timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        resolved = adb_path or shutil.which("adb")
        if resolved is None:
            raise AdbNotAvailable(
                "adb binary not found on PATH — install Android "
                "platform-tools and add adb to PATH, or pass adb_path=…",
            )
        self._adb = resolved
        self._default_serial = default_serial
        self._timeout = float(timeout_s)

    @property
    def adb_path(self) -> str:
        return self._adb

    @property
    def default_serial(self) -> Optional[str]:
        """The serial every call targets when it names none."""
        return self._default_serial

    # --- low-level command runner -------------------------------------

    def run(self, args: Sequence[str], *, serial: Optional[str] = None,
            input_bytes: Optional[bytes] = None,
            timeout: Optional[float] = None,
            check: bool = True) -> subprocess.CompletedProcess:
        """Invoke adb with ``args``. Honours the per-instance default serial."""
        cmd: List[str] = [self._adb]
        target = serial if serial is not None else self._default_serial
        if target:
            cmd.extend(["-s", target])
        cmd.extend(args)
        try:
            result = subprocess.run(  # nosec B603  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit  # reason: argv list, no shell, adb path resolved by shutil.which / explicit override
                cmd, input=input_bytes,
                capture_output=True, timeout=timeout or self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            # Not str(error): TimeoutExpired quotes the whole argv, typed text included.
            raise AdbTimeoutError(
                f"{_describe(args)} timed out after {timeout or self._timeout:g}s") from error
        except (OSError, subprocess.SubprocessError) as error:
            raise AdbError(f"{_describe(args)} failed: {error}") from error
        if check and result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise _exit_error(args, result.returncode, stderr)
        return result

    def shell(self, command: str, *, serial: Optional[str] = None,
              timeout: Optional[float] = None) -> str:
        """Run ``adb shell <command>`` and return the decoded stdout."""
        result = self.run(
            ["shell", command], serial=serial, timeout=timeout,
        )
        return result.stdout.decode("utf-8", errors="replace")

    def shell_status(self, command: str, *, serial: Optional[str] = None,
                     timeout: Optional[float] = None) -> Tuple[int, str]:
        """Run a shell command whose exit code is the answer: ``(code, stdout)``.

        ``pidof`` and ``pm path`` exit non-zero to say "no". A non-zero exit
        because the *device* failed (unauthorised, gone) is still raised, so
        an unreachable device is never read as "not running".
        """
        result = self.run(["shell", command], serial=serial, timeout=timeout, check=False)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            error = _exit_error(["shell"], result.returncode, stderr)
            if type(error) is not AdbError:
                raise error
        return result.returncode, result.stdout.decode("utf-8", errors="replace")

    def spawn(self, args: Sequence[str], *,
              serial: Optional[str] = None) -> "subprocess.Popen[bytes]":
        """Start adb without waiting for it (a screen recording); the caller owns the process."""
        cmd: List[str] = [self._adb]
        target = serial if serial is not None else self._default_serial
        if target:
            cmd.extend(["-s", target])
        cmd.extend(args)
        try:
            return subprocess.Popen(  # nosec B603  # nosemgrep  # reason: argv list, no shell, same adb path as run()
                cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
        except OSError as error:
            raise AdbError(f"{_describe(args)} failed: {error}") from error

    # --- device discovery ---------------------------------------------

    def list_devices(self) -> List[AndroidDevice]:
        """Parse ``adb devices -l`` into AndroidDevice records."""
        result = self.run(["devices", "-l"])
        out = result.stdout.decode("utf-8", errors="replace")
        devices: List[AndroidDevice] = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices") or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state, rest = parts[0], parts[1], parts[2:]
            if line[len(serial):].lstrip().startswith("no permissions"):
                # "no permissions (user in plugdev group; ...)": not the state "no".
                state = "no permissions"
            metadata = {
                key: value
                for token in rest
                if ":" in token
                for key, _, value in [token.partition(":")]
            }
            devices.append(AndroidDevice(
                serial=serial, state=state,
                model=metadata.get("model", ""),
                product=metadata.get("product", ""),
                transport_id=metadata.get("transport_id"),
            ))
        return devices

    def device_state(self, serial: Optional[str] = None) -> str:
        """The ``adb devices`` state of one device, or ``""`` when it is not listed.

        With no serial (and no default one) the answer is the single attached
        device's state; several devices and no serial is ``""``.
        """
        target = serial if serial is not None else self._default_serial
        devices = self.list_devices()
        if target:
            return next((d.state for d in devices if d.serial == target), "")
        return devices[0].state if len(devices) == 1 else ""

    def version(self) -> str:
        """The adb build, e.g. ``"1.0.41 (35.0.2-12147458)"``."""
        out = self.run(["version"]).stdout.decode("utf-8", errors="replace")
        release = re.search(r"Android Debug Bridge version (\S+)", out)
        build = re.search(r"^Version (\S+)", out, re.MULTILINE)
        parts = [release.group(1) if release else "",
                 f"({build.group(1)})" if build else ""]
        return " ".join(part for part in parts if part)

    # --- input -------------------------------------------------------

    def tap(self, x: int, y: int, *, serial: Optional[str] = None) -> None:
        """Single tap at ``(x, y)`` in device pixels."""
        self.shell(f"input tap {int(x)} {int(y)}", serial=serial)

    def swipe(self, x1: int, y1: int, x2: int, y2: int,
              *, duration_ms: int = 250,
              serial: Optional[str] = None) -> None:
        """Touch swipe from ``(x1,y1)`` to ``(x2,y2)`` over ``duration_ms``."""
        self.shell(
            f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} "
            f"{int(duration_ms)}",
            serial=serial,
        )

    def input_command(self, command: str, *, serial: Optional[str] = None,
                      timeout: Optional[float] = None) -> None:
        """Run ``adb shell input <command>``, raising when ``input`` rejected it.

        An ``input`` build that does not know a subcommand prints its usage
        and can still exit 0.
        """
        out = self.shell(f"input {command}", serial=serial, timeout=timeout)
        if "Unknown command" in out or out.lstrip().startswith("Error:"):
            raise AdbUnsupportedError(
                f"this device's `input` does not support `{command.split()[0]}`",
                alternative="uiautomator2 (pip install uiautomator2)")

    def key_event(self, key: str, *, serial: Optional[str] = None) -> None:
        """Send a keycode — accepts ``KEYCODE_HOME`` or numeric codes."""
        # ``input keyevent`` accepts both ``HOME`` and the full ``KEYCODE_HOME``
        # variant, plus integer codes. Strip the ``KEYCODE_`` prefix on the
        # way through so adb errors stay readable.
        if isinstance(key, str) and key.upper().startswith("KEYCODE_"):
            payload = key.upper()[len("KEYCODE_"):]
        else:
            payload = str(key)
        # The key goes into a command line the device shell parses again:
        # "HOME; echo x" ran the second command. Key names and codes are
        # letters, digits and underscores.
        if not re.fullmatch(r"\w+", payload, re.ASCII):
            raise AdbError(f"invalid key name: {key!r}")
        self.shell(f"input keyevent {payload}", serial=serial)

    def text(self, value: str, *, serial: Optional[str] = None) -> None:
        """Type ``value`` via ``input text``. Spaces are %s-escaped.

        ``input text`` carries printable ASCII only and turns every ``%s``
        into a space with no escape for it, while reporting success either
        way. Text it cannot deliver is refused here rather than sent;
        :func:`je_auto_control.android.input.type_text` picks a path that can.
        """
        if not isinstance(value, str):
            raise AdbError(f"text must be a string, got {type(value).__name__}")
        if not adb_text_safe(value):
            raise AdbUnsupportedError(
                "adb input text cannot deliver this text (non-ASCII characters or a "
                "literal %s); it would be dropped or altered while reporting success",
                alternative="type_text() / AC_android_type_text, which use the "
                            "ADBKeyBoard IME or uiautomator2")
        # ``input text`` mangles spaces; the official workaround is to
        # replace them with %s before passing through the shell layer.
        escaped = value.replace(" ", "%s")
        # shlex.quote: inside double quotes the device shell still expanded
        # $(...), backticks and $VAR, and a '"' closed the quote -- typed
        # text could run commands on the device.
        self.shell("input text " + shlex.quote(escaped), serial=serial)

    # --- screen capture -----------------------------------------------

    def screencap_png(self, *, serial: Optional[str] = None) -> bytes:
        """Capture the current screen as a PNG byte string.

        Uses ``exec-out screencap -p`` which streams PNG bytes straight
        to stdout — the older ``shell screencap`` form mangles CRLF
        on Windows hosts and produces corrupt PNGs.
        """
        result = self.run(
            ["exec-out", "screencap", "-p"], serial=serial,
        )
        return result.stdout

    def save_screenshot(self, file_path,
                        *, serial: Optional[str] = None) -> Path:
        """Persist the live screen capture to ``file_path``; returns the path."""
        target = Path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.screencap_png(serial=serial))
        return target


__all__ = [
    "AdbClient", "AdbDeviceMissingError", "AdbError", "AdbNotAvailable",
    "AdbTimeoutError", "AdbUnauthorizedError", "AdbUnsupportedError",
    "AndroidDevice", "adb_text_safe",
]
