"""Transparent topmost overlay for host-side annotation rendering.

Receives stroke deltas from the viewer (begin / point / end / clear) via
``WebRTCDesktopHost.on_annotation`` and paints them on a click-through
fullscreen window over the host's screen — so the host user sees the same
annotations the viewer is drawing in real time.

The viewer draws in frame pixels; the host stamps each event with the frame's
``screen_origin``, and the overlay moves to the screen holding the point and
converts native pixels to that screen's logical ones.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from je_auto_control.gui._screen_geometry import logical_point, screen_at_native

# A viewer could send strokes and points without end, each one repainting
# every earlier one: the host's memory and paint time grew with it.
_MAX_STROKES = 200
_MAX_POINTS_PER_STROKE = 5000
_MAX_WIDTH = 32
_DEFAULT_WIDTH = 3


def _point(event: dict) -> Optional[Tuple[float, float]]:
    """The event's finite (x, y), or ``None``."""
    try:
        x, y = float(event.get("x", 0)), float(event.get("y", 0))
    except (TypeError, ValueError):
        return None
    return (x, y) if math.isfinite(x) and math.isfinite(y) else None


def _origin(value) -> Tuple[int, int]:
    """The host-stamped frame origin; (0, 0) when missing or malformed."""
    try:
        x, y = value
        return int(x), int(y)
    except (TypeError, ValueError, OverflowError):
        return 0, 0


def _width(value) -> int:
    """A pen width between 1 and ``_MAX_WIDTH``."""
    try:
        return min(_MAX_WIDTH, max(1, int(value or _DEFAULT_WIDTH)))
    except (TypeError, ValueError, OverflowError):
        return _DEFAULT_WIDTH


class HostAnnotationOverlay(QWidget):
    """Click-through transparent window painting annotation strokes."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._strokes: List[dict] = []
        self._current: Optional[dict] = None
        # The primary screen until a point lands on another one.
        self._target = QGuiApplication.primaryScreen()
        if self._target is not None:
            self.setGeometry(self._target.geometry())

    def show_overlay(self) -> None:
        if not self.isVisible():
            self.showFullScreen()

    def apply(self, event: dict) -> None:
        """Apply one ``begin`` / ``point`` / ``end`` / ``clear`` event from a viewer.

        The event comes from the remote viewer: a coordinate or width that is
        not a number raised ``ValueError`` out of the host panel's slot, and
        is now dropped (a width is clamped to 1..32).
        """
        action = event.get("action")
        if action == "clear":
            self.clear()
        elif action == "end":
            self.end_stroke()
        elif action in ("begin", "point"):
            point = _point(event)
            if point is None:
                return
            point = self._local_point(point, _origin(event.get("screen_origin")))
            if action == "point":
                self.add_point(*point)
                return
            self.begin_stroke(*point, color=str(event.get("color") or "#ff0000"),
                              width=_width(event.get("width")))

    def _local_point(self, point: Tuple[float, float],
                     origin: Tuple[int, int]) -> Tuple[float, float]:
        """A frame point as a position in this overlay.

        Frame pixels used to be drawn as the overlay's logical pixels: off by
        the frame's origin on screen, and on a scaled screen by its ratio.
        """
        native_x, native_y = point[0] + origin[0], point[1] + origin[1]
        screen = screen_at_native(native_x, native_y) or self._target
        if screen is None:
            return point
        if screen is not self._target:
            # Strokes on the old screen would be drawn at the new one's positions.
            self.hide()
            self.clear()
            self._target = screen
            self.setScreen(screen)
            self.setGeometry(screen.geometry())
        logical = logical_point(screen, native_x, native_y)
        corner = self.geometry().topLeft()
        return logical.x() - corner.x(), logical.y() - corner.y()

    def begin_stroke(self, x: float, y: float, *,
                     color: str = "#ff0000", width: int = _DEFAULT_WIDTH) -> None:
        self._current = {
            "color": color, "width": int(width),
            "points": [(float(x), float(y))],
        }
        self._strokes.append(self._current)
        del self._strokes[:-_MAX_STROKES]
        self.show_overlay()
        self.update()

    def add_point(self, x: float, y: float) -> None:
        if self._current is None or len(self._current["points"]) >= _MAX_POINTS_PER_STROKE:
            return
        self._current["points"].append((float(x), float(y)))
        self.update()

    def end_stroke(self) -> None:
        self._current = None

    def clear(self) -> None:
        self._strokes.clear()
        self._current = None
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 Qt override
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            for stroke in self._strokes:
                self._paint_stroke(painter, stroke)
        finally:
            painter.end()

    @staticmethod
    def _paint_stroke(painter: QPainter, stroke: dict) -> None:
        points: List[Tuple[float, float]] = stroke.get("points") or []
        if len(points) < 2:
            return
        pen = QPen(QColor(stroke.get("color") or "#ff0000"))
        pen.setWidth(int(stroke.get("width") or 3))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        poly = QPolygonF([QPointF(x, y) for x, y in points])
        painter.drawPolyline(poly)


__all__ = ["HostAnnotationOverlay"]
