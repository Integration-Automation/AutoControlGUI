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


# Every spelling of a key -> the names the platform key tables use, in order.
# The tables differ: Windows knows "return" / "escape" / "next" / "back" /
# "menu" / "lwin", X11 and macOS "enter" / "esc" / "pagedown" / "backspace" /
# "alt" / "win" or "command". A fixed alias ("return" -> "enter") is wrong on
# one of them, and names from a model ("ENTER", "Page_Down") on all of them.
_KEY_SPELLINGS = {
    ("enter", "return", "kp_enter"): ("enter", "return"),
    ("esc", "escape"): ("esc", "escape"),
    ("pageup", "page_up", "prior", "pgup"): ("pageup", "prior"),
    ("pagedown", "page_down", "next", "pgdn"): ("pagedown", "next"),
    ("backspace", "back_space", "bksp", "back"): ("backspace", "back"),
    ("alt", "alt_l", "alt_r", "option", "menu"): ("alt", "menu"),
    ("win", "super", "super_l", "super_r", "meta", "meta_l", "meta_r", "cmd",
     "command", "lwin"): ("win", "lwin", "command"),
    ("ctrl", "control", "ctrl_l", "ctrl_r", "control_l", "control_r"): ("ctrl", "control"),
    ("shift", "shift_l", "shift_r"): ("shift",),
    ("delete", "del"): ("delete", "del"),
    ("space", " "): ("space",),
}
_KEY_CANDIDATES = {spelling: names for spellings, names in _KEY_SPELLINGS.items()
                   for spelling in spellings}


def _platform_key_table() -> Mapping[str, Any]:
    try:
        from je_auto_control.wrapper.platform_wrapper import keyboard_keys_table
    except Exception:  # noqa: BLE001  # reason: no usable input backend here; names pass through
        return {}
    return keyboard_keys_table or {}


def resolve_key_name(name: str, table: Optional[Mapping[str, Any]] = None) -> str:
    """The key name this platform's keyboard table uses for ``name``.

    Case-insensitive, and aware of each platform's spelling of the special
    keys; a name with no known alternative is returned lower-cased.
    """
    key = str(name).strip().lower() or str(name)
    names = _platform_key_table() if table is None else table
    for candidate in _KEY_CANDIDATES.get(key, (key,)):
        if candidate in names:
            return candidate
    return key


def split_key_combo(combo: str) -> List[str]:
    """``ctrl+shift+T`` -> its key names; a trailing ``+`` is the plus key."""
    text = str(combo)
    trailing_plus = text.endswith("++") or text == "+"
    parts = [part.strip() for part in text.split("+") if part.strip()]
    return parts + ["+"] if trailing_plus else parts


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
    if action in ("key", "hold_key") and tool_input.get("text") is None:
        fields["text"] = tool_input.get("key")
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
    elif kind == "double_click":
        kind = "double_click"
    elif kind == "keypress":
        kind, fields["text"] = "key", "+".join(item.get("keys", []))
    elif kind == "type":
        fields["text"] = item.get("text")
    elif kind == "scroll":
        fields["scroll_x"] = item.get("scroll_x")
        fields["scroll_y"] = item.get("scroll_y")
    return canonical_action(kind, **fields)


def _scroll_params(action: Mapping[str, Any]) -> Dict[str, Any]:
    """``AC_mouse_scroll`` arguments for a canonical scroll.

    A positive count scrolls ``scroll_direction``; negative reverses it. The
    direction used to be left out, so X11 / Wayland scrolled their default
    way ("up" went down there), and a sideways scroll became a vertical one.
    """
    direction = action.get("direction")
    if action.get("amount") is not None and direction in ("left", "right"):
        return _horizontal(int(action["amount"]), direction)
    if action.get("amount") is not None:
        sign = 1 if direction == "up" else -1
        return {"scroll_value": sign * int(action["amount"]), "scroll_direction": "scroll_up"}
    scroll_y, scroll_x = int(action.get("scroll_y") or 0), int(action.get("scroll_x") or 0)
    if scroll_y == 0 and scroll_x != 0:
        return _horizontal(abs(scroll_x), "right" if scroll_x > 0 else "left")
    return {"scroll_value": -scroll_y, "scroll_direction": "scroll_up"}  # OpenAI: +y is down


def _horizontal(amount: int, direction: str) -> Dict[str, Any]:
    from je_auto_control.wrapper.platform_wrapper import special_mouse_keys_table
    axis = f"scroll_{direction}"
    if axis not in (special_mouse_keys_table or {}):
        # Windows and macOS mouse_scroll has one (vertical) wheel.
        raise AutoControlActionException(
            f"no horizontal scroll wheel on this platform for a {direction} scroll")
    return {"scroll_value": amount, "scroll_direction": axis}


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
        click = ["AC_click_mouse", {"mouse_keycode": _CLICK_BUTTONS[kind], **point}]
        # AC_click_mouse clicks once: a double click was a single click.
        return ["AC_loop", {"times": 2, "body": [click]}] if kind == "double_click" else click
    keys = [resolve_key_name(key) for key in split_key_combo(action.get("text", ""))]
    builders = {
        "move": lambda: ["AC_set_mouse_position", point],
        "type": lambda: ["AC_write", {"write_string": str(action.get("text", ""))}],
        "key": lambda: ["AC_hotkey", {"key_code_list": keys}],
        "scroll": lambda: ["AC_mouse_scroll", {**_scroll_params(action), **point}],
        "screenshot": lambda: ["AC_screenshot", {}],
    }
    if kind in builders:
        return builders[kind]()
    raise AutoControlActionException(f"no AC mapping for action type: {kind!r}")
