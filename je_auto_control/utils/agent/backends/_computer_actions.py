"""Anthropic computer-use actions as ``AgentLoop`` decisions.

One action of the ``computer`` tool -- or one member call of the computer
toolset, which uses the same verbs -- becomes the equivalent ``AC_*``
invocation here. Both request shapes of :mod:`.anthropic_computer_use` share
this translation; nothing in it talks to the API.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Tuple

from je_auto_control.utils.agent.backends.base import AgentBackendError
from je_auto_control.utils.exception.exceptions import AutoControlException


#: Upper bounds on what one model action may ask for. The spec caps ``wait``
#: at 100 s; a hold longer than that, or a scroll of more notches, is not a
#: step an agent needs, and an unbounded scroll overflowed the platform call.
_MAX_WAIT_S = 100.0
_MAX_SCROLL_NOTCHES = 100
_MAX_KEY_REPEAT = 100


# Map xdotool-style key names (used by Anthropic's tool spec) to the
# names AutoControl's keyboard wrappers expect. Anything outside this
# table is forwarded as-is; the wrapper rejects unknown keys cleanly.
_XDOTOOL_KEY_ALIAS = {
    "return": "enter",
    "escape": "esc",
    "page_up": "pageup",
    "page_down": "pagedown",
    "back_space": "backspace",
    "bksp": "backspace",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "shift_l": "shift",
    "shift_r": "shift",
    "alt_l": "alt",
    "alt_r": "alt",
    "super_l": "win",
    "super_r": "win",
    "meta_l": "win",
    "meta_r": "win",
}


def _normalise_key(name: str) -> str:
    """This platform's name for an xdotool key.

    The fixed aliases ("return" -> "enter", "escape" -> "esc", "page_down" ->
    "pagedown") are not names the Windows key table knows, so Enter, Esc,
    paging, Alt and Super failed there; cua_action's resolver knows each
    platform's spelling.
    """
    from je_auto_control.utils.cua_action.cua_action import resolve_key_name
    return resolve_key_name(_XDOTOOL_KEY_ALIAS.get(name.lower(), name.lower()))


def _parse_combo(combo: str) -> List[str]:
    """Split an xdotool-style hotkey (``ctrl+shift+T``) into key names.

    ``ctrl++`` is Ctrl and the plus key: splitting on "+" dropped the plus.
    """
    from je_auto_control.utils.cua_action.cua_action import split_key_combo
    return [_normalise_key(part) for part in split_key_combo(combo)]


def _click_button(action: str) -> str:
    return {
        "left_click": "mouse_left",
        "right_click": "mouse_right",
        "middle_click": "mouse_middle",
        "double_click": "mouse_left",
        "triple_click": "mouse_left",
    }.get(action, "mouse_left")


def _click_repeats(action: str) -> int:
    return {"double_click": 2, "triple_click": 3}.get(action, 1)


def _action_screenshot(_payload):
    return {"tool": "AC_screenshot", "input": {}}


def _action_cursor_position(_payload):
    return {"tool": "AC_get_mouse_position", "input": {}}


def _action_mouse_move(payload):
    x, y = _xy(payload.get("coordinate"))
    return {"tool": "AC_set_mouse_position", "input": {"x": x, "y": y}}


def _action_type(payload):
    return {
        "tool": "AC_write",
        "input": {"write_string": str(payload.get("text") or "")},
    }


def _action_wait(payload):
    duration = payload.get("duration")
    # An explicit 0 is a valid "don't wait" — only fall back when unset.
    seconds = _number(duration, "duration") if duration is not None else 1.0
    return _sequence([["AC_sleep", {"seconds": _bounded_seconds(seconds)}]])


def _bounded_seconds(seconds: float) -> float:
    """A model-chosen duration within ``[0, _MAX_WAIT_S]``.

    The run's wall-clock budget is checked between steps, so one unbounded
    ``wait`` or ``hold_key`` blocked far past it.
    """
    return min(max(float(seconds), 0.0), _MAX_WAIT_S)


_CLICK_ACTIONS = frozenset({
    "left_click", "right_click", "middle_click",
    "double_click", "triple_click",
})


def _decision_from_computer_action(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Turn one ``computer`` tool payload into an ``AgentLoop`` decision."""
    action = str(payload.get("action") or "").lower()
    if action in _CLICK_ACTIONS:
        decision = _click_decision(action, payload.get("coordinate"))
    else:
        handler = _ACTION_HANDLERS.get(action)
        if handler is None:
            raise AgentBackendError(
                f"computer-use action {action!r} is not recognised",
            )
        decision = handler(payload)
    if action in _MODIFIER_ACTIONS and payload.get("text"):
        return _with_modifiers(decision, str(payload["text"]))
    return decision


#: Actions whose ``text`` names modifier keys to hold (``shift`` for a
#: shift-click). The field was ignored, so a ctrl-click was a plain click.
_MODIFIER_ACTIONS = _CLICK_ACTIONS | {"left_click_drag", "scroll"}


def _with_modifiers(decision: Dict[str, Any], combo: str) -> Dict[str, Any]:
    """Run ``decision`` with the keys of ``combo`` held; they are released even on failure."""
    keys = _parse_combo(combo)
    if not keys:
        return decision
    inner = decision["input"]
    actions = (inner["action_list"] if decision["tool"] == "AC_execute_action"
               else [[decision["tool"], inner]])
    return {"tool": "AC_with_modifiers",
            "input": {"modifiers": keys, "actions": actions}}


def _click_decision(action: str, coordinate) -> Dict[str, Any]:
    button = _click_button(action)
    repeats = _click_repeats(action)
    inputs: Dict[str, Any] = {"mouse_keycode": button}
    if coordinate is not None:
        x, y = _xy(coordinate)
        inputs["x"], inputs["y"] = x, y
    if repeats == 1:
        return {"tool": "AC_click_mouse", "input": inputs}
    # AC_click_mouse takes no repeat count (a 'repeat' argument made every
    # click a TypeError): move once, then click the given number of times.
    clicks = [["AC_click_mouse", inputs]]
    clicks += [["AC_click_mouse", {"mouse_keycode": button}]] * (repeats - 1)
    return _sequence(clicks)


def _sequence(actions: List[List[Any]]) -> Dict[str, Any]:
    """Run several executor actions as one step, failing the step on any error."""
    return {"tool": "AC_execute_action",
            "input": {"action_list": actions, "raise_on_error": True}}


def _drag_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    # The spec's end point is ``coordinate`` (``start_coordinate`` is the
    # start); reading only ``end_coordinate`` failed every drag the model made.
    start = payload.get("start_coordinate")
    end = payload.get("end_coordinate") or payload.get("coordinate")
    if start is None or end is None:
        raise AgentBackendError(
            "left_click_drag requires start_coordinate and coordinate",
        )
    sx, sy = _xy(start)
    ex, ey = _xy(end)
    # No AC_drag command exists: press at the start, move, release at the end.
    return _sequence([
        ["AC_press_mouse", {"mouse_keycode": "mouse_left", "x": sx, "y": sy}],
        ["AC_set_mouse_position", {"x": ex, "y": ey}],
        ["AC_release_mouse", {"mouse_keycode": "mouse_left", "x": ex, "y": ey}],
    ])


def _scroll_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    direction = str(payload.get("scroll_direction") or "down").lower()
    raw_amount = payload.get("scroll_amount")
    # An explicit 0 means "no scroll" — only default when the key is absent.
    amount = int(_number(raw_amount, "scroll_amount")) if raw_amount is not None else 3
    amount = min(max(amount, 0), _MAX_SCROLL_NOTCHES)
    # The direction goes to AC_mouse_scroll as cua_action sends it: left out,
    # X11 and Wayland scrolled their default way ("up" went down there), and
    # left / right became a vertical scroll everywhere.
    from je_auto_control.utils.cua_action.cua_action import scroll_params
    try:
        inputs: Dict[str, Any] = scroll_params({"direction": direction, "amount": amount})
    except AutoControlException as error:
        raise AgentBackendError(str(error)) from error
    # The scroll happens where the model pointed, not wherever the cursor was;
    # _clamp_decision keeps the point on the display.
    if payload.get("coordinate") is not None:
        inputs["x"], inputs["y"] = _xy(payload["coordinate"])
    return {"tool": "AC_mouse_scroll", "input": inputs}


def _key_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    combo = str(payload.get("text") or payload.get("key") or "")
    keys = _parse_combo(combo)
    if not keys:
        raise AgentBackendError("key action missing 'text'")
    press = ({"tool": "AC_type_keyboard", "input": {"keycode": keys[0]}} if len(keys) == 1
             else {"tool": "AC_hotkey", "input": {"key_code_list": keys}})
    raw_repeat = payload.get("repeat")
    repeat = int(_number(raw_repeat, "repeat")) if raw_repeat is not None else 1
    repeat = min(max(repeat, 1), _MAX_KEY_REPEAT)
    if repeat == 1:
        return press
    # ``repeat`` (1..100) was ignored, so "press Down 5 times" pressed once.
    return _sequence([[press["tool"], press["input"]]] * repeat)


def _hold_key_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    key = _normalise_key(str(payload.get("text") or payload.get("key") or ""))
    if not key:
        raise AgentBackendError("hold_key action missing 'text'")
    duration = _bounded_seconds(_number(payload.get("duration") or 0.0, "duration"))
    return {
        "tool": "AC_hold_key",
        "input": {"key": key, "duration_s": duration},
    }


def _mouse_button_decision(tool: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map a bare press/release verb to an ``AC_press/release_mouse`` call."""
    inputs: Dict[str, Any] = {"mouse_keycode": "mouse_left"}
    coordinate = payload.get("coordinate")
    if coordinate is not None:
        inputs["x"], inputs["y"] = _xy(coordinate)
    return {"tool": tool, "input": inputs}


def _mouse_down_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _mouse_button_decision("AC_press_mouse", payload)


def _mouse_up_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _mouse_button_decision("AC_release_mouse", payload)


# Dispatch table — populated after every handler is defined so the
# table reads its targets at module load time.
_ACTION_HANDLERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "screenshot": _action_screenshot,
    "cursor_position": _action_cursor_position,
    "mouse_move": _action_mouse_move,
    "type": _action_type,
    "wait": _action_wait,
    "left_click_drag": _drag_decision,
    "scroll": _scroll_decision,
    "key": _key_decision,
    "hold_key": _hold_key_decision,
    # computer_20250124 press/release verbs — without these an otherwise
    # valid action raised AgentBackendError outside the create() try and
    # aborted the run.
    "left_mouse_down": _mouse_down_decision,
    "left_mouse_up": _mouse_up_decision,
}


def _xy(coordinate: Any) -> Tuple[int, int]:
    if (not isinstance(coordinate, (list, tuple))
            or len(coordinate) != 2):
        raise AgentBackendError(
            f"coordinate must be [x, y]; got {coordinate!r}",
        )
    return int(_number(coordinate[0], "x")), int(_number(coordinate[1], "y"))


def _number(value: Any, what: str) -> float:
    """``value`` as a finite float, or :class:`AgentBackendError`."""
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise AgentBackendError(f"{what} must be a number, got {value!r}") from error
    if not math.isfinite(number):
        raise AgentBackendError(f"{what} must be finite, got {value!r}")
    return number


def _clamp_decision(decision: Dict[str, Any], width: int, height: int) -> Dict[str, Any]:
    """Keep every ``x`` / ``y`` in the decision on the declared display.

    The model's coordinates went to the mouse unchecked: [-500, 99999] on a
    100x100 display was dispatched as given.
    """
    inputs = decision.get("input") or {}
    _clamp_inputs(inputs, width, height)
    for key in ("action_list", "actions"):
        for action in inputs.get(key) or []:
            if isinstance(action, (list, tuple)) and len(action) == 2 and isinstance(action[1], dict):
                _clamp_inputs(action[1], width, height)
    return decision


def _clamp_inputs(inputs: Dict[str, Any], width: int, height: int) -> None:
    if "x" in inputs:
        inputs["x"] = min(max(int(inputs["x"]), 0), width - 1)
    if "y" in inputs:
        inputs["y"] = min(max(int(inputs["y"]), 0), height - 1)
