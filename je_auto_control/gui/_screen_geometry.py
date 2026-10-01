"""Convert between Qt's logical coordinates and the screen coordinates captures use.

Qt keeps each screen's top-left corner the same in both and scales within the
screen by its device pixel ratio. Measured on Windows in a per-monitor-aware
process: a 125% screen at (1920, -164) is 1536x864 in Qt and 1920x1080
natively. (``import je_auto_control`` makes a process system-DPI-aware, and
then Qt reports a ratio of 1.0 there, in the same virtualised space as the
cursor and ``mss``.) On macOS the capture APIs and the pointer take points,
which is Qt's logical unit, so no scaling applies.
"""
import sys
from typing import Optional, Tuple

from PySide6.QtCore import QPointF, QRect
from PySide6.QtGui import QGuiApplication, QScreen

Region = Tuple[int, int, int, int]


def capture_ratio(screen: QScreen) -> float:
    """Screen-coordinate units per Qt logical pixel on ``screen``.

    The device pixel ratio, except on macOS: ``mss``, ``screencapture`` and
    Quartz events all take points there, and scaling a Retina screen by 2
    doubled every region.
    """
    return 1.0 if sys.platform == "darwin" else screen.devicePixelRatio()


def native_region(screen: QScreen, rect: QRect) -> Region:
    """``rect`` (logical pixels, relative to ``screen``'s corner) in screen coordinates (x, y, w, h)."""
    origin = screen.geometry().topLeft()
    ratio = capture_ratio(screen)
    return (origin.x() + round(rect.x() * ratio), origin.y() + round(rect.y() * ratio),
            round(rect.width() * ratio), round(rect.height() * ratio))


def screen_at_native(x: float, y: float) -> Optional[QScreen]:
    """The screen whose native rectangle holds (x, y), or ``None``."""
    for screen in QGuiApplication.screens():
        geometry, ratio = screen.geometry(), capture_ratio(screen)
        if (geometry.x() <= x < geometry.x() + geometry.width() * ratio
                and geometry.y() <= y < geometry.y() + geometry.height() * ratio):
            return screen
    return None


def logical_point(screen: QScreen, x: float, y: float) -> QPointF:
    """Native (x, y) on ``screen`` as a global logical point."""
    origin = screen.geometry().topLeft()
    ratio = capture_ratio(screen)
    return QPointF(origin.x() + (x - origin.x()) / ratio, origin.y() + (y - origin.y()) / ratio)
