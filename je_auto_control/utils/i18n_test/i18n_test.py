"""Internationalization / localization (i18n / l10n) testing helpers.

Three pure-standard-library checks that compound:

* :func:`pseudo_localize` accents and pads UI strings (preserving
  placeholders) to flush out hardcoded text and pre-stress layout *before*
  any real translation exists.
* :func:`check_overflow` flags text whose estimated width exceeds its
  widget bounds — the #1 l10n bug, computable from the accessibility bounds
  AutoControl already reads.
* :func:`check_catalog` diffs a translation catalog against a base locale
  for missing / empty / orphaned keys and placeholder mismatches.

Imports no ``PySide6``; no third-party dependency.
"""
import re
from typing import Any, Dict, List

# Accent map for common Latin letters (pseudo-localization).
_ACCENTS = str.maketrans(
    "aeiouAEIOUncysNCYS", "àèìòùÀÈÌÒÙñçÿśÑÇÝŚ")
# printf conversions: %s, %d, %(user)s, %1$s, %-5.2f, %i, %%.
_PRINTF = r"%(?:\(\w+\))?(?:\d+\$)?[-+ #0]*\d*(?:\.\d+)?[sdifxXeEgGcr@%]"
# Kept verbatim by pseudo-localization: {name}, {{x}}, {0}, printf, HTML tags.
_PROTECTED = re.compile(r"\{\{[^{}]*\}\}|\{[^{}]*\}|" + _PRINTF + r"|<[^<>]+>")
# An ICU plural / select argument: its header, each case selector, and ``#``
# (in plurals) are kept; the text of every case is localized.
_ICU_HEAD = re.compile(r"\{\s*\w+\s*,\s*(plural|selectordinal|select)\s*,")
_ICU_CASE = re.compile(r"\s*(?:offset:\d+\s*)?(?:=\d+|\w+)\s*\{")
_ICU_CLOSE = re.compile(r"\s*\}")
# What check_catalog compares: printf conversions and {argument} names.
_ARGUMENT = re.compile(r"\{\{?\s*(\w+)")
_PRINTF_ONLY = re.compile(_PRINTF)


class _Segmenter:
    """Split a UI string into ``(protected, text)`` pieces."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.pieces: List[List[Any]] = []

    def run(self) -> List[List[Any]]:
        self._scan(0, nested=False, plural=False)
        return self.pieces

    def _add(self, protected: bool, text: str) -> None:
        if self.pieces and self.pieces[-1][0] == protected:
            self.pieces[-1][1] += text
        else:
            self.pieces.append([protected, text])

    def _scan(self, index: int, *, nested: bool, plural: bool) -> int:
        """Consume up to the ``}`` closing a nested case (not consumed); return its index."""
        text = self.text
        while index < len(text):
            char = text[index]
            if nested and char == "}":
                return index
            head = _ICU_HEAD.match(text, index)
            simple = None if head else _PROTECTED.match(text, index)
            if head:
                index = self._icu(head)
            elif simple:
                self._add(True, simple.group(0))
                index = simple.end()
            else:
                self._add(plural and char == "#", char)
                index += 1
        return index

    def _icu(self, head: "re.Match") -> int:
        self._add(True, head.group(0))
        plural = head.group(1) != "select"
        index = head.end()
        case = _ICU_CASE.match(self.text, index)
        while case:
            self._add(True, case.group(0))
            index = self._scan(case.end(), nested=True, plural=plural)
            if index < len(self.text):
                self._add(True, "}")
                index += 1
            case = _ICU_CASE.match(self.text, index)
        close = _ICU_CLOSE.match(self.text, index)
        if close:
            self._add(True, close.group(0))
            return close.end()
        return index


def pseudo_localize(text: str, *, expansion: float = 0.4,
                    accent: bool = True, brackets: bool = True) -> str:
    """Return a pseudo-localized copy of ``text`` (placeholders preserved).

    Accents Latin letters, pads by ``expansion`` (a fraction of the visible
    text's length) to mimic translation growth, and wraps in ``⟦…⟧`` so
    truncation is visible. Placeholders (``{name}``, ``{{x}}``, printf
    conversions such as ``%(user)s`` / ``%1$s``), HTML tags and the structure
    of ICU ``plural`` / ``select`` arguments are kept verbatim, while the text
    of each ICU case is localized.
    """
    pieces = _Segmenter(text or "").run()
    visible = sum(len(piece) for protected, piece in pieces if not protected)
    body = "".join(piece if protected or not accent else piece.translate(_ACCENTS)
                   for protected, piece in pieces)
    body += "·" * max(0, round(visible * float(expansion)))
    return f"⟦{body}⟧" if brackets else body


def pseudo_localize_catalog(mapping: Dict[str, Any],
                            **kwargs: Any) -> Dict[str, str]:
    """Apply :func:`pseudo_localize` to every value of a catalog mapping."""
    return {key: pseudo_localize(str(value), **kwargs)
            for key, value in mapping.items()}


def _text_of(element: Any) -> str:
    if isinstance(element, dict):
        return str(element.get("text") or element.get("name") or "")
    return str(getattr(element, "name", "") or "")


def _bounds_of(element: Any) -> List[int]:
    if isinstance(element, dict):
        raw = element.get("bbox") or element.get("bounds") or []
    else:
        raw = getattr(element, "bounds", []) or []
    return list(raw)


def check_overflow(elements: List[Any], *,
                   avg_char_px: float = 7.0) -> List[Dict[str, Any]]:
    """Flag elements whose estimated text width exceeds their widget width.

    Width is estimated as ``len(text) * avg_char_px`` (a deterministic
    heuristic); each issue is ``{text, width, required_px, overflow_px}``.
    """
    issues: List[Dict[str, Any]] = []
    for element in elements:
        text = _text_of(element)
        bounds = _bounds_of(element)
        if not text or len(bounds) < 4 or bounds[2] <= 0:
            continue
        width = bounds[2]
        required = len(text) * float(avg_char_px)
        if required > width:
            issues.append({"text": text, "width": width,
                           "required_px": round(required, 1),
                           "overflow_px": round(required - width, 1)})
    return issues


def _placeholders(value: Any) -> set:
    """Printf conversions and ``{argument}`` names -- not ICU case keywords,
    which legitimately differ between languages."""
    text = str(value)
    return set(_PRINTF_ONLY.findall(text)) | {
        "{" + name + "}" for name in _ARGUMENT.findall(text)}


def _empty_keys(base: Dict[str, Any], target: Dict[str, Any]) -> List[str]:
    return sorted(key for key in target
                  if key in base and not str(target[key]).strip())


def _mismatch_keys(base: Dict[str, Any], target: Dict[str, Any]) -> List[str]:
    return sorted(
        key for key in base
        if key in target
        and _placeholders(base[key]) != _placeholders(target[key]))


def check_catalog(base: Dict[str, Any],
                  target: Dict[str, Any]) -> Dict[str, Any]:
    """Diff a translation ``target`` catalog against the ``base`` locale.

    Returns ``{ok, missing, orphaned, empty, placeholder_mismatch}``:
    keys absent in target, keys only in target, blank target values, and
    keys whose placeholder set differs from the base.
    """
    missing = sorted(key for key in base if key not in target)
    orphaned = sorted(key for key in target if key not in base)
    empty = _empty_keys(base, target)
    mismatch = _mismatch_keys(base, target)
    return {"ok": not (missing or empty or mismatch),
            "missing": missing, "orphaned": orphaned,
            "empty": empty, "placeholder_mismatch": mismatch}
