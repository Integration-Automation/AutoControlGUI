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
# Placeholders to preserve verbatim: {name}, {{x}}, %s, %d, {0}.
_PLACEHOLDER = re.compile(r"\{\{[^}]*\}\}|\{[^}]*\}|%[sd]")
_SENTINEL = re.compile("\x00(\\d+)\x00")


def pseudo_localize(text: str, *, expansion: float = 0.4,
                    accent: bool = True, brackets: bool = True) -> str:
    """Return a pseudo-localized copy of ``text`` (placeholders preserved).

    Accents Latin letters, pads by ``expansion`` (fraction of length) to
    mimic translation growth, and wraps in ``⟦…⟧`` so truncation is visible.
    """
    source = text or ""
    holders: List[str] = []

    def stash(match: "re.Match") -> str:
        holders.append(match.group(0))
        return f"\x00{len(holders) - 1}\x00"

    protected = _PLACEHOLDER.sub(stash, source)
    body = protected.translate(_ACCENTS) if accent else protected
    body += "·" * max(0, round(len(protected) * float(expansion)))
    restored = _SENTINEL.sub(lambda m: holders[int(m.group(1))], body)
    return f"⟦{restored}⟧" if brackets else restored


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
    return set(_PLACEHOLDER.findall(str(value)))


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
