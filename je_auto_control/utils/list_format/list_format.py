"""Locale-aware list formatting ("A, B, and C") in the style of CLDR.

``locale_parse`` formats numbers/dates and ``message_format`` (planned) renders
plural/select messages, but joining a list of items the way a language expects —
the conjunction word, whether there is a serial/Oxford comma, the two-item
special case — is its own small problem. Naive ``", ".join`` gives "A, B, C"
with no "and"/"or" and no localisation.

This implements the CLDR list-pattern composition (start/middle/end + a two-item
pattern) for a handful of locales and the conjunction / disjunction / unit
styles. Pure standard library; imports no ``PySide6``. Every function is pure, so
it is fully deterministic in CI.
"""
from typing import Dict, List, Sequence

# Conjunction word per (locale, style). Unit style uses no word at all.
_CONJUNCTIONS: Dict[str, Dict[str, str]] = {
    "en": {"and": "and", "or": "or"},
    "es": {"and": "y", "or": "o"},
    "fr": {"and": "et", "or": "ou"},
    "de": {"and": "und", "or": "oder"},
    "pt": {"and": "e", "or": "ou"},
}
# Locales that place a serial (Oxford) comma before the final conjunction.
_SERIAL_COMMA = {"en"}
_VALID_STYLES = ("and", "or", "unit")


def _patterns(locale: str, style: str) -> Dict[str, str]:
    """Return the ``two``/``start``/``middle``/``end`` patterns for a locale."""
    pair = "{0}, {1}"
    if style == "unit":
        return {"two": pair, "start": pair, "middle": pair, "end": pair}
    if locale not in _CONJUNCTIONS:   # unknown locale -> behave as English
        locale = "en"
    word = _CONJUNCTIONS[locale][style]
    separator = ", " if locale in _SERIAL_COMMA else " "
    return {
        "two": f"{{0}} {word} {{1}}",
        "start": pair,
        "middle": pair,
        "end": f"{{0}}{separator}{word} {{1}}",
    }


def format_list(items: Sequence[object], *, style: str = "and",
                locale: str = "en") -> str:
    """Join ``items`` into a localised list string.

    ``style`` is ``"and"`` (conjunction), ``"or"`` (disjunction) or ``"unit"``
    (comma-separated, no conjunction). ``locale`` selects the conjunction word
    and serial-comma rule (``en``/``es``/``fr``/``de``/``pt``; unknown falls back
    to English). Raises ``ValueError`` on an unknown ``style``.
    """
    if style not in _VALID_STYLES:
        raise ValueError(f"unknown style: {style!r}")
    values: List[str] = [str(item) for item in items]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    patterns = _patterns(locale, style)
    if len(values) == 2:
        return patterns["two"].format(values[0], values[1])
    result = patterns["end"].format(values[-2], values[-1])
    for index in range(len(values) - 3, 0, -1):
        result = patterns["middle"].format(values[index], result)
    return patterns["start"].format(values[0], result)
