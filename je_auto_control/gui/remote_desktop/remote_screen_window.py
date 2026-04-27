"""Pop-out window that hosts the remote screen the viewer is watching.

This is the AnyDesk-style behaviour: when the viewer connects, the
remote desktop opens in its own resizable, modeless window so the
operator gets a real workspace instead of a thumbnail squashed into a
crowded panel. The control panel stays free for connection metadata
and disconnect controls.

The window owns a :class:`_FrameDisplay` and re-emits all of its
input / drag-and-drop / annotation signals so the panel that opened
the window can route them to the underlying viewer transport
unchanged. ``closed`` fires when the operator closes the window
manually so the panel can mirror that into a disconnect.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout

from je_auto_control.gui.remote_desktop._helpers import _t
from je_auto_control.gui.remote_desktop.frame_display import _FrameDisplay


class RemoteScreenWindow(QDialog):
    """Resizable popup that displays the remote desktop the viewer streams."""

    # --- input signals re-emitted from the inner _FrameDisplay -----------
    mouse_moved = Signal(int, int)
    mouse_pressed = Signal(int, int, str)
    mouse_released = Signal(int, int, str)
    mouse_scrolled = Signal(int, int, int)
    key_pressed = Signal(str)
    key_released = Signal(str)
    type_text = Signal(str)
    files_dropped = Signal(list)
    annotation_event = Signal(str, int, int)
    closed = Signal()

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        # Modeless: the operator can keep poking the control panel while
        # watching the remote desktop, just like AnyDesk lets you keep
        # the address-book sidebar open alongside the session window.
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        # Detach from the parent so it lands as a top-level OS window
        # instead of being clipped inside the parent's geometry.
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.resize(1024, 640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._display = _FrameDisplay(self)
        layout.addWidget(self._display, stretch=1)

        # Footer for transfer progress / status. Hidden until the host
        # panel actually asks to show progress, so the chrome stays
        # minimal while the remote desktop is the focus.
        self._progress_label = QLabel(self)
        self._progress_label.setStyleSheet(
            "padding: 4px 8px; color: #ddd; background-color: #202020;"
        )
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)

        self._progress_bar = QProgressBar(self)
        self._progress_bar.setVisible(False)
        self._progress_bar.setTextVisible(False)
        layout.addWidget(self._progress_bar)

        # Re-emit FrameDisplay's signals so the panel only needs to
        # listen to the window — removes the need for the panel to
        # know about the inner widget at all.
        self._display.mouse_moved.connect(self.mouse_moved)
        self._display.mouse_pressed.connect(self.mouse_pressed)
        self._display.mouse_released.connect(self.mouse_released)
        self._display.mouse_scrolled.connect(self.mouse_scrolled)
        self._display.key_pressed.connect(self.key_pressed)
        self._display.key_released.connect(self.key_released)
        self._display.type_text.connect(self.type_text)
        self._display.files_dropped.connect(self.files_dropped)
        self._display.annotation_event.connect(self.annotation_event)

    # --- panel-facing API ------------------------------------------------

    def set_image(self, image: Optional[QImage]) -> None:
        if image is None or image.isNull():
            self._display.clear()
        else:
            self._display.set_image(image)

    def clear(self) -> None:
        self._display.clear()

    def set_pen_mode(self, value: bool) -> None:
        self._display.set_pen_mode(value)

    def set_progress(self, label: str, done: int, total: int) -> None:
        self._progress_label.setVisible(True)
        self._progress_label.setText(label)
        self._progress_bar.setVisible(True)
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(min(done, total))
        else:
            self._progress_bar.setRange(0, 0)

    def show_progress_text(self, label: str) -> None:
        self._progress_label.setVisible(bool(label))
        self._progress_label.setText(label)
        self._progress_bar.setVisible(False)

    def hide_progress(self) -> None:
        self._progress_label.setVisible(False)
        self._progress_bar.setVisible(False)

    @property
    def display(self) -> _FrameDisplay:
        """Direct access for callers that need the underlying widget."""
        return self._display

    # --- close handling --------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 Qt override
        self.closed.emit()
        super().closeEvent(event)


def make_remote_screen_window(parent=None) -> RemoteScreenWindow:
    """Factory that picks a sensible default title from the i18n table."""
    return RemoteScreenWindow(_t("rd_remote_screen_title"), parent=parent)


__all__ = ["RemoteScreenWindow", "make_remote_screen_window"]
