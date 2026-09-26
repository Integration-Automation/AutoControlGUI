"""Rotation- and scale-tolerant template matching.

``visual_match`` searches a template across *scales* (DPI / zoom tolerance) but
assumes the template is axis-aligned — a control that is rendered at a slight skew,
a rotated icon, or a knob/dial at a different angle is missed because OpenCV's
``matchTemplate`` is not rotation-invariant. This sweeps a set of rotation
*angles* (each warped with ``cv2.warpAffine``) crossed with a scale-space
(``np.linspace`` pyramid), correlates every (scale, angle) candidate and keeps the
best — reporting the winning ``angle`` and ``scale`` so the caller knows the pose.

It reuses ``visual_match``'s grayscale loaders, scale resize, correlation method
table and non-maximum suppression, so no matching or geometry code is duplicated.
The ``haystack`` is injectable (ndarray / path / PIL), so the search is unit-testable
on synthetic arrays; only the default (grab the screen) is device-bound. OpenCV +
NumPy arrive via the project's ``je_open_cv`` dependency and are imported lazily.
Imports no ``PySide6``.
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.visual_match.visual_match import (
    _NMS_CANDIDATE_FACTOR, _NMS_CANDIDATE_MIN, _contain_cv2_error,
    _haystack_gray_with_origin, _method, _nms, _reject_flat_template, _resize,
    _to_gray, _to_screen,
)

ImageSource = Any


@dataclass(frozen=True)
class RotatedMatch:
    """One match with its recovered pose: top-left, size, score, scale, angle."""

    x: int
    y: int
    width: int
    height: int
    score: float
    scale: float
    angle: float

    @property
    def center(self) -> List[int]:
        """The match's centre point ``[x, y]`` (ready to click)."""
        return [self.x + self.width // 2, self.y + self.height // 2]

    def to_dict(self) -> Dict[str, Any]:
        """Return the match as a plain dict including the centre point."""
        data = asdict(self)
        data["center"] = self.center
        return data


def _rotate(template, angle: float):
    """Rotate ``template`` by ``angle`` degrees, expanding the canvas to fit it."""
    import cv2
    if abs(angle) < 1e-9:
        return template
    height, width = template.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, float(angle), 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int(height * sin + width * cos)
    new_h = int(height * cos + width * sin)
    matrix[0, 2] += (new_w / 2.0) - center[0]
    matrix[1, 2] += (new_h / 2.0) - center[1]
    return cv2.warpAffine(template, matrix, (new_w, new_h))


def _rotate_with_mask(template, angle: float):
    """The rotated template and a mask of its real pixels.

    The enlarged canvas is padded with black, and without a mask the black
    corners took part in the correlation: a rotated control on a white
    background scored 0.32 at the wrong place instead of 1.0.
    """
    import numpy as np
    return _rotate(template, angle), _rotate(np.full_like(template, 255), angle)


def scale_space(min_scale: float = 0.8, max_scale: float = 1.25,
                steps: int = 5) -> List[float]:
    """Return ``steps`` evenly spaced scales in ``[min_scale, max_scale]``."""
    import numpy as np
    return [round(float(s), 4)
            for s in np.linspace(float(min_scale), float(max_scale), int(steps))]


def _scores_at(hay, tmpl, scale: float, angle: float, metric: int):
    """The score map (higher is better) for one (scale, angle) and the warped size, or ``None``."""
    import cv2
    import numpy as np
    warped, mask = _rotate_with_mask(_resize(tmpl, float(scale)), float(angle))
    if warped.shape[0] > hay.shape[0] or warped.shape[1] > hay.shape[1]:
        return None
    scores = cv2.matchTemplate(hay, warped, metric, mask=mask)
    if metric == cv2.TM_SQDIFF_NORMED:
        scores = 1.0 - scores  # lower is better for sqdiff; the maximum was the worst spot
    # Masked correlation over a flat window divides by zero.
    return np.nan_to_num(scores, nan=-1.0, posinf=-1.0, neginf=-1.0), warped.shape[1], warped.shape[0]


def _best_at(hay, tmpl, scale: float, angle: float, metric: int):
    """Return the best ``RotatedMatch`` for one (scale, angle), or ``None``."""
    import cv2
    found = _scores_at(hay, tmpl, scale, angle, metric)
    if found is None:
        return None
    scores, width, height = found
    _, max_val, _, max_loc = cv2.minMaxLoc(scores)
    return RotatedMatch(int(max_loc[0]), int(max_loc[1]), width, height,
                        round(float(max_val), 4), float(scale), float(angle))


def _hits_at(hay, tmpl, scale: float, angle: float, metric: int,
             min_score: float, cap: int) -> List[RotatedMatch]:
    """Every position of one (scale, angle) scoring >= ``min_score``, the best ``cap`` of them.

    ``match_rotated_all`` kept only each pose's single peak, so three copies of
    a button on screen came back as one.
    """
    import numpy as np
    found = _scores_at(hay, tmpl, scale, angle, metric)
    if found is None:
        return []
    scores, width, height = found
    ys, xs = np.nonzero(scores >= float(min_score))
    values = scores[ys, xs]
    if values.size > cap:
        top = np.argpartition(values, values.size - cap)[-cap:]
        xs, ys, values = xs[top], ys[top], values[top]
    return [RotatedMatch(int(x), int(y), width, height, round(float(value), 4),
                         float(scale), float(angle)) for x, y, value in zip(xs, ys, values)]


def _sweep(template: ImageSource, haystack: Optional[ImageSource],
           region: Optional[Sequence[int]], scales: Sequence[float],
           angles: Sequence[float], method: str,
           min_score: Optional[float] = None, cap: int = 0) -> List[RotatedMatch]:
    """Correlate every (scale, angle): each pose's best, or with ``min_score`` all its hits."""
    tmpl = _to_gray(template)
    _reject_flat_template(tmpl)
    hay, origin_x, origin_y = _haystack_gray_with_origin(haystack, region)
    metric = _method(method)
    found: List[RotatedMatch] = []
    for scale in scales:
        for angle in angles:
            if min_score is not None:
                found.extend(_hits_at(hay, tmpl, scale, angle, metric, min_score, cap))
                continue
            candidate = _best_at(hay, tmpl, scale, angle, metric)
            if candidate is not None:
                found.append(candidate)
    return [_to_screen(candidate, origin_x, origin_y) for candidate in found]


@_contain_cv2_error
def match_rotated(template: ImageSource, *, haystack: Optional[ImageSource] = None,
                  region: Optional[Sequence[int]] = None,
                  scales: Sequence[float] = (1.0,),
                  angles: Sequence[float] = (0.0,), min_score: float = 0.8,
                  method: str = "ccoeff_normed") -> Optional[RotatedMatch]:
    """Return the single best match over the scale x angle sweep, or ``None``.

    Each angle in ``angles`` (degrees) is applied to the template at each scale in
    ``scales``; the highest-scoring hit at or above ``min_score`` wins, carrying the
    recovered ``scale`` and ``angle``.
    """
    best: Optional[RotatedMatch] = None
    for candidate in _sweep(template, haystack, region, scales, angles, method):
        if candidate.score >= min_score and (best is None
                                             or candidate.score > best.score):
            best = candidate
    return best


@_contain_cv2_error
def match_rotated_all(template: ImageSource, *,
                      haystack: Optional[ImageSource] = None,
                      region: Optional[Sequence[int]] = None,
                      scales: Sequence[float] = (1.0,),
                      angles: Sequence[float] = (0.0,), min_score: float = 0.8,
                      method: str = "ccoeff_normed", max_results: int = 20,
                      nms_iou: float = 0.3) -> List[RotatedMatch]:
    """Return every match >= ``min_score`` over the sweep, overlaps removed (NMS).

    Detections from neighbouring scales / angles that overlap are merged by
    non-maximum suppression (highest score kept), ordered by score and capped at
    ``max_results``.
    """
    cap = max(int(max_results) * _NMS_CANDIDATE_FACTOR, _NMS_CANDIDATE_MIN)
    hits = _sweep(template, haystack, region, scales, angles, method,
                  min_score=float(min_score), cap=cap)
    return _nms(hits, float(nms_iou))[:int(max_results)]
