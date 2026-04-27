"""Popup window that displays a connected viewer's shared screen.

Used by the host panel when ``accept_viewer_video=True`` and at least one
viewer is sharing. Wraps :class:`_FrameDisplay` so we get the same fit /
center / paint behavior as the regular viewer.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QDialog, QVBoxLayout

from je_auto_control.gui.remote_desktop._helpers import _t
from je_auto_control.gui.remote_desktop.frame_display import _FrameDisplay


class ViewerScreenWindow(QDialog):
    """Resizable, modeless dialog showing the viewer's shared screen."""

    closed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_t("rd_webrtc_viewer_screen_title"))
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.resize(960, 540)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._display = _FrameDisplay()
        layout.addWidget(self._display)

    def set_image(self, image: Optional[QImage]) -> None:
        if image is not None:
            self._display.set_image(image)
        else:
            self._display.clear()

    def closeEvent(self, event) -> None:  # noqa: N802 Qt override
        self.closed.emit()
        super().closeEvent(event)


__all__ = ["ViewerScreenWindow"]
