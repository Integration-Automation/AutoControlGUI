"""Self-consistency over multiple grounding proposals for one target.

A target can be grounded several ways at once — set-of-marks, OCR, template match, the a11y
tree, or N samples from a model — and they don't always agree. ``ab_locator`` /
``element_scoring`` rank locator *strategies* by historical reliability but never fuse
*simultaneous* proposals into one consensus point with a dispersion metric, and
``action_grounding.snap_to_element`` snaps a *single* coordinate to the nearest element with no
notion of disagreement. ``grounding_consensus`` clusters the candidate points (or votes
candidate elements), returns the agreed target plus an *agreement* fraction and *spread*, and
flags low-agreement targets so the caller can zoom / ask a human instead of clicking blind.

Pure-stdlib geometry; deterministic and unit-testable with no device. Imports no ``PySide6``.
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

Candidate = Any
Element = Dict[str, Any]


@dataclass(frozen=True)
class ConsensusResult:
    """The agreed target point plus its agreement fraction, spread and cluster count."""

    point: List[int]
    agreement: float
    spread: float
    n_clusters: int

    def to_dict(self) -> Dict[str, Any]:
        """Return the result as a plain dict."""
        return asdict(self)


def _xyw(candidate: Candidate) -> Tuple[float, float, float]:
    """Normalise a candidate to ``(x, y, weight)`` from a dict or ``[x, y[, w]]``."""
    if isinstance(candidate, dict):
        return (float(candidate.get("x", 0)), float(candidate.get("y", 0)),
                float(candidate.get("weight", 1.0)))
    seq = list(candidate)
    return float(seq[0]), float(seq[1]), float(seq[2]) if len(seq) > 2 else 1.0


def _assign(point: Tuple[float, float, float], clusters: List[Dict[str, Any]],
            radius: float) -> bool:
    """Add ``point`` to the first cluster whose centroid is within ``radius``."""
    x, y, weight = point
    for cluster in clusters:
        cx, cy = cluster["sx"] / cluster["w"], cluster["sy"] / cluster["w"]
        if abs(x - cx) <= radius and abs(y - cy) <= radius:
            cluster["sx"] += x * weight
            cluster["sy"] += y * weight
            cluster["w"] += weight
            cluster["members"].append((x, y))
            return True
    return False


def consensus_point(candidates: Sequence[Candidate], *,
                    cluster_radius: float = 24) -> Optional[ConsensusResult]:
    """Cluster candidate points and return the agreed target, or ``None`` if empty.

    ``agreement`` is the winning cluster's weight over the total; ``spread`` is the
    largest member distance from its centroid; ``n_clusters`` is how many groups formed.
    """
    points = [_xyw(c) for c in candidates]
    if not points:
        return None
    total = sum(weight for _, _, weight in points)
    clusters: List[Dict[str, Any]] = []
    for point in points:
        if not _assign(point, clusters, float(cluster_radius)):
            x, y, weight = point
            clusters.append({"sx": x * weight, "sy": y * weight, "w": weight,
                             "members": [(x, y)]})
    best = max(clusters, key=lambda c: c["w"])
    cx, cy = best["sx"] / best["w"], best["sy"] / best["w"]
    spread = max(abs(mx - cx) + abs(my - cy) for mx, my in best["members"])
    return ConsensusResult([int(round(cx)), int(round(cy))],
                           round(best["w"] / total, 4), round(spread, 2),
                           len(clusters))


def _center(element: Element) -> Tuple[float, float]:
    return (float(element.get("x", 0)) + float(element.get("width", 0)) / 2.0,
            float(element.get("y", 0)) + float(element.get("height", 0)) / 2.0)


def _nearest_index(x: float, y: float, elements: Sequence[Element]) -> int:
    """Index of the element whose centre is closest (Manhattan) to ``(x, y)``."""
    best_index, best_distance = 0, None
    for index, element in enumerate(elements):
        cx, cy = _center(element)
        distance = abs(cx - x) + abs(cy - y)
        if best_distance is None or distance < best_distance:
            best_index, best_distance = index, distance
    return best_index


def consensus_element(candidates: Sequence[Candidate],
                      elements: Sequence[Element]
                      ) -> Optional[Tuple[Element, float]]:
    """Vote each candidate point to its nearest element; return ``(winner, agreement)``."""
    if not elements or not candidates:
        return None
    votes = [0.0] * len(elements)
    total = 0.0
    for candidate in candidates:
        x, y, weight = _xyw(candidate)
        votes[_nearest_index(x, y, elements)] += weight
        total += weight
    best = max(range(len(votes)), key=votes.__getitem__)
    return elements[best], round(votes[best] / total, 4)


def is_confident(result: Optional[ConsensusResult], *,
                 min_agreement: float = 0.6) -> bool:
    """Return whether a consensus result clears the ``min_agreement`` threshold."""
    return result is not None and result.agreement >= float(min_agreement)
