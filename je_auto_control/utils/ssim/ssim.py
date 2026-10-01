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
_K1, _K2 = 0.01, 0.03


def _gray_code(channels: int, is_bgr: bool) -> int:
    """OpenCV colour-to-gray conversion code for the given channel order."""
    import cv2
    if channels == 4:
        return cv2.COLOR_BGRA2GRAY if is_bgr else cv2.COLOR_RGBA2GRAY
    return cv2.COLOR_BGR2GRAY if is_bgr else cv2.COLOR_RGB2GRAY


def _data_range(array) -> float:
    """The dynamic range L of an image (Wang et al. 2004): 255 for 8-bit, 1 for 0..1 floats."""
    import numpy as np
    if np.issubdtype(array.dtype, np.integer):
        return float(np.iinfo(array.dtype).max)
    if np.issubdtype(array.dtype, np.bool_):
        return 1.0
    return 1.0 if array.size and float(np.nanmax(array)) <= 1.0 else 255.0


def _to_gray_f(source: ImageSource):
    """Load a path / ndarray / PIL image as ``(2-D float64 grayscale, dynamic range)``.

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
        from je_auto_control.utils.cv2_utils.image_file import read_image
        array = read_image(source, cv2.IMREAD_COLOR)
        if array is None:
            raise ValueError(f"could not read image: {source!r}")
        is_bgr = True
    else:
        array = np.asarray(source)
    data_range = _data_range(array)
    if array.ndim == 3 and array.shape[2] == 1:
        array = array[..., 0]            # cvtColor has no 1-channel-to-gray code
    if array.ndim == 3:
        if array.dtype == np.float64:
            array = array.astype(np.float32)   # cvtColor takes 8U / 16U / 32F
        array = cv2.cvtColor(array, _gray_code(array.shape[2], is_bgr))
    return array.astype(np.float64), data_range


def _grab_gray_f(region: Optional[Sequence[int]]):
    from je_auto_control.utils.cv2_utils.region_capture import grab_screen_region
    return _to_gray_f(grab_screen_region(region))


def _resolve_pair(reference: ImageSource, current: Optional[ImageSource],
                  region: Optional[Sequence[int]]):
    reference_gray, reference_range = _to_gray_f(reference)
    current_gray, current_range = (_to_gray_f(current) if current is not None
                                   else _grab_gray_f(region))
    if reference_gray.shape != current_gray.shape:
        raise ValueError(f"reference {reference_gray.shape} and current "
                         f"{current_gray.shape} must be the same size")
    return reference_gray, current_gray, max(reference_range, current_range)


def _ssim_map(reference, current, data_range: float):
    """Per-pixel SSIM map via an 11x11 Gaussian window (sigma 1.5).

    C1 and C2 scale with the images' dynamic range: fixed at 255, two 0..1
    float images of independent noise scored 0.996.
    """
    import cv2
    c1, c2 = (_K1 * data_range) ** 2, (_K2 * data_range) ** 2
    mu_ref = cv2.GaussianBlur(reference, _WINDOW, _SIGMA)
    mu_cur = cv2.GaussianBlur(current, _WINDOW, _SIGMA)
    mu_ref2, mu_cur2, mu_cross = mu_ref * mu_ref, mu_cur * mu_cur, mu_ref * mu_cur
    var_ref = cv2.GaussianBlur(reference * reference, _WINDOW, _SIGMA) - mu_ref2
    var_cur = cv2.GaussianBlur(current * current, _WINDOW, _SIGMA) - mu_cur2
    cov = cv2.GaussianBlur(reference * current, _WINDOW, _SIGMA) - mu_cross
    numerator = (2 * mu_cross + c1) * (2 * cov + c2)
    denominator = (mu_ref2 + mu_cur2 + c1) * (var_ref + var_cur + c2)
    return numerator / denominator


def _keep_mask(shape, ignore: IgnoreBoxes):
    """Boolean keep-mask (True = counted); ``ignore`` boxes [x,y,w,h] set False."""
    import numpy as np
    keep = np.ones(shape, dtype=bool)
    for box in ignore or ():
        x, y, width, height = (int(value) for value in box[:4])
        # Clamped at 0: a negative start sliced from the far edge, so
        # x=-5, w=10 became keep[:, -5:5] -- empty -- and ignored nothing.
        keep[max(0, y):max(0, y + height), max(0, x):max(0, x + width)] = False
    return keep


def ssim_compare(reference: ImageSource, current: Optional[ImageSource] = None,
                 *, ignore: IgnoreBoxes = None,
                 region: Optional[Sequence[int]] = None) -> float:
    """Return the mean SSIM (-1..1) between ``reference`` and ``current``.

    ``current`` defaults to a screen grab of the optional ``region``. ``ignore``
    is a list of ``[x, y, w, h]`` boxes excluded from the score (dynamic clocks,
    blinking cursors). ``1.0`` means structurally identical; lower means more
    change, and a negative score an inverted structure. Raises ``ValueError``
    if the two images differ in size.
    """
    import numpy as np
    reference_gray, current_gray, data_range = _resolve_pair(reference, current, region)
    smap = _ssim_map(reference_gray, current_gray, data_range)
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
    reference_gray, current_gray, data_range = _resolve_pair(reference, current, region)
    smap = _ssim_map(reference_gray, current_gray, data_range)
    changed = (1.0 - smap) > float(threshold)
    changed &= _keep_mask(smap.shape, ignore)
    return connected_boxes(changed.astype(np.uint8), int(min_area))
