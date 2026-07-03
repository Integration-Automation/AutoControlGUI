"""Model-free on-screen text-region detection (MSER) — where is text, without OCR.

``shape_locator`` finds rectangular contours (buttons / cards, not text) and
``locate_text`` needs a Tesseract / Paddle engine *and* the exact string to search
for. Neither answers "where is there *any* text on screen" without running OCR or
knowing the words. This uses MSER (Maximally Stable Extremal Regions) to find the
glyph/word blobs, so a script can crop candidate text boxes to feed OCR (much faster
and more accurate than full-frame OCR) or detect that a label appeared with no OCR
dependency installed.

Runs on an injectable ``haystack`` (ndarray / path / PIL), so it is headless-testable
on synthetic arrays. OpenCV + NumPy come in via ``je_open_cv`` (``cv2.MSER_create`` is
base OpenCV, no contrib). Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.visual_match.visual_match import _haystack_gray

ImageSource = Any
Rect = Tuple[int, int, int, int]


def _box_dict(rect: Rect) -> Dict[str, Any]:
    x, y, width, height = rect
    return {"x": x, "y": y, "width": width, "height": height,
            "area": width * height, "center": [x + width // 2, y + height // 2]}


def _accept(rect: Rect, shape, min_area: int, max_area: Optional[int],
            max_aspect: float) -> bool:
    """Whether an MSER box looks like text (size / aspect, not the whole frame)."""
    _x, _y, width, height = rect
    frame_h, frame_w = shape[:2]
    if width >= 0.95 * frame_w and height >= 0.95 * frame_h:
        return False                                  # whole-frame extremal region
    area = width * height
    if area < min_area or (max_area is not None and area > max_area):
        return False
    aspect = width / height if height else 0.0
    return aspect <= max_aspect


# OpenCV 5 tightened MSER's diversity pruning: flat-background UI scenes
# that OpenCV 4 segmented fine now yield zero regions at the default
# min_diversity (0.2). Relax the pruning progressively before concluding
# the frame has no text.
_MSER_PARAM_LADDER = ({}, {"min_diversity": 0.01},
                      {"delta": 1, "min_diversity": 0.0})


def _detect_regions(gray):
    """Return MSER point sets, relaxing diversity pruning if none found."""
    import cv2
    regions = ()
    for params in _MSER_PARAM_LADDER:
        regions, _bboxes = cv2.MSER_create(**params).detectRegions(gray)
        if len(regions):
            break
    return regions


def _filtered_boxes(gray, min_area: int, max_area: Optional[int],
                    max_aspect: float) -> List[Rect]:
    """Return de-duplicated MSER bounding boxes passing the size / aspect filters."""
    import cv2
    regions = _detect_regions(gray)
    out: List[Rect] = []
    seen = set()
    for points in regions:
        rect = cv2.boundingRect(points.reshape(-1, 1, 2))
        if rect not in seen and _accept(rect, gray.shape, min_area, max_area,
                                        max_aspect):
            out.append(rect)
        seen.add(rect)
    return out


def _overlaps(a: Rect, b: Rect) -> bool:
    return (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
            and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


def _union(a: Rect, b: Rect) -> Rect:
    x, y = min(a[0], b[0]), min(a[1], b[1])
    return (x, y, max(a[0] + a[2], b[0] + b[2]) - x,
            max(a[1] + a[3], b[1] + b[3]) - y)


def _merge_pass(rects: Sequence[Rect]) -> Tuple[bool, List[Rect]]:
    out: List[Rect] = []
    changed = False
    for rect in rects:
        index = next((i for i, kept in enumerate(out) if _overlaps(rect, kept)),
                     None)
        if index is None:
            out.append(rect)
        else:
            out[index] = _union(rect, out[index])
            changed = True
    return changed, out


def _merge_overlapping(rects: Sequence[Rect]) -> List[Rect]:
    """Union all overlapping rectangles (collapses MSER's nested glyph regions)."""
    result = list(rects)
    changed = True
    while changed:
        changed, result = _merge_pass(result)
    return result


def find_text_regions(haystack: Optional[ImageSource] = None, *,
                      region: Optional[Sequence[int]] = None, min_area: int = 60,
                      max_area: Optional[int] = None, merge: bool = True,
                      max_aspect: float = 12.0) -> List[Dict[str, Any]]:
    """Return boxes of text/glyph regions on screen, largest first (no OCR needed).

    ``merge`` unions overlapping detections (MSER reports nested regions per glyph).
    ``min_area`` / ``max_area`` drop specks and page-sized blobs; ``max_aspect``
    rejects long thin lines that are rules rather than text. Each result is
    ``{x, y, width, height, area, center}``.
    """
    rects = _filtered_boxes(_haystack_gray(haystack, region), int(min_area),
                            int(max_area) if max_area is not None else None,
                            float(max_aspect))
    if merge:
        rects = _merge_overlapping(rects)
    rects.sort(key=lambda rect: rect[2] * rect[3], reverse=True)
    return [_box_dict(rect) for rect in rects]


def find_text_lines(haystack: Optional[ImageSource] = None, *,
                    region: Optional[Sequence[int]] = None,
                    y_tolerance: int = 8) -> List[Dict[str, Any]]:
    """Return one box per horizontal line of text, top-to-bottom.

    Glyph boxes whose vertical centres are within ``y_tolerance`` pixels are grouped
    into a line spanning their combined extent — ready to crop and feed to OCR.
    """
    boxes = _filtered_boxes(_haystack_gray(haystack, region), 40, None, 20.0)
    rows: List[Dict[str, Any]] = []
    for rect in sorted(boxes, key=lambda item: item[1]):
        center_y = rect[1] + rect[3] // 2
        row = next((candidate for candidate in rows
                    if abs(center_y - candidate["cy"]) <= int(y_tolerance)), None)
        if row is None:
            rows.append({"cy": center_y, "rect": rect})
        else:
            row["rect"] = _union(row["rect"], rect)
    return [_box_dict(row["rect"])
            for row in sorted(rows, key=lambda item: item["cy"])]
