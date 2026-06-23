"""Multi-template consensus matching (vote several references onto one location).

A button often renders in several states — default / hover / pressed / disabled — yet it is a
single logical target. ``ab_locator`` A/B-tests *which single strategy wins* and
``match_template(scales=...)`` sweeps *one* template across scales — neither fuses *multiple
reference crops* into one vote. ``match_ensemble`` matches each reference, clusters the hit
centres and accepts a target only when at least ``min_votes`` references agree within
``agree_px`` — sharply cutting false positives on themed / animated UI.

The voting core (``vote_centers``) is pure-stdlib and reuses ``grounding_consensus`` for the
clustering, so it is unit-testable with no image; only ``match_ensemble`` itself calls
``visual_match.match_template`` (and is testable on a synthetic injected ``haystack``). Imports
no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence

ImageSource = Any


def vote_centers(centers: Sequence[Sequence[int]], *, agree_px: float = 10,
                 min_votes: int = 2) -> Optional[Dict[str, Any]]:
    """Cluster candidate hit centres and return the agreed target if enough agree.

    Returns ``{point, votes, n_candidates, spread}`` for the largest cluster, or ``None``
    when fewer than ``min_votes`` candidates fall within ``agree_px`` of each other.
    """
    from je_auto_control.utils.grounding_consensus import consensus_point
    result = consensus_point(centers, cluster_radius=float(agree_px))
    if result is None:
        return None
    votes = round(result.agreement * len(centers))
    if votes < int(min_votes):
        return None
    return {"point": result.point, "votes": votes,
            "n_candidates": len(centers), "spread": result.spread}


def match_ensemble(templates: Sequence[ImageSource], *,
                   haystack: Optional[ImageSource] = None,
                   region: Optional[Sequence[int]] = None,
                   scales: Sequence[float] = (1.0,), min_score: float = 0.8,
                   agree_px: float = 10, min_votes: int = 2
                   ) -> Optional[Dict[str, Any]]:
    """Match each reference in ``templates`` and return their voted consensus target.

    Each template is located with ``visual_match.match_template``; the hit centres are then
    fused by :func:`vote_centers`. Returns ``{point, votes, n_candidates, spread}`` or
    ``None`` if too few references agree.
    """
    from je_auto_control.utils.visual_match import match_template
    centers: List[List[int]] = []
    for template in templates:
        match = match_template(template, haystack=haystack, region=region,
                               scales=tuple(scales), min_score=float(min_score))
        if match is not None:
            centers.append(match.center)
    return vote_centers(centers, agree_px=agree_px, min_votes=min_votes)
