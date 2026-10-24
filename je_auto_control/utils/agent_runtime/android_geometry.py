"""Exact half-open Android touch-region coverage for whole pointer paths, including swipe interiors."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from je_auto_control.utils.agent_runtime.errors import AgentTaskError

Point = tuple[int, int]


@dataclass(frozen=True)
class _Interval:
    low: Fraction
    high: Fraction
    left: bool = True
    right: bool = True

    def intersect(self, other: _Interval) -> _Interval | None:
        """Intersect parameter intervals while preserving open native edges."""
        low, high = max(self.low, other.low), min(self.high, other.high)
        left = (self.low != low or self.left) and (other.low != low or other.left)
        right = (self.high != high or self.right) and (other.high != high or other.right)
        value = _Interval(low, high, left, right)
        return None if value.empty() else value

    def empty(self) -> bool:
        """Return whether no parameter, including a single shared endpoint, remains."""
        return self.low > self.high or (self.low == self.high and not (self.left and self.right))

    def complete(self) -> bool:
        """Report coverage through the final endpoint of the pointer path."""
        return self.high == 1 and self.right


def _axis(start: int, end: int, low: int, high: int) -> _Interval | None:
    if start == end:
        return _Interval(Fraction(0), Fraction(1)) if low <= start < high else None
    distance = end - start
    if distance > 0:
        return _Interval(Fraction(low - start, distance), Fraction(high - start, distance), True, False)
    return _Interval(Fraction(high - start, distance), Fraction(low - start, distance), False, True)


@dataclass(frozen=True)
class AndroidRect:
    """Native logical coordinates use closed left/top and open right/bottom edges."""

    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        values = (self.left, self.top, self.right, self.bottom)
        if any(isinstance(value, bool) or not isinstance(value, int) or not -2**31 <= value <= 2**31 - 1
               for value in values):
            raise AgentTaskError("Android rectangle contains invalid native coordinates")
        if self.left > self.right or self.top > self.bottom:
            raise AgentTaskError("Android rectangle edges are reversed")

    def path(self, start: Point, end: Point) -> _Interval | None:
        """Return the exact parameter interval where a segment lies inside this rectangle."""
        result: _Interval | None = _Interval(Fraction(0), Fraction(1))
        for first, last, low, high in ((start[0], end[0], self.left, self.right),
                                       (start[1], end[1], self.top, self.bottom)):
            axis = _axis(first, last, low, high)
            if axis is None or result is None:
                return None
            result = result.intersect(axis)
        return result


def _join(first: _Interval, second: _Interval) -> _Interval | None:
    if second.low > first.high or (second.low == first.high and not (first.right or second.left)):
        return None
    if second.high < first.high:
        return first
    right = second.right if second.high > first.high else first.right or second.right
    return _Interval(first.low, second.high, first.left, right)


def covers_android_path(regions: tuple[AndroidRect, ...], start: Point, end: Point) -> bool:
    """Require all points, rather than just endpoints or finite samples, inside the region union."""
    parts = [part for rect in regions if (part := rect.path(start, end)) is not None]
    if not parts:
        return False
    parts.sort(key=lambda value: (value.low, not value.left))
    current = parts[0]
    if current.low != 0 or not current.left:
        return False
    for part in parts[1:]:
        if current.complete():
            return True
        joined = _join(current, part)
        if joined is None:
            return False
        current = joined
    return current.complete()
