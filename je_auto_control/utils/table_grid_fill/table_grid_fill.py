"""Fill a ruling-line grid with OCR text to get an addressable table.

``edge_lines.find_grid`` recovers a bordered table's geometry — ``{rows: [y…],
cols: [x…], cells: […]}`` — but the cells come back *empty* (pure rectangles from the
ruling lines). ``ocr`` / OCR word boxes give the text but no table structure. Nothing
joined the two, so reading a bordered table meant hand-rolling the box→cell assignment.

This drops OCR text boxes into the grid: each box is assigned to the cell its centre
falls in (gated by an overlap fraction so a box straddling a thin rule is not double
counted), text within a cell is concatenated in reading order, and boxes that span
multiple cells are reported separately. The result is an ``R x C`` text table that
converts straight to records / CSV.

Pure-stdlib geometry over plain dicts (the grid + the boxes); fully unit-testable with
no image, no OCR engine, no device. Imports no ``PySide6``.
"""
import csv
import io
from typing import Any, Dict, List, Optional, Sequence, Tuple

Box = Dict[str, Any]
Bounds = Tuple[int, int, int, int]


def _box_bounds(box: Box) -> Bounds:
    """Return ``(left, top, right, bottom)`` from an ``x/y/w/h``, ``left/top/w/h`` or ``l/t/r/b`` box.

    Tesseract's ``left/top/width/height`` shape, or a box missing ``y``, raised
    ``KeyError`` instead of the documented ``ValueError``.
    """
    if {"left", "top", "right", "bottom"} <= box.keys():
        return int(box["left"]), int(box["top"]), int(box["right"]), int(box["bottom"])
    left, top = box.get("x", box.get("left")), box.get("y", box.get("top"))
    if left is None or top is None or "width" not in box or "height" not in box:
        raise ValueError("box needs x/y/width/height, left/top/width/height or left/top/right/bottom")
    return int(left), int(top), int(left) + int(box["width"]), int(top) + int(box["height"])


def _covered(bounds: Bounds, col_spans, row_spans):
    """``(r0, c0, r1, c1)``: the cells under the middle half of a box, or ``None`` off the grid.

    The middle half, so a box crossing a rule by a sliver stays in its cell,
    and one really spanning two cells is a span.
    """
    left, top, right, bottom = bounds
    quarter_x, quarter_y = (right - left) / 4, (bottom - top) / 4
    c0, c1 = _index_of(left + quarter_x, col_spans), _index_of(right - quarter_x, col_spans)
    r0, r1 = _index_of(top + quarter_y, row_spans), _index_of(bottom - quarter_y, row_spans)
    if None in (c0, c1, r0, r1):
        return None
    return r0, c0, r1, c1


def _intervals(edges: Sequence[int]) -> List[Tuple[int, int]]:
    """Turn sorted edge coordinates into consecutive ``(start, end)`` spans."""
    ordered = sorted(int(e) for e in edges)
    return [(ordered[i], ordered[i + 1]) for i in range(len(ordered) - 1)]


def _index_of(value: float, spans: Sequence[Tuple[int, int]]) -> Optional[int]:
    """Return the index of the span containing ``value``, else ``None``."""
    for i, (start, end) in enumerate(spans):
        if start <= value < end:
            return i
    return None


def _overlap_fraction(bounds: Bounds, cell: Tuple[Tuple[int, int], Tuple[int, int]]) -> float:
    """Intersection area of a box and a cell, divided by the box area."""
    (left, top, right, bottom) = bounds
    (cx0, cx1), (cy0, cy1) = cell
    inter = max(0, min(right, cx1) - max(left, cx0)) * max(0, min(bottom, cy1) - max(top, cy0))
    area = max(1, (right - left) * (bottom - top))
    return inter / area


def _grid_spans(grid: Dict[str, Any]) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
    """Return ``(column_spans, row_spans)`` from a grid's ``cols`` / ``rows`` edges."""
    return _intervals(grid.get("cols", [])), _intervals(grid.get("rows", []))


def _placed(box: Box, col_spans, row_spans, overlap: float):
    """Return ``(row, col)`` for a box, or ``None`` if it misses every cell.

    A spanning box goes to its anchor (top-left) cell, where its span is
    reported: it used to land in the cell under its centre as well, counted
    twice.
    """
    left, top, right, bottom = _box_bounds(box)
    covered = _covered((left, top, right, bottom), col_spans, row_spans)
    if covered is not None and covered[:2] != covered[2:]:
        return covered[0], covered[1]
    col = _index_of((left + right) / 2, col_spans)
    row = _index_of((top + bottom) / 2, row_spans)
    if row is None or col is None:
        return None
    cell = (col_spans[col], row_spans[row])
    if _overlap_fraction((left, top, right, bottom), cell) < overlap:
        return None
    return row, col


def _in_reading_order(boxes: Sequence[Box]) -> List[Box]:
    """Order a cell's boxes line by line, left to right within a line.

    A box joins a line when its vertical centre is within half that line's
    first box height. Sorting on ``(left, top, ...)`` alone interleaved a
    two-line cell by x: "Hello world" over "foo" came out "Hello foo world".
    """
    lines: List[Tuple[float, float, List[Box]]] = []
    for box in sorted(boxes, key=lambda item: _box_bounds(item)[1]):
        _left, top, _right, bottom = _box_bounds(box)
        center = (top + bottom) / 2
        line = next((entry for entry in lines if abs(center - entry[0]) <= entry[1]), None)
        if line is None:
            lines.append((center, max(1.0, (bottom - top) / 2), [box]))
        else:
            line[2].append(box)
    return [box for _center, _half, items in lines
            for box in sorted(items, key=lambda item: _box_bounds(item)[0])]


def assign_text_to_grid(grid: Dict[str, Any], text_boxes: Sequence[Box], *,
                        overlap: float = 0.4) -> List[List[str]]:
    """Return an ``R x C`` table of cell text from a grid + OCR boxes (reading order)."""
    col_spans, row_spans = _grid_spans(grid)
    buckets: Dict[Tuple[int, int], List[Box]] = {}
    for box in text_boxes:
        placed = _placed(box, col_spans, row_spans, float(overlap))
        if placed is not None:
            buckets.setdefault(placed, []).append(box)
    table: List[List[str]] = []
    for row in range(len(row_spans)):
        cells = []
        for col in range(len(col_spans)):
            ordered = _in_reading_order(buckets.get((row, col), []))
            cells.append(" ".join(str(b.get("text", "")) for b in ordered).strip())
        table.append(cells)
    return table


def _spans(grid: Dict[str, Any], text_boxes: Sequence[Box]) -> List[Dict[str, Any]]:
    """Return boxes that straddle more than one cell (merged-cell candidates)."""
    col_spans, row_spans = _grid_spans(grid)
    found: List[Dict[str, Any]] = []
    for box in text_boxes:
        covered = _covered(_box_bounds(box), col_spans, row_spans)
        if covered is None or covered[:2] == covered[2:]:
            continue
        r0, c0, r1, c1 = covered
        found.append({"row": r0, "col": c0, "row_span": r1 - r0 + 1,
                      "col_span": c1 - c0 + 1, "text": str(box.get("text", ""))})
    return found


def populate_table(grid: Dict[str, Any], text_boxes: Sequence[Box], *,
                   overlap: float = 0.4) -> Dict[str, Any]:
    """Fill ``grid`` with ``text_boxes`` → ``{n_rows, n_cols, cells, spans}``."""
    table = assign_text_to_grid(grid, text_boxes, overlap=overlap)
    cells = [{"row": r, "col": c, "text": table[r][c]}
             for r in range(len(table)) for c in range(len(table[r]))]
    return {"n_rows": len(table), "n_cols": len(table[0]) if table else 0,
            "cells": cells, "spans": _spans(grid, text_boxes)}


def table_to_records(rows: Sequence[Sequence[str]]) -> List[Dict[str, str]]:
    """Use the first row as headers; return the remaining rows as dicts."""
    if not rows:
        return []
    header = list(rows[0])
    return [dict(zip(header, row)) for row in rows[1:]]


def table_to_csv(rows: Sequence[Sequence[str]]) -> str:
    """Render a 2-D text table as a CSV string."""
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue()
