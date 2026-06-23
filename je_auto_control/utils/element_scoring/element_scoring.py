"""Weighted candidate scoring — rank ambiguous elements by role + name + proximity.

``anchor_locator`` filters by a single spatial relation and sorts by distance, and
``ab_locator`` races *whole strategies* and picks by elapsed time — neither is a
*weighted multi-signal scorer* that ranks ambiguous candidates by combining a role
match, a fuzzy name similarity, proximity to an anchor and enabled-state into one
confidence. That is what self-healing / grounding needs when several boxes could be the
target. The name similarity is injectable (defaulting to the project's ``fuzzy_ratio``),
so no new string-distance code is added.

Pure-stdlib over plain element dicts (``role`` / ``name`` / ``x`` / ``y`` / ``width`` /
``height`` / optional ``enabled``), fully unit-testable. Imports no ``PySide6``.
"""
import math
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from je_auto_control.utils.fuzzy import fuzzy_ratio

Element = Dict[str, Any]


@dataclass(frozen=True)
class ScoredCandidate:
    """One ranked candidate: the element, its 0..1 ``score`` and the per-signal breakdown."""

    element: Element
    score: float
    matched_on: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        """Return the scored candidate as a plain dict."""
        return asdict(self)


def _proximity(element: Element, anchor: Sequence[int]) -> float:
    cx = int(element.get("x", 0)) + int(element.get("width", 0)) // 2
    cy = int(element.get("y", 0)) + int(element.get("height", 0)) // 2
    distance = math.hypot(cx - int(anchor[0]), cy - int(anchor[1]))
    return 1.0 / (1.0 + distance / 100.0)


def score_candidates(candidates: Sequence[Element], *,
                     want_role: Optional[str] = None,
                     want_name: Optional[str] = None,
                     name_similarity: Optional[Callable[[str, str], float]] = None,
                     prefer_enabled: bool = True,
                     anchor: Optional[Sequence[int]] = None
                     ) -> List[ScoredCandidate]:
    """Score and rank ``candidates`` best-first by the supplied signals.

    Each active signal contributes 0..1 and the score is their mean: ``want_role`` (1
    on an exact role match), ``want_name`` (via ``name_similarity``, default
    ``fuzzy_ratio``), ``anchor`` proximity, and ``prefer_enabled``. ``matched_on`` holds
    the per-signal breakdown.
    """
    similarity = name_similarity or fuzzy_ratio
    scored: List[ScoredCandidate] = []
    for element in candidates:
        parts: Dict[str, float] = {}
        if want_role is not None:
            parts["role"] = (1.0 if str(element.get("role", "")).lower()
                             == str(want_role).lower() else 0.0)
        if want_name is not None:
            parts["name"] = float(similarity(want_name,
                                             str(element.get("name", ""))))
        if anchor is not None:
            parts["proximity"] = _proximity(element, anchor)
        if prefer_enabled:
            parts["enabled"] = 1.0 if element.get("enabled", True) else 0.0
        score = sum(parts.values()) / len(parts) if parts else 0.0
        scored.append(ScoredCandidate(element, round(score, 4), parts))
    scored.sort(key=lambda candidate: candidate.score, reverse=True)
    return scored


def best_candidate(candidates: Sequence[Element], *,
                   want_role: Optional[str] = None,
                   want_name: Optional[str] = None,
                   name_similarity: Optional[Callable[[str, str], float]] = None,
                   prefer_enabled: bool = True,
                   anchor: Optional[Sequence[int]] = None
                   ) -> Optional[ScoredCandidate]:
    """Return the single highest-scoring candidate (or ``None`` if there are none)."""
    scored = score_candidates(candidates, want_role=want_role, want_name=want_name,
                              name_similarity=name_similarity,
                              prefer_enabled=prefer_enabled, anchor=anchor)
    return scored[0] if scored else None
