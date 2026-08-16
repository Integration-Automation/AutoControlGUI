"""Type arbitrary Unicode (emoji / CJK / accented) by key injection or clipboard.

``write`` types through the platform virtual-key table and *raises* on any
character outside it — emoji, CJK, many accented letters, and on a US table even
``, . / : ? ! _ + @ %`` — so non-ASCII and most punctuation are unreachable
through the normal path.

Two ways out, and the difference matters:

* **Key injection** (:func:`type_unicode_keys`) sends each UTF-16 code unit as a
  character-carrying key event. Nothing else on the machine changes, so it is the
  default wherever the backend supports it (Windows ``KEYEVENTF_UNICODE``).
* **Clipboard paste** (:func:`type_unicode`) works everywhere but **overwrites
  whatever the user had on the clipboard**, and fails outright in fields that
  block paste (many password and licence-key inputs).

:func:`plan_paste`, :func:`plan_unicode_keys` and :func:`unicode_code_units` are
pure and unit-testable; the typing entry points dispatch through an injectable
``sink`` so they are tested without touching the real clipboard or keyboard.
Imports no ``PySide6``.
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


def plan_unicode_keys(text: str) -> List[Dict[str, Any]]:
    """Return the op-plan to enter ``text`` as character-carrying key events.

    One op per UTF-16 code unit, so a character above U+FFFF becomes the two
    surrogates the platform layer has to send separately.
    """
    return [{"op": "unicode_unit", "unit": unit}
            for unit in unicode_code_units(text)]


def unicode_keys_supported() -> bool:
    """Whether this platform's keyboard backend can inject Unicode directly."""
    try:
        from je_auto_control.wrapper.platform_wrapper import keyboard
    except (ImportError, AttributeError):
        return False
    return callable(getattr(keyboard, "type_unicode_unit", None))


def _default_sink(event: Dict[str, Any]) -> None:
    """Default dispatch: drive the real clipboard / keyboard backend."""
    op = event["op"]
    if op == "set_clipboard":
        from je_auto_control.utils.clipboard.clipboard import set_clipboard
        set_clipboard(event["text"])
    elif op == "hotkey":
        from je_auto_control.wrapper.auto_control_keyboard import hotkey
        hotkey(list(event["keys"]))
    elif op == "unicode_unit":
        from je_auto_control.wrapper.platform_wrapper import keyboard
        keyboard.type_unicode_unit(int(event["unit"]))


def type_unicode(text: str, *, modifier: str = "ctrl",
                 sink: Optional[Sink] = None) -> Dict[str, Any]:
    """Enter ``text`` (any Unicode) by setting the clipboard then pasting.

    ``modifier`` is the platform paste key (``"ctrl"``; use ``"command"`` on
    macOS). Returns the dispatched plan plus the UTF-16 code-unit count.

    Prefer :func:`type_unicode_text` unless the clipboard route is wanted
    deliberately — this one replaces the user's clipboard contents.
    """
    plan = plan_paste(text, modifier=modifier)
    return _dispatch(plan, text, sink, "paste")


def type_unicode_keys(text: str, *,
                      sink: Optional[Sink] = None) -> Dict[str, Any]:
    """Enter ``text`` as character-carrying key events, leaving the clipboard alone.

    Requires a backend exposing ``type_unicode_unit`` (Windows today); callers
    that need a guaranteed route on every platform should use
    :func:`type_unicode_text`.
    """
    plan = plan_unicode_keys(text)
    return _dispatch(plan, text, sink, "keys")


def type_unicode_text(text: str, *, modifier: str = "ctrl",
                      sink: Optional[Sink] = None) -> Dict[str, Any]:
    """Enter ``text`` by the best route this platform offers.

    Key injection when the backend supports it, clipboard paste otherwise. The
    returned ``method`` says which one ran, because the two are not equivalent:
    paste clobbers the clipboard and is refused by some inputs.
    """
    if unicode_keys_supported():
        return type_unicode_keys(text, sink=sink)
    return type_unicode(text, modifier=modifier, sink=sink)


def _dispatch(plan: List[Dict[str, Any]], text: str,
              sink: Optional[Sink], method: str) -> Dict[str, Any]:
    """Run ``plan`` through ``sink`` and describe what was dispatched."""
    dispatch = sink or _default_sink
    for event in plan:
        dispatch(event)
    return {"ops": len(plan), "plan": plan, "method": method,
            "code_units": len(unicode_code_units(text))}
