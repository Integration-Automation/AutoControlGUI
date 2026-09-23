"""Pace a screen recorder to the frame rate its file header declares.

Both recorders wrote frames as fast as capture allowed while the video header
said ``fps``: capture at 200 frames/s into a 30 fps file played two seconds
back as four, a slow capture as the opposite. :func:`record_paced` writes
exactly the frames the clock owes -- repeating the last one when capture falls
behind and waiting when it runs ahead.
"""
import math
import time
from typing import Any, Callable

from je_auto_control.utils.exception.exceptions import AutoControlScreenException


def check_fps(fps: Any) -> float:
    """``fps`` as a finite positive float, or :class:`AutoControlScreenException`."""
    try:
        value = float(fps)
    except (TypeError, ValueError) as error:
        raise AutoControlScreenException(f"fps must be a number, got {fps!r}") from error
    if not math.isfinite(value) or value <= 0:
        raise AutoControlScreenException(f"fps must be a positive number, got {fps!r}")
    return value


def record_paced(running: Callable[[], bool], grab: Callable[[], Any],
                 write: Callable[[Any], None], fps: float, *,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> int:
    """Capture with ``grab`` and ``write`` frames at ``fps`` while ``running()``; return the count.

    The frame count tracks wall time, so the file plays back as long as the
    recording lasted.
    """
    interval = 1.0 / check_fps(fps)
    start = clock()
    written = 0
    while running():
        frame = grab()
        owed = int((clock() - start) / interval) + 1
        while written < owed:
            write(frame)
            written += 1
        remaining = start + written * interval - clock()
        # Short steps so a stop is noticed within 50 ms at any frame rate.
        while remaining > 0 and running():
            sleep(min(remaining, 0.05))
            remaining = start + written * interval - clock()
    return written
