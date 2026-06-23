"""Canonical computer-use action schema — normalize Anthropic / OpenAI payloads to AC_*.

``tool_use_schema`` exports the AC_* command *signatures* as tool definitions and
``coordinate_space`` rescales a model grid — but neither *normalizes an inbound action
payload*. Anthropic emits ``{action:"left_click", coordinate:[x,y]}``, OpenAI's CUA
emits ``{type:"click", x, y, button}`` — there is no adapter mapping these heterogeneous
shapes onto a canonical action and then onto a runnable AC_* command. Integrators
hand-write this glue today.

All pure-stdlib dict mapping (an optional ``scale`` callable applies coordinate-space
rescaling), so it is fully headless-testable. Imports no ``PySide6``.
"""
from typing import Any, Callable, Dict, List, Mapping, Optional

from je_auto_control.utils.exception.exceptions import AutoControlActionException

# Anthropic computer-use "action" -> canonical type.
_ANTHROPIC = {"left_click": "click", "right_click": "right_click",
              "middle_click": "middle_click", "double_click": "double_click",
              "mouse_move": "move", "left_click_drag": "drag", "type": "type",
              "key": "key", "scroll": "scroll", "screenshot": "screenshot",
              "cursor_position": "cursor_position"}

# canonical click type -> AC mouse button keycode.
_CLICK_BUTTONS = {"click": "mouse_left", "double_click": "mouse_left",
                  "right_click": "mouse_right", "middle_click": "mouse_middle"}


def canonical_action(action_type: str, **fields: Any) -> Dict[str, Any]:
    """Build a canonical action dict ``{type, …}`` dropping ``None`` fields."""
    result: Dict[str, Any] = {"type": action_type}
    result.update({key: value for key, value in fields.items() if value is not None})
    return result


def _xy(coordinate) -> Dict[str, int]:
    if not coordinate:
        return {}
    return {"x": int(coordinate[0]), "y": int(coordinate[1])}


def from_anthropic(tool_input: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize an Anthropic computer-use tool input to a canonical action."""
    action = tool_input.get("action", "")
    fields: Dict[str, Any] = _xy(tool_input.get("coordinate"))
    if tool_input.get("text") is not None:
        fields["text"] = tool_input["text"]
    if action == "scroll":
        fields["direction"] = tool_input.get("scroll_direction")
        fields["amount"] = tool_input.get("scroll_amount")
    return canonical_action(_ANTHROPIC.get(action, action), **fields)


def _openai_click_type(item: Mapping[str, Any]) -> str:
    button = item.get("button", "left")
    return {"right": "right_click", "wheel": "middle_click",
            "middle": "middle_click"}.get(button, "click")


def from_openai_cua(item: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize an OpenAI CUA ``computer_call`` item to a canonical action."""
    kind = item.get("type", "")
    fields: Dict[str, Any] = {}
    if item.get("x") is not None and item.get("y") is not None:
        fields["x"], fields["y"] = int(item["x"]), int(item["y"])
    if kind == "click":
        kind = _openai_click_type(item)
    elif kind == "keypress":
        kind, fields["text"] = "key", "+".join(item.get("keys", []))
    elif kind == "type":
        fields["text"] = item.get("text")
    elif kind == "scroll":
        fields["scroll_x"] = item.get("scroll_x")
        fields["scroll_y"] = item.get("scroll_y")
    return canonical_action(kind, **fields)


def _scroll_value(action: Mapping[str, Any]) -> int:
    if action.get("amount") is not None:
        sign = 1 if action.get("direction") in ("up", "left") else -1
        return sign * int(action["amount"])
    if action.get("scroll_y") is not None:
        return -int(action["scroll_y"])              # OpenAI: +y is downward
    return 0


def _point(action: Mapping[str, Any],
           scale: Optional[Callable[[int, int], Any]]) -> Dict[str, int]:
    if action.get("x") is None or action.get("y") is None:
        return {}
    x, y = int(action["x"]), int(action["y"])
    if scale is not None:
        x, y = (int(coord) for coord in scale(x, y))
    return {"x": x, "y": y}


def to_ac_command(action: Mapping[str, Any], *,
                  scale: Optional[Callable[[int, int], Any]] = None) -> List[Any]:
    """Map a canonical action to a runnable ``[command_name, params]`` AC action.

    ``scale`` optionally remaps ``(x, y)`` (e.g. ``coordinate_space`` model→physical).
    Raises ``AutoControlActionException`` for an action with no AC mapping.
    """
    kind = action.get("type")
    point = _point(action, scale)
    if kind in _CLICK_BUTTONS:
        return ["AC_click_mouse", {"mouse_keycode": _CLICK_BUTTONS[kind], **point}]
    keys = [part.strip() for part in str(action.get("text", "")).split("+")
            if part.strip()]
    builders = {
        "move": lambda: ["AC_set_mouse_position", point],
        "type": lambda: ["AC_write", {"write_string": str(action.get("text", ""))}],
        "key": lambda: ["AC_hotkey", {"key_code_list": keys}],
        "scroll": lambda: ["AC_mouse_scroll",
                           {"scroll_value": _scroll_value(action), **point}],
        "screenshot": lambda: ["AC_screenshot", {}],
    }
    if kind in builders:
        return builders[kind]()
    raise AutoControlActionException(f"no AC mapping for action type: {kind!r}")
