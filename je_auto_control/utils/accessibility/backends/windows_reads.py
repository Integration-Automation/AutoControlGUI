"""Plain reads of Windows UIA pattern and element properties.

Each helper turns one COM object (a pattern, a text range, a header array, a
raw element) into plain Python values and answers ``None`` / ``""`` for a
property the provider cannot deliver, instead of letting one unreadable field
fail the whole read. No state and no COM lifetime management live here --
that stays in :mod:`windows_backend`.

Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Tuple, Type

from je_auto_control.utils.accessibility.backends.windows_query import UIA_ERRORS

#: Every guard below. ``COMError`` is why a narrower tuple would contain
#: nothing -- see ``windows_query._uia_errors``; ``TypeError`` joins it because
#: several of these reads coerce whatever the provider returned.
UIA_READ_ERRORS: Tuple[Type[BaseException], ...] = UIA_ERRORS + (TypeError,)
_UIA_ERRORS = UIA_READ_ERRORS


def _view_name(pattern, view_id) -> str:
    """Return a MultipleViewPattern view's name, or '' on failure."""
    try:
        return str(pattern.GetViewName(int(view_id)) or "")
    except _UIA_ERRORS:
        return ""


def _header_names(array) -> List[str]:
    """Read an IUIAutomationElementArray of header elements into name strings."""
    names: List[str] = []
    try:
        count = int(array.Length or 0)
    except _UIA_ERRORS:
        return names
    for index in range(count):
        try:
            names.append(str(array.GetElement(index).CurrentName or ""))
        except _UIA_ERRORS:
            names.append("")
    return names


def _read_cell(item_pattern, cell, row: int, column: int) -> Dict[str, Any]:
    """Build a cell record, enriching with GridItemPattern row/col/span if present."""
    info: Dict[str, Any] = {
        "value": _safe_name(cell), "row": row, "column": column,
        "row_span": 1, "column_span": 1,
    }
    if item_pattern is not None:
        for key, attr in (("row", "CurrentRow"), ("column", "CurrentColumn"),
                          ("row_span", "CurrentRowSpan"),
                          ("column_span", "CurrentColumnSpan")):
            try:
                info[key] = int(getattr(item_pattern, attr))
            except _UIA_ERRORS:
                pass
    return info


def _safe_name(raw) -> str:
    try:
        return str(raw.CurrentName or "")
    except _UIA_ERRORS:
        return ""


def _as_text(value) -> str:
    return str(value or "")


# UIA TextPattern attribute ids (UIAutomationClient AttributeId range).
_TEXT_ATTR_FONT_NAME = 40005
_TEXT_ATTR_FONT_SIZE = 40006
_TEXT_ATTR_FONT_WEIGHT = 40007
_TEXT_ATTR_FOREGROUND = 40008
_TEXT_ATTR_IS_ITALIC = 40014


def _attr(text_range, attribute_id, cast):
    try:
        return cast(text_range.GetAttributeValue(attribute_id))
    except _UIA_ERRORS:
        return None


def _read_text_attributes(text_range) -> Dict[str, Any]:
    """Read font / colour formatting of a TextRange into a plain dict."""
    weight = _attr(text_range, _TEXT_ATTR_FONT_WEIGHT, int)
    return {
        "font_name": _attr(text_range, _TEXT_ATTR_FONT_NAME, _as_text),
        "font_size": _attr(text_range, _TEXT_ATTR_FONT_SIZE, float),
        "bold": (weight >= 700) if isinstance(weight, int) else None,
        "italic": _attr(text_range, _TEXT_ATTR_IS_ITALIC, bool),
        "foreground_color": _attr(text_range, _TEXT_ATTR_FOREGROUND, int),
    }


# (key, LegacyIAccessiblePattern attribute, cast) for the MSAA bridge read.
_LEGACY_READS = (
    ("name", "CurrentName", _as_text),
    ("value", "CurrentValue", _as_text),
    ("description", "CurrentDescription", _as_text),
    ("default_action", "CurrentDefaultAction", _as_text),
    ("role", "CurrentRole", int),
    ("state", "CurrentState", int),
)


def _read_legacy(pattern) -> Dict[str, Any]:
    """Read a LegacyIAccessiblePattern's MSAA fields into a plain dict."""
    info: Dict[str, Any] = {}
    for key, attribute, cast in _LEGACY_READS:
        try:
            info[key] = cast(getattr(pattern, attribute))
        except _UIA_ERRORS:
            info[key] = None
    return info


# (key, UIA element attribute, cast) for the rich properties the flat list omits.
_PROPERTY_READS = (
    ("enabled", "CurrentIsEnabled", bool),
    ("offscreen", "CurrentIsOffscreen", bool),
    ("help_text", "CurrentHelpText", _as_text),
    ("item_status", "CurrentItemStatus", _as_text),
    ("accelerator_key", "CurrentAcceleratorKey", _as_text),
    ("access_key", "CurrentAccessKey", _as_text),
    ("orientation", "CurrentOrientation", int),
)


def _read_properties(raw) -> Dict[str, Any]:
    """Read the rich UIA properties of a raw element into a plain dict."""
    properties: Dict[str, Any] = {}
    for key, attribute, cast in _PROPERTY_READS:
        try:
            properties[key] = cast(getattr(raw, attribute))
        except _UIA_ERRORS:
            properties[key] = None
    return properties
