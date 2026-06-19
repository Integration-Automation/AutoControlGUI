"""Fuzzy string matching for noisy automation text (OCR labels, table cells).

Exact string comparison is brittle when text comes from OCR or shifting UI
copy. These helpers score similarity, pick the best candidate from a list, and
collapse near-duplicates. The default backend is the standard library
``difflib`` (so the feature works with **zero** extra dependencies); if the
optional ``rapidfuzz`` package is installed it is used instead for speed — the
scores are normalised to ``0.0..1.0`` either way, so callers don't care which
backend ran. :data:`BACKEND` names the active one.

Pure Python; imports no ``PySide6``.
"""
from typing import Any, List, Optional, Sequence, Tuple

try:  # optional acceleration; the difflib fallback is always correct
    from rapidfuzz import fuzz as _rf

    BACKEND = "rapidfuzz"

    def _similarity(left: str, right: str) -> float:
        return _rf.ratio(left, right) / 100.0
except ImportError:  # pragma: no cover - exercised wherever rapidfuzz is absent
    from difflib import SequenceMatcher

    BACKEND = "difflib"

    def _similarity(left: str, right: str) -> float:
        return SequenceMatcher(None, left, right).ratio()


def _prepare(value: Any, ignore_case: bool) -> str:
    text = str(value)
    return text.lower() if ignore_case else text


def fuzzy_ratio(left: Any, right: Any, *, ignore_case: bool = True) -> float:
    """Return a similarity score in ``0.0..1.0`` for two values."""
    return _similarity(_prepare(left, ignore_case),
                       _prepare(right, ignore_case))


def fuzzy_matches(query: Any, choices: Sequence[Any], *, limit: int = 5,
                  score_cutoff: float = 0.0, ignore_case: bool = True
                  ) -> List[Tuple[Any, float, int]]:
    """Return up to ``limit`` ``(choice, score, index)`` tuples, best first.

    Only choices scoring at least ``score_cutoff`` are returned.
    """
    prepared_query = _prepare(query, ignore_case)
    scored = [
        (choice, _similarity(prepared_query, _prepare(choice, ignore_case)),
         index)
        for index, choice in enumerate(choices)
    ]
    scored = [item for item in scored if item[1] >= score_cutoff]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit] if limit >= 0 else scored


def fuzzy_best_match(query: Any, choices: Sequence[Any], *,
                     score_cutoff: float = 0.0, ignore_case: bool = True
                     ) -> Optional[Tuple[Any, float, int]]:
    """Return the single best ``(choice, score, index)`` or ``None``."""
    ranked = fuzzy_matches(query, choices, limit=1, score_cutoff=score_cutoff,
                           ignore_case=ignore_case)
    return ranked[0] if ranked else None


def fuzzy_dedupe(items: Sequence[Any], *, threshold: float = 0.9,
                 ignore_case: bool = True) -> List[Any]:
    """Collapse near-duplicate items, keeping the first of each cluster.

    An item is dropped when it scores at least ``threshold`` against an item
    already kept.
    """
    kept: List[Any] = []
    kept_prepared: List[str] = []
    for item in items:
        prepared = _prepare(item, ignore_case)
        if any(_similarity(prepared, seen) >= threshold
               for seen in kept_prepared):
            continue
        kept.append(item)
        kept_prepared.append(prepared)
    return kept
