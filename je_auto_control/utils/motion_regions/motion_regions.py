"""Localized change / activity detection between two frames (cheap absdiff).

Three near-neighbours, all distinct: ``wait_until_screen_stable`` returns a *boolean*
over a live poll loop (not localized boxes on an injectable pair); ``ssim_changed_regions``
is *structural* (Gaussian-windowed SSIM, illumination-tolerant — deliberately ignores
the fast pixel motion you'd want for "where is the spinner / video / animation");
``diff_screenshots`` highlights pixel diffs but is not framed as activity blobs with a
score. This is the cheap absdiff path: which sub-regions are *moving* right now, so a
script can pick a quiet region or locate a busy spinner.

Operates on two injectable frames (ndarray / path / PIL), so it is headless-testable on
synthetic arrays. OpenCV + NumPy come in via ``je_open_cv``; reuses the shared
connected-component helper. Imports no ``PySide6``.
"""
from typing import Any, Dict, List

from je_auto_control.utils.visual_match.visual_match import _to_gray

ImageSource = Any


def _diff_mask(before: ImageSource, after: ImageSource, threshold: int, blur: int):
    """Return the binary motion mask between two frames (same size required)."""
    import cv2
    first = _to_gray(before)
    second = _to_gray(after)
    if first.shape != second.shape:
        raise ValueError(f"frames must be the same size: {first.shape} vs "
                         f"{second.shape}")
    if int(blur) > 0:
        kernel = int(blur) | 1
        first = cv2.GaussianBlur(first, (kernel, kernel), 0)
        second = cv2.GaussianBlur(second, (kernel, kernel), 0)
    _retval, mask = cv2.threshold(cv2.absdiff(first, second), int(threshold), 255,
                                  cv2.THRESH_BINARY)
    return mask


def changed_regions(before: ImageSource, after: ImageSource, *,
                    threshold: int = 25, min_area: int = 80,
                    blur: int = 5) -> List[Dict[str, Any]]:
    """Return boxes of the regions that moved between ``before`` and ``after``.

    A pixel counts as moved where the absolute difference exceeds ``threshold``;
    connected moved pixels covering at least ``min_area`` are returned as
    ``{x, y, width, height, area, center}`` largest first. ``blur`` denoises first.
    """
    import cv2
    from je_auto_control.utils.cv2_utils.blobs import connected_boxes
    mask = _diff_mask(before, after, threshold, blur)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.dilate(mask, kernel, iterations=2)
    return connected_boxes(mask, int(min_area))


def has_motion(before: ImageSource, after: ImageSource, *, threshold: int = 25,
               min_area: int = 80) -> bool:
    """Return whether any region of at least ``min_area`` moved between the frames."""
    return bool(changed_regions(before, after, threshold=threshold,
                                min_area=min_area))


def activity_score(before: ImageSource, after: ImageSource, *,
                   threshold: int = 25) -> float:
    """Return the fraction (0..1) of pixels that moved between the two frames."""
    mask = _diff_mask(before, after, threshold, 0)
    return round(float((mask > 0).sum()) / mask.size, 4)
