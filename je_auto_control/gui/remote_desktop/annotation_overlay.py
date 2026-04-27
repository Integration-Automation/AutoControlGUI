"""Transparent topmost overlay for host-side annotation rendering.

Receives stroke deltas from the viewer (begin / point / end / clear) via
``WebRTCDesktopHost.on_annotation`` and paints them on a click-through
fullscreen window over the host's screen — so the host user sees the same
annotations the viewer is drawing in real time.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget


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
        # Cover the primary screen (multi-monitor case: caller can move/resize)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())

    def show_overlay(self) -> None:
        if not self.isVisible():
            self.showFullScreen()

    def begin_stroke(self, x: float, y: float, *,
                     color: str = "#ff0000", width: int = 3) -> None:
        self._current = {
            "color": color, "width": int(width),
            "points": [(float(x), float(y))],
        }
        self._strokes.append(self._current)
        self.show_overlay()
        self.update()

    def add_point(self, x: float, y: float) -> None:
        if self._current is None:
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
