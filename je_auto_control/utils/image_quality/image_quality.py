"""Score image quality before OCR / template matching.

OCR and template matching quietly fail on a blurry, washed-out or too-dark
capture — the locate returns nothing and the caller can't tell a *missing*
element from an *unreadable* one. ``image_quality`` measures the three things
that wreck recognition and gates on them:

* **sharpness** — variance of the Laplacian (low = blurry / out of focus),
* **contrast** — standard deviation of the grayscale (low = washed out),
* **brightness** — mean grayscale 0–255 (too low = dark, too high = blown out).

:func:`image_quality` returns the raw metrics, :func:`is_blurry` is the common
one-liner, and :func:`quality_gate` turns the metrics into a pass / fail verdict
with named issues so a script can refuse to OCR a bad frame (or pre-process it
first). It reuses ``visual_match``'s grayscale loader, so the source is any
ndarray / path / PIL image (or the live screen when omitted); ``region`` applies
to a live-screen grab. cv2 / numpy are lazily imported. Imports no ``PySide6``.
"""
from typing import Any, Dict, Optional, Sequence, Tuple

ImageSource = Any


def _gray(source: Optional[ImageSource], region: Optional[Sequence[int]]):
    from je_auto_control.utils.visual_match.visual_match import _haystack_gray
    return _haystack_gray(source, region)


def image_quality(source: Optional[ImageSource] = None, *,
                  region: Optional[Sequence[int]] = None) -> Dict[str, float]:
    """Return ``{sharpness, contrast, brightness}`` for an image (or live screen).

    ``sharpness`` is the variance of the Laplacian, ``contrast`` the grayscale
    standard deviation, ``brightness`` the mean grayscale (0–255).
    """
    import cv2
    gray = _gray(source, region)
    return {"sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
            "contrast": float(gray.std()),
            "brightness": float(gray.mean())}


def is_blurry(source: Optional[ImageSource] = None, *,
              region: Optional[Sequence[int]] = None,
              threshold: float = 100.0) -> bool:
    """Return True if the image's Laplacian variance is below ``threshold``."""
    return image_quality(source, region=region)["sharpness"] < float(threshold)


def quality_gate(source: Optional[ImageSource] = None, *,
                 region: Optional[Sequence[int]] = None,
                 min_sharpness: float = 100.0, min_contrast: float = 12.0,
                 brightness_range: Tuple[float, float] = (40.0, 220.0),
                 ) -> Dict[str, Any]:
    """Grade an image for OCR readability: ``{..., passed, issues}``.

    ``issues`` flags ``blurry`` / ``low_contrast`` / ``too_dark`` / ``too_bright``;
    ``passed`` is True only when no issue fires.
    """
    metrics = image_quality(source, region=region)
    low, high = brightness_range
    issues = []
    if metrics["sharpness"] < float(min_sharpness):
        issues.append("blurry")
    if metrics["contrast"] < float(min_contrast):
        issues.append("low_contrast")
    if metrics["brightness"] < float(low):
        issues.append("too_dark")
    elif metrics["brightness"] > float(high):
        issues.append("too_bright")
    return {**metrics, "passed": not issues, "issues": issues}
