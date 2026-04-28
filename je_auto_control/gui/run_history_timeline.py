"""Custom timeline widget for the Run History tab.

Renders one colored bar per run on a horizontal time axis (newest on the
right). Status drives the bar colour (green = ok, red = error, amber =
still running). Clicking a bar emits ``run_clicked`` so the host tab can
sync the row selection / thumbnail preview.

Pure :mod:`PySide6` — the headless run history store has zero Qt deps.
"""
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from je_auto_control.utils.run_history.history_store import (
    STATUS_ERROR, STATUS_OK, STATUS_RUNNING, RunRecord,
)

_STATUS_COLOURS = {
    STATUS_OK: QColor("#4caf50"),
    STATUS_ERROR: QColor("#e53935"),
    STATUS_RUNNING: QColor("#ffb300"),
}
_DEFAULT_COLOUR = QColor("#9e9e9e")
_GUTTER = 6
_MIN_BAR_PX = 4
_BAR_HEIGHT_FRACTION = 0.55


@dataclass
class _Bar:
    record: RunRecord
    rect: QRectF


class RunHistoryTimeline(QWidget):
    """Horizontal Gantt-style strip of run records."""

    run_clicked = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._records: List[RunRecord] = []
        self._bars: List[_Bar] = []
        self._range: Tuple[float, float] = (0.0, 0.0)
        self._highlight_id: Optional[int] = None
        self.setMouseTracking(True)

    def set_records(self, records: Sequence[RunRecord]) -> None:
        """Replace the displayed records and trigger a repaint."""
        self._records = list(records)
        self._range = self._compute_range(self._records)
        self.update()

    def set_highlighted(self, run_id: Optional[int]) -> None:
        """Visually mark a single run id (called from external selection)."""
        self._highlight_id = run_id
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.fillRect(self.rect(), self.palette().window())
            self._bars = self._layout_bars()
            self._draw_axis(painter)
            for bar in self._bars:
                self._draw_bar(painter, bar)
        finally:
            painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        for bar in self._bars:
            if bar.rect.contains(event.position()):
                self._highlight_id = bar.record.id
                self.update()
                self.run_clicked.emit(bar.record.id)
                return
        super().mousePressEvent(event)

    @staticmethod
    def _compute_range(records: Sequence[RunRecord]) -> Tuple[float, float]:
        if not records:
            return (0.0, 0.0)
        starts = [r.started_at for r in records]
        ends = []
        for r in records:
            if r.finished_at is not None:
                ends.append(r.finished_at)
            else:
                ends.append(r.started_at + 0.001)
        lo = min(starts)
        hi = max(ends)
        if hi <= lo:
            hi = lo + 1.0
        return (lo, hi)

    def _layout_bars(self) -> List[_Bar]:
        if not self._records:
            return []
        lo, hi = self._range
        span = max(hi - lo, 1e-6)
        usable_w = max(1, self.width() - 2 * _GUTTER)
        bar_height = max(8, int(self.height() * _BAR_HEIGHT_FRACTION))
        y = (self.height() - bar_height) // 2
        bars: List[_Bar] = []
        for record in self._records:
            start_frac = (record.started_at - lo) / span
            end_at = record.finished_at if record.finished_at is not None \
                else min(hi, record.started_at + 0.001)
            end_frac = (end_at - lo) / span
            x = _GUTTER + int(start_frac * usable_w)
            width = max(_MIN_BAR_PX, int((end_frac - start_frac) * usable_w))
            rect = QRectF(x, y, width, bar_height)
            bars.append(_Bar(record=record, rect=rect))
        return bars

    def _draw_axis(self, painter: QPainter) -> None:
        if not self._records:
            painter.setPen(self.palette().text().color())
            painter.drawText(self.rect(), Qt.AlignCenter, "no runs yet")
            return
        font = QFont(painter.font())
        font.setPointSize(max(7, font.pointSize() - 1))
        painter.setFont(font)
        metrics = QFontMetrics(font)
        lo, hi = self._range
        baseline_y = self.height() - max(2, metrics.descent() + 2)
        painter.setPen(QColor(120, 120, 120, 160))
        painter.drawLine(_GUTTER, baseline_y,
                         self.width() - _GUTTER, baseline_y)
        painter.setPen(self.palette().text().color())
        from datetime import datetime
        try:
            left_label = datetime.fromtimestamp(lo).strftime("%H:%M:%S")
            right_label = datetime.fromtimestamp(hi).strftime("%H:%M:%S")
        except (OSError, ValueError, OverflowError):
            left_label, right_label = str(lo), str(hi)
        painter.drawText(_GUTTER, baseline_y - 2, left_label)
        right_w = metrics.horizontalAdvance(right_label)
        painter.drawText(self.width() - _GUTTER - right_w,
                         baseline_y - 2, right_label)

    def _draw_bar(self, painter: QPainter, bar: _Bar) -> None:
        colour = QColor(_STATUS_COLOURS.get(bar.record.status, _DEFAULT_COLOUR))
        if bar.record.id == self._highlight_id:
            painter.setPen(QColor(255, 255, 255, 220))
        else:
            painter.setPen(Qt.NoPen)
        painter.setBrush(colour)
        painter.drawRoundedRect(bar.rect, 3, 3)
