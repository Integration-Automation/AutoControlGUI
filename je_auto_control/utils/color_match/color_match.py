"""Colour-aware template matching on HSV channels.

Every matcher in ``visual_match`` converts to grayscale first, so a red versus green status
indicator of identical shape is *indistinguishable* to ``match_template`` — the discriminating
signal is thrown away. ``color_region`` finds blobs of a *known* colour but cannot template-match
a multi-colour glyph by appearance. ``color_match`` correlates on the HSV hue / saturation
channels (hue is illumination-invariant), so it locates colour-discriminated targets — a
coloured chip, a syntax-highlighted token, a status light with structure — that grayscale
matching collapses.

It reuses ``color_region``'s RGB loaders and ``visual_match``'s resize / NMS / ``Match`` (no new
image or matching code). The ``haystack`` is injectable; the search is unit-testable on synthetic
arrays. OpenCV + NumPy are imported lazily. Imports no ``PySide6``.

Note: like any NCC, a *flat* single-colour patch has no per-channel variance to correlate; for
solid colour blobs use ``color_region``. ``color_match`` is for targets with colour *structure*.
"""
from typing import Any, List, Optional, Sequence

from je_auto_control.utils.color_region.color_region import _grab_rgb, _to_rgb
from je_auto_control.utils.visual_match.visual_match import Match, _nms, _resize

ImageSource = Any
_CHANNEL_INDEX = {"h": 0, "s": 1, "v": 2}


def _hsv(source, region, is_haystack: bool):
    import cv2
    if is_haystack:
        rgb = _to_rgb(source) if source is not None else _grab_rgb(region)
    else:
        rgb = _to_rgb(source)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)


def _score_map(template_hsv, haystack_hsv, channels: Sequence[str]):
    """Per-channel colour-distance score (higher = better) over the chosen channels.

    Uses ``TM_SQDIFF_NORMED`` (not a correlation): correlation methods normalise away the
    *absolute* hue, so a red→green edge and a black→blue edge correlate identically. Squared
    distance keeps the absolute colour, so red is told from green. Score is ``1 - mean(sqdiff)``;
    a flat channel (no variance, sqdiff undefined) contributes the worst score.
    """
    import cv2
    import numpy as np
    accumulator = None
    for channel in channels:
        index = _CHANNEL_INDEX[channel]
        result = cv2.matchTemplate(haystack_hsv[:, :, index],
                                   template_hsv[:, :, index], cv2.TM_SQDIFF_NORMED)
        result = np.nan_to_num(result, nan=1.0, posinf=1.0)
        accumulator = result if accumulator is None else accumulator + result
    if accumulator is None:
        raise ValueError("match_color needs at least one channel")
    return 1.0 - accumulator / len(channels)


def match_color(template: ImageSource, *, haystack: Optional[ImageSource] = None,
                region: Optional[Sequence[int]] = None,
                channels: Sequence[str] = ("h", "s"),
                scales: Sequence[float] = (1.0,),
                min_score: float = 0.7) -> Optional[Match]:
    """Return the best colour (HSV-channel) match at or above ``min_score``, or ``None``."""
    import cv2
    template_hsv = _hsv(template, None, is_haystack=False)
    haystack_hsv = _hsv(haystack, region, is_haystack=True)
    best: Optional[Match] = None
    for scale in scales:
        scaled = _resize(template_hsv, float(scale))
        if scaled.shape[0] > haystack_hsv.shape[0] \
                or scaled.shape[1] > haystack_hsv.shape[1]:
            continue
        _, max_val, _, max_loc = cv2.minMaxLoc(
            _score_map(scaled, haystack_hsv, channels))
        if max_val >= min_score and (best is None or max_val > best.score):
            best = Match(int(max_loc[0]), int(max_loc[1]), scaled.shape[1],
                         scaled.shape[0], round(float(max_val), 4), float(scale))
    return best


def match_color_all(template: ImageSource, *,
                    haystack: Optional[ImageSource] = None,
                    region: Optional[Sequence[int]] = None,
                    channels: Sequence[str] = ("h", "s"), min_score: float = 0.7,
                    max_results: int = 20, nms_iou: float = 0.3) -> List[Match]:
    """Return every colour match >= ``min_score`` (scale 1.0), overlaps removed (NMS)."""
    import numpy as np
    template_hsv = _hsv(template, None, is_haystack=False)
    haystack_hsv = _hsv(haystack, region, is_haystack=True)
    if template_hsv.shape[0] > haystack_hsv.shape[0] \
            or template_hsv.shape[1] > haystack_hsv.shape[1]:
        return []
    score_map = _score_map(template_hsv, haystack_hsv, channels)
    height, width = template_hsv.shape[:2]
    ys, xs = np.nonzero(score_map >= float(min_score))
    candidates = [Match(int(x), int(y), width, height,
                        round(float(score_map[y, x]), 4), 1.0)
                  for y, x in zip(ys, xs)]
    return _nms(candidates, float(nms_iou))[:int(max_results)]
