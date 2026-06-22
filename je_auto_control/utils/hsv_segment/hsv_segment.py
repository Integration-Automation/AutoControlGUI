"""HSV colour-space segmentation — find "any shade of red" regardless of lighting.

``color_region`` masks in RGB with a per-channel ± tolerance box, which fails the
canonical case: a status light, highlight or theme tint that is "the same colour" but
at a different brightness. HSV separates hue from saturation/value, so a hue band with
a saturation/value floor catches every shade of a colour across lighting. This adds
HSV masking + blob boxes, reusing the shared connected-component helper, with correct
hue-wrap handling for red (which straddles the 0/180 boundary).

Runs on an injectable ``haystack`` (ndarray / path / PIL, RGB), so it is headless-
testable on synthetic arrays. OpenCV + NumPy come in via ``je_open_cv``. Imports no
``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence

ImageSource = Any


def _to_rgb(source: ImageSource):
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


def _hsv(haystack: Optional[ImageSource], region: Optional[Sequence[int]]):
    import cv2
    rgb = _to_rgb(haystack) if haystack is not None else _grab_rgb(region)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)


def color_mask(haystack: Optional[ImageSource] = None, *,
               region: Optional[Sequence[int]] = None,
               lower_hsv: Sequence[int], upper_hsv: Sequence[int]):
    """Return a uint8 mask of pixels inside the ``lower_hsv``..``upper_hsv`` band.

    HSV ranges are OpenCV's: H in 0..179, S and V in 0..255.
    """
    import cv2
    import numpy as np
    hsv = _hsv(haystack, region)
    lower = np.array([int(value) for value in lower_hsv], dtype=np.uint8)
    upper = np.array([int(value) for value in upper_hsv], dtype=np.uint8)
    return cv2.inRange(hsv, lower, upper)


def segment_hsv(haystack: Optional[ImageSource] = None, *,
                region: Optional[Sequence[int]] = None,
                lower_hsv: Sequence[int], upper_hsv: Sequence[int],
                min_area: int = 50) -> List[Dict[str, Any]]:
    """Return blob boxes for pixels inside an explicit HSV band, largest first."""
    from je_auto_control.utils.cv2_utils.blobs import connected_boxes
    mask = color_mask(haystack, region=region, lower_hsv=lower_hsv,
                      upper_hsv=upper_hsv)
    return connected_boxes(mask, int(min_area))


def _hue_mask(hsv, low_h: int, high_h: int, sat_min: int, val_min: int):
    """Build an inRange mask for a hue band, OR-ing the two parts when it wraps 0/180."""
    import cv2
    import numpy as np
    floor = [int(sat_min), int(val_min)]
    top = [255, 255]

    def band(start: int, end: int):
        return cv2.inRange(hsv, np.array([start, *floor], dtype=np.uint8),
                           np.array([end, *top], dtype=np.uint8))

    if low_h < 0:
        return cv2.bitwise_or(band(180 + low_h, 179), band(0, high_h))
    if high_h > 179:
        return cv2.bitwise_or(band(low_h, 179), band(0, high_h - 180))
    return band(low_h, high_h)


def dominant_hue_regions(haystack: Optional[ImageSource] = None, *,
                         region: Optional[Sequence[int]] = None, hue: int,
                         hue_tol: int = 10, sat_min: int = 80, val_min: int = 80,
                         min_area: int = 50) -> List[Dict[str, Any]]:
    """Return blob boxes for any pixel near ``hue`` (± ``hue_tol``), any brightness.

    Only the hue is constrained (plus a ``sat_min`` / ``val_min`` floor to skip greys),
    so this catches every shade of a colour across lighting — unlike ``color_region``'s
    RGB box. Red's 0/180 hue wrap is handled automatically.
    """
    from je_auto_control.utils.cv2_utils.blobs import connected_boxes
    mask = _hue_mask(_hsv(haystack, region), int(hue) - int(hue_tol),
                     int(hue) + int(hue_tol), int(sat_min), int(val_min))
    return connected_boxes(mask, int(min_area))
