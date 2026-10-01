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
import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.accessibility.element import element_box

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
    """Normalise a candidate to ``(x, y, weight)`` from a dict or ``[x, y[, w]]``.

    A weight must be finite and not negative; 0 is allowed ("no confidence").
    """
    if isinstance(candidate, dict):
        x, y = float(candidate.get("x", 0)), float(candidate.get("y", 0))
        weight = float(candidate.get("weight", 1.0))
    else:
        seq = list(candidate)
        x, y = float(seq[0]), float(seq[1])
        weight = float(seq[2]) if len(seq) > 2 else 1.0
    if not (math.isfinite(x) and math.isfinite(y)):
        # int(round(inf)) raised OverflowError, and NaN ValueError, from the centroid.
        raise ValueError(f"candidate point must be finite, got ({x!r}, {y!r})")
    if not math.isfinite(weight) or weight < 0:
        raise ValueError(f"candidate weight must be finite and >= 0, got {weight!r}")
    return x, y, weight


def _centroid(cluster: Dict[str, Any]) -> Tuple[float, float]:
    """The weighted centre, or the plain mean while every member weighs 0.

    Dividing by the cluster's weight raised ``ZeroDivisionError`` as soon as a
    zero-weight candidate started a cluster.
    """
    if cluster["w"] > 0:
        return cluster["sx"] / cluster["w"], cluster["sy"] / cluster["w"]
    members = cluster["members"]
    return (sum(mx for mx, _ in members) / len(members),
            sum(my for _, my in members) / len(members))


def _assign(point: Tuple[float, float, float], clusters: List[Dict[str, Any]],
            radius: float) -> bool:
    """Add ``point`` to the first cluster whose centroid is within ``radius``."""
    x, y, weight = point
    for cluster in clusters:
        cx, cy = _centroid(cluster)
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

    ``agreement`` is the winning cluster's weight over the total (its share of
    the candidates when every weight is 0); ``spread`` is the largest member
    distance from its centroid; ``n_clusters`` is how many groups formed.
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
    best = max(clusters, key=lambda c: (c["w"], len(c["members"])))
    cx, cy = _centroid(best)
    spread = max(abs(mx - cx) + abs(my - cy) for mx, my in best["members"])
    agreement = best["w"] / total if total > 0 else len(best["members"]) / len(points)
    return ConsensusResult([int(round(cx)), int(round(cy))],
                           round(agreement, 4), round(spread, 2), len(clusters))


def _center(element: Element) -> Optional[Tuple[float, float]]:
    """The element's centre, or ``None`` without geometry.

    Only ``x/y/width/height`` used to be read: accessibility elements
    (``bounds``) and set-of-marks output (``bbox``) all sat at (0, 0), and the
    first of them won with full agreement.
    """
    box = element_box(element)
    if box is None:
        return None
    left, top, width, height = box
    return left + width / 2.0, top + height / 2.0


def _nearest_index(x: float, y: float, elements: Sequence[Element]) -> Optional[int]:
    """Index of the element whose centre is closest (Manhattan) to ``(x, y)``, or ``None``."""
    best_index, best_distance = None, None
    for index, element in enumerate(elements):
        center = _center(element)
        if center is None:
            continue
        cx, cy = center
        distance = abs(cx - x) + abs(cy - y)
        if best_distance is None or distance < best_distance:
            best_index, best_distance = index, distance
    return best_index


def consensus_element(candidates: Sequence[Candidate],
                      elements: Sequence[Element]
                      ) -> Optional[Tuple[Element, float]]:
    """Vote each candidate point to its nearest element; return ``(winner, agreement)``.

    When every weight is 0 each candidate counts as one vote instead.
    """
    if not elements or not candidates:
        return None
    points = [_xyw(candidate) for candidate in candidates]
    if sum(weight for _, _, weight in points) <= 0:
        points = [(x, y, 1.0) for x, y, _ in points]
    votes = [0.0] * len(elements)
    for x, y, weight in points:
        nearest = _nearest_index(x, y, elements)
        if nearest is None:
            return None                  # no element has geometry to vote for
        votes[nearest] += weight
    best = max(range(len(votes)), key=votes.__getitem__)
    return elements[best], round(votes[best] / sum(votes), 4)


def is_confident(result: Optional[ConsensusResult], *,
                 min_agreement: float = 0.6) -> bool:
    """Return whether a consensus result clears the ``min_agreement`` threshold."""
    return result is not None and result.agreement >= float(min_agreement)
