"""Compile finite Android inputs behind same-connection identity checks; never dispatch raw model shell."""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any

from je_auto_control.utils.agent_runtime.android_scope import AndroidSnapshot
from je_auto_control.utils.agent_runtime.android_transport import _shell_service
from je_auto_control.utils.agent_runtime.errors import AgentTaskError

ANDROID_INPUT_TOOLS = frozenset({"AC_android_tap", "AC_android_swipe", "AC_android_text", "AC_android_key"})
ACTION_MARKER = b"__JE_ANDROID_ACTION_V1__\n"
_KEYS = frozenset({"BACK", "ENTER", "TAB", "DEL", "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT",
                   "MOVE_HOME", "MOVE_END"})


@dataclass(frozen=True)
class AndroidActionProposal:
    """Host-only, non-JSON proposal; repr excludes command text and it never grants input authority."""

    transport_id: int
    snapshot: AndroidSnapshot
    command: str = field(repr=False)
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


def compile_android_action(snapshot: AndroidSnapshot, name: str, arguments: dict[str, Any]) -> str:
    """Build a host-only proposal; input-window/occlusion/lock authorization is still required.

    The guard runs in the SAME selected ADB command connection as the finite input, preventing
    an ID reused by a different physical device/boot/app from receiving it. A focus snapshot is
    not an input-window hit test or a human-activity gate. This compiler grants no execution authority.
    """
    if not isinstance(snapshot, AndroidSnapshot):
        raise AgentTaskError("Android action requires a validated scope snapshot")
    command = android_input_command(name, arguments)
    guard = _guard(snapshot)
    script = (guard + "; /system/bin/input -d 0 " + command + " >/dev/null 2>&1 || exit 94; "
              + guard + "; /system/bin/printf '__JE_ANDROID_ACTION_V1__\\n'")
    _shell_service(script)
    return script
