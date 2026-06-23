"""Clear-then-type a text field (the Playwright ``fill`` idiom).

Setting a field's value reliably means *clearing* whatever is there first, then
entering the new text — otherwise automation appends to or corrupts the existing
content. The framework has ``write`` (types, but raises on emoji / CJK / chars
outside the layout table) and ``set_clipboard`` / ``hotkey`` separately, but no
single "focus → clear → set value" primitive, and no paste strategy for text
``write`` cannot type.

:func:`plan_field_set` builds the deterministic op-plan (pure, unit-testable);
:func:`set_field_text` dispatches it through an injectable ``sink`` so it is
tested without real input. Imports no ``PySide6``.
"""
from typing import Any, Callable, Dict, List, Optional

_CLEAR_MODES = ("select_all", "none")
Sink = Callable[[Dict[str, Any]], None]


def plan_field_set(text: str, *, clear: str = "select_all", paste: bool = False,
                   modifier: str = "ctrl") -> List[Dict[str, Any]]:
    """Return the op-plan to set a focused field to ``text``.

    ``clear`` is ``"select_all"`` (``modifier``+A then Delete) or ``"none"``.
    ``paste=True`` enters the text via the clipboard (``modifier``+V) — the
    reliable path for Unicode / emoji / CJK that ``write`` cannot type — instead
    of typing it key by key. ``modifier`` is the platform command key
    (``"ctrl"``; use ``"command"`` on macOS). Raises ``ValueError`` on an unknown
    ``clear`` mode.
    """
    if clear not in _CLEAR_MODES:
        raise ValueError(f"unknown clear mode: {clear!r}")
    plan: List[Dict[str, Any]] = []
    if clear == "select_all":
        plan.append({"op": "hotkey", "keys": [modifier, "a"]})
        plan.append({"op": "key", "key": "delete"})
    if paste:
        plan.append({"op": "set_clipboard", "text": text})
        plan.append({"op": "hotkey", "keys": [modifier, "v"]})
    else:
        plan.append({"op": "type", "text": text})
    return plan


def _default_sink(event: Dict[str, Any]) -> None:
    """Default dispatch: drive the real keyboard / clipboard backend."""
    op = event["op"]
    if op == "hotkey":
        from je_auto_control.wrapper.auto_control_keyboard import hotkey
        hotkey(list(event["keys"]))
    elif op == "key":
        from je_auto_control.wrapper.auto_control_keyboard import type_keyboard
        type_keyboard(event["key"])
    elif op == "type":
        from je_auto_control.wrapper.auto_control_keyboard import write
        write(event["text"])
    elif op == "set_clipboard":
        from je_auto_control.utils.clipboard.clipboard import set_clipboard
        set_clipboard(event["text"])


def set_field_text(text: str, *, clear: str = "select_all", paste: bool = False,
                   modifier: str = "ctrl",
                   sink: Optional[Sink] = None) -> Dict[str, Any]:
    """Clear the focused field and enter ``text``; return the dispatched plan."""
    plan = plan_field_set(text, clear=clear, paste=paste, modifier=modifier)
    dispatch = sink or _default_sink
    for event in plan:
        dispatch(event)
    return {"ops": len(plan), "plan": plan}
