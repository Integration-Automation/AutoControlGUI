"""Confusable / homoglyph detection (Unicode-spoofing skeletons + mixed script).

``secrets_scan`` finds secret-shaped tokens and ``guardrail`` screens text for
prompt injection, but nothing catches *visual* spoofing: a Cyrillic ``"а"``
(U+0430) is pixel-for-pixel a Latin ``"a"`` (U+0061), so ``"pаypal"`` (with a
Cyrillic ``а``) reads as ``"paypal"`` to a human yet compares unequal — the basis
of IDN-homograph phishing and lookalike UI labels.

Following the idea of Unicode TR39, this folds confusable characters to a
prototype *skeleton* (two strings are confusable when their skeletons match) and
flags strings that mix scripts (Latin + Cyrillic). Pure standard library
(``unicodedata``); imports no ``PySide6``. Every function is pure, so it is fully
deterministic in CI.
"""
import unicodedata
from typing import Dict, List, Set, Tuple

# Cross-script homoglyphs that NFKC does not fold. Maps each lookalike to its
# Latin/ASCII prototype. (Fullwidth, math-alphanumerics, etc. are handled by the
# NFKC pass in ``skeleton`` and need no entry here.)
_CONFUSABLES: Dict[str, str] = {
    # Cyrillic lowercase
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "һ": "h", "ѵ": "v", "ԛ": "q",
    "ԝ": "w", "ё": "e", "г": "r", "п": "n",
    # Cyrillic uppercase
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "Х": "X", "І": "I", "Ј": "J", "Ѕ": "S",
    "У": "Y", "Ԛ": "Q", "Ԝ": "W", "Г": "r",
    # Greek lowercase
    "ο": "o", "α": "a", "ν": "v", "ρ": "p", "ε": "e", "ι": "i", "κ": "k",
    "μ": "u", "τ": "t", "υ": "u", "χ": "x", "γ": "y",
    # Greek uppercase
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
}

# Script blocks for mixed-script detection. Ranges are inclusive; characters
# outside every range (digits, punctuation, spaces, symbols) count as COMMON and
# are ignored when deciding whether scripts are mixed.
_SCRIPT_RANGES: Tuple[Tuple[int, int, str], ...] = (
    (0x0041, 0x005A, "LATIN"), (0x0061, 0x007A, "LATIN"),
    (0x00C0, 0x024F, "LATIN"), (0x1E00, 0x1EFF, "LATIN"),
    (0x0370, 0x03FF, "GREEK"), (0x1F00, 0x1FFF, "GREEK"),
    (0x0400, 0x052F, "CYRILLIC"),
    (0x0530, 0x058F, "ARMENIAN"),
    (0x0590, 0x05FF, "HEBREW"),
    (0x0600, 0x06FF, "ARABIC"),
    (0x3040, 0x309F, "HIRAGANA"), (0x30A0, 0x30FF, "KATAKANA"),
    (0x3400, 0x9FFF, "HAN"), (0xAC00, 0xD7AF, "HANGUL"),
)


def _script_of(char: str) -> str:
    """Return the script name of a character (``COMMON`` if not a letter)."""
    code = ord(char)
    for start, end, name in _SCRIPT_RANGES:
        if start <= code <= end:
            return name
    return "COMMON"


def skeleton(text: str) -> str:
    """Return the confusable skeleton of ``text`` (TR39-style).

    NFKC-normalises (folding fullwidth, ligatures, math alphanumerics), then maps
    each remaining cross-script homoglyph to its Latin prototype. Two strings are
    confusable exactly when their skeletons are equal.
    """
    normalised = unicodedata.normalize("NFKC", text or "")
    return "".join(_CONFUSABLES.get(char, char) for char in normalised)


def is_confusable(first: str, second: str) -> bool:
    """Whether two *distinct* strings render to the same skeleton."""
    return first != second and skeleton(first) == skeleton(second)


def detect_homoglyphs(text: str) -> List[Dict[str, object]]:
    """List the confusable characters in ``text``.

    Each entry is ``{index, char, prototype}`` for a character whose skeleton
    differs from itself (i.e. a cross-script lookalike).
    """
    findings: List[Dict[str, object]] = []
    for index, char in enumerate(unicodedata.normalize("NFKC", text or "")):
        prototype = _CONFUSABLES.get(char)
        if prototype is not None:
            findings.append({"index": index, "char": char,
                             "prototype": prototype})
    return findings


def scripts_of(text: str) -> Set[str]:
    """Return the set of (non-common) scripts present in ``text``."""
    scripts = {_script_of(char) for char in text or ""}
    scripts.discard("COMMON")
    return scripts


def is_mixed_script(text: str) -> bool:
    """Whether ``text`` mixes more than one script (a spoofing red flag)."""
    return len(scripts_of(text)) > 1
