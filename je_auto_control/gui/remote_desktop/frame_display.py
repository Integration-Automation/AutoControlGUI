"""``_FrameDisplay`` widget: paints JPEG frames and emits remote-input events."""
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QDragEnterEvent, QDropEvent, QImage, QKeyEvent, QMouseEvent, QPainter,
    QWheelEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from je_auto_control.gui.remote_desktop._helpers import (
    _key_event_to_ac, _qt_button_name, _scroll_amount,
)


class _FrameDisplay(QWidget):
    """Paints the latest frame and emits remapped input events.

    Also accepts drag-and-drop of local files; each dropped file path is
    re-emitted via :pyattr:`files_dropped` so the parent panel can choose
    a destination on the remote host and start a transfer.
    """

    mouse_moved = Signal(int, int)
    mouse_pressed = Signal(int, int, str)
    mouse_released = Signal(int, int, str)
    mouse_scrolled = Signal(int, int, int)
    key_pressed = Signal(str)
    key_released = Signal(str)
    type_text = Signal(str)
    files_dropped = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._image: Optional[QImage] = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        self.setMinimumSize(320, 200)
        self.setStyleSheet("background-color: #101010;")
        self.setAcceptDrops(True)

    def set_image(self, image: QImage) -> None:
        self._image = image
        self.update()

    def clear(self) -> None:
        self._image = None
        self.update()

    def has_image(self) -> bool:
        return self._image is not None and not self._image.isNull()

    # --- painting -------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802  Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if not self.has_image():
            return
        target = self._fit_rect()
        if target.isValid():
            painter.drawImage(target, self._image)

    def _fit_rect(self) -> QRect:
        if self._image is None or self._image.isNull():
            return QRect()
        img_w = self._image.width()
        img_h = self._image.height()
        widget_w = self.width()
        widget_h = self.height()
        if img_w <= 0 or img_h <= 0 or widget_w <= 0 or widget_h <= 0:
            return QRect()
        scale = min(widget_w / img_w, widget_h / img_h)
        scaled_w = max(1, int(img_w * scale))
        scaled_h = max(1, int(img_h * scale))
        x = (widget_w - scaled_w) // 2
        y = (widget_h - scaled_h) // 2
        return QRect(x, y, scaled_w, scaled_h)

    def _to_remote(self, pos: QPoint) -> Optional[tuple]:
        rect = self._fit_rect()
        if not rect.isValid() or not rect.contains(pos):
            return None
        if self._image is None:
            return None
        rel_x = pos.x() - rect.x()
        rel_y = pos.y() - rect.y()
        scale_x = self._image.width() / rect.width()
        scale_y = self._image.height() / rect.height()
        return int(rel_x * scale_x), int(rel_y * scale_y)

    # --- input ---------------------------------------------------------

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        coords = self._to_remote(event.position().toPoint())
        if coords is not None:
            self.mouse_moved.emit(*coords)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.setFocus()
        coords = self._to_remote(event.position().toPoint())
        if coords is None:
            return
        button = _qt_button_name(event.button())
        if button is not None:
            self.mouse_pressed.emit(*coords, button)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        coords = self._to_remote(event.position().toPoint())
        if coords is None:
            return
        button = _qt_button_name(event.button())
        if button is not None:
            self.mouse_released.emit(*coords, button)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        coords = self._to_remote(event.position().toPoint())
        if coords is None:
            return
        amount = _scroll_amount(event.angleDelta().y())
        if amount:
            self.mouse_scrolled.emit(coords[0], coords[1], amount)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.isAutoRepeat():
            return
        keycode = _key_event_to_ac(event)
        if keycode is not None:
            self.key_pressed.emit(keycode)
            return
        text = event.text()
        if text:
            self.type_text.emit(text)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.isAutoRepeat():
            return
        keycode = _key_event_to_ac(event)
        if keycode is not None:
            self.key_released.emit(keycode)

    # --- drag-and-drop --------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        local_paths = [
            url.toLocalFile() for url in urls
            if url.isLocalFile() and url.toLocalFile()
        ]
        files = [p for p in local_paths if Path(p).is_file()]
        if files:
            self.files_dropped.emit(files)
            event.acceptProposedAction()
