"""Full-screen translucent overlay for drawing a selection rectangle."""
from typing import Optional, Tuple

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget


class RegionOverlay(QWidget):
    """Frameless full-screen widget for selecting a rectangular region."""

    region_selected = Signal(int, int, int, int)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        virtual = self._virtual_geometry()
        self.setGeometry(virtual)
        self._virtual_origin = virtual.topLeft()
        self._origin: Optional[QPoint] = None
        self._current: Optional[QPoint] = None

    @staticmethod
    def _virtual_geometry() -> QRect:
        screens = QApplication.screens()
        geom = screens[0].geometry()
        for screen in screens[1:]:
            geom = geom.united(screen.geometry())
        return geom

    def _rect(self) -> QRect:
        if self._origin is None or self._current is None:
            return QRect()
        return QRect(self._origin, self._current).normalized()

    def paintEvent(self, event) -> None:  # noqa: N802 Qt override
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))
        rect = self._rect()
        if rect.isEmpty():
            return
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(rect, Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        pen = QPen(QColor(255, 180, 0), 2)
        painter.setPen(pen)
        painter.drawRect(rect)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._current = self._origin
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._origin is not None:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        self._current = event.position().toPoint()
        rect = self._rect()
        self.close()
        if rect.width() < 2 or rect.height() < 2:
            self.cancelled.emit()
            return
        screen_x = rect.x() + self._virtual_origin.x()
        screen_y = rect.y() + self._virtual_origin.y()
        self.region_selected.emit(screen_x, screen_y, rect.width(), rect.height())

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)


def pick_region_blocking(parent: Optional[QWidget] = None
                         ) -> Optional[Tuple[int, int, int, int]]:
    """Open overlay and block until the user selects a region or cancels."""
    del parent
    overlay = RegionOverlay()
    result: dict = {"region": None}

    def on_selected(x: int, y: int, w: int, h: int) -> None:
        result["region"] = (x, y, w, h)

    overlay.region_selected.connect(on_selected)
    overlay.cancelled.connect(lambda: None)
    overlay.showFullScreen()
    overlay.activateWindow()
    overlay.raise_()
    # Spin the local event loop until the overlay closes.
    while overlay.isVisible():
        QApplication.processEvents()
    return result["region"]
