"""Full-screen translucent overlays for drawing a selection rectangle.

One overlay covers each screen. A single window sized to the whole virtual
desktop did not work: ``showFullScreen`` put it on one screen, while the
result was still offset by the virtual desktop's origin, and Qt's logical
coordinates are not the native pixels screenshots use on a scaled screen.
"""
from typing import List, Optional, Tuple

from PySide6.QtCore import QEventLoop, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen, QScreen
from PySide6.QtWidgets import QApplication, QWidget

Region = Tuple[int, int, int, int]


def native_region(screen: QScreen, rect: QRect) -> Region:
    """``rect`` (in logical pixels, relative to ``screen``) as native (x, y, w, h).

    Qt keeps a screen's top-left corner the same in logical and native
    coordinates and scales within the screen by its device pixel ratio.
    """
    origin = screen.geometry().topLeft()
    ratio = screen.devicePixelRatio()
    return (origin.x() + round(rect.x() * ratio), origin.y() + round(rect.y() * ratio),
            round(rect.width() * ratio), round(rect.height() * ratio))


class RegionOverlay(QWidget):
    """Frameless full-screen widget on one screen for selecting a rectangle.

    ``region_selected`` carries native screen pixels; ``cancelled`` fires on
    Escape, a too-small drag, or the overlay closing any other way.
    """

    region_selected = Signal(int, int, int, int)
    cancelled = Signal()

    def __init__(self, screen: Optional[QScreen] = None) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._target = screen or QApplication.primaryScreen()
        self.setScreen(self._target)
        self.setGeometry(self._target.geometry())
        self._origin: Optional[QPoint] = None
        self._current: Optional[QPoint] = None
        self._finished = False

    @property
    def target_screen(self) -> QScreen:
        """The screen this overlay covers."""
        return self._target

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
        if rect.width() < 2 or rect.height() < 2:
            self._finish(None)
            return
        self._finish(native_region(self._target, rect))

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._finish(None)
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802 Qt override
        # Closed some other way (Alt+F4, the window manager): a cancel, so a
        # caller waiting for an answer is not left waiting.
        if not self._finished:
            self._finished = True
            self.cancelled.emit()
        super().closeEvent(event)

    def _finish(self, region: Optional[Region]) -> None:
        if self._finished:
            return
        self._finished = True
        if region is None:
            self.cancelled.emit()
        else:
            self.region_selected.emit(*region)
        self.close()


def pick_region_blocking(parent: Optional[QWidget] = None) -> Optional[Region]:
    """Cover every screen, wait for a selection, and return it in native pixels.

    Returns ``(x, y, width, height)``, or ``None`` when cancelled. The wait is
    a local event loop, not a ``processEvents`` spin that kept a core busy.
    """
    del parent
    overlays: List[RegionOverlay] = [RegionOverlay(screen) for screen in QApplication.screens()]
    result: dict = {"region": None, "done": False}
    loop = QEventLoop()

    def finish(region: Optional[Region] = None) -> None:
        if result["done"]:
            return
        result["done"] = True
        result["region"] = region
        for overlay in overlays:
            overlay.close()
        loop.quit()

    for overlay in overlays:
        overlay.region_selected.connect(lambda x, y, w, h: finish((x, y, w, h)))
        overlay.cancelled.connect(finish)
        overlay.showFullScreen()
    overlays[0].activateWindow()
    overlays[0].raise_()
    if not result["done"]:
        loop.exec()
    for overlay in overlays:
        overlay.deleteLater()
    return result["region"]
