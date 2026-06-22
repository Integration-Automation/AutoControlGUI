"""Moving-average smoothing for noisy value series.

``stats.describe`` summarises a whole sample and ``timeseries`` rolls counters
into rates, but nothing smooths a noisy signal or weights recent points. This
adds trailing simple / weighted / exponentially-weighted moving averages and a
generic rolling reducer, e.g. for a ``resource_profiler`` FPS/CPU timeline.

Pure standard library; imports no ``PySide6``. Every function is pure (values
in, list out), so it is fully deterministic in CI.
"""
from typing import Callable, List, Sequence


def sma(values: Sequence[float], window: int) -> List[float]:
    """Trailing simple moving average over the last ``window`` points."""
    if window <= 0:
        raise ValueError("window must be positive")
    out: List[float] = []
    for i in range(len(values)):
        chunk = values[max(0, i - window + 1):i + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def wma(values: Sequence[float], weights: Sequence[float]) -> List[float]:
    """Trailing weighted moving average; ``weights`` align to the latest points."""
    weight_list = list(weights)
    if not weight_list:
        raise ValueError("weights must be non-empty")
    out: List[float] = []
    for i in range(len(values)):
        chunk = values[max(0, i - len(weight_list) + 1):i + 1]
        applied = weight_list[-len(chunk):]
        out.append(sum(x * w for x, w in zip(chunk, applied)) / sum(applied))
    return out


def ewma(values: Sequence[float], *, alpha: float) -> List[float]:
    """Exponentially-weighted moving average (smoothing factor ``alpha``)."""
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    out: List[float] = []
    previous = None
    for value in values:
        previous = value if previous is None else alpha * value + (
            1 - alpha) * previous
        out.append(previous)
    return out


def rolling(values: Sequence[float], window: int,
            func: Callable[[Sequence[float]], float]) -> List[float]:
    """Apply ``func`` over each trailing window of size ``window``."""
    if window <= 0:
        raise ValueError("window must be positive")
    return [func(values[max(0, i - window + 1):i + 1])
            for i in range(len(values))]
