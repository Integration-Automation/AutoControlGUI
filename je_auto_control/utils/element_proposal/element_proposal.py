"""Propose a clean element list from raw pixels, with no template or model.

Set-of-Marks, ``observation`` and the grounding helpers all assume you already
have a list of element boxes — but on a screen the framework doesn't model
(a game, a custom-drawn app, a remote desktop) there is no accessibility tree to
provide one. ``element_proposal`` builds that top-of-funnel list from pixels:
detect candidate *widget* boxes (closed-edge blobs) and *text* boxes
(:func:`text_regions.find_text_regions`), fuse them — dropping widget boxes that
are really just text — and return them in reading order, each tagged ``text`` or
``widget``.

* :func:`propose_elements` — the full pixel-to-elements pipeline.
* :func:`tag_kinds` — pure: label fused boxes ``text`` / ``widget`` by source and
  keep their reading-order ``index``.

The fusion / cross-check / ordering reuse :mod:`element_parse` (the ``ocr`` >
``icon`` priority *is* the "drop widget-that-is-really-text" check) and
:mod:`text_regions`; ``cv2`` is imported lazily so the module stays importable.
:func:`tag_kinds` is pure and fully testable. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence

# Reading-order source tag to element kind.
_KIND_BY_SOURCE = {"ocr": "text", "icon": "widget", "a11y": "element"}


def tag_kinds(elements: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Label fused boxes ``text`` / ``widget`` by source (pure).

    Each input box carries a ``source`` (``ocr`` / ``icon``) and an ``index``
    from :func:`element_parse.reading_order`. Returns ``[{box, kind, index}]``.
    """
    result: List[Dict[str, Any]] = []
    for element in elements:
        box = [int(element["x"]), int(element["y"]),
               int(element["width"]), int(element["height"])]
        kind = _KIND_BY_SOURCE.get(str(element.get("source", "")), "widget")
        result.append({"box": box, "kind": kind, "index": element.get("index")})
    return result


def _reasonable(box: Dict[str, Any], frame_w: int, frame_h: int) -> bool:
    """Keep plausibly-widget blobs: not the whole frame, not a thin rule."""
    width, height = int(box["width"]), int(box["height"])
    if width >= 0.95 * frame_w and height >= 0.95 * frame_h:
        return False
    aspect = width / height if height else 0.0
    return 0.05 <= aspect <= 15.0


def _widget_boxes(gray: Any, min_area: int) -> List[Dict[str, Any]]:
    """Detect candidate widget boxes as closed-edge blobs (cv2)."""
    import cv2
    from je_auto_control.utils.cv2_utils.blobs import connected_boxes
    edges = cv2.Canny(gray, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    height, width = gray.shape[:2]
    return [box for box in connected_boxes(closed, min_area=int(min_area))
            if _reasonable(box, width, height)]


def propose_elements(source: Optional[Any] = None, *,
                     region: Optional[Sequence[int]] = None, min_area: int = 80,
                     iou_threshold: float = 0.5) -> List[Dict[str, Any]]:
    """Propose ``text`` / ``widget`` element boxes from pixels, in reading order.

    Detects widget blobs and text regions on ``source`` (a fresh screen grab of
    ``region`` by default), fuses them (overlapping text wins over widget), and
    orders them. Returns ``[{box, kind, index}]``.
    """
    from je_auto_control.utils.element_parse import fuse_elements, reading_order
    from je_auto_control.utils.text_regions import find_text_regions
    from je_auto_control.utils.visual_match.visual_match import _haystack_gray
    gray = _haystack_gray(source, region)
    text = find_text_regions(gray, min_area=int(min_area))
    widgets = _widget_boxes(gray, int(min_area))
    fused = fuse_elements(ocr_boxes=text, icon_boxes=widgets,
                          iou_threshold=float(iou_threshold))
    return tag_kinds(reading_order(fused))
