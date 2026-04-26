"""Remote-desktop tab: host this machine, or view+control another.

Two sub-tabs share the same window:

* **Host**: starts a :class:`RemoteDesktopHost` and shows the bound port,
  token, host ID, and connected-viewer count. Token + host ID together
  identify the session; users hand both to whoever is connecting.
* **Viewer**: connects a :class:`RemoteDesktopViewer` (or its WebSocket
  variant), decodes incoming JPEG frames into a custom
  :class:`_FrameDisplay` widget that accepts drag-and-drop file uploads,
  and forwards mouse / keyboard / wheel events back to the host as JSON
  ``INPUT`` messages. Coordinates are mapped from widget space to the
  original remote-screen pixel space using the latest received frame's
  size.
"""
import secrets
import ssl
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QDragEnterEvent, QDropEvent, QGuiApplication, QImage,
    QKeyEvent, QMouseEvent, QPainter, QWheelEvent,
)
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QSizePolicy, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.remote_desktop import (
    FileReceiver, RemoteDesktopHost, RemoteDesktopViewer,
    WebSocketDesktopHost, WebSocketDesktopViewer,
)
from je_auto_control.utils.remote_desktop.audio import (
    AudioCaptureConfig, AudioPlayer, is_audio_backend_available,
)
from je_auto_control.utils.remote_desktop.host_id import (
    HostIdError, format_host_id, parse_host_id,
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


# --- shared UI building blocks -------------------------------------------


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


class _HostPanel(TranslatableMixin, QWidget):
    """Start / stop the singleton host and show what is being streamed."""

    _PREVIEW_INTERVAL_MS = 250  # 4 fps preview is enough to confirm liveness

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._host_id_label = QLabel("---")
        self._host_id_label.setStyleSheet(
            "font-family: 'Consolas', 'Menlo', 'Courier New', monospace; "
            "font-size: 26pt; font-weight: bold; color: #2070d0; "
            "letter-spacing: 2px;"
        )
        self._badge = _StatusBadge()
        self._token = QLineEdit()
        self._bind = QLineEdit("127.0.0.1")
        self._port = QSpinBox()
        self._port.setRange(0, 65535)
        self._port.setValue(0)
        self._transport = QComboBox()
        self._transport.addItems(["TCP", "WebSocket"])
        self._fps = QSpinBox()
        self._fps.setRange(1, 60)
        self._fps.setValue(10)
        self._quality = QSpinBox()
        self._quality.setRange(1, 95)
        self._quality.setValue(70)
        self._tls_cert = QLineEdit()
        self._tls_key = QLineEdit()
        self._enable_audio = QCheckBox()
        self._enable_audio.setChecked(False)
        if not is_audio_backend_available():
            self._enable_audio.setEnabled(False)
        self._preview = _FrameDisplay()
        # Preview is read-only — a host watching their own stream shouldn't
        # trigger fake input on themselves through the local widget.
        self._preview.setEnabled(False)
        self._start_btn: Optional[QPushButton] = None
        self._stop_btn: Optional[QPushButton] = None
        self._copy_id_btn: Optional[QPushButton] = None
        self._copy_share_btn: Optional[QPushButton] = None
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
        self._tls_cert.setPlaceholderText(_t("rd_tls_cert_placeholder"))
        self._tls_key.setPlaceholderText(_t("rd_tls_key_placeholder"))

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)

        warning = QLabel()
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "color: #cc7000; padding: 6px; border: 1px solid #cc7000; "
            "border-radius: 4px;"
        )
        self._tr(warning, "rd_host_security_warning")
        root.addWidget(warning)

        # === Connection card — the focal point ===
        card = self._tr(QGroupBox(), "rd_host_card_group")
        card.setStyleSheet("QGroupBox { font-weight: bold; }")
        card_layout = QVBoxLayout()

        id_row = QHBoxLayout()
        id_row.addWidget(self._tr(QLabel(), "rd_host_id_label"))
        id_row.addWidget(self._host_id_label, stretch=1)
        id_row.addWidget(self._badge)
        card_layout.addLayout(id_row)

        token_row = QHBoxLayout()
        token_row.addWidget(self._tr(QLabel(), "rd_token_label"))
        token_row.addWidget(self._token, stretch=1)
        gen_btn = self._tr(QPushButton(), "rd_token_generate")
        gen_btn.clicked.connect(self._generate_token)
        token_row.addWidget(gen_btn)
        card_layout.addLayout(token_row)

        copy_row = QHBoxLayout()
        self._copy_id_btn = self._tr(QPushButton(), "rd_host_id_copy")
        self._copy_id_btn.clicked.connect(self._copy_host_id)
        self._copy_share_btn = self._tr(QPushButton(), "rd_host_copy_share")
        self._copy_share_btn.clicked.connect(self._copy_share_text)
        copy_row.addWidget(self._copy_id_btn)
        copy_row.addWidget(self._copy_share_btn)
        copy_row.addStretch()
        card_layout.addLayout(copy_row)

        card.setLayout(card_layout)
        root.addWidget(card)

        # === Basic connection settings ===
        basics = self._tr(QGroupBox(), "rd_host_basics_group")
        basics_layout = QVBoxLayout()
        bind_row = QHBoxLayout()
        bind_row.addWidget(self._tr(QLabel(), "rd_bind_label"))
        bind_row.addWidget(self._bind, stretch=1)
        bind_row.addWidget(self._tr(QLabel(), "rd_port_label"))
        bind_row.addWidget(self._port)
        bind_row.addWidget(self._tr(QLabel(), "rd_transport_label"))
        bind_row.addWidget(self._transport)
        basics_layout.addLayout(bind_row)
        basics.setLayout(basics_layout)
        root.addWidget(basics)

        # === Advanced (collapsible) ===
        advanced = _CollapsibleSection()
        self._tr(advanced, "rd_advanced_group", setter="setTitle")
        adv_layout = QVBoxLayout()

        tls_row = QHBoxLayout()
        tls_row.addWidget(self._tr(QLabel(), "rd_tls_cert_label"))
        tls_row.addWidget(self._tls_cert, stretch=2)
        cert_browse = self._tr(QPushButton(), "rd_browse")
        cert_browse.clicked.connect(self._browse_cert)
        tls_row.addWidget(cert_browse)
        adv_layout.addLayout(tls_row)

        key_row = QHBoxLayout()
        key_row.addWidget(self._tr(QLabel(), "rd_tls_key_label"))
        key_row.addWidget(self._tls_key, stretch=2)
        key_browse = self._tr(QPushButton(), "rd_browse")
        key_browse.clicked.connect(self._browse_key)
        key_row.addWidget(key_browse)
        adv_layout.addLayout(key_row)

        media_row = QHBoxLayout()
        media_row.addWidget(self._tr(QLabel(), "rd_fps_label"))
        media_row.addWidget(self._fps)
        media_row.addWidget(self._tr(QLabel(), "rd_quality_label"))
        media_row.addWidget(self._quality)
        media_row.addStretch()
        adv_layout.addLayout(media_row)

        adv_layout.addWidget(self._tr(self._enable_audio, "rd_enable_audio"))

        advanced.set_body_layout(adv_layout)
        root.addWidget(advanced)

        # === Primary action row ===
        btn_row = QHBoxLayout()
        self._start_btn = self._tr(QPushButton(), "rd_host_start")
        self._start_btn.setMinimumHeight(36)
        self._start_btn.setStyleSheet("font-weight: bold;")
        self._start_btn.clicked.connect(self._start)
        self._stop_btn = self._tr(QPushButton(), "rd_host_stop")
        self._stop_btn.setMinimumHeight(36)
        self._stop_btn.clicked.connect(self._stop)
        btn_row.addWidget(self._start_btn, stretch=2)
        btn_row.addWidget(self._stop_btn, stretch=1)
        root.addLayout(btn_row)

        # === Preview ===
        root.addWidget(self._tr(QLabel(), "rd_host_preview_label"))
        root.addWidget(self._preview, stretch=1)

    def _generate_token(self) -> None:
        self._token.setText(secrets.token_urlsafe(24))

    def _copy_host_id(self) -> None:
        host = registry.host
        if host is None:
            return
        QGuiApplication.clipboard().setText(format_host_id(host.host_id))

    def _copy_share_text(self) -> None:
        """Copy a one-line bundle of address / port / token / id (token leak risk)."""
        host = registry.host
        if host is None:
            QMessageBox.information(
                self, _t("rd_host_copy_share"),
                _t("rd_host_copy_share_unavailable"),
            )
            return
        confirm = QMessageBox.question(
            self, _t("rd_host_copy_share"),
            _t("rd_host_copy_share_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        bundle = (
            f"AutoControl Remote Desktop\n"
            f"Host ID: {format_host_id(host.host_id)}\n"
            f"Address: {self._bind.text().strip() or '127.0.0.1'}\n"
            f"Port:    {host.port}\n"
            f"Transport: {self._transport.currentText()}\n"
            f"Token:   {self._token.text().strip()}"
        )
        QGuiApplication.clipboard().setText(bundle)

    def _browse_cert(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("rd_tls_cert_label"), "",
            "PEM (*.pem *.crt *.cer);;All (*)",
        )
        if path:
            self._tls_cert.setText(path)

    def _browse_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("rd_tls_key_label"), "",
            "PEM (*.pem *.key);;All (*)",
        )
        if path:
            self._tls_key.setText(path)

    def _build_ssl_context(self) -> Optional[ssl.SSLContext]:
        cert_path = self._tls_cert.text().strip()
        key_path = self._tls_key.text().strip()
        if not cert_path and not key_path:
            return None
        if not cert_path or not key_path:
            raise ValueError(_t("rd_tls_both_required"))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
        return ctx

    def _start(self) -> None:
        token = self._token.text().strip()
        if not token:
            self._generate_token()
            token = self._token.text().strip()
        try:
            ssl_context = self._build_ssl_context()
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, _t("rd_host_start"), str(error))
            return
        host_cls = (WebSocketDesktopHost
                    if self._transport.currentText() == "WebSocket"
                    else RemoteDesktopHost)
        registry.disconnect_viewer()
        registry.stop_host()
        try:
            host = host_cls(
                token=token,
                bind=self._bind.text().strip() or "127.0.0.1",
                port=self._port.value(),
                fps=float(self._fps.value()),
                quality=self._quality.value(),
                ssl_context=ssl_context,
                audio_config=AudioCaptureConfig(
                    enabled=self._enable_audio.isChecked()
                    and self._enable_audio.isEnabled(),
                ),
            )
            host.start()
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self, _t("rd_host_start"), str(error))
            return
        registry._host = host  # noqa: SLF001  centralised lifecycle ownership
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
            host_id = status.get("host_id") or ""
            self._host_id_label.setText(
                format_host_id(host_id) if host_id else "---"
            )
            self._badge.set_state(
                "running",
                _t("rd_badge_running")
                .replace("{port}", str(status["port"]))
                .replace("{n}", str(status["connected_clients"])),
            )
        else:
            self._host_id_label.setText("---")
            self._badge.set_state("stopped", _t("rd_badge_stopped"))

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
    _audio_signal = Signal(bytes)
    _clipboard_signal = Signal(str, object)
    _file_progress_signal = Signal(str, int, int)
    _file_complete_signal = Signal(str, bool, str, str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._host_field = QLineEdit("127.0.0.1")
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(0)
        self._token = QLineEdit()
        self._host_id = QLineEdit()
        self._host_id.setStyleSheet(
            "font-family: 'Consolas', 'Menlo', 'Courier New', monospace; "
            "font-size: 18pt; letter-spacing: 1px;"
        )
        self._transport = QComboBox()
        self._transport.addItems(["TCP", "WebSocket", "TLS", "WSS"])
        self._tls_insecure = QCheckBox()
        self._tls_insecure.setChecked(True)
        self._enable_audio = QCheckBox()
        self._enable_audio.setChecked(False)
        if not is_audio_backend_available():
            self._enable_audio.setEnabled(False)
        self._badge = _StatusBadge()
        self._status = QLabel()
        self._status.setStyleSheet("color: #555; font-size: 9pt;")
        self._display = _FrameDisplay()
        self._connect_btn: Optional[QPushButton] = None
        self._disconnect_btn: Optional[QPushButton] = None
        self._action_row: Optional[QWidget] = None
        self._connected = False
        self._audio_player: Optional[AudioPlayer] = None
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_label = QLabel()
        self._progress_label.setVisible(False)
        self._active_progress_id: Optional[str] = None
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

        # === Connection card ===
        card = self._tr(QGroupBox(), "rd_viewer_card_group")
        card.setStyleSheet("QGroupBox { font-weight: bold; }")
        card_layout = QVBoxLayout()

        id_row = QHBoxLayout()
        id_row.addWidget(self._tr(QLabel(), "rd_host_id_label"))
        id_row.addWidget(self._host_id, stretch=1)
        id_row.addWidget(self._badge)
        card_layout.addLayout(id_row)

        addr_row = QHBoxLayout()
        addr_row.addWidget(self._tr(QLabel(), "rd_bind_label"))
        addr_row.addWidget(self._host_field, stretch=1)
        addr_row.addWidget(self._tr(QLabel(), "rd_port_label"))
        addr_row.addWidget(self._port)
        addr_row.addWidget(self._tr(QLabel(), "rd_transport_label"))
        addr_row.addWidget(self._transport)
        card_layout.addLayout(addr_row)

        token_row = QHBoxLayout()
        token_row.addWidget(self._tr(QLabel(), "rd_token_label"))
        token_row.addWidget(self._token, stretch=1)
        card_layout.addLayout(token_row)

        card.setLayout(card_layout)
        root.addWidget(card)

        # === Advanced (collapsible) ===
        advanced = _CollapsibleSection()
        self._tr(advanced, "rd_advanced_group", setter="setTitle")
        adv_layout = QVBoxLayout()
        adv_layout.addWidget(self._tr(self._tls_insecure, "rd_tls_insecure"))
        adv_layout.addWidget(self._tr(self._enable_audio,
                                      "rd_viewer_audio_play"))
        advanced.set_body_layout(adv_layout)
        root.addWidget(advanced)

        # === Connect / Disconnect ===
        btn_row = QHBoxLayout()
        self._connect_btn = self._tr(QPushButton(), "rd_viewer_connect")
        self._connect_btn.setMinimumHeight(36)
        self._connect_btn.setStyleSheet("font-weight: bold;")
        self._connect_btn.clicked.connect(self._connect)
        self._disconnect_btn = self._tr(QPushButton(), "rd_viewer_disconnect")
        self._disconnect_btn.setMinimumHeight(36)
        self._disconnect_btn.clicked.connect(self._disconnect)
        btn_row.addWidget(self._connect_btn, stretch=2)
        btn_row.addWidget(self._disconnect_btn, stretch=1)
        root.addLayout(btn_row)

        # === Live actions (only visible while connected) ===
        action_row_widget = QWidget()
        action_row = QHBoxLayout(action_row_widget)
        action_row.setContentsMargins(0, 0, 0, 0)
        push_clip_btn = self._tr(QPushButton(), "rd_viewer_push_clipboard")
        push_clip_btn.clicked.connect(self._push_clipboard_to_host)
        send_file_btn = self._tr(QPushButton(), "rd_viewer_send_file")
        send_file_btn.clicked.connect(self._on_send_file_clicked)
        action_row.addWidget(push_clip_btn)
        action_row.addWidget(send_file_btn)
        action_row.addStretch()
        action_row_widget.setVisible(False)
        self._action_row = action_row_widget
        root.addWidget(action_row_widget)

        # === Frame display + progress ===
        root.addWidget(self._display, stretch=1)
        root.addWidget(self._progress_label)
        root.addWidget(self._progress_bar)
        root.addWidget(self._status)

    def _wire_signals(self) -> None:
        self._frame_signal.connect(self._on_frame_main)
        self._error_signal.connect(self._on_error_main)
        self._audio_signal.connect(self._on_audio_main)
        self._clipboard_signal.connect(self._on_clipboard_main)
        self._file_progress_signal.connect(self._on_file_progress_main)
        self._file_complete_signal.connect(self._on_file_complete_main)
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
        self._display.files_dropped.connect(self._on_files_dropped)

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
            expected_id = self._parse_host_id_input()
        except HostIdError as error:
            QMessageBox.warning(self, _t("rd_viewer_connect"), str(error))
            return
        transport = self._transport.currentText()
        ssl_context = self._build_client_ssl_context(transport)
        viewer_cls = (WebSocketDesktopViewer
                      if transport in ("WebSocket", "WSS")
                      else RemoteDesktopViewer)
        registry.disconnect_viewer()
        try:
            viewer = viewer_cls(
                host=host, port=port, token=token,
                on_frame=self._frame_signal.emit,
                on_error=lambda exc: self._error_signal.emit(str(exc)),
                on_audio=self._audio_signal.emit,
                on_clipboard=lambda kind, data:
                    self._clipboard_signal.emit(kind, data),
                expected_host_id=expected_id,
                ssl_context=ssl_context,
            )
            viewer.set_file_receiver(FileReceiver(
                on_progress=lambda tid, done, total:
                    self._file_progress_signal.emit(tid, done, total),
                on_complete=lambda tid, ok, err, dst:
                    self._file_complete_signal.emit(
                        tid, bool(ok), err or "", dst,
                    ),
            ))
            viewer.connect(timeout=5.0)
        except AuthenticationError as error:
            QMessageBox.warning(self, _t("rd_viewer_connect"), str(error))
            return
        except (OSError, RuntimeError) as error:
            QMessageBox.warning(self, _t("rd_viewer_connect"), str(error))
            return
        registry._viewer = viewer  # noqa: SLF001  centralised lifecycle ownership
        self._connected = True
        self._start_audio_player_if_requested()
        self._refresh_status()

    def _parse_host_id_input(self) -> Optional[str]:
        text = self._host_id.text().strip()
        if not text:
            return None
        return parse_host_id(text)

    def _build_client_ssl_context(
            self, transport: str) -> Optional[ssl.SSLContext]:
        if transport not in ("TLS", "WSS"):
            return None
        if self._tls_insecure.isChecked():
            return _build_insecure_client_context()
        return _build_verifying_client_context()

    def _start_audio_player_if_requested(self) -> None:
        if not (self._enable_audio.isChecked()
                and self._enable_audio.isEnabled()):
            return
        try:
            player = AudioPlayer()
            player.start()
        except (OSError, RuntimeError) as error:
            self._status.setText(f"{_t('rd_viewer_audio_play')}: {error}")
            return
        self._audio_player = player

    def _stop_audio_player(self) -> None:
        player = self._audio_player
        self._audio_player = None
        if player is not None:
            try:
                player.stop()
            except (OSError, RuntimeError):
                pass

    def _disconnect(self) -> None:
        registry.disconnect_viewer()
        self._stop_audio_player()
        self._connected = False
        self._display.clear()
        self._progress_bar.setVisible(False)
        self._progress_label.setText("")
        self._active_progress_id = None
        self._refresh_status()

    def _refresh_status(self) -> None:
        live = self._connected and registry.viewer_status()["connected"]
        if live:
            self._badge.set_state("live", _t("rd_badge_live"))
        else:
            self._badge.set_state("idle", _t("rd_badge_idle"))
        if self._action_row is not None:
            self._action_row.setVisible(live)

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

    def _on_audio_main(self, payload: bytes) -> None:
        player = self._audio_player
        if player is None:
            return
        try:
            player.play(payload)
        except (OSError, RuntimeError):
            pass

    def _on_clipboard_main(self, kind: str, data) -> None:
        from je_auto_control.utils.clipboard.clipboard import (
            set_clipboard, set_clipboard_image,
        )
        try:
            if kind == "text":
                set_clipboard(data)
            elif kind == "image":
                set_clipboard_image(data)
        except (OSError, RuntimeError) as error:
            self._status.setText(f"{_t('rd_viewer_error')}: {error}")
            return
        self._status.setText(_t("rd_viewer_clipboard_received"))

    def _on_file_progress_main(self, transfer_id: str,
                               bytes_done: int, total: int) -> None:
        if (self._active_progress_id is not None
                and self._active_progress_id != transfer_id):
            return
        self._active_progress_id = transfer_id
        self._progress_bar.setVisible(True)
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(min(bytes_done, total))
        else:
            self._progress_bar.setRange(0, 0)
        self._progress_label.setText(
            _t("rd_progress_label")
            .replace("{done}", str(bytes_done))
            .replace("{total}", str(total))
        )

    def _on_file_complete_main(self, transfer_id: str, success: bool,
                               error: str, dest_path: str) -> None:
        del transfer_id
        self._active_progress_id = None
        self._progress_bar.setVisible(False)
        if success:
            self._progress_label.setText(
                _t("rd_progress_done").replace("{path}", dest_path)
            )
        else:
            self._progress_label.setText(
                _t("rd_progress_failed").replace("{error}", error)
            )

    # --- input forwarding ---------------------------------------------

    def _send(self, action: dict) -> None:
        viewer = registry.viewer
        if viewer is None or not viewer.connected:
            return
        try:
            viewer.send_input(action)
        except OSError as error:
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

    # --- clipboard / file transfer (viewer -> host) -------------------

    def _push_clipboard_to_host(self) -> None:
        viewer = registry.viewer
        if viewer is None or not viewer.connected:
            QMessageBox.warning(self, _t("rd_viewer_push_clipboard"),
                                _t("rd_viewer_status_idle"))
            return
        text = QGuiApplication.clipboard().text()
        if not text:
            self._status.setText(_t("rd_clipboard_empty"))
            return
        try:
            viewer.send_clipboard_text(text)
        except OSError as error:
            QMessageBox.warning(self, _t("rd_viewer_push_clipboard"),
                                str(error))
            return
        self._status.setText(_t("rd_clipboard_sent"))

    def _on_send_file_clicked(self) -> None:
        viewer = registry.viewer
        if viewer is None or not viewer.connected:
            QMessageBox.warning(self, _t("rd_viewer_send_file"),
                                _t("rd_viewer_status_idle"))
            return
        source, _ = QFileDialog.getOpenFileName(
            self, _t("rd_viewer_send_file"), "", "All Files (*)",
        )
        if not source:
            return
        self._upload_file(source)

    def _on_files_dropped(self, paths) -> None:
        viewer = registry.viewer
        if viewer is None or not viewer.connected:
            return
        for path in paths:
            self._upload_file(path)

    def _upload_file(self, source_path: str) -> None:
        default_dest = "~/" + Path(source_path).name
        dest, ok = QInputDialog.getText(
            self, _t("rd_viewer_send_file"),
            _t("rd_dest_path_prompt").replace("{name}",
                                              Path(source_path).name),
            text=default_dest,
        )
        if not ok or not dest:
            return
        viewer = registry.viewer
        if viewer is None:
            return
        thread = _FileSendThread(viewer, source_path, dest, self)
        thread.progress.connect(self._on_file_progress_main)
        thread.completed.connect(self._on_file_complete_main)
        thread.finished.connect(thread.deleteLater)
        thread.start()


class _FileSendThread(QThread):
    """Run send_file off the GUI thread; bridge progress via signals."""

    progress = Signal(str, int, int)
    completed = Signal(str, bool, str, str)

    def __init__(self, viewer: RemoteDesktopViewer, source: str, dest: str,
                 parent=None) -> None:
        super().__init__(parent)
        self._viewer = viewer
        self._source = source
        self._dest = dest

    def run(self) -> None:
        def relay(transfer_id, done, total):
            self.progress.emit(transfer_id, done, total)
        try:
            result = self._viewer.send_file(
                self._source, self._dest, on_progress=relay,
            )
        except (OSError, RuntimeError) as error:
            self.completed.emit("", False, str(error), self._dest)
            return
        self.completed.emit(
            result.transfer_id, bool(result.success),
            result.error or "", self._dest,
        )


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
