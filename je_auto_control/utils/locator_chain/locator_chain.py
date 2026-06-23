"""Composable / filtered candidate locators — Playwright-style chained locators.

``anchor_locator`` resolves a single anchor→target relation and ``grid_locator``
addresses grid cells; neither supports *composable refinement* of a candidate set —
``.within(panel).filter(has_text="Delete").nth(2)`` — the Selenium-4 / Playwright
chained-and-filtered locator idiom. Today refining means re-querying a backend; this is
a pure post-filter over boxes from *any* source (template / OCR / a11y).

A ``Candidates`` wraps a list of ``{x, y, width, height, ...}`` boxes; every method
returns a new ``Candidates`` so chains are side-effect-free and fully unit-testable.
Pure-stdlib, imports no ``PySide6``.
"""
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

Box = Dict[str, Any]


def _center(box: Box) -> List[int]:
    return [int(box["x"]) + int(box["width"]) // 2,
            int(box["y"]) + int(box["height"]) // 2]


def _area(box: Box) -> int:
    return int(box["width"]) * int(box["height"])


class Candidates:
    """An immutable, chainable set of element boxes."""

    def __init__(self, boxes: Sequence[Box]):
        self._boxes: List[Box] = [dict(box) for box in boxes]

    def __iter__(self):
        return iter(self._boxes)

    def __len__(self) -> int:
        return len(self._boxes)

    def resolve(self) -> List[Box]:
        """Return the surviving boxes as a list."""
        return list(self._boxes)

    def center(self) -> Optional[List[int]]:
        """Return the centre of the first surviving box (or ``None``)."""
        return _center(self._boxes[0]) if self._boxes else None

    def within(self, region: Sequence[int]) -> "Candidates":
        """Keep boxes whose centre falls inside ``region`` ``(x, y, w, h)``."""
        rx, ry, rw, rh = (int(value) for value in region[:4])
        kept = [box for box in self._boxes
                if rx <= _center(box)[0] <= rx + rw
                and ry <= _center(box)[1] <= ry + rh]
        return Candidates(kept)

    def filter(self, *, has_text: Optional[str] = None,
               near: Optional[Tuple[int, int, float]] = None,
               min_area: Optional[int] = None, max_area: Optional[int] = None,
               predicate: Optional[Callable[[Box], bool]] = None) -> "Candidates":
        """Keep boxes matching every supplied criterion.

        ``has_text`` substring (case-insensitive) of the box ``text``; ``near``
        ``(x, y, max_dist)`` centre proximity; ``min_area`` / ``max_area`` size;
        ``predicate`` an arbitrary callable.
        """
        checks: List[Callable[[Box], bool]] = []
        if has_text is not None:
            needle = str(has_text).lower()
            checks.append(lambda b: needle in str(b.get("text", "")).lower())
        if near is not None:
            nx, ny, dist = near
            checks.append(
                lambda b: math.hypot(_center(b)[0] - nx, _center(b)[1] - ny) <= dist)
        if min_area is not None:
            low = int(min_area)
            checks.append(lambda b: _area(b) >= low)
        if max_area is not None:
            high = int(max_area)
            checks.append(lambda b: _area(b) <= high)
        if predicate is not None:
            checks.append(predicate)
        return Candidates([b for b in self._boxes if all(c(b) for c in checks)])

    def sort_reading(self, row_tol: int = 12) -> "Candidates":
        """Order the boxes top-to-bottom, left-to-right (reuses element_parse)."""
        from je_auto_control.utils.element_parse import reading_order
        return Candidates(reading_order(self._boxes, row_tol=int(row_tol)))

    def nth(self, index: int) -> "Candidates":
        """Keep only the box at ``index`` (negative allowed), else empty."""
        if -len(self._boxes) <= index < len(self._boxes):
            return Candidates([self._boxes[index]])
        return Candidates([])

    def first(self) -> "Candidates":
        """Keep only the first box."""
        return self.nth(0)

    def last(self) -> "Candidates":
        """Keep only the last box."""
        return self.nth(-1)


def from_boxes(boxes: Sequence[Box]) -> Candidates:
    """Wrap a list of element boxes in a :class:`Candidates` for chaining."""
    return Candidates(boxes)
