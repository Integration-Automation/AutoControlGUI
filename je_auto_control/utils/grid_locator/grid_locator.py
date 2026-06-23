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

Box = Sequence[int]


def _center(box: Box) -> Tuple[int, int]:
    """Return the integer centre ``(x, y)`` of an ``(x, y, w, h)`` box."""
    x, y, width, height = (int(value) for value in box[:4])
    return x + width // 2, y + height // 2


def cluster_grid(boxes: Sequence[Box], *,
                 row_tolerance: int = 10) -> List[List[List[int]]]:
    """Cluster ``(x, y, w, h)`` boxes into rows (top-down), cells left-to-right.

    Boxes whose centre-y values are within ``row_tolerance`` of the previous
    box (after sorting by y) share a row; within a row the cells are ordered by
    centre-x. Returns a list of rows, each a list of ``[x, y, w, h]`` boxes.
    """
    items = sorted((list(map(int, box[:4])) for box in boxes),
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
                row_tolerance: int = 10) -> Dict[str, Any]:
    """Return the cell at ``(row, col)`` (both 0-based) of the clustered grid."""
    grid = cluster_grid(boxes, row_tolerance=row_tolerance)
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
