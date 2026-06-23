"""Edge-shape (Chamfer / distance-transform) template matching.

Intensity correlation (``visual_match``) is dragged down when the same control is rendered
with a different fill, gradient, theme or anti-aliasing, and ORB feature matching
(``feature_match``) needs corner texture that flat-design glyphs — a hamburger menu, a plain
chevron — simply do not have. ``edge_match`` locates a template by its *edge shape* instead:
it runs Canny on both images, builds a distance transform of the scene edges, and slides the
template's edges over it, scoring each position by the mean distance from a template edge to
the nearest scene edge (Chamfer matching). A perfect alignment costs ~0 regardless of how the
shape is filled or shaded.

It reuses ``visual_match``'s gray loaders / resize / NMS / ``Match`` and ``edge_lines``'s Canny
default, so no matching or geometry code is duplicated. The ``haystack`` is injectable
(ndarray / path / PIL); the search is unit-testable on synthetic arrays. OpenCV + NumPy are
imported lazily. Imports no ``PySide6``.
"""
from typing import Any, List, Optional, Sequence, Tuple

from je_auto_control.utils.visual_match.visual_match import (
    Match, _haystack_gray, _nms, _resize, _to_gray,
)

ImageSource = Any
_DEFAULT_CANNY = (50, 150)


def _edges(gray, canny: Sequence[int]):
    import cv2
    return cv2.Canny(gray, int(canny[0]), int(canny[1]))


def _chamfer_score_map(template_gray, scene_gray, canny: Sequence[int]):
    """Return ``(score_map, (w, h))`` where higher = better edge alignment, or ``(None, _)``."""
    import cv2
    import numpy as np
    scene_edges = _edges(scene_gray, canny)
    template_edges = _edges(template_gray, canny)
    edge_count = int(np.count_nonzero(template_edges))
    if edge_count == 0 or template_edges.shape[0] > scene_edges.shape[0] \
            or template_edges.shape[1] > scene_edges.shape[1]:
        return None, (0, 0)
    distance = cv2.distanceTransform(cv2.bitwise_not(scene_edges),
                                     cv2.DIST_L2, 3).astype(np.float32)
    mask = (template_edges > 0).astype(np.float32)
    total = cv2.matchTemplate(distance, mask, cv2.TM_CCORR)
    score_map = 1.0 / (1.0 + total / edge_count)
    return score_map, (template_edges.shape[1], template_edges.shape[0])


def _best(score_map, size: Tuple[int, int], scale: float, min_score: float,
          current: Optional[Match]) -> Optional[Match]:
    import cv2
    _, max_val, _, max_loc = cv2.minMaxLoc(score_map)
    if max_val >= min_score and (current is None or max_val > current.score):
        return Match(int(max_loc[0]), int(max_loc[1]), size[0], size[1],
                     round(float(max_val), 4), float(scale))
    return current


def edge_match(template: ImageSource, *, haystack: Optional[ImageSource] = None,
               region: Optional[Sequence[int]] = None,
               scales: Sequence[float] = (1.0,),
               canny: Sequence[int] = _DEFAULT_CANNY,
               min_score: float = 0.7) -> Optional[Match]:
    """Return the best edge-shape (Chamfer) match at or above ``min_score``, or ``None``."""
    template_gray = _to_gray(template)
    scene_gray = _haystack_gray(haystack, region)
    best: Optional[Match] = None
    for scale in scales:
        score_map, size = _chamfer_score_map(_resize(template_gray, float(scale)),
                                             scene_gray, canny)
        if score_map is not None:
            best = _best(score_map, size, float(scale), float(min_score), best)
    return best


def edge_match_all(template: ImageSource, *,
                   haystack: Optional[ImageSource] = None,
                   region: Optional[Sequence[int]] = None,
                   canny: Sequence[int] = _DEFAULT_CANNY, min_score: float = 0.7,
                   max_results: int = 20, nms_iou: float = 0.3) -> List[Match]:
    """Return every edge-shape match >= ``min_score`` (scale 1.0), overlaps removed (NMS)."""
    import numpy as np
    score_map, size = _chamfer_score_map(_to_gray(template),
                                         _haystack_gray(haystack, region), canny)
    if score_map is None:
        return []
    ys, xs = np.nonzero(score_map >= float(min_score))
    candidates = [Match(int(x), int(y), size[0], size[1],
                        round(float(score_map[y, x]), 4), 1.0)
                  for y, x in zip(ys, xs)]
    return _nms(candidates, float(nms_iou))[:int(max_results)]


def chamfer_distance(template: ImageSource, *,
                     haystack: Optional[ImageSource] = None,
                     region: Optional[Sequence[int]] = None,
                     canny: Sequence[int] = _DEFAULT_CANNY) -> float:
    """Return the mean edge-to-edge distance at the best alignment (0 = perfect)."""
    import cv2
    score_map, _ = _chamfer_score_map(_to_gray(template),
                                      _haystack_gray(haystack, region), canny)
    if score_map is None:
        return float("inf")
    _, max_val, _, _ = cv2.minMaxLoc(score_map)
    return round(1.0 / max_val - 1.0, 4) if max_val > 0 else float("inf")
