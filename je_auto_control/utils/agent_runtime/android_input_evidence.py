"""Bind current Android dispatcher geometry and keyguard evidence without granting input authority."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from je_auto_control.utils.agent_runtime.android_geometry import Point, covers_android_path
from je_auto_control.utils.agent_runtime.android_input_windows import (
    AndroidInputWindow, android_input_name, parse_android_windows)
from je_auto_control.utils.agent_runtime.android_scope import AndroidSnapshot
from je_auto_control.utils.agent_runtime.errors import AgentTaskError

INPUT_START = "Input Dispatcher State:\n"
INPUT_END = "  RecentQueue:"
POLICY_START = "    KeyguardServiceDelegate\n"
POLICY_END = "    Looper state:\n"


def _text(value: bytes) -> str:
    if not isinstance(value, bytes) or len(value) > 1_000_000 or b"\0" in value or b"\r" in value:
        raise AgentTaskError("Android input evidence exceeds its closed byte format")
    try:
        return value.decode("utf-8")
    except UnicodeError:
        raise AgentTaskError("Android input evidence must be valid UTF-8") from None


def _section(text: str, start: str, end: str) -> str:
    starts = list(re.finditer("^" + re.escape(start), text, re.MULTILINE))
    if len(starts) != 1:
        raise AgentTaskError("Android current input/security section is missing or duplicated")
    section = text[starts[0].start():]
    ending = re.search("^" + re.escape(end), section, re.MULTILINE)
    if ending is None:
        raise AgentTaskError("Android input/security section is incomplete")
    return section[:ending.start()]


def _current(raw: bytes) -> str:
    text = _text(raw)
    current = text.split("\nInput Dispatcher State at time of last ANR:\n", 1)[0]
    if not current.endswith("\n"):
        raise AgentTaskError("Android current input state is truncated")
    return current


def _one(text: str, pattern: str) -> str:
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise AgentTaskError("Android input/security evidence is missing or ambiguous")
    return matches[0]


def _required(text: str, expected: dict[str, str], *, indent: int, separator: str) -> None:
    for key, value in expected.items():
        actual = _one(text, "^" + " " * indent + re.escape(key + separator) + r"([^\n]*)$")
        if actual != value:
            raise AgentTaskError("Android device is locked, busy or has unsupported input routing")


def _policy(raw: bytes, snapshot: AndroidSnapshot) -> str:
    block = _section(_text(raw), POLICY_START, POLICY_END)
    _required(block, {"showing": "false", "inputRestricted": "false", "occluded": "false",
        "dreaming": "false", "systemIsReady": "true", "enabled": "true", "bootCompleted": "true",
        "currentUser": str(snapshot.user), "screenState": "SCREEN_STATE_ON",
        "interactiveState": "INTERACTIVE_STATE_AWAKE"}, indent=6, separator="=")
    _one(block, r"^      (KeyguardStateMonitor)$")
    _required(block, {"mIsShowing": "false", "mInputRestricted": "false", "mCurrentUserId": str(snapshot.user)},
              indent=8, separator="=")
    for key in ("secure", "deviceHasKeyguard", "mSimSecure", "mTrusted"):
        indent = 8 if key.startswith("m") else 6
        _one(block, "^" + " " * indent + re.escape(key) + r"=(true|false)$")
    _one(block, r"^      offReason=([A-Z_]+)$")
    return block


def _routing(prefix: str, snapshot: AndroidSnapshot) -> None:
    _required(prefix, {"DispatchEnabled": "true", "DispatchFrozen": "false", "InputFilterEnabled": "false",
        "FocusedDisplayId": "0", "Pointer Capture Requested": "false",
        "Current Window with Pointer Capture": "None", "TouchStates": "<no displays touched>"},
              indent=2, separator=": ")
    name = re.escape(android_input_name(snapshot))
    app = re.escape(snapshot.activity)
    _one(prefix, r"^  (FocusedApplications):$")
    _one(prefix, r"^  (FocusedWindows):$")
    _one(prefix, r"^  FocusedApplications:\n(    displayId=0, name='" + app
         + r"', dispatchingTimeout=\d+ms)\n(?=  FocusedWindows:)")
    _one(prefix, r"^  FocusedWindows:\n(    displayId=0, name='" + name + r"')\n(?=  FocusRequests:)")
    _one(prefix, r"^  (FocusRequests):")
    requests = r"(?: <none>|\n    displayId=0, name='" + name + r"' result='OK')"
    _one(prefix, r"^  FocusRequests:(" + requests + r")\n(?=  Pointer Capture Requested:)")
    if "  DragState:" in prefix or "  TouchStatesByDisplay:" in prefix:
        raise AgentTaskError("Android touch or drag is already active")


def _queues(current: str, snapshot: AndroidSnapshot) -> str:
    block = _section(current, "  PendingEvent:", "  AppSwitch:") + _one(current, r"^(  AppSwitch: [^\n]*\n)")
    _required(block, {"PendingEvent": "<none>", "InboundQueue": "<empty>", "ReplacedKeys": "<empty>",
        "CommandQueue": "<empty>", "AppSwitch": "not pending"}, indent=2, separator=": ")
    _connections(block, snapshot)
    return block


def _connections(block: str, snapshot: AndroidSnapshot) -> None:
    connections = _section(block, "  Connections:\n", "  AppSwitch:")[len("  Connections:\n"):]
    pattern = re.compile(r"    (?P<fd>\d{1,8}): channelName='(?P<channel>[^'\n]{1,512})', "
        r"windowName='(?P<window>[^'\n]{1,512})', status=(?P<status>NORMAL|BROKEN|ZOMBIE), "
        r"monitor=(?P<monitor>true|false), responsive=(?P<responsive>true|false)\n"
        r"      OutboundQueue: <empty>\n      WaitQueue: <empty>\n")
    rows = list(pattern.finditer(connections))
    if not 1 <= len(rows) <= 256 or "".join(row[0] for row in rows) != connections:
        raise AgentTaskError("Android native connection state is queued, incomplete or unsupported")
    _target_connection(rows, snapshot)


def _target_connection(rows: list[re.Match], snapshot: AndroidSnapshot) -> None:
    if len({row["fd"] for row in rows}) != len(rows):
        raise AgentTaskError("Android native channel descriptors are duplicated")
    if any(row["channel"] != row["window"] for row in rows):
        raise AgentTaskError("Android native channel/window names disagree")
    expected = android_input_name(snapshot) + " (server)"
    targets = [row for row in rows if row["window"] == expected]
    if len(targets) != 1 or targets[0].group("status", "monitor", "responsive") != ("NORMAL", "false", "true"):
        raise AgentTaskError("Android focused native channel is missing, blocked or unresponsive")


def _monitors(lines: list[str]) -> bool:
    if lines == ["  Global Monitors: <none>"]:
        return False
    if not lines or lines[0] != "  Global monitors on display 0:" or not 1 <= len(lines[1:]) <= 128:
        raise AgentTaskError("Android input-window section has unparsed trailing evidence")
    for index, line in enumerate(lines[1:]):
        if re.fullmatch(r"    " + str(index) + r": '[^'\n]{1,512}', ", line) is None:
            raise AgentTaskError("Android global input monitor metadata is unsupported")
    return True


def _display(prefix: str) -> tuple[int, int, list[str], bool]:
    if re.findall(r"^  Display: ([^\n]*)$", prefix, re.MULTILINE) != ["0"]:
        raise AgentTaskError("Android input proof requires one identified default display")
    match = re.search(r"^  Display: 0\n    logicalSize=(\d{1,5})x(\d{1,5})\n"
                      r"        transform \(ROT_0\) \(IDENTITY\)\n    Windows:\n", prefix, re.MULTILINE)
    if match is None:
        raise AgentTaskError("Android display size/transform is unsupported")
    width, height = int(match[1]), int(match[2])
    if not 1 <= width <= 16384 or not 1 <= height <= 16384:
        raise AgentTaskError("Android logical display dimensions exceed the limit")
    tail = prefix[match.end():].splitlines()
    stop = next((index for index, line in enumerate(tail) if not line.startswith("      ")), len(tail))
    lines = tail[:stop]
    if not lines:
        raise AgentTaskError("Android input window list is empty")
    return width, height, lines, _monitors(tail[stop:])


@dataclass(frozen=True)
class AndroidInputEvidence:
    """Read-only geometry/security evidence; it does not certify human inactivity or authorize input."""

    snapshot: AndroidSnapshot
    size: tuple[int, int]
    windows: tuple[AndroidInputWindow, ...] = field(repr=False)
    input_sha256: str
    policy_sha256: str
    has_global_monitors: bool
    input_authorized: bool = field(default=False, init=False)

    def require_path(self, start: Point, end: Point) -> None:
        """Reject foreign interception/occlusion anywhere along a tap or swipe, including its interior."""
        _require_path(self.windows, self.size, start, end)


def _require_path(windows: tuple[AndroidInputWindow, ...], size: tuple[int, int], start: Point, end: Point) -> None:
    _point(start, size)
    _point(end, size)
    target_index = next(index for index, window in enumerate(windows) if window.target)
    target = windows[target_index]
    if not covers_android_path((target.frame,), start, end) or not covers_android_path(target.regions, start, end):
        raise AgentTaskError("Android pointer path leaves the reviewed native input window")
    for index, window in enumerate(windows):
        if window.target or "NOT_VISIBLE" in window.flags:
            continue
        if index < target_index or "SPY" in window.flags:
            _unobscured(window, start, end, above=index < target_index)


def _point(point: Point, size: tuple[int, int]) -> None:
    if not isinstance(point, tuple) or len(point) != 2:
        raise AgentTaskError("Android pointer point must contain two native coordinates")
    if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < bound
           for value, bound in zip(point, size)):
        raise AgentTaskError("Android pointer point is outside the logical display")


def _unobscured(window: AndroidInputWindow, start: Point, end: Point, *, above: bool) -> None:
    if above and "WATCH_OUTSIDE_TOUCH" in window.flags:
        raise AgentTaskError("Android foreign window receives outside-touch notifications")
    if above and window.alpha > 0 and window.frame.path(start, end) is not None:
        raise AgentTaskError("Android pointer path intersects a visible overlay window")
    if "NOT_TOUCHABLE" not in window.flags and any(rect.path(start, end) is not None for rect in window.regions):
        raise AgentTaskError("Android pointer path intersects a foreign input/overlay window")


def parse_android_input_evidence(raw_input: bytes, raw_policy: bytes,
                                 snapshot: AndroidSnapshot) -> AndroidInputEvidence:
    """Validate current native routing and both keyguard views before publishing a read-only proof."""
    if not isinstance(snapshot, AndroidSnapshot):
        raise AgentTaskError("Android input evidence requires validated device identity")
    current = _current(raw_input)
    prefix = _section(current, INPUT_START, INPUT_END)
    _one(current, r"^(  RecentQueue: (?:<empty>|length=\d+)\n)")
    _routing(prefix, snapshot)
    width, height, lines, monitors = _display(prefix)
    windows = parse_android_windows(lines, snapshot)
    target = next(window for window in windows if window.target)
    if target.flags or target.alpha != 1 or not target.regions:
        raise AgentTaskError("Android target input is disabled, translucent or unsupported")
    policy = _policy(raw_policy, snapshot)
    return AndroidInputEvidence(snapshot, (width, height), windows,
        hashlib.sha256((prefix + _queues(current, snapshot)).encode("utf-8")).hexdigest(),
        hashlib.sha256(policy.encode("utf-8")).hexdigest(), monitors)
