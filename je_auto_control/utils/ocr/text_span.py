"""Match a target that OCR split across several word boxes on one line.

Engines return one box per *word*, so ``另存新檔`` comes back as ``另存`` +
``新檔`` and ``Save As`` as ``Save`` + ``As``. Comparing the target against one
box at a time therefore misses every target that crosses a word boundary — which
is most real menu items and button labels, and the failure is silent: the caller
just gets "text not found" for text plainly on the screen.

The logic here is pure and backend-agnostic. Boxes are grouped into lines by
vertical overlap rather than by an engine-supplied line id, because not every
backend reports one. Within a line, the shortest run of consecutive boxes whose
concatenation contains the target wins. Whitespace is dropped from both sides
before comparing: where the engine chooses to split is arbitrary, so it must not
decide whether a match exists. Imports no ``PySide6``.
"""
import re
from typing import Any, List, Optional, Sequence, Tuple

# How far apart two boxes' vertical centres may be, as a fraction of the shorter
# box's height, and still count as the same line. Generous enough for mixed font
# sizes in one row (an icon label next to a heading), tight enough that the row
# above does not bleed in.
LINE_TOLERANCE = 0.6

# Give up extending a run once it is this many characters longer than the target
# — beyond that the run cannot become a *shortest* match, and a long line would
# otherwise cost O(words²) concatenations.
MAX_OVERSHOOT = 40

_WHITESPACE = re.compile(r"\s+")


def normalize(text: str, case_sensitive: bool = False) -> str:
    """Strip all whitespace (and case, by default) for comparison."""
    stripped = _WHITESPACE.sub("", text or "")
    return stripped if case_sensitive else stripped.lower()


def same_line(first: Any, second: Any,
              tolerance: float = LINE_TOLERANCE) -> bool:
    """Whether two boxes sit on the same text line, by vertical overlap."""
    first_centre = first.y + first.height / 2.0
    second_centre = second.y + second.height / 2.0
    shorter = max(1.0, float(min(first.height, second.height)))
    return abs(first_centre - second_centre) <= tolerance * shorter


def group_lines(boxes: Sequence[Any],
                tolerance: float = LINE_TOLERANCE) -> List[List[Any]]:
    """Group boxes into lines, each sorted left to right."""
    lines: List[List[Any]] = []
    for box in sorted(boxes, key=lambda item: (item.y, item.x)):
        for line in lines:
            if same_line(line[-1], box, tolerance):
                line.append(box)
                break
        else:
            lines.append([box])
    return [sorted(line, key=lambda item: item.x) for line in lines]


def _joined(line: Sequence[Any], start: int, end: int,
            case_sensitive: bool) -> str:
    """Concatenated, normalized text of ``line[start:end + 1]``."""
    return "".join(normalize(box.text, case_sensitive)
                   for box in line[start:end + 1])


def _shrink_left(line: Sequence[Any], start: int, end: int, needle: str,
                 case_sensitive: bool) -> int:
    """Advance ``start`` while the run still contains ``needle``.

    Without this the run is merely *a* match, not the *shortest* one: searching
    "Save As" in ``File | Save | As`` would report the whole line and click its
    centre — on "Save" if you are lucky, on nothing if you are not.
    """
    while start < end and needle in _joined(line, start + 1, end, case_sensitive):
        start += 1
    return start


def _next_span(line: Sequence[Any], index: int, needle: str,
               case_sensitive: bool) -> Optional[Tuple[int, int]]:
    """First ``(start, end)`` run at or after ``index`` that spells ``needle``."""
    accumulated = ""
    for end in range(index, len(line)):
        accumulated += normalize(line[end].text, case_sensitive)
        if needle in accumulated:
            return _shrink_left(line, index, end, needle, case_sensitive), end
        if len(accumulated) > len(needle) + MAX_OVERSHOOT:
            # This start can no longer produce a shortest match; drop the
            # leftmost box and keep scanning instead of restarting the line.
            index += 1
            accumulated = _joined(line, index, end, case_sensitive)
    return None


def find_spans(boxes: Sequence[Any], target: str,
               case_sensitive: bool = False,
               tolerance: float = LINE_TOLERANCE) -> List[List[Any]]:
    """Return every run of consecutive same-line boxes that spells ``target``.

    Runs are minimal, and a single box that already contains the target comes
    back as a one-box run — so this is a superset of per-box matching.
    """
    needle = normalize(target, case_sensitive)
    if not needle:
        return []
    spans: List[List[Any]] = []
    for line in group_lines(boxes, tolerance):
        index = 0
        while index < len(line):
            found = _next_span(line, index, needle, case_sensitive)
            if found is None:
                break
            start, end = found
            spans.append(list(line[start:end + 1]))
            # Resume after the run so one hit is not reported again from a
            # later start inside it.
            index = end + 1
    return spans
