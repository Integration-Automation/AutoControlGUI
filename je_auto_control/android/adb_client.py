"""AdbClient — thin wrapper around the ``adb`` CLI for Android automation."""
from __future__ import annotations

import shutil
import subprocess  # nosec B404  # reason: required to invoke the adb binary
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

_DEFAULT_TIMEOUT_S = 30.0


class AdbError(RuntimeError):
    """Raised when adb returns a non-zero exit code."""


class AdbNotAvailable(RuntimeError):
    """Raised when the adb binary isn't on PATH and no path was supplied."""


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
        except (OSError, subprocess.SubprocessError) as error:
            raise AdbError(f"adb {' '.join(args)} failed: {error}") from error
        if check and result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise AdbError(
                f"adb {' '.join(args)} exited {result.returncode}: {stderr}",
            )
        return result

    def shell(self, command: str, *, serial: Optional[str] = None,
              timeout: Optional[float] = None) -> str:
        """Run ``adb shell <command>`` and return the decoded stdout."""
        result = self.run(
            ["shell", command], serial=serial, timeout=timeout,
        )
        return result.stdout.decode("utf-8", errors="replace")

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
            serial, state = parts[0], parts[1]
            metadata = {
                key: value
                for token in parts[2:]
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

    def key_event(self, key: str, *, serial: Optional[str] = None) -> None:
        """Send a keycode — accepts ``KEYCODE_HOME`` or numeric codes."""
        # ``input keyevent`` accepts both ``HOME`` and the full ``KEYCODE_HOME``
        # variant, plus integer codes. Strip the ``KEYCODE_`` prefix on the
        # way through so adb errors stay readable.
        if isinstance(key, str) and key.upper().startswith("KEYCODE_"):
            payload = key.upper()[len("KEYCODE_"):]
        else:
            payload = str(key)
        self.shell(f"input keyevent {payload}", serial=serial)

    def text(self, value: str, *, serial: Optional[str] = None) -> None:
        """Type ``value`` via ``input text``. Spaces are %s-escaped."""
        if not isinstance(value, str):
            raise AdbError(f"text must be a string, got {type(value).__name__}")
        # ``input text`` mangles spaces; the official workaround is to
        # replace them with %s before passing through the shell layer.
        escaped = value.replace(" ", "%s")
        self.shell(f'input text "{escaped}"', serial=serial)

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


__all__ = ["AdbClient", "AdbError", "AdbNotAvailable", "AndroidDevice"]
