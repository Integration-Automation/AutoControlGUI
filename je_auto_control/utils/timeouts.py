"""Turn a user-supplied timeout into a deadline, refusing NaN."""
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
