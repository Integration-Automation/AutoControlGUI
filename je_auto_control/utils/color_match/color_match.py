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
from je_auto_control.utils.visual_match.visual_match import (
    Match, _contain_cv2_error, _nms, _resize, _select_candidates,
)

ImageSource = Any
_CHANNEL_INDEX = {"h": 0, "s": 1, "v": 2}
# Saturation from which a template pixel carries colour; below it, hue is noise.
_MIN_SATURATION = 40


def _hsv(source, region, is_haystack: bool):
    import cv2
    if is_haystack:
        rgb = _to_rgb(source) if source is not None else _grab_rgb(region)
    else:
        rgb = _to_rgb(source)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)


def _origin(haystack: Optional[ImageSource], region: Optional[Sequence[int]]):
    """Screen position of the haystack's top-left pixel.

    A grabbed ``region`` (left, top, right, bottom) starts at its corner; a
    supplied haystack is its own space. Matches were region-local, so
    ``AC_match_color``'s ``center`` clicked that far off.
    """
    if haystack is None and region:
        return int(region[0]), int(region[1])
    return 0, 0


def _chromatic_mask(template_hsv):
    """The template pixels that carry colour, or ``None`` when too few do.

    A thin coloured glyph on white is mostly background: scored over every
    pixel, a red cross matched a blank white screen at 0.78.
    """
    import numpy as np
    mask = template_hsv[:, :, 1] >= _MIN_SATURATION
    if int(mask.sum()) < max(1, mask.size // 100):
        return None                  # an achromatic template: every pixel counts
    return mask.astype(np.float32)


def _channel_distance(template, haystack, channel: str, mask=None):
    """Mean squared distance per pixel, scaled to 0..1, for one HSV channel.

    Plain ``TM_SQDIFF`` divided by the largest possible distance -- not
    ``TM_SQDIFF_NORMED``, which divides by the template's own energy: a red
    glyph on white has hue 0 everywhere, so that was 0 / 0 and even an exact
    copy scored as the worst match. Hue is circular (OpenCV's 0..179), so it
    is also compared shifted half-way round and the nearer reading wins:
    hue 1 and hue 179 are both red.
    """
    import cv2
    import numpy as np
    index = _CHANNEL_INDEX[channel]
    t_plane = template[:, :, index].astype(np.float32)
    h_plane = haystack[:, :, index].astype(np.float32)
    pixels = float(mask.sum()) if mask is not None else float(t_plane.size)
    masked = {"mask": mask} if mask is not None else {}
    if channel != "h":
        return cv2.matchTemplate(h_plane, t_plane, cv2.TM_SQDIFF, **masked) / (pixels * 255.0 ** 2)
    direct = cv2.matchTemplate(h_plane, t_plane, cv2.TM_SQDIFF, **masked)
    shifted = cv2.matchTemplate(np.mod(h_plane + 90.0, 180.0),
                                np.mod(t_plane + 90.0, 180.0), cv2.TM_SQDIFF, **masked)
    return np.minimum(direct, shifted) / (pixels * 90.0 ** 2)


def _score_map(template_hsv, haystack_hsv, channels: Sequence[str]):
    """Per-channel colour-distance score (higher = better) over the chosen channels.

    Uses squared distance (not a correlation): correlation methods normalise away the
    *absolute* hue, so a red→green edge and a black→blue edge correlate identically. Squared
    distance keeps the absolute colour, so red is told from green. Score is ``1 -`` the
    root-mean-square distance averaged over the channels, each scaled to 0..1: linear in
    how far the colours are apart, so a hue 30-60 degrees off does not pass as a match.
    """
    import numpy as np
    accumulator = None
    mask = _chromatic_mask(template_hsv)
    for channel in channels:
        result = np.sqrt(np.clip(
            _channel_distance(template_hsv, haystack_hsv, channel, mask), 0.0, 1.0))
        accumulator = result if accumulator is None else accumulator + result
    if accumulator is None:
        raise ValueError("match_color needs at least one channel")
    return 1.0 - accumulator / len(channels)


@_contain_cv2_error
def match_color(template: ImageSource, *, haystack: Optional[ImageSource] = None,
                region: Optional[Sequence[int]] = None,
                channels: Sequence[str] = ("h", "s"),
                scales: Sequence[float] = (1.0,),
                min_score: float = 0.7) -> Optional[Match]:
    """Return the best colour (HSV-channel) match at or above ``min_score``, or ``None``."""
    import cv2
    template_hsv = _hsv(template, None, is_haystack=False)
    haystack_hsv = _hsv(haystack, region, is_haystack=True)
    origin_x, origin_y = _origin(haystack, region)
    best: Optional[Match] = None
    for scale in scales:
        scaled = _resize(template_hsv, float(scale))
        if scaled.shape[0] > haystack_hsv.shape[0] \
                or scaled.shape[1] > haystack_hsv.shape[1]:
            continue
        _, max_val, _, max_loc = cv2.minMaxLoc(
            _score_map(scaled, haystack_hsv, channels))
        if max_val >= min_score and (best is None or max_val > best.score):
            best = Match(int(max_loc[0]) + origin_x, int(max_loc[1]) + origin_y, scaled.shape[1],
                         scaled.shape[0], round(float(max_val), 4), float(scale))
    return best


@_contain_cv2_error
def match_color_all(template: ImageSource, *,
                    haystack: Optional[ImageSource] = None,
                    region: Optional[Sequence[int]] = None,
                    channels: Sequence[str] = ("h", "s"), min_score: float = 0.7,
                    max_results: int = 20, nms_iou: float = 0.3) -> List[Match]:
    """Return every colour match >= ``min_score`` (scale 1.0), overlaps removed (NMS).

    Candidates are capped before NMS as ``match_template_all`` caps them: every
    position above ``min_score`` went into a quadratic NMS, 18 s for a
    320x240 haystack and past five minutes for 640x480.
    """
    template_hsv = _hsv(template, None, is_haystack=False)
    haystack_hsv = _hsv(haystack, region, is_haystack=True)
    if template_hsv.shape[0] > haystack_hsv.shape[0] \
            or template_hsv.shape[1] > haystack_hsv.shape[1]:
        return []
    score_map = _score_map(template_hsv, haystack_hsv, channels)
    height, width = template_hsv.shape[:2]
    candidates = _select_candidates(score_map, float(min_score), width, height,
                                    int(max_results), _origin(haystack, region))
    return _nms(candidates, float(nms_iou))[:int(max_results)]
