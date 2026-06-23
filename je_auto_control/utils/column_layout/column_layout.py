"""Infer columns from vertical whitespace, for borderless tables.

``ocr/structure`` detects tables only when *every* row's cell-left-x matches within a
tolerance — it collapses on ragged or borderless tables, right-aligned numeric columns, or
any row with a missing cell. ``edge_lines.find_grid`` needs ruling lines, so a table drawn
purely with whitespace (no borders) has no grid at all. ``column_layout`` finds columns the
robust way the layout-analysis literature uses: by the *gaps*. It projects the OCR boxes onto
the x-axis (an ink-density profile), reads off the persistent empty vertical bands as column
gutters, and assigns each box a column index — then buckets rows by vertical spacing to emit a
borderless table.

Pure-stdlib over plain box dicts (no numpy needed — a difference-array projection), so it is
fully unit-testable with no image and no OCR engine. Reuses ``table_grid_fill``'s box-bounds
reader. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.table_grid_fill.table_grid_fill import _box_bounds

Box = Dict[str, Any]


def _center_x(box: Box) -> int:
    left, _, right, _ = _box_bounds(box)
    return (left + right) // 2


def _center_y(box: Box) -> int:
    _, top, _, bottom = _box_bounds(box)
    return (top + bottom) // 2


def vertical_projection(boxes: Sequence[Box], *,
                        page_width: Optional[int] = None) -> List[int]:
    """Return the per-column ink-density profile (how many boxes cover each x)."""
    bounds = [_box_bounds(box) for box in boxes]
    width = int(page_width) if page_width else max((r for _, _, r, _ in bounds),
                                                   default=0)
    diff = [0] * (width + 1)
    for left, _, right, _ in bounds:
        left, right = max(0, min(width, left)), max(0, min(width, right))
        if right > left:
            diff[left] += 1
            diff[right] -= 1
    profile, running = [], 0
    for x in range(width):
        running += diff[x]
        profile.append(running)
    return profile


def column_gutters(boxes: Sequence[Box], *, page_width: Optional[int] = None,
                   min_gap: int = 8) -> List[Dict[str, int]]:
    """Return the interior empty vertical bands (column separators) >= ``min_gap`` wide."""
    profile = vertical_projection(boxes, page_width=page_width)
    gutters: List[Dict[str, int]] = []
    start: Optional[int] = None
    for x, value in enumerate(profile):
        if value == 0:
            start = x if start is None else start
            continue
        if start is not None and start > 0 and x - start >= int(min_gap):
            gutters.append({"start": start, "end": x, "width": x - start})
        start = None
    return gutters


def _column_cuts(gutters: Sequence[Dict[str, int]]) -> List[int]:
    """Return the x mid-points of the gutters — the column boundaries."""
    return [(gutter["start"] + gutter["end"]) // 2 for gutter in gutters]


def _column_of(center_x: int, cuts: Sequence[int]) -> int:
    """Return the 0-based column index of a centre-x given the boundary cuts."""
    index = 0
    for cut in cuts:
        if center_x < cut:
            break
        index += 1
    return index


def assign_columns(boxes: Sequence[Box], *, page_width: Optional[int] = None,
                   min_gap: int = 8) -> List[Box]:
    """Return each box tagged with a ``column`` index derived from the gutters."""
    cuts = _column_cuts(column_gutters(boxes, page_width=page_width, min_gap=min_gap))
    return [dict(box, column=_column_of(_center_x(box), cuts)) for box in boxes]


def _row_gap(boxes: Sequence[Box], row_gap: Optional[int]) -> int:
    """Pick the row-split gap: caller value, or half the median box height."""
    if row_gap is not None:
        return int(row_gap)
    heights = sorted((_box_bounds(b)[3] - _box_bounds(b)[1]) for b in boxes)
    return max(1, heights[len(heights) // 2] // 2)


def _bucket_rows(boxes: Sequence[Box], gap: int) -> List[List[Box]]:
    """Group boxes into rows by vertical spacing; sort each row by column."""
    ordered = sorted(boxes, key=_center_y)
    rows: List[List[Box]] = [[ordered[0]]]
    last = _center_y(ordered[0])
    for box in ordered[1:]:
        center = _center_y(box)
        if center - last > gap:
            rows.append([box])
        else:
            rows[-1].append(box)
        last = center
    for row in rows:
        row.sort(key=lambda item: item.get("column", 0))
    return rows


def detect_borderless_table(boxes: Sequence[Box], *,
                            page_width: Optional[int] = None, min_gap: int = 8,
                            row_gap: Optional[int] = None,
                            min_cols: int = 2,
                            min_rows: int = 2) -> Optional[Dict[str, Any]]:
    """Infer a borderless table from OCR boxes, or ``None`` if it is not tabular.

    Columns come from whitespace gutters, rows from vertical spacing. Returns
    ``{n_rows, n_cols, rows:[[text]], columns:[gutter]}`` when at least ``min_cols``
    columns and ``min_rows`` rows are found.
    """
    if not boxes:
        return None
    tagged = assign_columns(boxes, page_width=page_width, min_gap=min_gap)
    n_cols = max(box["column"] for box in tagged) + 1
    if n_cols < int(min_cols):
        return None
    rows = _bucket_rows(tagged, _row_gap(tagged, row_gap))
    if len(rows) < int(min_rows):
        return None
    table = [["" for _ in range(n_cols)] for _ in rows]
    for r, row in enumerate(rows):
        for box in row:
            col = box["column"]
            table[r][col] = f'{table[r][col]} {box.get("text", "")}'.strip()
    return {"n_rows": len(rows), "n_cols": n_cols, "rows": table,
            "columns": column_gutters(boxes, page_width=page_width, min_gap=min_gap)}
