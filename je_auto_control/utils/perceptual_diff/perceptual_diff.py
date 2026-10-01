"""Perceptual (YIQ) image diff with anti-alias edge suppression.

``visual_regression.image_difference`` counts raw per-channel max-delta pixels and
``ssim`` gives a global structural score. Neither uses a *perceptual* colour metric, and
neither ignores **anti-aliased edges** — the #1 source of false-positive visual-diff
failures across DPI / font-hinting. This compares pixels in YIQ space (the pixelmatch
colour metric, far closer to human perception than RGB) and, by default, discounts the
pixels pixelmatch's ``antialiased()`` test classifies as anti-aliasing: a pixel between a
darker and a brighter neighbour, next to a flat area in both images. A thin changed stroke
-- edited small text, a 1 px rule -- still counts. (A morphological open used to stand in
for that test and erased every change narrower than 3 px.)

Runs on an injectable image pair (ndarray / path / PIL), so it is headless-testable on
synthetic arrays. OpenCV + NumPy come in via ``je_open_cv``; reuses the shared
connected-component helper and the RGB loader. Imports no ``PySide6``.
"""
from dataclasses import dataclass
from typing import Any, Dict, List

# Reuse the RGB loader (single source of truth, no copy).
from je_auto_control.utils.color_region.color_region import _to_rgb
from je_auto_control.utils.visual_match.visual_match import _contain_cv2_error

ImageSource = Any
_MAX_YIQ_DELTA = 35215.0          # pixelmatch: max possible YIQ delta for 255 diff
_LUMA = (0.29889531, 0.58662247, 0.11448223)
#: The eight neighbours as (dx, dy), in pixelmatch's scan order (x outer, y
#: inner) so ties between equally dark or bright neighbours resolve the same way.
_NEIGHBOURS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


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


#: Candidate pixels examined per batch, which bounds the per-pixel arrays.
_CHUNK = 1 << 18


def _padded(image):
    """``image`` with a one-pixel NaN border, so neighbours off the edge compare unequal."""
    import numpy as np
    pad = ((1, 1), (1, 1)) + ((0, 0),) * (image.ndim - 2)
    return np.pad(image, pad, constant_values=np.nan)


def _sibling_map(image):
    """pixelmatch ``hasManySiblings`` for every pixel: 3+ identical neighbours.

    A pixel on the border starts its count at one, as in pixelmatch.
    """
    import numpy as np
    height, width = image.shape[:2]
    padded = _padded(image)
    count = np.zeros((height, width), dtype=np.int8)
    count[0, :] = count[-1, :] = count[:, 0] = count[:, -1] = 1
    for dx, dy in _NEIGHBOURS:
        count += np.all(padded[1 + dy:1 + dy + height, 1 + dx:1 + dx + width] == image, axis=-1)
    return count > 2


class _Image:
    """What the anti-aliasing test needs of one image, computed once.

    Siblings are looked up point by point for a few candidate pixels, and
    mapped for the whole frame once many pixels differ (cheaper per point).
    """

    def __init__(self, rgb, whole_frame: bool) -> None:
        import numpy as np
        self.shape = rgb.shape[:2]
        self.luma = _padded(rgb @ np.array(_LUMA))
        self._rgb: Any = None if whole_frame else _padded(rgb)
        self._map: Any = _sibling_map(rgb) if whole_frame else None

    def many_siblings(self, ys, xs):
        """pixelmatch ``hasManySiblings`` at the pixels ``(ys, xs)``."""
        import numpy as np
        if self._map is not None:
            return self._map[ys, xs]
        height, width = self.shape
        centre = self._rgb[ys + 1, xs + 1]
        count = ((xs == 0) | (xs == width - 1) | (ys == 0) | (ys == height - 1)).astype(int)
        for dx, dy in _NEIGHBOURS:
            count += np.all(self._rgb[ys + 1 + dy, xs + 1 + dx] == centre, axis=-1)
        return count > 2


def _antialiased(image: _Image, other: _Image, ys, xs):
    """pixelmatch ``antialiased()`` for the pixels ``(ys, xs)`` of ``image``.

    True where the pixel has at most two equal-brightness neighbours, both a
    darker and a brighter one, and the darkest or the brightest of those sits
    in a flat area (3+ identical neighbours) of both images.
    """
    import numpy as np
    height, width = image.shape
    offsets = np.array(_NEIGHBOURS)
    centre = image.luma[ys + 1, xs + 1]
    deltas = np.stack([centre - image.luma[ys + 1 + dy, xs + 1 + dx]
                       for dx, dy in _NEIGHBOURS], axis=1)
    edge = (xs == 0) | (xs == width - 1) | (ys == 0) | (ys == height - 1)
    zeroes = edge.astype(int) + np.count_nonzero(deltas == 0, axis=1)
    darker = np.where(deltas < 0, deltas, np.inf)
    brighter = np.where(deltas > 0, deltas, -np.inf)
    candidate = ((zeroes <= 2) & np.isfinite(darker.min(axis=1))
                 & np.isfinite(brighter.max(axis=1)))
    flat = np.zeros(len(ys), dtype=bool)
    for extreme in (darker.argmin(axis=1), brighter.argmax(axis=1)):
        ny = np.clip(ys + offsets[extreme, 1], 0, height - 1)
        nx = np.clip(xs + offsets[extreme, 0], 0, width - 1)
        flat |= image.many_siblings(ny, nx) & other.many_siblings(ny, nx)
    return candidate & flat


def _drop_antialiased(mask, first, second) -> None:
    """Clear the pixels of ``mask`` that either image renders as anti-aliasing."""
    import numpy as np
    ys, xs = np.nonzero(mask)
    whole_frame = len(ys) * 8 > mask.size
    one, two = _Image(first, whole_frame), _Image(second, whole_frame)
    for start in range(0, len(ys), _CHUNK):
        y, x = ys[start:start + _CHUNK], xs[start:start + _CHUNK]
        aa = _antialiased(one, two, y, x) | _antialiased(two, one, y, x)
        mask[y[aa], x[aa]] = 0


@_contain_cv2_error
def perceptual_diff(actual: ImageSource, expected: ImageSource, *,
                    threshold: float = 0.1, include_aa: bool = False,
                    min_area: int = 1) -> PerceptualDiffResult:
    """Compare two images perceptually; return the changed pixels, ratio and regions.

    ``threshold`` (0..1) is the pixelmatch sensitivity — higher tolerates more colour
    difference before a pixel counts as changed. When ``include_aa`` is False (default)
    pixels pixelmatch classifies as anti-aliasing are not counted. Different-sized
    images raise ``ValueError``.
    """
    import numpy as np
    from je_auto_control.utils.cv2_utils.blobs import connected_boxes
    first = _to_rgb(actual).astype(np.float64)
    second = _to_rgb(expected).astype(np.float64)
    if first.shape != second.shape:
        raise ValueError(f"images must be the same size: {first.shape} vs "
                         f"{second.shape}")
    max_delta = _MAX_YIQ_DELTA * float(threshold) * float(threshold)
    mask = (_yiq_delta(first, second) > max_delta).astype(np.uint8)
    if not include_aa and mask.any():
        _drop_antialiased(mask, first, second)
    diff_pixels = int(np.count_nonzero(mask))
    total = int(mask.size)
    regions = connected_boxes(mask * 255, int(min_area))
    return PerceptualDiffResult(diff_pixels, total,
                                round(diff_pixels / total, 6) if total else 0.0,
                                regions)


@_contain_cv2_error
def assert_perceptual(actual: ImageSource, expected: ImageSource, *,
                      threshold: float = 0.1, include_aa: bool = False,
                      max_diff_ratio: float = 0.0) -> PerceptualDiffResult:
    """Like :func:`perceptual_diff` but raise when the diff ratio exceeds ``max_diff_ratio``."""
    from je_auto_control.utils.exception.exceptions import (
        AutoControlActionException)
    result = perceptual_diff(actual, expected, threshold=threshold,
                             include_aa=include_aa)
    # Unrounded: diff_ratio has six decimals, so one changed pixel in a 1080p
    # frame (and up to four at 4K) read 0.0 and passed a zero budget.
    exact = result.diff_pixels / result.total_pixels if result.total_pixels else 0.0
    if exact > float(max_diff_ratio):
        raise AutoControlActionException(
            f"perceptual diff {exact:.3g} exceeds {max_diff_ratio} "
            f"({result.diff_pixels} pixels changed)")
    return result
