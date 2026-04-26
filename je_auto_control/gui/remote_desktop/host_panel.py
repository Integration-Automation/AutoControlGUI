"""``_HostPanel``: the 'host this machine' Remote Desktop sub-tab."""
import secrets
import ssl
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.remote_desktop._helpers import (
    _CollapsibleSection, _StatusBadge, _t,
)
from je_auto_control.gui.remote_desktop.frame_display import _FrameDisplay
from je_auto_control.utils.remote_desktop import (
    RemoteDesktopHost, WebSocketDesktopHost,
)
from je_auto_control.utils.remote_desktop.audio import (
    AudioCaptureConfig, is_audio_backend_available,
)
from je_auto_control.utils.remote_desktop.host_id import format_host_id
from je_auto_control.utils.remote_desktop.registry import registry


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
        path, _selected = QFileDialog.getOpenFileName(
            self, _t("rd_tls_cert_label"), "",
            "PEM (*.pem *.crt *.cer);;All (*)",
        )
        if path:
            self._tls_cert.setText(path)

    def _browse_key(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
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
