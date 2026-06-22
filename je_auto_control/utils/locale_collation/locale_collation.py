"""Locale-aware string collation (deterministic multi-level sort keys).

``text_normalize`` canonicalises text and ``locale_parse`` formats numbers, but
nothing sorts strings the way a human reading a given language expects: Python's
default ``sorted`` is codepoint order, so ``"Z" < "a"`` and ``"ä"`` lands far
from ``"a"``. A real collation orders by base letter first, then accent, then
case, and lets a locale tailor the alphabet (Swedish sorts ``å ä ö`` after
``z``).

This builds a Unicode-Collation-lite sort key with three levels — primary (base
letter), secondary (diacritics), tertiary (case) — plus an optional alphabet
``tailoring``. Pure standard library (``unicodedata``); imports no ``PySide6``.
Every function is pure (text in, key/order out), so it is fully deterministic in
CI and across platforms (unlike ``locale.strxfrm``).
"""
import unicodedata
from typing import Callable, Dict, List, Optional, Sequence, Tuple

_STRENGTHS = {"primary": 1, "secondary": 2, "tertiary": 3}

CollationKey = Tuple[Tuple[int, ...], ...]


def _build_tailoring(tailoring: Optional[str]) -> Optional[Dict[str, int]]:
    """Map each character of an ordered alphabet to its primary rank."""
    if not tailoring:
        return None
    ranks: Dict[str, int] = {}
    for index, char in enumerate(tailoring):
        folded = char.casefold()
        if folded not in ranks:
            ranks[folded] = index
    return ranks


def _untailored_weight(base: str, ranks: Optional[Dict[str, int]],
                       offset: int) -> int:
    """Primary weight of a folded base character outside any tailoring."""
    if not base:
        return offset if ranks is not None else 0
    return offset + ord(base[0]) if ranks is not None else ord(base[0])


def _char_weights(char: str, ranks: Optional[Dict[str, int]],
                  offset: int) -> Tuple[List[int], List[int], List[int]]:
    """Primary/secondary/tertiary weight contributions of one character.

    A tailored character is treated atomically (no decomposition) so a
    precomposed letter like ``"å"`` keeps its alphabet rank; everything else is
    NFKD-decomposed so diacritics fall to the secondary level.
    """
    folded = char.casefold()
    if ranks is not None and folded in ranks:
        return [ranks[folded]], [], [1 if char != folded else 0]
    primary: List[int] = []
    secondary: List[int] = []
    tertiary: List[int] = []
    for sub in unicodedata.normalize("NFKD", char):
        if unicodedata.combining(sub):
            secondary.append(ord(sub))
            continue
        subfold = sub.casefold()
        primary.append(_untailored_weight(subfold, ranks, offset))
        tertiary.append(1 if sub != subfold else 0)
    return primary, secondary, tertiary


def collation_key(text: str, *, strength: str = "tertiary",
                  tailoring: Optional[str] = None) -> CollationKey:
    """Return a comparable multi-level sort key for ``text``.

    Levels: primary (base letter), secondary (diacritics), tertiary (case,
    lowercase before uppercase). ``strength`` (``primary`` / ``secondary`` /
    ``tertiary``) caps the levels compared. ``tailoring`` is an ordered alphabet
    whose characters sort in the given order and before any unlisted character
    (so a Swedish ``"...xyzåäö"`` puts ``å`` after ``z``).
    """
    level = _STRENGTHS.get(strength)
    if level is None:
        raise ValueError(f"unknown strength: {strength!r}")
    ranks = _build_tailoring(tailoring)
    offset = len(tailoring) if tailoring else 0
    primary: List[int] = []
    secondary: List[int] = []
    tertiary: List[int] = []
    for char in text or "":
        char_primary, char_secondary, char_tertiary = _char_weights(
            char, ranks, offset)
        primary.extend(char_primary)
        secondary.extend(char_secondary)
        tertiary.extend(char_tertiary)
    levels = (tuple(primary), tuple(secondary), tuple(tertiary))
    return levels[:level]


def compare(first: str, second: str, *, strength: str = "tertiary",
            tailoring: Optional[str] = None) -> int:
    """Return ``-1`` / ``0`` / ``1`` ordering ``first`` against ``second``."""
    key_first = collation_key(first, strength=strength, tailoring=tailoring)
    key_second = collation_key(second, strength=strength, tailoring=tailoring)
    if key_first < key_second:
        return -1
    if key_first > key_second:
        return 1
    return 0


def sort_strings(items: Sequence[str], *, strength: str = "tertiary",
                 tailoring: Optional[str] = None, reverse: bool = False,
                 key: Optional[Callable[[object], str]] = None) -> List[object]:
    """Return ``items`` sorted by collation key.

    ``key`` extracts the string from each item (default: the item itself), so
    dicts or tuples can be sorted by one of their fields.
    """
    extract = key or (lambda item: item)

    def sort_key(item: object) -> CollationKey:
        return collation_key(str(extract(item)), strength=strength,
                             tailoring=tailoring)

    return sorted(items, key=sort_key, reverse=reverse)
