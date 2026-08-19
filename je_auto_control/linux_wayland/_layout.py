"""The output layout's origin, for the input paths that must translate into it.

Capture and input do not share a coordinate space on Wayland, and the gap is
the layout origin: :func:`je_auto_control.linux_wayland.screen.grab_image`
returns the whole output layout, whose top-left pixel is
:func:`~je_auto_control.linux_wayland.screen.layout_origin` and only ``(0, 0)``
while every output sits at a non-negative position. Put a monitor left of the
primary one and the origin goes negative, while both input transports address
a space that starts at that corner:

* libei advertises regions with ``uint32`` offsets, so it *cannot* describe a
  point left of or above the origin;
* ``ydotool mousemove --absolute`` drives the cursor into the corner the
  compositor clamps to and then moves relative to it, and that corner is the
  layout's top-left.

Both therefore need the same subtraction, which is why it lives here rather
than in either of them. It is a separate module because
:mod:`je_auto_control.linux_wayland.screen` imports Pillow at module scope and
the input paths must keep working on a host without it — a missing capture
tool means no correction, never a failed move.
"""
from __future__ import annotations

import time
from typing import Dict, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException

#: How long a reading stays good for.
#:
#: :mod:`je_auto_control.linux_wayland.screen` deliberately caches nothing —
#: an output can move between two captures and a stale layout is worse than
#: the ``shutil.which`` miss it costs. That reasoning does not survive the move
#: to the input path: the ydotool backend consults this on *every* absolute
#: move, so an uncached lookup spawns a ``wlr-randr`` process per move and
#: doubles the cost of a path that already spawns one. A window this short is
#: orders of magnitude below any real monitor rearrangement and orders of
#: magnitude above the gap between two moves in a drag.
_CACHE_SECONDS = 1.0

#: ``{"origin": (monotonic_stamp, (x, y))}``. A dict rather than a pair of
#: module globals so refreshing it needs no ``global`` statement.
_CACHE: Dict[str, Tuple[float, Tuple[int, int]]] = {}


def layout_origin() -> Tuple[int, int]:
    """Return the layout coordinate of the capture's top-left pixel.

    ``(0, 0)`` whenever the answer cannot be obtained — no ``wlr-randr``, no
    Pillow, no capture tool — which is also the correct answer for every
    layout those hosts are likely to have, and leaves the caller sending the
    coordinate it would have sent before this translation existed.

    Cached for :data:`_CACHE_SECONDS`; see there for why this one caches and
    the capture path does not.

    :return: (origin_x, origin_y)
    """
    now = time.monotonic()
    cached = _CACHE.get("origin")
    if cached is not None and now - cached[0] < _CACHE_SECONDS:
        return cached[1]
    origin = _read_layout_origin()
    _CACHE["origin"] = (now, origin)
    return origin


def _read_layout_origin() -> Tuple[int, int]:
    """Ask the screen backend, tolerating every way it can be unavailable."""
    try:
        from je_auto_control.linux_wayland import screen
        return screen.layout_origin()
    except (ImportError, OSError, AutoControlException):
        return (0, 0)


def reset_cache() -> None:
    """Drop the cached reading, so the next call measures again."""
    _CACHE.clear()


__all__ = ["layout_origin", "reset_cache"]
