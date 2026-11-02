"""Decode pinned AOSP input-window records without retaining foreign names or raw window dumps."""
from __future__ import annotations

import re
from dataclasses import dataclass

from je_auto_control.utils.agent_runtime.android_geometry import AndroidRect
from je_auto_control.utils.agent_runtime.android_scope import AndroidSnapshot
from je_auto_control.utils.agent_runtime.errors import AgentTaskError

_RECT = r"\[(-?\d{1,10}),(-?\d{1,10})\]\[(-?\d{1,10}),(-?\d{1,10})\]"
_FLAGS = frozenset({"DEFAULT", "NO_INPUT_CHANNEL", "NOT_VISIBLE", "NOT_FOCUSABLE", "NOT_TOUCHABLE",
    "PREVENT_SPLITTING", "DUPLICATE_TOUCH_TO_WALLPAPER", "IS_WALLPAPER", "PAUSE_DISPATCHING",
    "TRUSTED_OVERLAY", "WATCH_OUTSIDE_TOUCH", "SLIPPERY", "DISABLE_USER_ACTIVITY", "DROP_INPUT",
    "DROP_INPUT_IF_OBSCURED", "SPY", "INTERCEPTS_STYLUS", "CLONE"})
_WINDOW = re.compile(
    r"      (?P<index>\d{1,3}): name='(?P<name>[^'\r\n]{1,512})', id=(?P<id>\d{1,10}), displayId=0, "
    r"inputConfig=(?P<flags>[A-Z_0-9x |]{1,512}), alpha=(?P<alpha>\d\.\d{2}), "
    r"frame=(?P<frame>\[-?\d{1,10},-?\d{1,10}\]\[-?\d{1,10},-?\d{1,10}\]), globalScale=1\.000000, "
    r"applicationInfo.name=(?P<app>[^,\r\n]{0,512}), applicationInfo.token=(?P<app_token>[^,\r\n]{1,64}), "
    rf"touchableRegion=(?P<regions>(?:<empty>|{_RECT}(?:\|{_RECT}){{0,63}})), ownerPid=(?P<pid>-?\d{{1,10}}), "
    r"ownerUid=(?P<uid>-?\d{1,10}), dispatchingTimeout=\d{1,6}ms, hasToken=(?P<token>[^,\r\n]{1,64}), "
    r"touchOcclusionMode=(?:BLOCK_UNTRUSTED|USE_OPACITY|ALLOW)")
_TRANSFORM = re.compile(r"        transform \((?:ROT_0|ROT_90|ROT_180|ROT_270|FLIP_H|FLIP_V)\) "
                        r"\((?:IDENTITY|(?:SCALE |ROTATE |TRANSLATE){1,3})\)")
_MATRIX = re.compile(r"            -?\d{1,10}\.\d{4}  -?\d{1,10}\.\d{4}  -?\d{1,10}\.\d{4}")


def android_input_name(snapshot: AndroidSnapshot) -> str:
    """Map the validated WM record to WindowState.getName, without accepting a caller-supplied alias."""
    identity, _user, component = snapshot.window[7:-1].split(" ")
    return identity + " " + component


def _flags(value: str) -> frozenset[str]:
    if value == "0x0":
        return frozenset()
    parts = value.split(" | ")
    if not set(parts) <= _FLAGS or len(parts) != len(set(parts)):
        raise AgentTaskError("Android input configuration contains unknown or duplicate flags")
    return frozenset(parts)


def _rect(value: str) -> AndroidRect:
    match = re.fullmatch(_RECT, value)
    if match is None:
        raise AgentTaskError("Android input rectangle has an unsupported format")
    return AndroidRect(*(int(part) for part in match.groups()))


def _regions(value: str) -> tuple[AndroidRect, ...]:
    if value == "<empty>":
        return ()
    parts = value.split("|")
    if len(parts) > 64:
        raise AgentTaskError("Android touch region exceeds the rectangle limit")
    result = tuple(_rect(part) for part in parts)
    if any(rect.left == rect.right or rect.top == rect.bottom for rect in result):
        raise AgentTaskError("Android touch region contains an empty rectangle")
    return result


@dataclass(frozen=True)
class AndroidInputWindow:
    """Private scope geometry, owner and flags; foreign display names are deliberately absent."""

    window_id: int
    owner: tuple[int, int]
    frame: AndroidRect
    regions: tuple[AndroidRect, ...]
    flags: frozenset[str]
    target: bool
    alpha: float


def _window(line: str, index: int, snapshot: AndroidSnapshot) -> AndroidInputWindow:
    match = _WINDOW.fullmatch(line)
    if match is None or int(match["index"]) != index or len(line) > 4096:
        raise AgentTaskError("Android input-window record is incomplete, out of order or unsupported")
    owner = int(match["pid"]), int(match["uid"])
    if any(not -1 <= number <= 2**31 - 1 for number in (*owner, int(match["id"]))):
        raise AgentTaskError("Android input-window owner or identifier is invalid")
    alpha = float(match["alpha"])
    if not 0 <= alpha <= 1:
        raise AgentTaskError("Android input-window opacity is invalid")
    target = match["name"] == android_input_name(snapshot)
    if target:
        _target(match, owner, snapshot)
    return AndroidInputWindow(int(match["id"]), owner, _rect(match["frame"]), _regions(match["regions"]),
                              _flags(match["flags"]), target, alpha)


def _target(match: re.Match, owner: tuple[int, int], snapshot: AndroidSnapshot) -> None:
    if match["app"] != snapshot.activity or owner[0] <= 0 or owner[1] // 100000 != snapshot.user:
        raise AgentTaskError("Android input-window application/owner does not match the reviewed focus")
    if any(re.fullmatch(r"0x[1-9a-f][0-9a-f]*", match[key]) is None for key in ("app_token", "token")):
        raise AgentTaskError("Android input target has no identified native channel")


def parse_android_windows(lines: list[str], snapshot: AndroidSnapshot) -> tuple[AndroidInputWindow, ...]:
    """Decode front-to-back windows and their transforms, refusing unparsed or duplicate records."""
    windows: list[AndroidInputWindow] = []
    index = 0
    while index < len(lines):
        if len(windows) >= 128:
            raise AgentTaskError("Android input-window count exceeds the limit")
        windows.append(_window(lines[index], len(windows), snapshot))
        index = _transform(lines, index + 1)
    if len({window.window_id for window in windows}) != len(windows):
        raise AgentTaskError("Android input-window identifiers are duplicated")
    if sum(window.target for window in windows) != 1:
        raise AgentTaskError("Android native input target is missing or ambiguous")
    return tuple(windows)


def _transform(lines: list[str], index: int) -> int:
    if index >= len(lines) or _TRANSFORM.fullmatch(lines[index]) is None:
        raise AgentTaskError("Android window transform has an unsupported format")
    if lines[index].endswith("(IDENTITY)"):
        return index + 1
    kinds = lines[index].rsplit("(", 1)[1][:-1].split()
    if kinds != [kind for kind in ("SCALE", "ROTATE", "TRANSLATE") if kind in kinds]:
        raise AgentTaskError("Android window transform flags are duplicated or out of order")
    matrix = lines[index + 1:index + 4]
    if len(matrix) != 3 or any(_MATRIX.fullmatch(line) is None for line in matrix):
        raise AgentTaskError("Android window transform matrix is incomplete")
    return index + 4
