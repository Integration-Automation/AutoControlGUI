"""Address a table / grid cell by (row, column) from a set of bounding boxes.

``anchor_locator`` does pairwise spatial relations (target *near* / *below* an
anchor) but nothing addresses a 2-D grid — "the cell at row 3, column 2" of a
table. Given the bounding boxes of the cells (from an image or OCR enumeration —
e.g. ``locate_all_image`` / ``find_text_matches``), this clusters them into rows
and columns and returns the requested cell's centre.

The clustering and lookup are pure (boxes in, grid / cell out) and fully
unit-testable; the box enumeration stays the caller's job, so nothing here needs a
real screen. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Sequence, Tuple

Box = Any
#: How a list box is laid out: ``locate_all_image`` answers ``ltrb``.
BOX_FORMATS = ("xywh", "ltrb")


def _as_xywh(box: Box, box_format: str) -> List[int]:
    """``[x, y, w, h]`` of a list box in ``box_format``, or of a dict / match object.

    ``AC_locate_all_image`` answers ``[left, top, right, bottom]`` but every
    box was read as ``[x, y, w, h]``, so its cell centres came out wrong; a
    ``find_text_matches`` object or a dict raised ``TypeError`` / ``KeyError``.
    """
    if isinstance(box, (list, tuple)):
        a, b, c, d = (int(value) for value in box[:4])
        return [a, b, c - a, d - b] if box_format == "ltrb" else [a, b, c, d]
    from je_auto_control.utils.accessibility.element import element_box
    found = element_box(box)
    if found is None:
        raise ValueError(f"not a box: {box!r}")
    return list(found)


def _checked_format(box_format: str) -> str:
    if box_format not in BOX_FORMATS:
        raise ValueError(f"box_format must be one of {BOX_FORMATS}, got {box_format!r}")
    return box_format


def _center(box: Box) -> Tuple[int, int]:
    """Return the integer centre ``(x, y)`` of an ``(x, y, w, h)`` box."""
    x, y, width, height = (int(value) for value in box[:4])
    return x + width // 2, y + height // 2


def cluster_grid(boxes: Sequence[Box], *, row_tolerance: int = 10,
                 box_format: str = "xywh") -> List[List[List[int]]]:
    """Cluster boxes into rows (top-down), cells left-to-right.

    List boxes are ``[x, y, w, h]``, or ``[left, top, right, bottom]`` with
    ``box_format="ltrb"`` (what ``locate_all_image`` answers); dicts and match
    objects are read by their fields. Boxes whose centre-y values are within
    ``row_tolerance`` of the previous box (after sorting by y) share a row;
    within a row the cells are ordered by centre-x. Returns a list of rows,
    each a list of ``[x, y, w, h]`` boxes.
    """
    box_format = _checked_format(box_format)
    items = sorted((_as_xywh(box, box_format) for box in boxes),
                   key=lambda box: _center(box)[1])
    rows: List[List[List[int]]] = []
    current: List[List[int]] = []
    last_cy = None
    for box in items:
        center_y = _center(box)[1]
        if last_cy is not None and abs(center_y - last_cy) > int(row_tolerance):
            rows.append(current)
            current = []
        current.append(box)
        last_cy = center_y
    if current:
        rows.append(current)
    for row in rows:
        row.sort(key=lambda box: _center(box)[0])
    return rows


def locate_cell(boxes: Sequence[Box], row: int, col: int, *,
                row_tolerance: int = 10, box_format: str = "xywh") -> Dict[str, Any]:
    """Return the cell at ``(row, col)`` (both 0-based) of the clustered grid; ``box`` is ``[x, y, w, h]``."""
    grid = cluster_grid(boxes, row_tolerance=row_tolerance, box_format=box_format)
    if not 0 <= row < len(grid):
        return {"found": False, "reason": "row out of range",
                "rows": len(grid), "cols": 0}
    line = grid[row]
    if not 0 <= col < len(line):
        return {"found": False, "reason": "col out of range",
                "rows": len(grid), "cols": len(line)}
    box = line[col]
    center = _center(box)
    return {"found": True, "center": [center[0], center[1]], "box": list(box),
            "row": row, "col": col, "rows": len(grid), "cols": len(line)}
