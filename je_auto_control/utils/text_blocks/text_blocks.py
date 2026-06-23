"""Group OCR lines into paragraphs and bulleted / numbered lists.

``text_regions.find_text_lines`` merges glyphs into lines, but nothing groups those *lines*
into paragraphs or detects lists — ``ocr/structure`` stops at flat rows. ``text_blocks`` adds
that: ``group_paragraphs`` splits lines into paragraphs wherever the vertical gap exceeds a
multiple of the median line height (the standard whitespace-grouping heuristic), and
``detect_lists`` recognises bulleted / numbered items by their leading marker and left indent.

Pure-stdlib over plain line dicts (text + bbox); fully unit-testable with no image and no OCR
engine. Reuses ``table_grid_fill``'s box-bounds reader. Imports no ``PySide6``.
"""
import re
from typing import Any, Dict, List, Sequence

from je_auto_control.utils.table_grid_fill.table_grid_fill import _box_bounds

Line = Dict[str, Any]

_MARKER = re.compile(r"^\s*([•‣◦\-\*]|\d+[.)]|[A-Za-z][.)])\s+")


def _height(line: Line) -> int:
    _, top, _, bottom = _box_bounds(line)
    return bottom - top


def _make_paragraph(lines: Sequence[Line]) -> Dict[str, Any]:
    """Build a paragraph dict (union bbox + joined text) from its lines."""
    bounds = [_box_bounds(line) for line in lines]
    left = min(b[0] for b in bounds)
    top = min(b[1] for b in bounds)
    right = max(b[2] for b in bounds)
    bottom = max(b[3] for b in bounds)
    text = " ".join(str(line.get("text", "")).strip() for line in lines).strip()
    return {"left": left, "top": top, "right": right, "bottom": bottom,
            "text": text, "n_lines": len(lines)}


def group_paragraphs(lines: Sequence[Line], *,
                     line_gap_factor: float = 1.6) -> List[Dict[str, Any]]:
    """Group lines into paragraphs, splitting where the vertical gap is large.

    A new paragraph starts when the gap from the previous line's bottom exceeds
    ``line_gap_factor`` times the median line height. Returns paragraph dicts
    (``left`` / ``top`` / ``right`` / ``bottom`` / ``text`` / ``n_lines``).
    """
    ordered = sorted(lines, key=lambda line: _box_bounds(line)[1])
    if not ordered:
        return []
    heights = sorted(_height(line) for line in ordered)
    threshold = heights[len(heights) // 2] * float(line_gap_factor)
    paragraphs: List[List[Line]] = [[ordered[0]]]
    prev_bottom = _box_bounds(ordered[0])[3]
    for line in ordered[1:]:
        top, bottom = _box_bounds(line)[1], _box_bounds(line)[3]
        if top - prev_bottom > threshold:
            paragraphs.append([line])
        else:
            paragraphs[-1].append(line)
        prev_bottom = bottom
    return [_make_paragraph(group) for group in paragraphs]


def detect_lists(lines: Sequence[Line]) -> List[Dict[str, Any]]:
    """Return the lines that are list items: ``{text, marker, indent, box}``.

    A line is a list item when its text starts with a bullet (``•`` / ``-`` / ``*``)
    or an ordinal (``1.`` / ``2)`` / ``a.``); ``indent`` is its left x (for nesting),
    ``text`` is the content after the marker.
    """
    items: List[Dict[str, Any]] = []
    for line in lines:
        text = str(line.get("text", ""))
        match = _MARKER.match(text)
        if match is None:
            continue
        left, top, right, bottom = _box_bounds(line)
        items.append({"text": text[match.end():].strip(),
                      "marker": match.group(1), "indent": left,
                      "box": {"left": left, "top": top, "right": right,
                              "bottom": bottom}})
    return items
