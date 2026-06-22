"""Bidirectional-text QA: bidi controls, nesting balance, Trojan-source scan.

``confusables`` catches lookalike *characters*, but invisible Unicode *directional
formatting* (LRE/RLE/LRO/RLO/PDF, the isolates LRI/RLI/FSI/PDI, and the marks
LRM/RLM/ALM) is a separate hazard: it can silently reorder how text renders. That
is both an RTL localisation-QA gap and the basis of the "Trojan Source" attack
(CVE-2021-42574), where override controls make source read differently than it
runs.

This reports the bidi controls in a string, checks that embeddings/isolates are
balanced, infers the base direction, and flags Trojan-source-style formatting.
Pure standard library (``unicodedata``); imports no ``PySide6``. Every function is
pure, so it is fully deterministic in CI.
"""
import unicodedata
from typing import Dict, List

# Code points are built with ``chr`` rather than literal characters so this
# source file itself contains no bidi controls (which would trip Trojan-source
# scanners such as Bandit B613 on the module that detects them).
_NAME_TO_CP = {
    "LRE": 0x202A, "RLE": 0x202B, "PDF": 0x202C, "LRO": 0x202D, "RLO": 0x202E,
    "LRI": 0x2066, "RLI": 0x2067, "FSI": 0x2068, "PDI": 0x2069,
    "LRM": 0x200E, "RLM": 0x200F, "ALM": 0x061C,
}
_BIDI_CONTROLS: Dict[str, str] = {chr(cp): name
                                  for name, cp in _NAME_TO_CP.items()}
# Opening controls mapped to their kind: "E" embedding/override, "I" isolate.
_OPEN_KIND = {chr(_NAME_TO_CP[name]): "E"
              for name in ("LRE", "RLE", "LRO", "RLO")}
_OPEN_KIND.update({chr(_NAME_TO_CP[name]): "I"
                   for name in ("LRI", "RLI", "FSI")})
_CLOSE_EMBED = chr(_NAME_TO_CP["PDF"])
_CLOSE_ISOLATE = chr(_NAME_TO_CP["PDI"])
# Marks do not nest; formatting (non-mark) controls are the reordering hazard.
_MARKS = {chr(_NAME_TO_CP[name]) for name in ("LRM", "RLM", "ALM")}


def bidi_controls(text: str) -> List[Dict[str, object]]:
    """List the bidi control characters in ``text`` as ``{index, char, name}``."""
    return [{"index": index, "char": char, "name": _BIDI_CONTROLS[char]}
            for index, char in enumerate(text or "")
            if char in _BIDI_CONTROLS]


def has_bidi_controls(text: str) -> bool:
    """Whether ``text`` contains any bidi control character."""
    return any(char in _BIDI_CONTROLS for char in text or "")


def _pop_matches(stack: List[str], expected: str) -> bool:
    """Pop ``stack`` and report whether the popped kind was ``expected``."""
    return bool(stack) and stack.pop() == expected


def is_balanced(text: str) -> bool:
    """Whether embeddings/overrides (PDF) and isolates (PDI) are well nested."""
    stack: List[str] = []
    for char in text or "":
        kind = _OPEN_KIND.get(char)
        if kind is not None:
            stack.append(kind)
        elif char == _CLOSE_EMBED and not _pop_matches(stack, "E"):
            return False
        elif char == _CLOSE_ISOLATE and not _pop_matches(stack, "I"):
            return False
    return not stack


def base_direction(text: str) -> str:
    """Infer the paragraph base direction from the first strong character."""
    for char in text or "":
        bidi = unicodedata.bidirectional(char)
        if bidi == "L":
            return "LTR"
        if bidi in ("R", "AL"):
            return "RTL"
    return "NEUTRAL"


def strip_bidi_controls(text: str) -> str:
    """Return ``text`` with every bidi control character removed."""
    return "".join(char for char in text or "" if char not in _BIDI_CONTROLS)


def is_trojan_source(text: str) -> bool:
    """Whether ``text`` carries reordering formatting (Trojan-source hazard).

    True when any non-mark formatting control (embedding/override/isolate) is
    present, or when the bidi nesting is unbalanced.
    """
    has_formatting = any(char in _BIDI_CONTROLS and char not in _MARKS
                         for char in text or "")
    return has_formatting or not is_balanced(text)


def detect_bidi_issues(text: str) -> Dict[str, object]:
    """Full bidi report: controls, balance, base direction, Trojan-source flag."""
    return {
        "controls": bidi_controls(text),
        "has_controls": has_bidi_controls(text),
        "balanced": is_balanced(text),
        "base_direction": base_direction(text),
        "trojan_source": is_trojan_source(text),
    }
