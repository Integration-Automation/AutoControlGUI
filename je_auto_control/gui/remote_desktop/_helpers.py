"""Shared helpers for the remote-desktop GUI panels."""
import ssl
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QWidget

from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)


def _t(key: str) -> str:
    """Translate ``key`` via the GUI's language wrapper."""
    return language_wrapper.translate(key, key)


def _qt_button_name(button: Qt.MouseButton) -> Optional[str]:
    """Map a Qt mouse button to the AC button name used by the wrappers."""
    if button == Qt.MouseButton.LeftButton:
        return "mouse_left"
    if button == Qt.MouseButton.RightButton:
        return "mouse_right"
    if button == Qt.MouseButton.MiddleButton:
        return "mouse_middle"
    return None


_QT_KEY_TO_AC = {
    Qt.Key.Key_Up: "up",
    Qt.Key.Key_Down: "down",
    Qt.Key.Key_Left: "left",
    Qt.Key.Key_Right: "right",
    Qt.Key.Key_Return: "return",
    Qt.Key.Key_Enter: "return",
    Qt.Key.Key_Escape: "escape",
    Qt.Key.Key_Tab: "tab",
    Qt.Key.Key_Backspace: "back",
    Qt.Key.Key_Space: "space",
    Qt.Key.Key_Delete: "delete",
    Qt.Key.Key_Home: "home",
    Qt.Key.Key_End: "end",
    Qt.Key.Key_Insert: "insert",
    Qt.Key.Key_Shift: "shift",
    Qt.Key.Key_Control: "control",
    Qt.Key.Key_Alt: "menu",
    Qt.Key.Key_PageUp: "prior",
    Qt.Key.Key_PageDown: "next",
}
for _i in range(1, 13):
    _QT_KEY_TO_AC[getattr(Qt.Key, f"Key_F{_i}")] = f"f{_i}"


def _key_event_to_ac(event: QKeyEvent) -> Optional[str]:
    """Return the AC keycode for ``event``, or ``None`` if unmappable."""
    mapped = _QT_KEY_TO_AC.get(Qt.Key(event.key()))
    if mapped is not None:
        return mapped
    text = event.text()
    if len(text) == 1 and text.isprintable():
        return text
    return None


def _scroll_amount(angle_delta: int) -> int:
    """Return ``+1`` / ``-1`` / ``0`` for a Qt wheel ``angleDelta`` value."""
    if angle_delta > 0:
        return 1
    if angle_delta < 0:
        return -1
    return 0


def _build_verifying_client_context() -> ssl.SSLContext:
    """TLS client context with full hostname + cert verification enabled."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_default_certs()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def _build_insecure_client_context() -> ssl.SSLContext:
    """Opt-in self-signed loopback context — verification intentionally off.

    Triggered only when the user ticks 'Skip cert verification' on the
    Viewer panel; meant for self-signed dev / LAN hosts where the user
    has already pinned the host out-of-band (token + 9-digit Host ID).
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # NOSONAR S5527  # opt-in self-signed
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # NOSONAR S4830  # opt-in self-signed
    return ctx


_BADGE_STYLES = {
    "stopped": "background-color: #888; color: white;",
    "starting": "background-color: #cc7000; color: white;",
    "running": "background-color: #2a8c4a; color: white;",
    "idle": "background-color: #888; color: white;",
    "connecting": "background-color: #cc7000; color: white;",
    "live": "background-color: #2a8c4a; color: white;",
    "error": "background-color: #b03030; color: white;",
}


class _StatusBadge(QLabel):
    """Small coloured pill that summarises the current host / viewer state."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(96)
        self.set_state("stopped", "")

    def set_state(self, state: str, text: str) -> None:
        style = _BADGE_STYLES.get(state, _BADGE_STYLES["stopped"])
        self.setStyleSheet(
            "padding: 4px 12px; border-radius: 10px; "
            "font-weight: bold; " + style
        )
        self.setText(text)


class _CollapsibleSection(QGroupBox):
    """``QGroupBox`` with a checkable header that hides/shows its body."""

    def __init__(self, title: str = "",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(title, parent)
        self.setCheckable(True)
        self.setChecked(False)
        self._body = QWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 14, 8, 8)
        outer.addWidget(self._body)
        self._body.setVisible(False)
        self.toggled.connect(self._body.setVisible)

    @property
    def body(self) -> QWidget:
        return self._body

    def set_body_layout(self, layout) -> None:
        self._body.setLayout(layout)
