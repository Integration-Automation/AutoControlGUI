"""Compile finite Android inputs behind same-connection identity checks; never dispatch raw model shell."""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any

from je_auto_control.utils.agent_runtime.android_scope import AndroidSnapshot
from je_auto_control.utils.agent_runtime.android_input_evidence import AndroidInputEvidence
from je_auto_control.utils.agent_runtime.android_transport import _shell_service
from je_auto_control.utils.agent_runtime.errors import AgentTaskError

ANDROID_INPUT_TOOLS = frozenset({"AC_android_tap", "AC_android_swipe", "AC_android_text", "AC_android_key"})
ACTION_MARKER = b"__JE_ANDROID_ACTION_V1__\n"
INPUT_MARKER = b"__JE_ANDROID_INPUT_V1__\n"
POLICY_MARKER = b"__JE_ANDROID_POLICY_V1__\n"
SAFETY_END = b"__JE_ANDROID_SAFETY_END_V1__\n"
_KEYS = frozenset({"BACK", "ENTER", "TAB", "DEL", "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT",
                   "MOVE_HOME", "MOVE_END"})


@dataclass(frozen=True)
class AndroidActionProposal:
    """Host-only, non-JSON proposal; repr excludes command text and it never grants input authority."""

    transport_id: int
    snapshot: AndroidSnapshot
    command: str = field(repr=False)
    input_evidence: AndroidInputEvidence | None = field(default=None, repr=False)
    input_authorized: bool = field(default=False, init=False)


def _number(value: Any, name: str, maximum: int, *, minimum: int = 0) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise AgentTaskError(f"Android {name} must be an integer within the reviewed bounds")
    return str(value)


def _text(value: Any) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 1024 or "%s" in value
            or any(ord(char) < 32 or ord(char) > 126 for char in value)):
        raise AgentTaskError("Android input text requires bounded printable ASCII without a literal %s")
    return shlex.quote(value.replace(" ", "%s"))


def _key(value: Any) -> str:
    if not isinstance(value, str):
        raise AgentTaskError("Android key must be a reviewed symbolic key")
    key = value.removeprefix("KEYCODE_")
    if key not in _KEYS:
        raise AgentTaskError("Android key is outside the finite app-input set")
    return key


def android_input_command(name: str, arguments: dict[str, Any]) -> str:
    """Validate a finite argument object before device access; the returned input body grants no scope."""
    if not isinstance(arguments, dict):
        raise AgentTaskError("Android action arguments must be a closed object")
    fields = {"AC_android_tap": {"x", "y"}, "AC_android_swipe": {"x1", "y1", "x2", "y2", "duration_ms"},
              "AC_android_text": {"text"}, "AC_android_key": {"key"}}
    if not isinstance(name, str) or name not in fields or set(arguments) - fields[name]:
        raise AgentTaskError("Android action has an unreviewed tool or argument")
    if name == "AC_android_text":
        return "text " + _text(arguments.get("text"))
    if name == "AC_android_key":
        return "keyevent " + _key(arguments.get("key"))
    return _pointer_input(name, arguments)


def _pointer_input(name: str, arguments: dict[str, Any]) -> str:
    coordinates = ["x", "y"] if name == "AC_android_tap" else ["x1", "y1", "x2", "y2"]
    values = [_number(arguments.get(key), key, 16383) for key in coordinates]
    if name == "AC_android_swipe":
        values.append(_number(arguments.get("duration_ms", 250), "duration", 2000, minimum=1))
    return ("tap " if name == "AC_android_tap" else "swipe ") + " ".join(values)


def _read_matches(command: str, expected: str, code: int) -> str:
    # A trailing sentinel preserves empty duplicate lines that POSIX command substitution otherwise strips.
    return ('[ "$(' + command + " && /system/bin/printf '@')\" = "
            + shlex.quote(expected + "\n@") + f' ] || exit {code}')


def _guard(snapshot: AndroidSnapshot) -> str:
    checks = [
        _read_matches("/system/bin/getprop ro.serialno 2>/dev/null", snapshot.physical_id, 91),
        _read_matches("/system/bin/cat /proc/sys/kernel/random/boot_id 2>/dev/null", snapshot.boot_id, 92),
        'je_android_wm="$(/system/bin/dumpsys window 2>/dev/null)" || exit 93',
    ]
    for name, expected in (("mTopFocusedDisplayId", "0"), ("mCurrentFocus", snapshot.window),
                           ("mFocusedApp", snapshot.activity)):
        extract = ('/system/bin/printf \'%s\\n\' "$je_android_wm" | /system/bin/sed -n '
                   + shlex.quote("s/^ *" + name + "=//p"))
        checks.append(_read_matches(extract, expected, 93))
    return "; ".join(checks)


def _input_digest_command() -> str:
    emit = '/system/bin/printf \'%s\\n\' "$je_android_current"'
    before_recent = emit + " | /system/bin/sed -n '/^Input Dispatcher State:$/,/^  RecentQueue:/p'"
    queues = emit + " | /system/bin/sed -n '/^  PendingEvent:/,/^  AppSwitch:/p'"
    return ("{ " + before_recent + " | /system/bin/sed '$d'; " + queues
            + "; } | /system/bin/sha256sum | /system/bin/cut -d' ' -f1")


def _safety_guard(evidence: AndroidInputEvidence) -> str:
    policy = ('/system/bin/printf \'%s\\n\' "$je_android_policy" | /system/bin/sed -n '
              "'/^    KeyguardServiceDelegate$/,/^    Looper state:$/p' | /system/bin/sed '$d'"
              " | /system/bin/sha256sum | /system/bin/cut -d' ' -f1")
    return "; ".join([
        'je_android_input="$(/system/bin/dumpsys input 2>/dev/null)" || exit 95',
        'je_android_current="$(/system/bin/printf \'%s\\n\' "$je_android_input" | /system/bin/sed -n '
        "'/^Input Dispatcher State:$/,$p' | /system/bin/sed '/^Input Dispatcher State at time of last ANR:/,$d')\""
        " || exit 95",
        'je_android_policy="$(/system/bin/dumpsys window policy 2>/dev/null)" || exit 95',
        _read_matches(_input_digest_command(), evidence.input_sha256, 95),
        _read_matches(policy, evidence.policy_sha256, 95),
    ])


def compile_android_input_probe(snapshot: AndroidSnapshot) -> str:
    """Read routing/security in one pinned command connection; never create input or install anything."""
    if not isinstance(snapshot, AndroidSnapshot):
        raise AgentTaskError("Android input probe requires a validated scope snapshot")
    guard = _guard(snapshot)
    script = (guard + "; /system/bin/printf '__JE_ANDROID_INPUT_V1__\\n'; "
              "/system/bin/dumpsys input || exit 95; /system/bin/printf '__JE_ANDROID_POLICY_V1__\\n'; "
              "/system/bin/dumpsys window policy || exit 95; " + guard
              + "; /system/bin/printf '__JE_ANDROID_SAFETY_END_V1__\\n'")
    _shell_service(script)
    return script


def _check_evidence(evidence: AndroidInputEvidence, snapshot: AndroidSnapshot, name: str, arguments: dict) -> None:
    if not isinstance(evidence, AndroidInputEvidence) or evidence.snapshot != snapshot:
        raise AgentTaskError("Android input evidence belongs to a different device/boot/window snapshot")
    if name == "AC_android_tap":
        point = (arguments["x"], arguments["y"])
        evidence.require_path(point, point)
    if name == "AC_android_swipe":
        evidence.require_path((arguments["x1"], arguments["y1"]), (arguments["x2"], arguments["y2"]))


def compile_android_action(snapshot: AndroidSnapshot, name: str, arguments: dict[str, Any], *,
                           input_evidence: AndroidInputEvidence | None = None) -> str:
    """Build a host-only proposal; input-window/occlusion/lock authorization is still required.

    The guard runs in the SAME selected ADB command connection as the finite input, preventing
    an ID reused by a different physical device/boot/app from receiving it. A focus snapshot is
    not an input-window hit test or a human-activity gate. This compiler grants no execution authority.
    """
    if not isinstance(snapshot, AndroidSnapshot):
        raise AgentTaskError("Android action requires a validated scope snapshot")
    command = android_input_command(name, arguments)
    guard = _guard(snapshot)
    safety = ""
    if input_evidence is not None:
        _check_evidence(input_evidence, snapshot, name, arguments)
        safety = _safety_guard(input_evidence) + "; "
    script = (guard + "; " + safety + "/system/bin/input -d 0 " + command + " >/dev/null 2>&1 || exit 94; "
              + guard + "; /system/bin/printf '__JE_ANDROID_ACTION_V1__\\n'")
    _shell_service(script)
    return script
