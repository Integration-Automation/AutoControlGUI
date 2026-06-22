"""Locate on-screen regions by colour — find the green pill, the red banner.

``color_stats`` only *describes* a region's dominant / average colour and
``assert_pixel`` checks a single point with a tolerance; neither *locates* a
coloured region. Template matching is brittle when only the colour is the signal
(a status light, a progress fill, an error banner). This masks pixels within a
tolerance of a target RGB and returns the bounding boxes of the connected blobs.

The masking + connected-components run on an injectable ``haystack`` image
(ndarray / path / PIL), so it is unit-testable on synthetic arrays without a real
screen. OpenCV + NumPy come in via the project's ``je_open_cv`` dependency and are
imported lazily. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence

ImageSource = Any


def _to_rgb(source: ImageSource):
    """Load a path / ndarray / PIL image as an RGB ndarray."""
    import cv2
    import numpy as np
    if hasattr(source, "shape"):
        return np.asarray(source)
    if isinstance(source, (str, bytes)) or hasattr(source, "__fspath__"):
        bgr = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError(f"could not read image: {source!r}")
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return np.asarray(source)


def _grab_rgb(region: Optional[Sequence[int]]):
    import numpy as np
    from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
    image = pil_screenshot(screen_region=list(region) if region else None)
    return np.asarray(image.convert("RGB"))


def find_color_regions(rgb: Sequence[int], *,
                       haystack: Optional[ImageSource] = None,
                       region: Optional[Sequence[int]] = None,
                       tolerance: int = 20,
                       min_area: int = 50) -> List[Dict[str, Any]]:
    """Return bounding boxes of blobs within ``tolerance`` of ``rgb``, largest first.

    Each result is ``{x, y, width, height, area, center}``. ``tolerance`` is the
    per-channel band around ``rgb``; ``min_area`` drops specks. ``haystack`` is an
    RGB ndarray / path / PIL image (default: grab the screen / ``region``).
    """
    import cv2
    import numpy as np
    from je_auto_control.utils.cv2_utils.blobs import connected_boxes
    image = _to_rgb(haystack) if haystack is not None else _grab_rgb(region)
    red, green, blue = (int(channel) for channel in rgb[:3])
    tol = int(tolerance)
    lower = np.array([max(0, red - tol), max(0, green - tol),
                      max(0, blue - tol)], dtype=np.uint8)
    upper = np.array([min(255, red + tol), min(255, green + tol),
                      min(255, blue + tol)], dtype=np.uint8)
    mask = cv2.inRange(image, lower, upper)
    return connected_boxes(mask, int(min_area))


def find_color_region(rgb: Sequence[int], *,
                      haystack: Optional[ImageSource] = None,
                      region: Optional[Sequence[int]] = None,
                      tolerance: int = 20,
                      min_area: int = 50) -> Optional[Dict[str, Any]]:
    """Return the largest blob within ``tolerance`` of ``rgb`` (or ``None``)."""
    regions = find_color_regions(rgb, haystack=haystack, region=region,
                                 tolerance=tolerance, min_area=min_area)
    return regions[0] if regions else None
