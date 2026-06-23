"""Sub-pixel refinement of a template match by quadratic peak fitting.

Every matcher (``match_template`` / ``match_rotated`` / ``match_masked``) returns *integer*
pixel coordinates straight from ``cv2.minMaxLoc``. For a drag handle, a fine slider, a
sub-pixel-rendered target, or a high-DPI display, that integer rounding is the dominant
click-placement error. ``subpixel_match`` refines the peak to a fraction of a pixel by fitting
a parabola to the 3x3 score neighbourhood around the integer maximum (the standard NCC
sub-pixel method) — independently on x and y.

It reuses ``visual_match._score_map`` (the full ``matchTemplate`` surface the public matchers
discard); no matching code is duplicated. The ``haystack`` is injectable; the analysis is
unit-testable on synthetic arrays. Imports no ``PySide6``.
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.visual_match.visual_match import _score_map

ImageSource = Any


@dataclass(frozen=True)
class SubPixelMatch:
    """A match whose centre is refined to sub-pixel precision."""

    x: int
    y: int
    width: int
    height: int
    score: float
    cx: float
    cy: float
    offset_x: float
    offset_y: float

    @property
    def center(self) -> List[int]:
        """The integer centre point ``[x, y]`` (top-left + half size)."""
        return [self.x + self.width // 2, self.y + self.height // 2]

    def to_dict(self) -> Dict[str, Any]:
        """Return the match as a plain dict including the integer centre point."""
        data = asdict(self)
        data["center"] = self.center
        return data


def _parabola_offset(low: float, mid: float, high: float) -> float:
    """Sub-sample offset in [-0.5, 0.5] of a peak from its two neighbours' scores."""
    denominator = low - 2.0 * mid + high
    if abs(denominator) < 1e-12:
        return 0.0
    offset = 0.5 * (low - high) / denominator
    return max(-0.5, min(0.5, offset))


def refine_peak(score_map, peak_xy: Tuple[int, int]) -> Tuple[float, float]:
    """Return the sub-pixel ``(offset_x, offset_y)`` of a peak via 3x3 quadratic fit."""
    peak_x, peak_y = int(peak_xy[0]), int(peak_xy[1])
    height, width = score_map.shape
    offset_x = offset_y = 0.0
    if 0 < peak_x < width - 1:
        offset_x = _parabola_offset(float(score_map[peak_y, peak_x - 1]),
                                    float(score_map[peak_y, peak_x]),
                                    float(score_map[peak_y, peak_x + 1]))
    if 0 < peak_y < height - 1:
        offset_y = _parabola_offset(float(score_map[peak_y - 1, peak_x]),
                                    float(score_map[peak_y, peak_x]),
                                    float(score_map[peak_y + 1, peak_x]))
    return offset_x, offset_y


def match_subpixel(template: ImageSource, *, haystack: Optional[ImageSource] = None,
                   region: Optional[Sequence[int]] = None,
                   method: str = "ccoeff_normed",
                   min_score: float = 0.0) -> Optional[SubPixelMatch]:
    """Return the best match with a sub-pixel-refined centre, or ``None``.

    The integer top-left and score come from the correlation peak; ``cx`` / ``cy`` add the
    quadratic-fit offset to the integer centre for fractional-pixel click placement.
    """
    import cv2
    score_map, tmpl = _score_map(template, haystack, region=region, method=method)
    if score_map is None:
        return None
    _, max_val, _, max_loc = cv2.minMaxLoc(score_map)
    if max_val < min_score:
        return None
    peak_x, peak_y = int(max_loc[0]), int(max_loc[1])
    offset_x, offset_y = refine_peak(score_map, (peak_x, peak_y))
    height, width = tmpl.shape[:2]
    return SubPixelMatch(peak_x, peak_y, width, height, round(float(max_val), 4),
                         round(peak_x + width / 2.0 + offset_x, 3),
                         round(peak_y + height / 2.0 + offset_y, 3),
                         round(offset_x, 4), round(offset_y, 4))
