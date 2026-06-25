"""Read a field back after typing and confirm it holds the intended value.

``field_entry`` types into a control and *hopes* it landed: a slow IME, a focus
steal, an input mask or an auto-format can silently mangle or drop characters,
and nothing reads the field back to notice. This is distinct from
``action_effect`` (did *anything* change near the target?) and
``postcondition.text_present`` (does the text appear *anywhere* on screen?) —
neither confirms *this* field now equals *this* value.

* :func:`compare_field_value` — pure: compare an expected and actual value under
  a match ``mode`` (``exact`` / ``trim`` / ``ci`` / ``normalized`` /
  ``contains``).
* :func:`verify_field_value` — read the field through an injectable ``reader``
  and compare.
* :func:`fill_and_verify` — type through an injectable ``filler``, read back, and
  retry (optionally clearing first) until it matches or attempts run out.

The reader / filler seams default to the native accessibility value in the
executor, but every comparison and retry decision is pure and testable without a
real control. Imports no ``PySide6``.
"""
from typing import Any, Callable, Dict, Optional

# Match modes.
MATCH_EXACT = "exact"
MATCH_TRIM = "trim"
MATCH_CI = "ci"
MATCH_NORMALIZED = "normalized"
MATCH_CONTAINS = "contains"

# A reader returns the field's current value; a filler types a value into it.
FieldReader = Callable[[], Optional[str]]
FieldFiller = Callable[[str], None]


def _canonical(text: str, mode: str) -> str:
    """Canonicalize ``text`` for comparison under ``mode`` (pure)."""
    if mode in (MATCH_TRIM, MATCH_CI, MATCH_CONTAINS):
        text = text.strip()
    if mode in (MATCH_CI, MATCH_CONTAINS):
        text = text.casefold()
    if mode == MATCH_NORMALIZED:
        from je_auto_control.utils.text_normalize import normalize_text
        return normalize_text(text)
    return text


def _as_text(value: Any) -> str:
    """Coerce a value to a string, treating ``None`` as empty."""
    return "" if value is None else str(value)


def compare_field_value(expected: Any, actual: Any, *,
                        mode: str = MATCH_EXACT) -> Dict[str, Any]:
    """Compare ``expected`` against ``actual`` under ``mode`` (pure).

    Returns ``{match, mode, expected, actual}``. ``contains`` is a (trimmed,
    case-insensitive) substring test; the others compare canonical equality.
    """
    expected_text = _as_text(expected)
    actual_text = _as_text(actual)
    if mode == MATCH_CONTAINS:
        match = _canonical(expected_text, mode) in _canonical(actual_text, mode)
    else:
        match = _canonical(expected_text, mode) == _canonical(actual_text, mode)
    return {"match": bool(match), "mode": mode,
            "expected": expected_text, "actual": actual_text}


def verify_field_value(expected: Any, *, reader: FieldReader,
                       mode: str = MATCH_EXACT) -> Dict[str, Any]:
    """Read the field via ``reader`` and compare it to ``expected``.

    Returns the :func:`compare_field_value` result for the value read back.
    """
    return compare_field_value(expected, reader(), mode=mode)


def fill_and_verify(value: Any, *, filler: FieldFiller, reader: FieldReader,
                    attempts: int = 2, mode: str = MATCH_EXACT,
                    clear: Optional[Callable[[], None]] = None
                    ) -> Dict[str, Any]:
    """Type ``value`` via ``filler``, read it back, and retry until it matches.

    Up to ``attempts`` tries; before each retry (not the first) ``clear`` is
    called if supplied. Returns the final :func:`compare_field_value` result
    with an added ``attempts`` count.
    """
    total = max(1, int(attempts))
    result: Dict[str, Any] = compare_field_value(value, None, mode=mode)
    used = 0
    for used in range(1, total + 1):
        if clear is not None and used > 1:
            clear()
        filler(value)
        result = compare_field_value(value, reader(), mode=mode)
        if result["match"]:
            break
    result = dict(result)
    result["attempts"] = used
    return result
