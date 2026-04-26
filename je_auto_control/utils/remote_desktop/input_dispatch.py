"""Apply incoming viewer input messages on the host machine.

Each accepted ``action`` maps to one call against the existing
:mod:`je_auto_control.wrapper` helpers, so the dispatcher is a thin and
auditable boundary: any field not in the allowlist is rejected before it
ever reaches platform code. Wrappers are imported lazily so the module
can be imported on non-host systems (e.g. inside the viewer process)
without pulling in OS-specific backends.
"""
from typing import Any, Callable, Dict, Mapping

InputDispatcher = Callable[[Mapping[str, Any]], Any]


class InputDispatchError(ValueError):
    """Raised when an input message is malformed or references an unknown action."""


_ALLOWED_ACTIONS = {
    "mouse_move", "mouse_click", "mouse_press", "mouse_release",
    "mouse_scroll", "key_press", "key_release", "type", "ping",
}


def _import_wrappers():
    """Lazy import so headless/viewer-only consumers stay platform-agnostic."""
    from je_auto_control.wrapper.auto_control_keyboard import (
        press_keyboard_key, release_keyboard_key, write,
    )
    from je_auto_control.wrapper.auto_control_mouse import (
        click_mouse, mouse_scroll, press_mouse, release_mouse,
        set_mouse_position,
    )
    return {
        "click_mouse": click_mouse,
        "mouse_scroll": mouse_scroll,
        "press_mouse": press_mouse,
        "release_mouse": release_mouse,
        "set_mouse_position": set_mouse_position,
        "press_keyboard_key": press_keyboard_key,
        "release_keyboard_key": release_keyboard_key,
        "write": write,
    }


def dispatch_input(message: Mapping[str, Any]) -> Any:
    """Validate ``message`` and call the matching wrapper function."""
    if not isinstance(message, Mapping):
        raise InputDispatchError(
            f"input message must be a mapping, got {type(message).__name__}"
        )
    action = message.get("action")
    if action not in _ALLOWED_ACTIONS:
        raise InputDispatchError(f"unknown action: {action!r}")
    if action == "ping":
        return None
    wrappers = _import_wrappers()
    return _APPLIERS[action](message, wrappers)


def _apply_mouse_move(message: Mapping[str, Any], wrappers: Dict[str, Any]) -> Any:
    return wrappers["set_mouse_position"](
        int(message["x"]), int(message["y"]),
    )


def _apply_mouse_click(message: Mapping[str, Any], wrappers: Dict[str, Any]) -> Any:
    if "x" in message and "y" in message:
        wrappers["set_mouse_position"](
            int(message["x"]), int(message["y"]),
        )
    button = message.get("button", "mouse_left")
    return wrappers["click_mouse"](button)


def _apply_mouse_press(message: Mapping[str, Any], wrappers: Dict[str, Any]) -> Any:
    return wrappers["press_mouse"](message.get("button", "mouse_left"))


def _apply_mouse_release(message: Mapping[str, Any], wrappers: Dict[str, Any]) -> Any:
    return wrappers["release_mouse"](message.get("button", "mouse_left"))


def _apply_mouse_scroll(message: Mapping[str, Any], wrappers: Dict[str, Any]) -> Any:
    amount = int(message["amount"])
    if "x" in message and "y" in message:
        return wrappers["mouse_scroll"](
            amount, int(message["x"]), int(message["y"]),
        )
    return wrappers["mouse_scroll"](amount)


def _apply_key_press(message: Mapping[str, Any], wrappers: Dict[str, Any]) -> Any:
    return wrappers["press_keyboard_key"](message["keycode"])


def _apply_key_release(message: Mapping[str, Any], wrappers: Dict[str, Any]) -> Any:
    return wrappers["release_keyboard_key"](message["keycode"])


def _apply_type(message: Mapping[str, Any], wrappers: Dict[str, Any]) -> Any:
    text = message.get("text", "")
    if not isinstance(text, str):
        raise InputDispatchError("'type' message requires string 'text'")
    return wrappers["write"](text)


_APPLIERS: Dict[str, Callable[[Mapping[str, Any], Dict[str, Any]], Any]] = {
    "mouse_move": _apply_mouse_move,
    "mouse_click": _apply_mouse_click,
    "mouse_press": _apply_mouse_press,
    "mouse_release": _apply_mouse_release,
    "mouse_scroll": _apply_mouse_scroll,
    "key_press": _apply_key_press,
    "key_release": _apply_key_release,
    "type": _apply_type,
}
