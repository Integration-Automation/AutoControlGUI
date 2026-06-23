"""Perceptual (YIQ) image diff with anti-alias edge suppression.

``visual_regression.image_difference`` counts raw per-channel max-delta pixels and
``ssim`` gives a global structural score. Neither uses a *perceptual* colour metric, and
neither ignores **anti-aliased edges** — the #1 source of false-positive visual-diff
failures across DPI / font-hinting. This compares pixels in YIQ space (the pixelmatch
colour metric, far closer to human perception than RGB) and, by default, suppresses the
thin one-pixel edge differences that anti-aliasing produces via a morphological open, so
only *solid* changed regions count.

Runs on an injectable image pair (ndarray / path / PIL), so it is headless-testable on
synthetic arrays. OpenCV + NumPy come in via ``je_open_cv``; reuses the shared
connected-component helper and the RGB loader. Imports no ``PySide6``.
"""
from dataclasses import dataclass
from typing import Any, Dict, List

# Reuse the RGB loader (single source of truth, no copy).
from je_auto_control.utils.color_region.color_region import _to_rgb

ImageSource = Any
_MAX_YIQ_DELTA = 35215.0          # pixelmatch: max possible YIQ delta for 255 diff


@dataclass(frozen=True)
class PerceptualDiffResult:
    """The outcome of a perceptual diff: changed-pixel count, ratio and regions."""

    diff_pixels: int
    total_pixels: int
    diff_ratio: float
    regions: List[Dict[str, Any]]


def _yiq_delta(first, second):
    """Return the per-pixel squared YIQ colour distance between two RGB float images."""
    weights_y = (0.29889531, 0.58662247, 0.11448223)
    weights_i = (0.59597799, -0.27417610, -0.32180189)
    weights_q = (0.21147017, -0.52261711, 0.31114694)

    def channel(image, weights):
        return (image[..., 0] * weights[0] + image[..., 1] * weights[1]
                + image[..., 2] * weights[2])

    delta_y = channel(first, weights_y) - channel(second, weights_y)
    delta_i = channel(first, weights_i) - channel(second, weights_i)
    delta_q = channel(first, weights_q) - channel(second, weights_q)
    return 0.5053 * delta_y ** 2 + 0.299 * delta_i ** 2 + 0.1957 * delta_q ** 2


def perceptual_diff(actual: ImageSource, expected: ImageSource, *,
                    threshold: float = 0.1, include_aa: bool = False,
                    min_area: int = 1) -> PerceptualDiffResult:
    """Compare two images perceptually; return the changed pixels, ratio and regions.

    ``threshold`` (0..1) is the pixelmatch sensitivity — higher tolerates more colour
    difference before a pixel counts as changed. When ``include_aa`` is False (default)
    a morphological open removes thin anti-aliased edge differences so only solid
    changes remain. Different-sized images raise ``ValueError``.
    """
    import cv2
    import numpy as np
    from je_auto_control.utils.cv2_utils.blobs import connected_boxes
    first = _to_rgb(actual).astype(np.float64)
    second = _to_rgb(expected).astype(np.float64)
    if first.shape != second.shape:
        raise ValueError(f"images must be the same size: {first.shape} vs "
                         f"{second.shape}")
    max_delta = _MAX_YIQ_DELTA * float(threshold) * float(threshold)
    mask = (_yiq_delta(first, second) > max_delta).astype(np.uint8)
    if not include_aa:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    diff_pixels = int(np.count_nonzero(mask))
    total = int(mask.size)
    regions = connected_boxes(mask * 255, int(min_area))
    return PerceptualDiffResult(diff_pixels, total,
                                round(diff_pixels / total, 6) if total else 0.0,
                                regions)


def assert_perceptual(actual: ImageSource, expected: ImageSource, *,
                      threshold: float = 0.1, include_aa: bool = False,
                      max_diff_ratio: float = 0.0) -> PerceptualDiffResult:
    """Like :func:`perceptual_diff` but raise when the diff ratio exceeds ``max_diff_ratio``."""
    from je_auto_control.utils.exception.exceptions import (
        AutoControlActionException)
    result = perceptual_diff(actual, expected, threshold=threshold,
                             include_aa=include_aa)
    if result.diff_ratio > float(max_diff_ratio):
        raise AutoControlActionException(
            f"perceptual diff {result.diff_ratio} exceeds {max_diff_ratio} "
            f"({result.diff_pixels} pixels changed)")
    return result
