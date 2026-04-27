"""System-tray icon for the WebRTC host.

Lets users keep the host process running in the background without a
visible window. Icon colour reflects host state (idle / running /
viewer-connected). Right-click menu exposes Open / Stop / Quit.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from je_auto_control.gui.remote_desktop._helpers import _t


def _build_icon(color_hex: str) -> QIcon:
    """Generate a simple coloured circle icon programmatically."""
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color_hex))
        painter.setPen(QColor("#222"))
        painter.drawEllipse(8, 8, 48, 48)
    finally:
        painter.end()
    return QIcon(pix)


class HostTrayIcon(QObject):
    """Wraps QSystemTrayIcon with state-driven colour + menu."""

    open_requested = Signal()
    stop_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._tray = QSystemTrayIcon(_build_icon("#888"), parent)
        self._tray.setToolTip(_t("rd_webrtc_tray_idle"))
        self._tray.activated.connect(self._on_activated)
        self._build_menu()
        self._tray.show()

    def _build_menu(self) -> None:
        menu = QMenu()
        open_action = QAction(_t("rd_webrtc_tray_open"), menu)
        open_action.triggered.connect(self.open_requested.emit)
        stop_action = QAction(_t("rd_webrtc_tray_stop"), menu)
        stop_action.triggered.connect(self.stop_requested.emit)
        quit_action = QAction(_t("rd_webrtc_tray_quit"), menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(open_action)
        menu.addAction(stop_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)

    def set_state(self, *, sessions: int) -> None:
        """Reflect host state via icon colour + tooltip."""
        if sessions == 0:
            color = "#888"
            tip = _t("rd_webrtc_tray_idle")
        elif sessions <= 3:
            color = "#3a9c3a"
            tip = _t("rd_webrtc_tray_running").format(n=sessions)
        else:
            color = "#c97a00"
            tip = _t("rd_webrtc_tray_running").format(n=sessions)
        self._tray.setIcon(_build_icon(color))
        self._tray.setToolTip(tip)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_requested.emit()

    def hide(self) -> None:
        self._tray.hide()


def install_host_tray(*, on_open: Callable, on_stop: Callable,
                      on_quit: Callable,
                      parent: Optional[QObject] = None) -> Optional[HostTrayIcon]:
    """Build a tray icon if the system supports it; return None otherwise."""
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    QApplication.setQuitOnLastWindowClosed(False)
    tray = HostTrayIcon(parent=parent)
    tray.open_requested.connect(on_open)
    tray.stop_requested.connect(on_stop)
    tray.quit_requested.connect(on_quit)
    return tray


__all__ = ["HostTrayIcon", "install_host_tray"]
