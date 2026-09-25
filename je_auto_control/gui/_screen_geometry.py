"""Convert between Qt's logical coordinates and the native pixels screenshots use.

Qt keeps each screen's top-left corner the same in both and scales within the
screen by its device pixel ratio. Measured on Windows: a 125% screen at
(1920, -164) is 1536x864 in Qt and 1920x1080 natively.
"""
from typing import Optional, Tuple

from PySide6.QtCore import QPointF, QRect
from PySide6.QtGui import QGuiApplication, QScreen

Region = Tuple[int, int, int, int]


def native_region(screen: QScreen, rect: QRect) -> Region:
    """``rect`` (logical pixels, relative to ``screen``'s corner) as native (x, y, w, h)."""
    origin = screen.geometry().topLeft()
    ratio = screen.devicePixelRatio()
    return (origin.x() + round(rect.x() * ratio), origin.y() + round(rect.y() * ratio),
            round(rect.width() * ratio), round(rect.height() * ratio))


def screen_at_native(x: float, y: float) -> Optional[QScreen]:
    """The screen whose native rectangle holds (x, y), or ``None``."""
    for screen in QGuiApplication.screens():
        geometry, ratio = screen.geometry(), screen.devicePixelRatio()
        if (geometry.x() <= x < geometry.x() + geometry.width() * ratio
                and geometry.y() <= y < geometry.y() + geometry.height() * ratio):
            return screen
    return None


def logical_point(screen: QScreen, x: float, y: float) -> QPointF:
    """Native (x, y) on ``screen`` as a global logical point."""
    origin = screen.geometry().topLeft()
    ratio = screen.devicePixelRatio()
    return QPointF(origin.x() + (x - origin.x()) / ratio, origin.y() + (y - origin.y()) / ratio)
