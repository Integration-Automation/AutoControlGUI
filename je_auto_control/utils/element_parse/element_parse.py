"""Fuse and order on-screen element boxes — the step before set-of-marks numbering.

``set_of_marks.mark_elements`` assumes a single, already-deduplicated element list
and just numbers it; nothing produces that list. A real screen parse yields *three*
overlapping sources — OCR text boxes, icon/shape boxes, accessibility boxes — with
heavy overlap and no consistent order. This module supplies the missing connective
tissue: ``iou`` / ``merge_boxes`` drop near-duplicates, ``fuse_elements`` unions the
three sources keeping the most trustworthy one on overlap, and ``reading_order``
sorts the survivors top-to-bottom, left-to-right and assigns a stable index.

Every box is a plain ``dict`` with ``x, y, width, height`` (plus any extra keys such
as ``text`` / ``source`` / ``score``), so this is pure-stdlib and fully unit-testable.
Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple

Box = Dict[str, Any]
_DEFAULT_PRIORITY = ("a11y", "ocr", "icon")


def _xywh(box: Box) -> Tuple[int, int, int, int]:
    return (int(box["x"]), int(box["y"]), int(box["width"]), int(box["height"]))


def _area(box: Box) -> int:
    _x, _y, width, height = _xywh(box)
    return width * height


def iou(box_a: Box, box_b: Box) -> float:
    """Return the intersection-over-union (0..1) of two ``{x,y,width,height}`` boxes."""
    ax, ay, aw, ah = _xywh(box_a)
    bx, by, bw, bh = _xywh(box_b)
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, right - left) * max(0, bottom - top)
    if inter == 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def _dedup(boxes: Sequence[Box], iou_threshold: float) -> List[Box]:
    kept: List[Box] = []
    for box in boxes:
        if all(iou(box, other) <= iou_threshold for other in kept):
            kept.append(box)
    return kept


def merge_boxes(boxes: Sequence[Box], *, iou_threshold: float = 0.9) -> List[Box]:
    """Drop near-duplicate boxes (IoU above ``iou_threshold``), largest kept first."""
    ordered = sorted(boxes, key=_area, reverse=True)
    return _dedup(ordered, float(iou_threshold))


def fuse_elements(ocr_boxes: Optional[Sequence[Box]] = None,
                  icon_boxes: Optional[Sequence[Box]] = None,
                  a11y_boxes: Optional[Sequence[Box]] = None, *,
                  iou_threshold: float = 0.9,
                  source_priority: Sequence[str] = _DEFAULT_PRIORITY
                  ) -> List[Box]:
    """Union OCR + icon + accessibility boxes, dropping cross-source duplicates.

    On overlap (IoU above ``iou_threshold``) the box from the higher-priority source
    wins (``source_priority`` default a11y > ocr > icon, then larger area). Each box
    is tagged with its ``source``.
    """
    rank = {name: index for index, name in enumerate(source_priority)}
    tagged: List[Box] = []
    for source, boxes in (("a11y", a11y_boxes), ("ocr", ocr_boxes),
                          ("icon", icon_boxes)):
        for box in boxes or ():
            item = dict(box)
            item.setdefault("source", source)
            tagged.append(item)
    tagged.sort(key=lambda box: (rank.get(str(box.get("source", "")), len(rank)),
                                 -_area(box)))
    return _dedup(tagged, float(iou_threshold))


def reading_order(elements: Sequence[Box], *, row_tol: int = 12) -> List[Box]:
    """Return the elements sorted top-to-bottom, left-to-right, with an ``index`` key.

    Elements whose tops are within ``row_tol`` pixels are treated as the same row and
    ordered by ``x`` within it.
    """
    rows: List[Dict[str, Any]] = []
    for element in sorted(elements, key=lambda box: _xywh(box)[1]):
        top = _xywh(element)[1]
        row = next((candidate for candidate in rows
                    if abs(top - candidate["top"]) <= int(row_tol)), None)
        if row is None:
            rows.append({"top": top, "items": [element]})
        else:
            row["items"].append(element)
    ordered: List[Box] = []
    for row in rows:
        ordered.extend(sorted(row["items"], key=lambda box: _xywh(box)[0]))
    return [dict(element, index=index) for index, element in enumerate(ordered)]
