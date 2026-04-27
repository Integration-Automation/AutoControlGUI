"""Full-screen blanking overlay used for privacy during a remote session.

Covers the host's monitors with a black, frameless, topmost window so
people walking by can't see what the remote viewer is doing. The overlay
intentionally does not steal input — Qt's mouse/keyboard events still pass
through to whatever windows are below (we set ``WA_TransparentForMouseEvents``).
The remote viewer's input is dispatched through the existing
``input_dispatch`` path so they can still drive the machine.

A visible "Currently being viewed" banner reassures local observers.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from je_auto_control.gui.remote_desktop._helpers import _t


class _BlankingWindow(QWidget):
    """One blanking window per screen."""

    def __init__(self, geometry, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("background-color: black;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        banner = QLabel(_t("rd_webrtc_blanking_banner"))
        banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner.setStyleSheet(
            "color: #ffaa00; font-size: 18pt; font-weight: bold;",
        )
        layout.addWidget(banner)
        self.setGeometry(geometry)


class BlankingOverlay:
    """Manages one ``_BlankingWindow`` per screen."""

    def __init__(self) -> None:
        self._windows: List[_BlankingWindow] = []

    def show(self) -> None:
        if self._windows:
            return
        for screen in QGuiApplication.screens():
            window = _BlankingWindow(screen.geometry())
            window.showFullScreen()
            self._windows.append(window)

    def hide(self) -> None:
        for window in self._windows:
            window.hide()
            window.deleteLater()
        self._windows.clear()

    def is_active(self) -> bool:
        return bool(self._windows)


__all__ = ["BlankingOverlay"]
