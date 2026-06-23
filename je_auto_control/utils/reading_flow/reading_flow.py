"""Column-aware reading order via recursive XY-cut.

``element_parse.reading_order`` is a flat top-to-bottom / left-to-right sort — it interleaves
columns on any multi-column page (the well-documented naive-sort failure: it reads row 1 of
column A, then row 1 of column B, then row 2 of A …). ``reading_flow`` recovers the correct
order with recursive XY-cut: it repeatedly splits the boxes at the widest whitespace valley
(vertical gutter → columns, horizontal gutter → rows/blocks), so a two-column layout is read
*down* column A fully, then column B. It returns the region tree and a column-aware flattened
order; the public flattener is named ``flow_order`` to sit beside (not shadow)
``reading_order``.

Pure-stdlib geometry over plain box dicts (no image, no OCR engine); reuses ``table_grid_fill``'s
box-bounds reader. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.table_grid_fill.table_grid_fill import _box_bounds

Box = Dict[str, Any]


def _axis_bounds(box: Box, axis: str) -> Tuple[int, int]:
    left, top, right, bottom = _box_bounds(box)
    return (left, right) if axis == "x" else (top, bottom)


def _center_on(box: Box, axis: str) -> float:
    low, high = _axis_bounds(box, axis)
    return (low + high) / 2.0


def _widest_gap(boxes: Sequence[Box], axis: str, min_gap: int):
    """Return ``(position, width)`` of the widest whitespace gap on ``axis``, or ``None``."""
    spans = sorted(_axis_bounds(box, axis) for box in boxes)
    best_pos: Optional[float] = None
    best_gap = 0.0
    cur_end = spans[0][1]
    for low, high in spans[1:]:
        gap = low - cur_end
        if gap > best_gap:
            best_gap, best_pos = gap, cur_end + gap / 2.0
        cur_end = max(cur_end, high)
    if best_pos is not None and best_gap >= min_gap:
        return best_pos, best_gap
    return None


def _choose_axis(boxes: Sequence[Box], min_gap: int):
    """Return ``(axis, position)`` of the widest gap across both axes, or ``None``."""
    candidates = []
    for axis in ("x", "y"):
        found = _widest_gap(boxes, axis, min_gap)
        if found is not None:
            candidates.append((found[1], axis, found[0]))
    if not candidates:
        return None
    _, axis, position = max(candidates)
    return axis, position


def _cut(boxes: List[Box], min_gap: int, depth: int) -> Dict[str, Any]:
    """Recursively XY-cut ``boxes`` into a region tree."""
    if len(boxes) <= 1 or depth <= 0:
        return {"type": "leaf", "boxes": list(boxes)}
    chosen = _choose_axis(boxes, min_gap)
    if chosen is None:
        return {"type": "leaf", "boxes": list(boxes)}
    axis, position = chosen
    first = [box for box in boxes if _center_on(box, axis) < position]
    second = [box for box in boxes if _center_on(box, axis) >= position]
    if not first or not second:
        return {"type": "leaf", "boxes": list(boxes)}
    return {"type": "split", "axis": axis,
            "children": [_cut(first, min_gap, depth - 1),
                         _cut(second, min_gap, depth - 1)]}


def xy_cut(boxes: Sequence[Box], *, min_gap: int = 12,
           max_depth: int = 8) -> Dict[str, Any]:
    """Return the recursive XY-cut region tree of ``boxes``."""
    if not boxes:
        return {"type": "leaf", "boxes": []}
    return _cut(list(boxes), int(min_gap), int(max_depth))


def _flatten(tree: Dict[str, Any]) -> List[Box]:
    if tree["type"] == "leaf":
        return sorted(tree["boxes"],
                      key=lambda b: (_box_bounds(b)[1], _box_bounds(b)[0]))
    flat: List[Box] = []
    for child in tree["children"]:
        flat.extend(_flatten(child))
    return flat


def flow_order(boxes: Sequence[Box], *, min_gap: int = 12,
               max_depth: int = 8) -> List[Box]:
    """Return ``boxes`` in column-aware reading order, each tagged with an ``index``."""
    flat = _flatten(xy_cut(boxes, min_gap=min_gap, max_depth=max_depth))
    return [dict(box, index=i) for i, box in enumerate(flat)]


def to_blocks(tree: Dict[str, Any]) -> List[List[Box]]:
    """Return the leaf blocks of an XY-cut ``tree`` in reading order."""
    if tree["type"] == "leaf":
        if not tree["boxes"]:
            return []
        return [sorted(tree["boxes"],
                       key=lambda b: (_box_bounds(b)[1], _box_bounds(b)[0]))]
    blocks: List[List[Box]] = []
    for child in tree["children"]:
        blocks.extend(to_blocks(child))
    return blocks
