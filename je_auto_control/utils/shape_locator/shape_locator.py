"""Locate UI elements by edge/contour detection — buttons, cards, fields, no template.

Template matching needs a reference image, colour-region needs a known colour, OCR
needs text — none of them answers "where are the rectangular, clickable regions on
this screen?". This runs Canny edge detection plus contour extraction and returns
the bounding boxes of the distinct shapes, optionally filtered to rectangles, so a
script can enumerate cards / buttons / inputs structurally and act on the Nth one
without ever supplying a sample image.

It runs on an injectable ``haystack`` image (ndarray / path / PIL), so it is
unit-testable on synthetic arrays without a real screen. OpenCV + NumPy come in via
the project's ``je_open_cv`` dependency and are imported lazily. Imports no
``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.visual_match.visual_match import _haystack_gray

ImageSource = Any
AspectRange = Optional[Tuple[float, float]]
_CANNY_LOW = 50
_CANNY_HIGH = 150


def _contours(gray):
    """Canny edges (dilated to close gaps) -> external contours, version-agnostic."""
    import cv2
    edges = cv2.Canny(gray, _CANNY_LOW, _CANNY_HIGH)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.dilate(edges, kernel, iterations=1)
    found = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return found[0] if len(found) == 2 else found[1]


def _box(contour) -> Dict[str, Any]:
    """Bounding box of one contour as ``{x,y,width,height,area,center,aspect}``."""
    import cv2
    x, y, width, height = cv2.boundingRect(contour)
    return {"x": int(x), "y": int(y), "width": int(width), "height": int(height),
            "area": int(width * height),
            "center": [int(x + width // 2), int(y + height // 2)],
            "aspect": round(width / height, 3) if height else 0.0}


def _passes(box: Dict[str, Any], min_area: int, max_area: Optional[int],
            aspect_range: AspectRange) -> bool:
    """Apply the size / aspect-ratio filters to one box."""
    if box["area"] < int(min_area):
        return False
    if max_area is not None and box["area"] > int(max_area):
        return False
    if aspect_range is not None and not (
            aspect_range[0] <= box["aspect"] <= aspect_range[1]):
        return False
    return True


def _is_rectangle(contour, epsilon: float) -> bool:
    """True when the contour approximates to a convex 4-gon (a rectangle)."""
    import cv2
    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, epsilon * perimeter, True)
    return len(approx) == 4 and cv2.isContourConvex(approx)


def find_shapes(haystack: Optional[ImageSource] = None, *,
                region: Optional[Sequence[int]] = None, min_area: int = 400,
                max_area: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return bounding boxes of all distinct shapes on screen, largest first.

    Each result is ``{x, y, width, height, area, center, aspect}`` where ``area``
    is the bounding-box area. ``haystack`` is an ndarray / path / PIL image
    (default: grab the screen / ``region``); ``min_area`` / ``max_area`` drop
    specks and full-frame borders.
    """
    boxes = [_box(contour) for contour in _contours(_haystack_gray(haystack, region))]
    boxes = [box for box in boxes if _passes(box, min_area, max_area, None)]
    boxes.sort(key=lambda box: box["area"], reverse=True)
    return boxes


def find_rectangles(haystack: Optional[ImageSource] = None, *,
                    region: Optional[Sequence[int]] = None, min_area: int = 400,
                    max_area: Optional[int] = None,
                    aspect_range: AspectRange = None,
                    epsilon: float = 0.04) -> List[Dict[str, Any]]:
    """Return boxes of the ~rectangular shapes (buttons / cards / fields), largest first.

    Keeps only contours that approximate to a convex quadrilateral (``epsilon`` is
    the ``approxPolyDP`` tolerance as a fraction of the perimeter). ``aspect_range``
    is an optional ``(min, max)`` width/height filter — e.g. ``(1.5, 8)`` for wide
    buttons, ``(0.8, 1.2)`` for square icons.
    """
    gray = _haystack_gray(haystack, region)
    boxes = [_box(contour) for contour in _contours(gray)
             if _is_rectangle(contour, float(epsilon))]
    boxes = [box for box in boxes if _passes(box, min_area, max_area, aspect_range)]
    boxes.sort(key=lambda box: box["area"], reverse=True)
    return boxes
