"""Tiny sparkline widget for the WebRTC stats panel.

Keeps the last N samples in a deque and paints a polyline. Designed for
displaying RTT / bitrate trends without pulling in a charting library.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QSizePolicy, QWidget


class Sparkline(QWidget):
    """Simple line chart of recent values."""

    def __init__(self, *, capacity: int = 60,
                 line_color: str = "#3a9c3a",
                 background: str = "#161616",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._values: "deque[float]" = deque(maxlen=capacity)
        self._line_color = QColor(line_color)
        self._bg_color = QColor(background)
        self.setMinimumHeight(28)
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def push(self, value: Optional[float]) -> None:
        """Append a sample (None counts as 0)."""
        self._values.append(float(value) if value is not None else 0.0)
        self.update()

    def clear(self) -> None:
        self._values.clear()
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 Qt override
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), self._bg_color)
            if len(self._values) < 2:
                return
            w = self.width()
            h = self.height()
            lo = min(self._values)
            hi = max(self._values)
            span = max(hi - lo, 1.0)
            n = len(self._values)
            step = w / max(n - 1, 1)
            poly = QPolygonF()
            for i, v in enumerate(self._values):
                x = i * step
                # Invert y so larger values draw higher
                y = h - 2 - ((v - lo) / span) * (h - 4)
                poly.append(QPointF(x, y))
            pen = QPen(self._line_color)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.drawPolyline(poly)
            # Latest value text in the corner
            painter.setPen(QColor("#888"))
            painter.drawText(
                self.rect().adjusted(2, 2, -2, -2),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
                f"{self._values[-1]:.0f}",
            )
        finally:
            painter.end()


__all__ = ["Sparkline"]
