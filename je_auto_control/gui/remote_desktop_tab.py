"""Remote-desktop tab: host this machine, or view+control another.

Two sub-tabs share the same window:

* **Host**: starts a :class:`RemoteDesktopHost` and shows the bound port,
  token, and connected-viewer count. The token field has a generator
  button so users can hand off a fresh secret per session.
* **Viewer**: connects a :class:`RemoteDesktopViewer`, decodes incoming
  JPEG frames into a custom :class:`_FrameDisplay` widget, and forwards
  mouse / keyboard / wheel events back to the host as JSON ``INPUT``
  messages. Coordinates are mapped from widget space to the original
  remote-screen pixel space using the latest received frame's size.
"""
import secrets
from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QKeyEvent, QMouseEvent, QPainter, QWheelEvent
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSizePolicy, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.remote_desktop.protocol import (
    AuthenticationError,
)
from je_auto_control.utils.remote_desktop.registry import registry


def _t(key: str) -> str:
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


class _FrameDisplay(QWidget):
    """Paints the latest frame and emits remapped input events."""

    mouse_moved = Signal(int, int)
    mouse_pressed = Signal(int, int, str)
    mouse_released = Signal(int, int, str)
    mouse_scrolled = Signal(int, int, int)
    key_pressed = Signal(str)
    key_released = Signal(str)
    type_text = Signal(str)

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
        delta = event.angleDelta().y()
        amount = 1 if delta > 0 else -1 if delta < 0 else 0
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


class _HostPanel(TranslatableMixin, QWidget):
    """Start / stop the singleton host and show what is being streamed."""

    _PREVIEW_INTERVAL_MS = 250  # 4 fps preview is enough to confirm liveness

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._token = QLineEdit()
        self._bind = QLineEdit("127.0.0.1")
        self._port = QSpinBox()
        self._port.setRange(0, 65535)
        self._port.setValue(0)
        self._fps = QSpinBox()
        self._fps.setRange(1, 60)
        self._fps.setValue(10)
        self._quality = QSpinBox()
        self._quality.setRange(1, 95)
        self._quality.setValue(70)
        self._status = QLabel()
        self._preview = _FrameDisplay()
        # Preview is read-only — a host watching their own stream shouldn't
        # trigger fake input on themselves through the local widget.
        self._preview.setEnabled(False)
        self._start_btn: Optional[QPushButton] = None
        self._stop_btn: Optional[QPushButton] = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self._refresh_status)
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(self._PREVIEW_INTERVAL_MS)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._build_layout()
        self._apply_placeholders()
        self._refresh_status()
        self._refresh_timer.start()
        self._preview_timer.start()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_placeholders()
        self._refresh_status()

    def _apply_placeholders(self) -> None:
        self._token.setPlaceholderText(_t("rd_token_placeholder"))

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)

        warning = QLabel()
        warning.setText(_t("rd_host_security_warning"))
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #cc7000;")
        self._tr(warning, "rd_host_security_warning")
        root.addWidget(warning)

        config = self._tr(QGroupBox(), "rd_host_config_group")
        grid = QVBoxLayout()
        token_row = QHBoxLayout()
        token_row.addWidget(self._tr(QLabel(), "rd_token_label"))
        token_row.addWidget(self._token, stretch=1)
        gen_btn = self._tr(QPushButton(), "rd_token_generate")
        gen_btn.clicked.connect(self._generate_token)
        token_row.addWidget(gen_btn)
        grid.addLayout(token_row)

        bind_row = QHBoxLayout()
        bind_row.addWidget(self._tr(QLabel(), "rd_bind_label"))
        bind_row.addWidget(self._bind, stretch=1)
        bind_row.addWidget(self._tr(QLabel(), "rd_port_label"))
        bind_row.addWidget(self._port)
        grid.addLayout(bind_row)

        media_row = QHBoxLayout()
        media_row.addWidget(self._tr(QLabel(), "rd_fps_label"))
        media_row.addWidget(self._fps)
        media_row.addWidget(self._tr(QLabel(), "rd_quality_label"))
        media_row.addWidget(self._quality)
        media_row.addStretch()
        grid.addLayout(media_row)
        config.setLayout(grid)
        root.addWidget(config)

        btn_row = QHBoxLayout()
        self._start_btn = self._tr(QPushButton(), "rd_host_start")
        self._start_btn.clicked.connect(self._start)
        self._stop_btn = self._tr(QPushButton(), "rd_host_stop")
        self._stop_btn.clicked.connect(self._stop)
        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        root.addWidget(self._tr(QLabel(), "rd_host_preview_label"))
        root.addWidget(self._preview, stretch=1)
        root.addWidget(self._status)

    def _generate_token(self) -> None:
        self._token.setText(secrets.token_urlsafe(24))

    def _start(self) -> None:
        token = self._token.text().strip()
        if not token:
            self._generate_token()
            token = self._token.text().strip()
        try:
            registry.start_host(
                token=token,
                bind=self._bind.text().strip() or "127.0.0.1",
                port=self._port.value(),
                fps=float(self._fps.value()),
                quality=self._quality.value(),
            )
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self, _t("rd_host_start"), str(error))
            return
        self._refresh_status()

    def _stop(self) -> None:
        try:
            registry.stop_host()
        except (OSError, RuntimeError) as error:
            QMessageBox.warning(self, _t("rd_host_stop"), str(error))
            return
        self._refresh_status()

    def _refresh_status(self) -> None:
        status = registry.host_status()
        if status["running"]:
            text = (_t("rd_host_status_running")
                    .replace("{port}", str(status["port"]))
                    .replace("{n}", str(status["connected_clients"])))
        else:
            text = _t("rd_host_status_stopped")
        self._status.setText(text)

    def _refresh_preview(self) -> None:
        host = registry.host
        if host is None or not host.is_running:
            self._preview.clear()
            return
        frame = host.latest_frame()
        if frame is None:
            return
        image = QImage.fromData(frame, "JPEG")
        if not image.isNull():
            self._preview.set_image(image)


class _ViewerPanel(TranslatableMixin, QWidget):
    """Connect to a host, render frames, and forward input events."""

    _frame_signal = Signal(bytes)
    _error_signal = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._host_field = QLineEdit("127.0.0.1")
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(0)
        self._token = QLineEdit()
        self._status = QLabel()
        self._display = _FrameDisplay()
        self._connect_btn: Optional[QPushButton] = None
        self._disconnect_btn: Optional[QPushButton] = None
        self._connected = False
        self._build_layout()
        self._apply_placeholders()
        self._wire_signals()
        self._refresh_status()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_placeholders()
        self._refresh_status()

    def _apply_placeholders(self) -> None:
        self._token.setPlaceholderText(_t("rd_token_placeholder"))

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        connect_group = self._tr(QGroupBox(), "rd_viewer_config_group")
        grid = QVBoxLayout()
        host_row = QHBoxLayout()
        host_row.addWidget(self._tr(QLabel(), "rd_bind_label"))
        host_row.addWidget(self._host_field, stretch=1)
        host_row.addWidget(self._tr(QLabel(), "rd_port_label"))
        host_row.addWidget(self._port)
        grid.addLayout(host_row)
        token_row = QHBoxLayout()
        token_row.addWidget(self._tr(QLabel(), "rd_token_label"))
        token_row.addWidget(self._token, stretch=1)
        grid.addLayout(token_row)
        connect_group.setLayout(grid)
        root.addWidget(connect_group)

        btn_row = QHBoxLayout()
        self._connect_btn = self._tr(QPushButton(), "rd_viewer_connect")
        self._connect_btn.clicked.connect(self._connect)
        self._disconnect_btn = self._tr(QPushButton(), "rd_viewer_disconnect")
        self._disconnect_btn.clicked.connect(self._disconnect)
        btn_row.addWidget(self._connect_btn)
        btn_row.addWidget(self._disconnect_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        root.addWidget(self._display, stretch=1)
        root.addWidget(self._status)

    def _wire_signals(self) -> None:
        self._frame_signal.connect(self._on_frame_main)
        self._error_signal.connect(self._on_error_main)
        self._display.mouse_moved.connect(self._send_mouse_move)
        self._display.mouse_pressed.connect(self._send_mouse_press)
        self._display.mouse_released.connect(self._send_mouse_release)
        self._display.mouse_scrolled.connect(self._send_mouse_scroll)
        self._display.key_pressed.connect(
            lambda k: self._send({"action": "key_press", "keycode": k})
        )
        self._display.key_released.connect(
            lambda k: self._send({"action": "key_release", "keycode": k})
        )
        self._display.type_text.connect(
            lambda text: self._send({"action": "type", "text": text})
        )

    # --- connection lifecycle ------------------------------------------

    def _connect(self) -> None:
        host = self._host_field.text().strip()
        token = self._token.text().strip()
        port = self._port.value()
        if not host or not token or port == 0:
            QMessageBox.warning(
                self, _t("rd_viewer_connect"), _t("rd_viewer_required_fields"),
            )
            return
        try:
            registry.connect_viewer(
                host=host, port=port, token=token, timeout=5.0,
                on_frame=self._frame_signal.emit,
                on_error=lambda exc: self._error_signal.emit(str(exc)),
            )
        except AuthenticationError as error:
            QMessageBox.warning(self, _t("rd_viewer_connect"), str(error))
            return
        except (OSError, ConnectionError, RuntimeError) as error:
            QMessageBox.warning(self, _t("rd_viewer_connect"), str(error))
            return
        self._connected = True
        self._refresh_status()

    def _disconnect(self) -> None:
        registry.disconnect_viewer()
        self._connected = False
        self._display.clear()
        self._refresh_status()

    def _refresh_status(self) -> None:
        if self._connected and registry.viewer_status()["connected"]:
            self._status.setText(_t("rd_viewer_status_connected"))
        else:
            self._status.setText(_t("rd_viewer_status_idle"))

    # --- slot handlers (run on GUI thread) -----------------------------

    def _on_frame_main(self, payload: bytes) -> None:
        image = QImage.fromData(payload, "JPEG")
        if image.isNull():
            return
        self._display.set_image(image)

    def _on_error_main(self, message: str) -> None:
        self._connected = False
        self._refresh_status()
        QMessageBox.warning(self, _t("rd_viewer_error"), message)

    # --- input forwarding ---------------------------------------------

    def _send(self, action: dict) -> None:
        viewer = registry.viewer
        if viewer is None or not viewer.connected:
            return
        try:
            viewer.send_input(action)
        except (OSError, ConnectionError) as error:
            self._error_signal.emit(str(error))

    def _send_mouse_move(self, x: int, y: int) -> None:
        self._send({"action": "mouse_move", "x": x, "y": y})

    def _send_mouse_press(self, x: int, y: int, button: str) -> None:
        self._send({"action": "mouse_move", "x": x, "y": y})
        self._send({"action": "mouse_press", "button": button})

    def _send_mouse_release(self, x: int, y: int, button: str) -> None:
        self._send({"action": "mouse_release", "button": button})

    def _send_mouse_scroll(self, x: int, y: int, amount: int) -> None:
        self._send({
            "action": "mouse_scroll", "x": x, "y": y, "amount": amount,
        })


class RemoteDesktopTab(TranslatableMixin, QWidget):
    """Outer container holding the host and viewer sub-tabs."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        layout = QVBoxLayout(self)
        self._tabs = QTabWidget()
        self._host_panel = _HostPanel()
        self._viewer_panel = _ViewerPanel()
        host_index = self._tabs.addTab(self._host_panel, _t("rd_host_tab"))
        viewer_index = self._tabs.addTab(self._viewer_panel, _t("rd_viewer_tab"))
        self._tr_tab(self._tabs, host_index, "rd_host_tab")
        self._tr_tab(self._tabs, viewer_index, "rd_viewer_tab")
        layout.addWidget(self._tabs)

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._host_panel.retranslate()
        self._viewer_panel.retranslate()
