"""Colour-histogram fingerprint & change detection — "is this the same view?".

``image_dedup`` fingerprints with a perceptual aHash/dHash (a *spatial* 64-bit hash,
brittle to colour / theme shifts) and ``color_stats`` reports a single average /
dominant colour. A normalized colour *histogram* is the standard illumination- and
scale-robust signal for "is this the same view, or has the palette shifted" — a theme
switch, a content reload, a rotated ad — which neither hashing nor one dominant colour
captures.

Every function runs on an injectable image (ndarray / path / PIL, RGB) so it is
headless-testable on synthetic arrays. ``cv2.calcHist`` / ``cv2.compareHist`` are base
OpenCV; OpenCV + NumPy come in via ``je_open_cv``. Imports no ``PySide6``.
"""
from typing import Any, List, Optional, Sequence

# Reuse the RGB loader / screen grab (single source of truth, no copy).
from je_auto_control.utils.color_region.color_region import _grab_rgb, _to_rgb

ImageSource = Any
_SIMILARITY_METHODS = ("correlation", "intersection")


def _convert(rgb, space: str):
    import cv2
    if space == "hsv":
        return (cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV),
                [[0, 180], [0, 256], [0, 256]])
    if space == "rgb":
        return rgb, [[0, 256], [0, 256], [0, 256]]
    if space == "gray":
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), [[0, 256]]
    raise ValueError(f"unknown space: {space!r}")


def image_histogram(haystack: Optional[ImageSource] = None, *,
                    region: Optional[Sequence[int]] = None, bins: int = 32,
                    space: str = "hsv") -> List[float]:
    """Return a per-channel normalized colour histogram as a flat list of floats.

    ``space`` is ``hsv`` / ``rgb`` / ``gray``; each channel contributes ``bins``
    values (so HSV/RGB give ``3 * bins``). ``haystack`` defaults to a screen grab of
    the optional ``region``.
    """
    import cv2
    rgb = _to_rgb(haystack) if haystack is not None else _grab_rgb(region)
    image, ranges = _convert(rgb, space)
    channels = 1 if image.ndim == 2 else image.shape[2]
    out: List[float] = []
    for channel in range(channels):
        hist = cv2.calcHist([image], [channel], None, [int(bins)], ranges[channel])
        cv2.normalize(hist, hist, 0.0, 1.0, cv2.NORM_MINMAX)
        out.extend(float(value) for value in hist.flatten())
    return out


def compare_histograms(hist_a: Sequence[float], hist_b: Sequence[float], *,
                       method: str = "correlation") -> float:
    """Compare two histograms. ``method``: correlation / chisqr / intersection / bhattacharyya.

    For correlation / intersection higher means more similar; for chisqr /
    bhattacharyya higher means more different.
    """
    import cv2
    import numpy as np
    methods = {"correlation": cv2.HISTCMP_CORREL,
               "chisqr": cv2.HISTCMP_CHISQR,
               "intersection": cv2.HISTCMP_INTERSECT,
               "bhattacharyya": cv2.HISTCMP_BHATTACHARYYA}
    if method not in methods:
        raise ValueError(f"unknown method: {method!r}")
    array_a = np.asarray(hist_a, dtype=np.float32)
    array_b = np.asarray(hist_b, dtype=np.float32)
    return round(float(cv2.compareHist(array_a, array_b, methods[method])), 4)


def histogram_changed(reference: ImageSource,
                      current: Optional[ImageSource] = None, *,
                      region: Optional[Sequence[int]] = None,
                      method: str = "correlation", threshold: float = 0.9,
                      space: str = "hsv") -> bool:
    """Return whether ``current`` (default: screen) differs from ``reference``.

    Compares their histograms with ``method``; for similarity methods (correlation /
    intersection) it is "changed" when the score drops below ``threshold``, for
    distance methods (chisqr / bhattacharyya) when it rises above ``threshold``.
    """
    reference_hist = image_histogram(reference, space=space)
    current_hist = (image_histogram(current, space=space) if current is not None
                    else image_histogram(region=region, space=space))
    score = compare_histograms(reference_hist, current_hist, method=method)
    if method in _SIMILARITY_METHODS:
        return score < float(threshold)
    return score > float(threshold)
