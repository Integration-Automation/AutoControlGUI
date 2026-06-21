"""Time-series transforms over ``(timestamp, value)`` sequences.

``observability`` counters/gauges store only the *current* value — nothing turns
a counter into a per-second rate, and ``cost_telemetry`` only buckets by a fixed
day. This adds Prometheus-style ``rate`` / ``irate`` / ``increase`` / ``delta``
(reset-aware) plus tumbling-bucket ``downsample`` and grid ``resample``.

Pure standard library (``bisect``); imports no ``PySide6``. No wall clock is
read — windows use the series' own timestamps — so every function is fully
deterministic in CI.
"""
import bisect
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

Point = Tuple[float, float]
Series = Sequence[Point]

_AGGS: Dict[str, Callable[[List[float]], float]] = {
    "avg": lambda values: sum(values) / len(values),
    "sum": sum,
    "min": min,
    "max": max,
    "first": lambda values: values[0],
    "last": lambda values: values[-1],
    "count": len,
}


def _sorted(series: Series) -> List[Point]:
    return sorted((float(ts), float(value)) for ts, value in series)


def ts_increase(series: Series) -> float:
    """Total counter increase over the series, treating drops as resets."""
    points = _sorted(series)
    if len(points) < 2:
        return 0.0
    total = 0.0
    previous = points[0][1]
    for _, value in points[1:]:
        total += (value - previous) if value >= previous else value
        previous = value
    return total


def ts_rate(series: Series, *, window_s: Optional[float] = None) -> float:
    """Per-second rate of a monotonic counter (reset-aware), over an optional window."""
    points = _sorted(series)
    if window_s is not None and points:
        cutoff = points[-1][0] - window_s
        points = [point for point in points if point[0] >= cutoff]
    if len(points) < 2:
        return 0.0
    span = points[-1][0] - points[0][0]
    return ts_increase(points) / span if span > 0 else 0.0


def ts_irate(series: Series) -> float:
    """Instant per-second rate from the last two samples (reset-aware)."""
    points = _sorted(series)
    if len(points) < 2:
        return 0.0
    (time_a, value_a), (time_b, value_b) = points[-2], points[-1]
    span = time_b - time_a
    if span <= 0:
        return 0.0
    increase = (value_b - value_a) if value_b >= value_a else value_b
    return increase / span


def ts_delta(series: Series) -> float:
    """First-to-last difference (for gauges)."""
    points = _sorted(series)
    return (points[-1][1] - points[0][1]) if len(points) >= 2 else 0.0


def ts_idelta(series: Series) -> float:
    """Difference of the last two samples (for gauges)."""
    points = _sorted(series)
    return (points[-1][1] - points[-2][1]) if len(points) >= 2 else 0.0


def ts_downsample(series: Series, bucket_s: float,
                  agg: str = "avg") -> List[Point]:
    """Roll the series into ``bucket_s`` tumbling buckets aggregated by ``agg``."""
    if bucket_s <= 0:
        raise ValueError("bucket_s must be positive")
    func = _AGGS.get(agg)
    if func is None:
        raise ValueError(f"unknown agg: {agg!r}")
    buckets: Dict[float, List[float]] = {}
    for ts, value in _sorted(series):
        start = (ts // bucket_s) * bucket_s
        buckets.setdefault(start, []).append(value)
    return [(start, float(func(values)))
            for start, values in sorted(buckets.items())]


def _value_at(times: List[float], values: List[float], at: float,
              fill: Optional[str]) -> Optional[float]:
    index = bisect.bisect_right(times, at) - 1
    if index < 0:
        return values[0] if fill in ("last", "linear") else None
    if times[index] == at or fill == "last":
        return values[index]
    if fill == "linear" and index + 1 < len(times):
        time_0, value_0 = times[index], values[index]
        time_1, value_1 = times[index + 1], values[index + 1]
        return value_0 + (value_1 - value_0) * (at - time_0) / (time_1 - time_0)
    if fill == "linear":
        return values[index]
    return None


def ts_resample(series: Series, bucket_s: float, *,
                fill: Optional[str] = "last") -> List[Tuple[float, Any]]:
    """Align the series to a fixed ``bucket_s`` grid, filling per ``fill``.

    ``fill`` is ``"last"`` (carry forward), ``"linear"`` (interpolate), or
    ``None`` (gaps become ``None``).
    """
    if bucket_s <= 0:
        raise ValueError("bucket_s must be positive")
    points = _sorted(series)
    if not points:
        return []
    times = [point[0] for point in points]
    values = [point[1] for point in points]
    start = (times[0] // bucket_s) * bucket_s
    steps = int((times[-1] - start) // bucket_s) + 1
    return [(start + index * bucket_s,
             _value_at(times, values, start + index * bucket_s, fill))
            for index in range(steps)]
