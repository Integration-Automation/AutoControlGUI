"""Validated native-point mobile gestures independent of optional SDKs."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Literal, Mapping, Any, Optional, TYPE_CHECKING

from je_auto_control.wrapper._mobile_models import DeviceSessionError

Point = tuple[float, float]

if TYPE_CHECKING:
    from je_auto_control.wrapper.device_frame import DeviceFrame


def finite_point(value: Point) -> Point:
    """Freeze a finite nonnegative coordinate pair without relative SDK semantics."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise DeviceSessionError('gesture point must contain two coordinates')
    if any(isinstance(item, bool) or not isinstance(item, (int, float))
           or not math.isfinite(item) or item < 0 for item in value):
        raise DeviceSessionError('gesture coordinates must be finite and nonnegative')
    return float(value[0]), float(value[1])


@dataclass(frozen=True)
class Gesture:
    """Native device points; pinch order is start1, start2, end1, end2.

    Use DeviceFrame.pixel_to_point for screenshot pixels. Duration is hold/drag
    time for WDA and motion time for Android; those backend semantics differ.
    """

    kind: Literal['tap', 'long_press', 'swipe', 'drag', 'pinch']
    points: tuple[Point, ...]
    duration_s: float = 0.5
    frame: Optional[DeviceFrame] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        count = ({'tap': 1, 'long_press': 1, 'swipe': 2, 'drag': 2, 'pinch': 4}.get(self.kind)
                 if isinstance(self.kind, str) else None)
        if count is None or not isinstance(self.points, (list, tuple)) or len(self.points) != count:
            raise DeviceSessionError('gesture kind/point count is invalid')
        object.__setattr__(self, 'points', tuple(finite_point(point) for point in self.points))
        if (isinstance(self.duration_s, bool) or not isinstance(self.duration_s, (float, int))
                or not math.isfinite(self.duration_s) or not 0 < self.duration_s <= 300):
            raise DeviceSessionError('gesture duration must be finite, positive and at most 300 seconds')
        _validate_frame_reference(self.frame)

    @classmethod
    def from_spec(cls, spec: Mapping[str, Any]) -> Gesture:
        """Validate one JSON gesture rather than silently dropping unknown fields."""
        if not isinstance(spec, Mapping) or set(spec) - {'kind', 'points', 'duration_s'}:
            raise DeviceSessionError('gesture must be an object with kind, points and optional duration_s')
        return cls(spec.get('kind', ''), spec.get('points', ()), spec.get('duration_s', .5))


def _validate_frame_reference(frame: Optional[DeviceFrame]) -> None:
    if frame is not None:
        # pylint: disable-next=import-outside-toplevel  # reason: validate optional frame without a model import cycle
        from je_auto_control.wrapper.device_frame import DeviceFrame
        if not isinstance(frame, DeviceFrame):
            raise DeviceSessionError('gesture frame must be an immutable DeviceFrame')
