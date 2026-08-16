"""Read what a Windows UIA control currently holds, safely.

This is the half that pixels cannot answer: text scrolled out of view, a
checkbox's true state, a slider's exact number. Values are read through
``GetCurrentPropertyValue`` rather than ``QueryInterface`` on each pattern —
only the value is wanted, not the pattern object.

Two rules shape everything here:

* **Ask whether the pattern exists before reading it.** An unsupported pattern
  answers with a *default* (empty string, ``0``), which reads as "the value is
  empty" instead of "this control has no value" — the more misleading of the
  two, because a caller will act on it.
* **Never return a password field's contents.** UIA is supposed to mask them,
  but that is a convention a custom-drawn control can ignore, and the caller
  may well be forwarding what it reads somewhere else.

Imports no ``PySide6``.
"""
from typing import Any, Dict

_UIA_IS_PASSWORD_PROPERTY = 30019
_UIA_VALUE_IS_READONLY_PROPERTY = 30046
_UIA_LEGACY_VALUE_PROPERTY = 30093

# ``key -> (is-this-pattern-available id, value id)``
_STATE_READS = (
    ("value", 30029, 30045),        # IsValuePatternAvailable, Value.Value
    ("toggle", 30041, 30086),       # IsTogglePatternAvailable, ToggleState
    ("selected", 30036, 30079),     # IsSelectionItemPatternAvailable, IsSelected
    ("number", 30034, 30047),       # IsRangeValuePatternAvailable, RangeValue
)

TOGGLE_STATES = {0: "off", 1: "on", 2: "mixed"}


def _prop(raw, property_id: int) -> Any:
    """Read one UIA property; ``None`` when it cannot be read."""
    try:
        return raw.GetCurrentPropertyValue(property_id)
    except (OSError, AttributeError, ValueError):
        return None


def is_password(raw) -> bool:
    """Whether the element is a password field. Unreadable counts as yes."""
    value = _prop(raw, _UIA_IS_PASSWORD_PROPERTY)
    return True if value is None else bool(value)


def _supported_values(raw) -> Dict[str, Any]:
    """Raw values for every pattern the control actually supports."""
    state: Dict[str, Any] = {}
    for key, available_id, value_id in _STATE_READS:
        if not _prop(raw, available_id):
            continue
        value = _prop(raw, value_id)
        if value is not None:
            state[key] = value
    return state


def _normalise_value(raw, state: Dict[str, Any]) -> None:
    """Coerce ``value`` to text, or fall back to the legacy accessible value."""
    if "value" in state:
        state["value"] = str(state["value"] or "")
        state["read_only"] = bool(_prop(raw, _UIA_VALUE_IS_READONLY_PROPERTY))
        return
    legacy = _prop(raw, _UIA_LEGACY_VALUE_PROPERTY)
    if legacy:
        state["value"] = str(legacy)


def _normalise_rest(state: Dict[str, Any]) -> None:
    """Turn the remaining raw enum / numeric values into plain Python ones."""
    if "toggle" in state:
        code = state["toggle"]
        state["toggle"] = TOGGLE_STATES.get(int(code or 0), str(code))
    if "selected" in state:
        state["selected"] = bool(state["selected"])
    if "number" in state:
        state["number"] = float(state["number"])


def read_state(raw) -> Dict[str, Any]:
    """``{value?, read_only?, toggle?, selected?, number?}`` for one element.

    A key is absent when the control does not support it. Password fields
    report only ``{"password": True}``.
    """
    if is_password(raw):
        # nosec B105  # reason: a flag marking the field AS a password,
        # returned deliberately in place of its contents — not a credential.
        return {"password": True}  # nosec B105
    state = _supported_values(raw)
    _normalise_value(raw, state)
    _normalise_rest(state)
    return state
