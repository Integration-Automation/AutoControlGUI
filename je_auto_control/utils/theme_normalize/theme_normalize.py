"""Theme-invariant image normalisation so light templates match dark mode.

``match_template`` correlates raw pixel intensities, so a template captured in
light mode scores terribly against the same control in dark mode — the polarity
is inverted. The fix is to compare *structure* (edges, gradients), which is the
same regardless of which way the colours run. ``theme_normalize`` turns an image
into a polarity-invariant representation before matching:

* :func:`normalize_theme` — map an image to a normalised single-channel image.
  ``sobel`` (default) and ``laplacian`` use gradient magnitude, which is
  identical for an image and its inverse; ``zscore`` standardises intensity.
* :func:`match_theme` — :func:`normalize_theme` both the template and the
  haystack (the screen by default), then locate the template — finding it across
  a light/dark theme flip that defeats raw matching.

cv2 / numpy are imported lazily, so importing this module never requires them
(the package stays importable everywhere) and the locating logic reuses
:func:`visual_match.match_template`. Imports no ``PySide6``.
"""
from typing import Any, Dict, Optional, Sequence

# A normalisation method name.
THEME_METHODS = ("sobel", "laplacian", "zscore")


def _to_uint8(array: Any) -> Any:
    """Rescale a float array to a 0..255 uint8 image."""
    import cv2
    return cv2.normalize(array, None, 0, 255, cv2.NORM_MINMAX).astype("uint8")


def _zscore(gray: Any) -> Any:
    """Standardise intensity to zero mean / unit variance (not inversion-safe)."""
    import numpy as np
    std = float(gray.std())
    if std < 1e-9:
        return np.zeros_like(gray)
    return (gray - gray.mean()) / std


def normalize_theme(source: Any, *, method: str = "sobel") -> Any:
    """Return ``source`` as a theme-normalised single-channel ``uint8`` image.

    ``sobel`` / ``laplacian`` return gradient magnitude — identical for an image
    and its colour-inverted (dark-mode) twin — and ``zscore`` standardises
    intensity. Raises ``ValueError`` for an unknown ``method``.
    """
    import cv2
    import numpy as np
    from je_auto_control.utils.visual_match.visual_match import _to_gray
    gray = _to_gray(source).astype("float64")
    if method == "sobel":
        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        result = np.sqrt(gx * gx + gy * gy)
    elif method == "laplacian":
        result = np.abs(cv2.Laplacian(gray, cv2.CV_64F, ksize=3))
    elif method == "zscore":
        result = _zscore(gray)
    else:
        raise ValueError(f"unknown theme-normalize method: {method!r}")
    return _to_uint8(result)


def match_theme(template: Any, *, haystack: Optional[Any] = None,
                method: str = "sobel", min_score: float = 0.5,
                region: Optional[Sequence[int]] = None
                ) -> Optional[Dict[str, Any]]:
    """Locate ``template`` in ``haystack`` after theme-normalising both.

    ``haystack`` defaults to a fresh screen grab (optionally clipped to
    ``region``). Returns ``{x, y, width, height, score}`` for the best match at
    or above ``min_score``, or ``None``. Robust to a light/dark theme flip that
    defeats raw :func:`visual_match.match_template`.
    """
    from je_auto_control.utils.visual_match import match_template
    from je_auto_control.utils.visual_match.visual_match import _grab_gray
    raw_haystack = haystack if haystack is not None else _grab_gray(region)
    norm_template = normalize_theme(template, method=method)
    norm_haystack = normalize_theme(raw_haystack, method=method)
    match = match_template(norm_template, haystack=norm_haystack,
                           min_score=float(min_score))
    if match is None:
        return None
    return {"x": match.x, "y": match.y, "width": match.width,
            "height": match.height, "score": round(float(match.score), 4)}
