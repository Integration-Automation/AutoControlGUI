"""Structural-similarity (SSIM) comparison: perceptual score + changed regions.

The framework already has pixel diff (``diff_screenshots``) and histogram drift
(``detect_drift``); neither is *structural*. SSIM is the standard visual-regression
metric — tolerant of small illumination shifts, sensitive to structural change
(text edits, moved or missing elements) — and yields a 0..1 similarity plus the
boxes of the regions that actually changed, so a test can both gate on a score and
point at *what* moved.

It is a pure NumPy + OpenCV implementation (no scikit-image, which is not a
dependency) over an injectable image pair, so it is unit-testable on synthetic
arrays without a real screen. OpenCV + NumPy come in via ``je_open_cv`` and are
imported lazily. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence

ImageSource = Any
IgnoreBoxes = Optional[Sequence[Sequence[int]]]
_WINDOW = (11, 11)
_SIGMA = 1.5
_C1 = (0.01 * 255) ** 2
_C2 = (0.03 * 255) ** 2


def _gray_code(channels: int, is_bgr: bool) -> int:
    """OpenCV colour-to-gray conversion code for the given channel order."""
    import cv2
    if channels == 4:
        return cv2.COLOR_BGRA2GRAY if is_bgr else cv2.COLOR_RGBA2GRAY
    return cv2.COLOR_BGR2GRAY if is_bgr else cv2.COLOR_RGB2GRAY


def _to_gray_f(source: ImageSource):
    """Load a path / ndarray / PIL image as a 2-D float64 grayscale image.

    Channel order is tracked so luminance weights stay correct: ``cv2.imread``
    paths are BGR, while ndarray / PIL sources (the live ``pil_screenshot``
    grab) are RGB. Converting both with BGR weights would swap the R/B
    luminance weights, so a saved red baseline and the same red on screen would
    read as structurally different (~47/255 apart).
    """
    import cv2
    import numpy as np
    is_bgr = False
    if hasattr(source, "shape"):
        array = np.asarray(source)
    elif isinstance(source, (str, bytes)) or hasattr(source, "__fspath__"):
        array = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if array is None:
            raise ValueError(f"could not read image: {source!r}")
        is_bgr = True
    else:
        array = np.asarray(source)
    if array.ndim == 3:
        array = cv2.cvtColor(array, _gray_code(array.shape[2], is_bgr))
    return array.astype(np.float64)


def _grab_gray_f(region: Optional[Sequence[int]]):
    from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
    image = pil_screenshot(screen_region=list(region) if region else None)
    return _to_gray_f(image)


def _resolve_pair(reference: ImageSource, current: Optional[ImageSource],
                  region: Optional[Sequence[int]]):
    reference_gray = _to_gray_f(reference)
    current_gray = (_to_gray_f(current) if current is not None
                    else _grab_gray_f(region))
    if reference_gray.shape != current_gray.shape:
        raise ValueError(f"reference {reference_gray.shape} and current "
                         f"{current_gray.shape} must be the same size")
    return reference_gray, current_gray


def _ssim_map(reference, current):
    """Per-pixel SSIM map via an 11x11 Gaussian window (sigma 1.5)."""
    import cv2
    mu_ref = cv2.GaussianBlur(reference, _WINDOW, _SIGMA)
    mu_cur = cv2.GaussianBlur(current, _WINDOW, _SIGMA)
    mu_ref2, mu_cur2, mu_cross = mu_ref * mu_ref, mu_cur * mu_cur, mu_ref * mu_cur
    var_ref = cv2.GaussianBlur(reference * reference, _WINDOW, _SIGMA) - mu_ref2
    var_cur = cv2.GaussianBlur(current * current, _WINDOW, _SIGMA) - mu_cur2
    cov = cv2.GaussianBlur(reference * current, _WINDOW, _SIGMA) - mu_cross
    numerator = (2 * mu_cross + _C1) * (2 * cov + _C2)
    denominator = (mu_ref2 + mu_cur2 + _C1) * (var_ref + var_cur + _C2)
    return numerator / denominator


def _keep_mask(shape, ignore: IgnoreBoxes):
    """Boolean keep-mask (True = counted); ``ignore`` boxes [x,y,w,h] set False."""
    import numpy as np
    keep = np.ones(shape, dtype=bool)
    for box in ignore or ():
        x, y, width, height = (int(value) for value in box[:4])
        keep[y:y + height, x:x + width] = False
    return keep


def ssim_compare(reference: ImageSource, current: Optional[ImageSource] = None,
                 *, ignore: IgnoreBoxes = None,
                 region: Optional[Sequence[int]] = None) -> float:
    """Return the mean SSIM (0..1) between ``reference`` and ``current``.

    ``current`` defaults to a screen grab of the optional ``region``. ``ignore``
    is a list of ``[x, y, w, h]`` boxes excluded from the score (dynamic clocks,
    blinking cursors). ``1.0`` means structurally identical; lower means more
    change. Raises ``ValueError`` if the two images differ in size.
    """
    import numpy as np
    reference_gray, current_gray = _resolve_pair(reference, current, region)
    smap = _ssim_map(reference_gray, current_gray)
    keep = _keep_mask(smap.shape, ignore)
    return round(float(np.mean(smap[keep])), 4) if keep.any() else 1.0


def ssim_changed_regions(reference: ImageSource,
                         current: Optional[ImageSource] = None, *,
                         ignore: IgnoreBoxes = None, threshold: float = 0.35,
                         min_area: int = 50,
                         region: Optional[Sequence[int]] = None
                         ) -> List[Dict[str, Any]]:
    """Return boxes of the regions that structurally changed, largest first.

    A pixel counts as changed where local dissimilarity ``1 - SSIM`` exceeds
    ``threshold``; connected changed pixels covering at least ``min_area`` are
    returned as ``{x, y, width, height, area, center}``. ``ignore`` boxes are
    suppressed before detection.
    """
    import numpy as np
    from je_auto_control.utils.cv2_utils.blobs import connected_boxes
    reference_gray, current_gray = _resolve_pair(reference, current, region)
    smap = _ssim_map(reference_gray, current_gray)
    changed = (1.0 - smap) > float(threshold)
    changed &= _keep_mask(smap.shape, ignore)
    return connected_boxes(changed.astype(np.uint8), int(min_area))
