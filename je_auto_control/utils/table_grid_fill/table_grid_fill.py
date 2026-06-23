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
    """Return ``(left, top, right, bottom)`` from an ``x/y/w/h`` or ``l/t/r/b`` box."""
    if "width" in box and "height" in box:
        left, top = int(box["x"]), int(box["y"])
        return left, top, left + int(box["width"]), top + int(box["height"])
    if {"left", "top", "right", "bottom"} <= box.keys():
        return int(box["left"]), int(box["top"]), int(box["right"]), int(box["bottom"])
    raise ValueError("box needs x/y/width/height or left/top/right/bottom")


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
    """Return ``(row, col)`` for a box, or ``None`` if it misses every cell."""
    left, top, right, bottom = _box_bounds(box)
    col = _index_of((left + right) / 2, col_spans)
    row = _index_of((top + bottom) / 2, row_spans)
    if row is None or col is None:
        return None
    cell = (col_spans[col], row_spans[row])
    if _overlap_fraction((left, top, right, bottom), cell) < overlap:
        return None
    return row, col


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
            ordered = sorted(buckets.get((row, col), []), key=_box_bounds)
            cells.append(" ".join(str(b.get("text", "")) for b in ordered).strip())
        table.append(cells)
    return table


def _spans(grid: Dict[str, Any], text_boxes: Sequence[Box]) -> List[Dict[str, Any]]:
    """Return boxes that straddle more than one cell (merged-cell candidates)."""
    col_spans, row_spans = _grid_spans(grid)
    found: List[Dict[str, Any]] = []
    for box in text_boxes:
        left, top, right, bottom = _box_bounds(box)
        c0, c1 = _index_of(left, col_spans), _index_of(right - 1, col_spans)
        r0, r1 = _index_of(top, row_spans), _index_of(bottom - 1, row_spans)
        if None in (c0, c1, r0, r1) or (c0 == c1 and r0 == r1):
            continue
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
