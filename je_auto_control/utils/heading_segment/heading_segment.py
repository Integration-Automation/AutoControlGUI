"""Classify OCR lines as headings vs body and build a document outline.

Nothing in the framework maps line height to heading levels or builds a section outline —
``ocr/structure`` and ``element_parse`` are purely positional, and ``text_blocks`` groups
paragraphs / lists but does not rank them. ``heading_segment`` adds the standard heuristic:
a line whose height exceeds ``heading_ratio`` times the median line height is a heading, and
distinct heading heights become heading *levels* (the tallest is level 1). From that it emits
a flat document outline.

Pure-stdlib over plain line dicts (text + bbox); fully unit-testable with no image and no OCR
engine. Reuses ``table_grid_fill``'s box-bounds reader. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Sequence

from je_auto_control.utils.table_grid_fill.table_grid_fill import _box_bounds

Line = Dict[str, Any]


def _height(line: Line) -> int:
    _, top, _, bottom = _box_bounds(line)
    return bottom - top


def _box(line: Line) -> Dict[str, int]:
    left, top, right, bottom = _box_bounds(line)
    return {"left": left, "top": top, "right": right, "bottom": bottom}


def classify_lines(lines: Sequence[Line], *,
                   heading_ratio: float = 1.2) -> List[Dict[str, Any]]:
    """Tag each line as a heading or body line with a heading ``level``.

    A line taller than ``heading_ratio`` x the median line height is a heading; distinct
    heading heights map to levels (tallest = 1). Body lines get ``level`` 0. Returns
    ``{box, text, role, level}`` per line, in input order.
    """
    if not lines:
        return []
    heights = sorted(_height(line) for line in lines)
    threshold = heights[len(heights) // 2] * float(heading_ratio)
    heading_heights = sorted({_height(line) for line in lines
                              if _height(line) > threshold}, reverse=True)
    level_of = {height: index + 1 for index, height in enumerate(heading_heights)}
    classified: List[Dict[str, Any]] = []
    for line in lines:
        height = _height(line)
        is_heading = height > threshold
        classified.append({"box": _box(line),
                           "text": str(line.get("text", "")),
                           "role": "heading" if is_heading else "body",
                           "level": level_of.get(height, 0) if is_heading else 0})
    return classified


def outline(lines: Sequence[Line], *,
            heading_ratio: float = 1.2) -> List[Dict[str, Any]]:
    """Return the document outline: the headings in top-to-bottom order with levels."""
    headings = [item for item in classify_lines(lines, heading_ratio=heading_ratio)
                if item["role"] == "heading"]
    headings.sort(key=lambda item: item["box"]["top"])
    return [{"level": item["level"], "text": item["text"],
             "top": item["box"]["top"]} for item in headings]
