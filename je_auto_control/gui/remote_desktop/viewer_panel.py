"""``_ViewerPanel``: the 'control another machine' Remote Desktop sub-tab."""
import ssl
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.remote_desktop._helpers import (
    _CollapsibleSection, _StatusBadge, _build_insecure_client_context,
    _build_verifying_client_context, _t,
)
from je_auto_control.gui.remote_desktop.remote_screen_window import (
    RemoteScreenWindow,
)
from je_auto_control.utils.remote_desktop import (
    FileReceiver, RemoteDesktopViewer, WebSocketDesktopViewer,
)
from je_auto_control.utils.remote_desktop.audio import (
    AudioPlayer, is_audio_backend_available,
)
from je_auto_control.utils.remote_desktop.host_id import (
    HostIdError, parse_host_id,
)
from je_auto_control.utils.remote_desktop.protocol import (
    AuthenticationError,
)
from je_auto_control.utils.remote_desktop.registry import registry


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
        # _screen_window is created lazily on connect — the AnyDesk-style
        # popout. While disconnected we hold ``None`` and the panel
        # itself stays compact instead of devoting half its height to a
        # blank frame area.
        self._screen_window: Optional[RemoteScreenWindow] = None
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
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        root.addWidget(self._build_card())
        root.addWidget(self._build_advanced())
        root.addLayout(self._build_button_row())
        root.addWidget(self._build_action_row())

        # The remote desktop opens in its own popup window on connect
        # (AnyDesk-style), so the panel itself only carries control
        # surface, status, and transfer progress.
        root.addWidget(self._progress_label)
        root.addWidget(self._progress_bar)
        root.addWidget(self._status)
        root.addStretch(1)

    def _build_card(self) -> QGroupBox:
        card = self._tr(QGroupBox(), "rd_viewer_card_group")
        card.setStyleSheet("QGroupBox { font-weight: bold; }")
        card_layout = QVBoxLayout()
        card_layout.setSpacing(6)

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
        return card

    def _build_advanced(self) -> _CollapsibleSection:
        advanced = _CollapsibleSection()
        self._tr(advanced, "rd_advanced_group", setter="setTitle")
        adv_layout = QVBoxLayout()
        adv_layout.addWidget(self._tr(self._tls_insecure, "rd_tls_insecure"))
        adv_layout.addWidget(self._tr(self._enable_audio,
                                      "rd_viewer_audio_play"))
        advanced.set_body_layout(adv_layout)
        return advanced

    def _build_button_row(self) -> QHBoxLayout:
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
        return btn_row

    def _build_action_row(self) -> QWidget:
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
        return action_row_widget

    def _wire_signals(self) -> None:
        # Cross-thread frame / event marshalling — the Signals fire on
        # the network thread, the slots run on the GUI thread.
        self._frame_signal.connect(self._on_frame_main)
        self._error_signal.connect(self._on_error_main)
        self._audio_signal.connect(self._on_audio_main)
        self._clipboard_signal.connect(self._on_clipboard_main)
        self._file_progress_signal.connect(self._on_file_progress_main)
        self._file_complete_signal.connect(self._on_file_complete_main)
        # Input-forwarding signals come from the popup window (see
        # _ensure_screen_window). They aren't wired here because the
        # window is created lazily on connect.

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
        # AnyDesk-style: open the live screen in its own window so the
        # operator gets a real workspace and the control panel stays
        # uncluttered.
        window = self._ensure_screen_window()
        window.show()
        window.raise_()
        window.activateWindow()
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
        self._close_screen_window()
        self._progress_bar.setVisible(False)
        self._progress_label.setText("")
        self._active_progress_id = None
        self._refresh_status()

    # --- pop-out screen window ----------------------------------------

    def _ensure_screen_window(self) -> RemoteScreenWindow:
        """Create-on-demand the AnyDesk-style remote-desktop window."""
        if self._screen_window is not None:
            return self._screen_window
        host_id = self._host_id.text().strip()
        title = (
            _t("rd_remote_screen_title_with_id").replace("{host_id}", host_id)
            if host_id else _t("rd_remote_screen_title")
        )
        window = RemoteScreenWindow(title, parent=self)
        window.mouse_moved.connect(self._send_mouse_move)
        window.mouse_pressed.connect(self._send_mouse_press)
        window.mouse_released.connect(self._send_mouse_release)
        window.mouse_scrolled.connect(self._send_mouse_scroll)
        window.key_pressed.connect(
            lambda k: self._send({"action": "key_press", "keycode": k})
        )
        window.key_released.connect(
            lambda k: self._send({"action": "key_release", "keycode": k})
        )
        window.type_text.connect(
            lambda text: self._send({"action": "type", "text": text})
        )
        window.files_dropped.connect(self._on_files_dropped)
        # If the operator closes the popup, mirror the action by
        # disconnecting — same behaviour AnyDesk has when you ✕ the
        # session window.
        window.closed.connect(self._on_screen_window_closed)
        self._screen_window = window
        return window

    def _close_screen_window(self) -> None:
        window = self._screen_window
        self._screen_window = None
        if window is not None:
            try:
                window.closed.disconnect(self._on_screen_window_closed)
            except (RuntimeError, TypeError):
                pass
            window.hide()
            window.deleteLater()

    def _on_screen_window_closed(self) -> None:
        # Operator dismissed the popup → fall through to disconnect.
        if self._connected:
            self._disconnect()

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
        if image.isNull() or self._screen_window is None:
            return
        self._screen_window.set_image(image)

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
        self._progress_label.setVisible(True)
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
        self._progress_label.setVisible(True)
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
        source, _selected = QFileDialog.getOpenFileName(
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
