"""Validate bounded Android device, boot and focused-app evidence without publishing raw dumps."""
from __future__ import annotations

import re
from dataclasses import dataclass

from je_auto_control.utils.agent_runtime.errors import AgentTaskError

_DEVICE = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_PACKAGE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+")
_BOOT = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_WINDOW = re.compile(r"Window\{([0-9a-f]+) u([0-9]+) ([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)\}")
_ACTIVITY = re.compile(r"ActivityRecord\{[0-9a-f]+ u([0-9]+) ([A-Za-z0-9_.]+)/[A-Za-z0-9_.$]+ t[0-9]+\}")
IDENTITY_MARKER = "__JE_ANDROID_IDENTITY_V1__"
IDENTITY_PROBE = (
    f"/system/bin/printf '{IDENTITY_MARKER}\\n'; "
    "/system/bin/getprop ro.serialno || exit 91; "
    "/system/bin/cat /proc/sys/kernel/random/boot_id || exit 92; "
    "/system/bin/dumpsys window || exit 93")


def validate_android_binding(physical_id: str, package: str, user: int = 0) -> None:
    """Reject ambiguous identity/package fields before any server or model interaction."""
    if not isinstance(physical_id, str) or _DEVICE.fullmatch(physical_id) is None:
        raise AgentTaskError("Android physical identity must be a bounded plain serial")
    if not isinstance(package, str) or len(package) > 255 or _PACKAGE.fullmatch(package) is None:
        raise AgentTaskError("Android scope requires an exact application package")
    if isinstance(user, bool) or not isinstance(user, int) or not 0 <= user <= 999999:
        raise AgentTaskError("Android scope requires an explicit nonnegative device user")


def _field(dump: str, name: str) -> str:
    matches = re.findall(r"^ *" + re.escape(name) + r"=([^\r\n]*)$", dump, flags=re.MULTILINE)
    if len(matches) != 1 or not matches[0] or len(matches[0]) > 512:
        raise AgentTaskError("Android focused-app evidence is missing, ambiguous or unsupported")
    return matches[0]


@dataclass(frozen=True)
class AndroidSnapshot:
    """Only validated plain identity data; no raw window dump or application text is retained."""

    physical_id: str
    boot_id: str
    package: str
    user: int
    window: str
    activity: str

    def __post_init__(self) -> None:
        validate_android_binding(self.physical_id, self.package, self.user)
        if not isinstance(self.boot_id, str) or _BOOT.fullmatch(self.boot_id) is None:
            raise AgentTaskError("Android boot identity must be an exact kernel boot UUID")
        window = _record(self.window, _WINDOW)
        activity = _record(self.activity, _ACTIVITY)
        if window is None or activity is None:
            raise AgentTaskError("Android window/activity evidence has an unsupported format")
        if (int(window[2]) != self.user or window[3] != self.package
                or int(activity[1]) != self.user or activity[2] != self.package):
            raise AgentTaskError("Android window/activity is outside its device-user/app scope")

    def identity(self) -> dict:
        """Return detached scope metadata, excluding raw remote diagnostics or control text."""
        return {"platform": "android", "physical_id": self.physical_id, "boot_id": self.boot_id,
                "package": self.package, "user": self.user, "display": 0,
                "window": self.window, "activity": self.activity}


def _record(value: str, pattern: re.Pattern) -> re.Match | None:
    return pattern.fullmatch(value) if isinstance(value, str) and len(value) <= 512 else None


def parse_android_snapshot(output: bytes, physical_id: str, package: str, *, user: int = 0) -> AndroidSnapshot:
    """Accept a single default-display focus in the pinned AOSP format, otherwise fail closed."""
    validate_android_binding(physical_id, package, user)
    if not isinstance(output, bytes) or len(output) > 262144 or b"\0" in output:
        raise AgentTaskError("Android identity evidence exceeds its closed byte format")
    try:
        marker, device, boot, dump = output.decode("utf-8").split("\n", 3)
    except (UnicodeError, ValueError):
        raise AgentTaskError("Android identity evidence is incomplete or invalid UTF-8") from None
    if marker != IDENTITY_MARKER or device != physical_id:
        raise AgentTaskError("Android endpoint does not identify the reviewed physical device")
    if _field(dump, "mTopFocusedDisplayId") != "0":
        raise AgentTaskError("Android scope requires the default focused display")
    return AndroidSnapshot(device, boot, package, user, _field(dump, "mCurrentFocus"),
                           _field(dump, "mFocusedApp"))
