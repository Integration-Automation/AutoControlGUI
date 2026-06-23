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
    _haystack_gray, _method, _nms, _resize, _to_gray,
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


def scale_space(min_scale: float = 0.8, max_scale: float = 1.25,
                steps: int = 5) -> List[float]:
    """Return ``steps`` evenly spaced scales in ``[min_scale, max_scale]``."""
    import numpy as np
    return [round(float(s), 4)
            for s in np.linspace(float(min_scale), float(max_scale), int(steps))]


def _best_at(hay, tmpl, scale: float, angle: float, metric: int):
    """Return the best ``RotatedMatch`` for one (scale, angle), or ``None``."""
    import cv2
    warped = _rotate(_resize(tmpl, float(scale)), float(angle))
    if warped.shape[0] > hay.shape[0] or warped.shape[1] > hay.shape[1]:
        return None
    _, max_val, _, max_loc = cv2.minMaxLoc(cv2.matchTemplate(hay, warped, metric))
    return RotatedMatch(int(max_loc[0]), int(max_loc[1]), warped.shape[1],
                        warped.shape[0], round(float(max_val), 4),
                        float(scale), float(angle))


def _sweep(template: ImageSource, haystack: Optional[ImageSource],
           region: Optional[Sequence[int]], scales: Sequence[float],
           angles: Sequence[float], method: str) -> List[RotatedMatch]:
    """Correlate every (scale, angle) candidate and return them all."""
    tmpl = _to_gray(template)
    hay = _haystack_gray(haystack, region)
    metric = _method(method)
    found: List[RotatedMatch] = []
    for scale in scales:
        for angle in angles:
            candidate = _best_at(hay, tmpl, scale, angle, metric)
            if candidate is not None:
                found.append(candidate)
    return found


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
    hits = [c for c in _sweep(template, haystack, region, scales, angles, method)
            if c.score >= min_score]
    return _nms(hits, float(nms_iou))[:int(max_results)]
