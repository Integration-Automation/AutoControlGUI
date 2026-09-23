"""Turn user-supplied timeouts and poll intervals into safe values."""
import math
from typing import Any


def deadline_after(start: float, timeout: Any, name: str = "timeout") -> float:
    """``start + timeout`` as a float; raise ``ValueError`` for a NaN timeout.

    Timeouts arrive from action JSON and MCP arguments, and Python's ``json``
    accepts ``NaN``. ``start + NaN`` is NaN, so a ``clock() >= deadline``
    check is never true and a ``while True`` poll loop never ends. Negative
    and infinite timeouts keep their meaning (look once / wait forever).
    """
    seconds = float(timeout)
    if math.isnan(seconds):
        raise ValueError(f"{name} must be a number, not NaN")
    return start + seconds


#: Longest poll interval a background loop accepts; an infinite one lands here.
MAX_POLL_INTERVAL_S = 3600.0


def clamp_poll_interval(seconds: Any, floor: float = 0.05) -> float:
    """Clamp a poll interval into ``[floor, MAX_POLL_INTERVAL_S]``; NaN gives ``floor``.

    ``Event.wait(inf)`` raises ``OverflowError`` on Windows, which killed a
    poll thread after its first pass; ``max(floor, inf)`` let it through.
    """
    value = float(seconds)
    if math.isnan(value):
        return floor
    return min(max(floor, value), MAX_POLL_INTERVAL_S)
