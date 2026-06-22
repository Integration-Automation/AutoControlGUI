"""Type arbitrary Unicode (emoji / CJK / accented) via the clipboard.

``write`` types through the platform virtual-key table and *raises* on any
character outside it — emoji, CJK, many accented letters — so non-ASCII text
entry is impossible through the normal path. The reliable, cross-platform way to
enter arbitrary Unicode is to put it on the clipboard and paste it.

:func:`plan_paste` builds the deterministic op-plan and :func:`unicode_code_units`
splits text into UTF-16 code units (for a backend that can do
``KEYEVENTF_UNICODE``); both are pure and unit-testable. :func:`type_unicode`
dispatches the paste plan through an injectable ``sink`` so it is tested without
touching the real clipboard. Imports no ``PySide6``.
"""
from typing import Any, Callable, Dict, List, Optional

Sink = Callable[[Dict[str, Any]], None]


def unicode_code_units(text: str) -> List[int]:
    """Return the UTF-16 code units of ``text`` (surrogate pairs for > U+FFFF)."""
    units: List[int] = []
    for char in text or "":
        code = ord(char)
        if code > 0xFFFF:
            code -= 0x10000
            units.append(0xD800 + (code >> 10))
            units.append(0xDC00 + (code & 0x3FF))
        else:
            units.append(code)
    return units


def plan_paste(text: str, *, modifier: str = "ctrl") -> List[Dict[str, Any]]:
    """Return the op-plan to enter ``text`` via clipboard paste."""
    return [{"op": "set_clipboard", "text": text},
            {"op": "hotkey", "keys": [modifier, "v"]}]


def _default_sink(event: Dict[str, Any]) -> None:
    """Default dispatch: drive the real clipboard / keyboard backend."""
    op = event["op"]
    if op == "set_clipboard":
        from je_auto_control.utils.clipboard.clipboard import set_clipboard
        set_clipboard(event["text"])
    elif op == "hotkey":
        from je_auto_control.wrapper.auto_control_keyboard import hotkey
        hotkey(list(event["keys"]))


def type_unicode(text: str, *, modifier: str = "ctrl",
                 sink: Optional[Sink] = None) -> Dict[str, Any]:
    """Enter ``text`` (any Unicode) by setting the clipboard then pasting.

    ``modifier`` is the platform paste key (``"ctrl"``; use ``"command"`` on
    macOS). Returns the dispatched plan plus the UTF-16 code-unit count.
    """
    plan = plan_paste(text, modifier=modifier)
    dispatch = sink or _default_sink
    for event in plan:
        dispatch(event)
    return {"ops": len(plan), "plan": plan,
            "code_units": len(unicode_code_units(text))}
