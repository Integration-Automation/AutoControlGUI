"""Multi-monitor / virtual-desktop geometry — which monitor, where, and remapping.

``snap_window`` / ``arrange_grid`` / the layout planner all take a single primary
``(width, height)`` — they are monitor-blind and cannot tile on the second display
or handle a negative-origin virtual desktop, and ``coordinate_space`` only rescales
a model grid. This adds the missing physical layer: enumerate the monitors, find the
union virtual bounds, ask which monitor contains a point or a window, convert between
virtual and per-monitor-local coordinates, and remap a point to the equivalent spot
on another monitor.

The geometry is pure arithmetic over plain ``Monitor`` dataclasses, so it is fully
unit-testable; only ``enumerate_monitors``' default provider touches the OS (and it
is injectable). Imports no ``PySide6``.
"""
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

Rect = Tuple[int, int, int, int]
MonitorRows = Callable[[], List[Dict[str, Any]]]


@dataclass(frozen=True)
class Monitor:
    """One display: virtual-desktop origin ``(x, y)``, size, DPI ``scale``, primary."""

    index: int
    x: int
    y: int
    width: int
    height: int
    scale: float = 1.0
    primary: bool = False
    work_area: Optional[Rect] = None

    @property
    def bounds(self) -> Rect:
        """Full monitor rectangle ``(x, y, width, height)`` in virtual coordinates."""
        return (self.x, self.y, self.width, self.height)

    @property
    def work(self) -> Rect:
        """Usable work area (minus taskbar/dock), or the full bounds if unknown."""
        return self.work_area if self.work_area is not None else self.bounds

    def contains(self, x: int, y: int) -> bool:
        """True when virtual point ``(x, y)`` falls inside this monitor."""
        return (self.x <= x < self.x + self.width
                and self.y <= y < self.y + self.height)

    def to_dict(self) -> Dict[str, Any]:
        """Return the monitor as a plain dict (``work_area`` as a list)."""
        data = asdict(self)
        data["work"] = list(self.work)
        return data


def virtual_bounds(monitors: Sequence[Monitor]) -> Rect:
    """Return the union bounding box of all monitors (origin may be negative)."""
    if not monitors:
        raise ValueError("no monitors")
    left = min(monitor.x for monitor in monitors)
    top = min(monitor.y for monitor in monitors)
    right = max(monitor.x + monitor.width for monitor in monitors)
    bottom = max(monitor.y + monitor.height for monitor in monitors)
    return (left, top, right - left, bottom - top)


def primary_monitor(monitors: Sequence[Monitor]) -> Optional[Monitor]:
    """Return the monitor flagged ``primary`` (or the first one, or ``None``)."""
    for monitor in monitors:
        if monitor.primary:
            return monitor
    return monitors[0] if monitors else None


def monitor_at_point(monitors: Sequence[Monitor], x: int,
                     y: int) -> Optional[Monitor]:
    """Return the monitor containing virtual point ``(x, y)`` (or ``None``)."""
    for monitor in monitors:
        if monitor.contains(int(x), int(y)):
            return monitor
    return None


def _overlap(rect: Rect, monitor: Monitor) -> int:
    rx, ry, rw, rh = rect
    left = max(rx, monitor.x)
    top = max(ry, monitor.y)
    right = min(rx + rw, monitor.x + monitor.width)
    bottom = min(ry + rh, monitor.y + monitor.height)
    return max(0, right - left) * max(0, bottom - top)


def monitor_for_window(rect: Rect,
                       monitors: Sequence[Monitor]) -> Optional[Monitor]:
    """Return the monitor a window ``rect`` mostly occupies (max overlap area)."""
    best: Optional[Monitor] = None
    best_area = 0
    for monitor in monitors:
        area = _overlap(rect, monitor)
        if area > best_area:
            best_area, best = area, monitor
    return best


def to_local(monitors: Sequence[Monitor], x: int,
             y: int) -> Optional[Tuple[int, int, int]]:
    """Map a virtual point to ``(monitor_index, local_x, local_y)`` (or ``None``)."""
    monitor = monitor_at_point(monitors, x, y)
    if monitor is None:
        return None
    return (monitor.index, int(x) - monitor.x, int(y) - monitor.y)


def to_virtual(monitor: Monitor, local_x: int, local_y: int) -> Tuple[int, int]:
    """Map a monitor-local point back to virtual-desktop coordinates."""
    return (monitor.x + int(local_x), monitor.y + int(local_y))


def remap_point(src: Monitor, dst: Monitor, local_x: int,
                local_y: int) -> Tuple[int, int]:
    """Remap a ``src``-local point to the equivalent relative spot on ``dst`` (local).

    Preserves the fractional position within the monitor, so it works across
    differing resolutions and physical sizes.
    """
    frac_x = (local_x / src.width) if src.width else 0.0
    frac_y = (local_y / src.height) if src.height else 0.0
    return (round(frac_x * dst.width), round(frac_y * dst.height))


def _mss_rows() -> List[Dict[str, Any]]:
    from je_auto_control.utils.cv2_utils.screen_grabber import mss_grabber
    with mss_grabber() as screen:
        monitors = screen.monitors
    return [{"x": int(m["left"]), "y": int(m["top"]),
             "width": int(m["width"]), "height": int(m["height"])}
            for m in monitors[1:]]                    # [0] is the combined desktop


def enumerate_monitors(provider: Optional[MonitorRows] = None) -> List[Monitor]:
    """Return the connected monitors as ``Monitor`` objects, primary-first index 0.

    ``provider`` yields raw ``{x, y, width, height[, scale, primary, work_area]}``
    rows; the default reads them from ``mss``. Injecting a provider makes the whole
    module headless-testable.
    """
    rows = (provider or _mss_rows)()
    monitors: List[Monitor] = []
    for index, row in enumerate(rows):
        work = row.get("work_area")
        monitors.append(Monitor(
            index=index, x=int(row["x"]), y=int(row["y"]),
            width=int(row["width"]), height=int(row["height"]),
            scale=float(row.get("scale", 1.0)),
            primary=bool(row.get("primary", index == 0)),
            work_area=tuple(work) if work else None))
    return monitors
