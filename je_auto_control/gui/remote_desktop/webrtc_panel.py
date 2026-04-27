"""WebRTC sub-tabs for the Remote Desktop tab.

Two sections per panel:
  * Signaling server flow — the AnyDesk-style "type host ID and connect"
    UX, backed by ``signaling_server.py``. Recommended for daily use.
  * Manual SDP exchange — copy/paste fallback when no server is reachable.

An advanced collapsible group below exposes STUN/TURN servers; defaults
to Google's public STUN, which is enough for most LAN/home-network
scenarios. Mobile / strict-NAT users will want to add a TURN server.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.remote_desktop._helpers import _t
from je_auto_control.gui.remote_desktop.blanking_overlay import BlankingOverlay
from je_auto_control.gui.remote_desktop.frame_display import _FrameDisplay
from je_auto_control.gui.remote_desktop.sparkline import Sparkline
from je_auto_control.gui.remote_desktop.annotation_overlay import (
    HostAnnotationOverlay,
)
from je_auto_control.gui.remote_desktop.tray_icon import install_host_tray
from je_auto_control.gui.remote_desktop.viewer_screen_window import (
    ViewerScreenWindow,
)
from je_auto_control.gui.remote_desktop.webrtc_dialogs import (
    AddressBookList, AuditLogDialog, KnownHostsDialog, LanBrowseDialog,
    PendingViewerDialog, RemoteFilesTable, TrustedViewersList,
)
from je_auto_control.gui.remote_desktop.webrtc_workers import (
    HostPublishLoopWorker, ViewerAnswerPushWorker, ViewerSignalingWorker,
    generate_host_id,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop import (
    MultiViewerHost, SessionRecorder, WebRTCConfig, WebRTCDesktopViewer,
    active_hardware_codec, available_hardware_codecs, default_address_book,
    default_trust_list, install_hardware_codec, is_webrtc_available,
    load_or_create_viewer_id, send_magic_packet, uninstall_hardware_codec,
)
from je_auto_control.utils.remote_desktop.adaptive_bitrate import (
    AdaptiveBitrateController,
)
from je_auto_control.utils.remote_desktop.session_quality_cache import (
    SessionQualityCache,
)
from je_auto_control.utils.remote_desktop.webrtc_inspector import (
    default_webrtc_inspector,
)
from je_auto_control.utils.remote_desktop.webrtc_stats import (
    StatsPoller, StatsSnapshot,
)
from je_auto_control.utils.remote_desktop.webrtc_transport import (
    BANDWIDTH_PRESETS, fps_for_preset,
)


_DEFAULT_FPS = 24
_DEFAULT_MONITOR = 1
# Plain http:// is intentional: the bundled signaling server defaults
# to localhost without TLS, and operators put TLS in front via nginx /
# Caddy. Hotspot S5332 acknowledged on a per-line basis; see callers.
_DEFAULT_SIGNALING_URL = "http://127.0.0.1:8765"  # NOSONAR python:S5332
_DEFAULT_STUN = "stun:stun.l.google.com:19302"

_QUALITY_DOT_STYLE = "background-color: #555; border-radius: 7px;"
_JSON_FILE_FILTER = "JSON (*.json);;All (*)"


def _av_frame_to_qimage(frame) -> Optional[QImage]:
    """Convert an aiortc/av video frame to a Qt-owned QImage."""
    try:
        arr = frame.to_ndarray(format="rgb24")
    except (ValueError, RuntimeError) as error:
        autocontrol_logger.debug("av->QImage failed: %r", error)
        return None
    height, width, _ = arr.shape
    image = QImage(
        arr.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888,
    )
    return image.copy()


class _PanelSignals(QObject):
    """Bridge so asyncio-thread callbacks reach Qt safely."""
    frame = Signal(QImage)
    state = Signal(str)
    auth = Signal(bool)
    # Host-side: (session_id, viewer_id-or-None) per pending viewer prompt.
    pending_viewer = Signal(str, object)
    stats = Signal(object)  # StatsSnapshot
    session_count = Signal(int)
    # Viewer-side file browser: list and op result.
    inbox_listing = Signal(object)  # list[dict]
    inbox_op = Signal(str, bool, object)  # name, ok, error
    # Host-side: incoming viewer-shared screen frame
    viewer_video_frame = Signal(QImage)
    # Host-side: incoming annotation event from viewer
    annotation = Signal(object)  # dict


def _build_advanced_group(panel: TranslatableMixin,
                          include_hw_codec: bool = False) -> QGroupBox:
    """Shared 'Advanced' STUN/TURN (+ optional hw codec) group."""
    group = panel._tr(QGroupBox(), "rd_webrtc_advanced_group")
    grid = QGridLayout()
    grid.addWidget(panel._tr(QLabel(), "rd_webrtc_stun_label"), 0, 0)
    panel._stun_edit = QLineEdit(_DEFAULT_STUN)
    grid.addWidget(panel._stun_edit, 0, 1, 1, 3)
    grid.addWidget(panel._tr(QLabel(), "rd_webrtc_turn_label"), 1, 0)
    panel._turn_edit = panel._tr(QLineEdit(), "rd_webrtc_turn_placeholder")
    grid.addWidget(panel._turn_edit, 1, 1, 1, 3)
    grid.addWidget(panel._tr(QLabel(), "rd_webrtc_turn_user_label"), 2, 0)
    panel._turn_user_edit = QLineEdit()
    grid.addWidget(panel._turn_user_edit, 2, 1)
    grid.addWidget(panel._tr(QLabel(), "rd_webrtc_turn_cred_label"), 2, 2)
    panel._turn_cred_edit = QLineEdit()
    panel._turn_cred_edit.setEchoMode(QLineEdit.EchoMode.Password)
    grid.addWidget(panel._turn_cred_edit, 2, 3)
    if include_hw_codec:
        grid.addWidget(panel._tr(QLabel(), "rd_webrtc_hw_codec_label"), 3, 0)
        panel._hw_codec_combo = QComboBox()
        panel._hw_codec_combo.addItem(_t("rd_webrtc_hw_codec_off"), "")
        for name in available_hardware_codecs():
            panel._hw_codec_combo.addItem(name, name)
        active = active_hardware_codec()
        if active:
            idx = panel._hw_codec_combo.findData(active)
            if idx >= 0:
                panel._hw_codec_combo.setCurrentIndex(idx)
        panel._hw_codec_combo.currentIndexChanged.connect(
            lambda _i: panel._on_hw_codec_changed(),
        )
        grid.addWidget(panel._hw_codec_combo, 3, 1, 1, 3)
    group.setLayout(grid)
    return group


def _checked_or(panel, attr: str, default: bool = False) -> bool:
    """Return ``panel.<attr>.isChecked()`` if the widget exists, else default."""
    widget = getattr(panel, attr, None)
    return widget.isChecked() if widget is not None else default


def _read_region(panel) -> Optional[tuple]:
    edit = getattr(panel, "_region_edit", None)
    if edit is None:
        return None
    text = edit.text().strip()
    if not text:
        return None
    try:
        parts = [int(p.strip()) for p in text.split(",")]
    except (ValueError, TypeError):
        return None
    return tuple(parts) if len(parts) == 4 else None


def _read_webrtc_config(panel) -> WebRTCConfig:
    """Build a WebRTCConfig from the advanced group + monitor/fps fields."""
    from je_auto_control.utils.remote_desktop.webrtc_transport import (
        _DEFAULT_STUN_SERVERS,
    )
    stun_field = panel._stun_edit.text().strip()
    ice_servers = [stun_field] if stun_field else list(_DEFAULT_STUN_SERVERS)
    monitor = (
        int(panel._monitor_combo.currentData() or _DEFAULT_MONITOR)
        if hasattr(panel, "_monitor_combo") else _DEFAULT_MONITOR
    )
    fps = (int(panel._fps_spin.value())
           if hasattr(panel, "_fps_spin") else _DEFAULT_FPS)
    max_bitrate = (
        int(panel._max_bitrate_spin.value())
        if hasattr(panel, "_max_bitrate_spin") else 0
    )
    return WebRTCConfig(
        ice_servers=ice_servers,
        turn_url=panel._turn_edit.text().strip() or None,
        turn_username=panel._turn_user_edit.text().strip() or None,
        turn_credential=panel._turn_cred_edit.text() or None,
        monitor_index=monitor,
        fps=fps,
        show_cursor=_checked_or(panel, "_cursor_check", default=True),
        accept_viewer_video=_checked_or(panel, "_accept_viewer_video_check"),
        accept_viewer_audio_opus=_checked_or(panel, "_accept_opus_audio_check"),
        share_my_screen=_checked_or(panel, "_share_my_screen_check"),
        share_my_audio_opus=_checked_or(panel, "_share_opus_mic_check"),
        max_bitrate_kbps=max_bitrate,
        region=_read_region(panel),
        host_voice=_checked_or(panel, "_host_voice_check"),
    )


class _WebRTCHostPanel(TranslatableMixin, QWidget):
    """Host: stream this machine's screen and accept viewer input."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._multi_host: Optional[MultiViewerHost] = None
        self._publish_loop: Optional[HostPublishLoopWorker] = None
        self._manual_session_id: Optional[str] = None
        self._adaptive_controller: Optional[AdaptiveBitrateController] = None
        self._adaptive_poller: Optional[StatsPoller] = None
        self._session_pollers: dict = {}    # session_id -> StatsPoller
        # Lock-protected cache replacing two raw dicts; mutated by the
        # asyncio bridge thread (StatsPoller cb) and read/cleared by the
        # Qt thread. See utils/remote_desktop/session_quality_cache.py.
        self._session_cache = SessionQualityCache()
        self._trust_list = default_trust_list()
        self._blanking: Optional[BlankingOverlay] = None
        self._viewer_screen_window: Optional[ViewerScreenWindow] = None
        self._lan_advertiser = None
        self._annotation_overlay: Optional[HostAnnotationOverlay] = None
        self._tray = install_host_tray(
            on_open=self._on_tray_open,
            on_stop=self._on_tray_stop,
            on_quit=self._on_tray_quit,
            parent=self,
        )
        self._signals = _PanelSignals()
        self._signals.state.connect(self._on_state)
        self._signals.auth.connect(self._on_auth)
        self._signals.pending_viewer.connect(self._on_pending_viewer)
        self._signals.session_count.connect(self._on_session_count)
        self._signals.viewer_video_frame.connect(self._on_viewer_video_image)
        self._signals.annotation.connect(self._on_annotation_event)
        self._build_ui()
        self._refresh_trusted_list()
        self._update_availability()

    # --- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(self._build_signaling_group())
        layout.addWidget(self._build_config_group())
        layout.addWidget(self._build_manual_group())
        layout.addWidget(_build_advanced_group(self, include_hw_codec=True))
        layout.addWidget(self._build_trusted_group())
        self._status_label = QLabel(_t("rd_webrtc_status_idle"))
        layout.addWidget(self._status_label)
        sessions_row = QHBoxLayout()
        self._host_quality_dot = QLabel()
        self._host_quality_dot.setFixedSize(14, 14)
        self._host_quality_dot.setStyleSheet(
            _QUALITY_DOT_STYLE,
        )
        self._host_quality_dot.setToolTip(_t("rd_webrtc_quality_unknown"))
        sessions_row.addWidget(self._host_quality_dot)
        self._sessions_label = QLabel(_t("rd_webrtc_sessions_count").format(n=0))
        sessions_row.addWidget(self._sessions_label, stretch=1)
        layout.addLayout(sessions_row)
        self._sessions_table = QTableWidget(0, 5)
        self._sessions_table.setHorizontalHeaderLabels([
            "",  # quality dot column
            _t("rd_webrtc_sess_col_id"),
            _t("rd_webrtc_sess_col_viewer"),
            _t("rd_webrtc_sess_col_state"),
            _t("rd_webrtc_sess_col_connected"),
        ])
        self._sessions_table.setColumnWidth(0, 18)
        self._sessions_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch,
        )
        self._sessions_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers,
        )
        self._sessions_table.setMaximumHeight(140)
        self._sessions_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows,
        )
        self._sessions_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection,
        )
        self._sessions_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu,
        )
        self._sessions_table.customContextMenuRequested.connect(
            self._on_sessions_context_menu,
        )
        layout.addWidget(self._sessions_table)
        sessions_btn_row = QHBoxLayout()
        self._disconnect_btn = self._tr(
            QPushButton(), "rd_webrtc_disconnect_selected",
        )
        self._disconnect_btn.clicked.connect(self._on_disconnect_selected)
        sessions_btn_row.addWidget(self._disconnect_btn)
        sessions_btn_row.addStretch()
        layout.addLayout(sessions_btn_row)
        push_row = QHBoxLayout()
        self._push_file_btn = self._tr(QPushButton(), "rd_webrtc_push_file")
        self._push_file_btn.clicked.connect(self._on_push_file)
        push_row.addWidget(self._push_file_btn)
        audit_btn = self._tr(QPushButton(), "rd_webrtc_view_audit")
        audit_btn.clicked.connect(self._on_view_audit)
        push_row.addWidget(audit_btn)
        push_row.addStretch()
        layout.addLayout(push_row)

    def _on_view_audit(self) -> None:
        from je_auto_control.utils.remote_desktop.audit_log import (
            default_audit_log,
        )
        AuditLogDialog(default_audit_log(), parent=self).exec()

    def _on_push_file(self) -> None:
        if self._multi_host is None or self._multi_host.session_count() == 0:
            QMessageBox.information(
                self, "WebRTC", _t("rd_webrtc_no_viewers"),
            )
            return
        path, _filter = QFileDialog.getOpenFileName(
            self, _t("rd_webrtc_push_file"), "",
        )
        if not path:
            return
        try:
            sent = self._multi_host.broadcast_file(path)
            QMessageBox.information(
                self, "WebRTC",
                _t("rd_webrtc_push_done").format(n=sent, name=path),
            )
        except (RuntimeError, OSError, ValueError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_hw_codec_changed(self) -> None:
        codec = self._hw_codec_combo.currentData() or ""
        if not codec:
            uninstall_hardware_codec()
            self._status_label.setText(_t("rd_webrtc_hw_codec_off_status"))
            return
        if install_hardware_codec(codec):
            self._status_label.setText(
                _t("rd_webrtc_hw_codec_active").format(codec=codec),
            )
        else:
            self._status_label.setText(
                _t("rd_webrtc_hw_codec_failed").format(codec=codec),
            )

    def _build_trusted_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "rd_webrtc_trusted_group")
        layout = QVBoxLayout()
        self._trusted_list = TrustedViewersList()
        self._trusted_list.removed.connect(self._on_remove_trust)
        layout.addWidget(self._trusted_list)
        button_row = QHBoxLayout()
        remove_btn = self._tr(QPushButton(), "rd_webrtc_remove_trusted")
        remove_btn.clicked.connect(self._on_remove_trust_button)
        button_row.addWidget(remove_btn)
        clear_btn = self._tr(QPushButton(), "rd_webrtc_clear_trusted")
        clear_btn.clicked.connect(self._on_clear_trust)
        button_row.addWidget(clear_btn)
        import_btn = self._tr(QPushButton(), "rd_webrtc_trust_import")
        import_btn.clicked.connect(self._on_import_trust)
        button_row.addWidget(import_btn)
        export_btn = self._tr(QPushButton(), "rd_webrtc_trust_export")
        export_btn.clicked.connect(self._on_export_trust)
        button_row.addWidget(export_btn)
        layout.addLayout(button_row)
        group.setLayout(layout)
        return group

    def _on_export_trust(self) -> None:
        import json as _json
        path, _filter = QFileDialog.getSaveFileName(
            self, _t("rd_webrtc_trust_export"), "trusted_viewers.json",
            _JSON_FILE_FILTER,
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                _json.dump({"viewers": self._trust_list.list_entries()},
                           fh, indent=2, ensure_ascii=False)
        except OSError as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_import_trust(self) -> None:
        import json as _json
        path, _filter = QFileDialog.getOpenFileName(
            self, _t("rd_webrtc_trust_import"), "", _JSON_FILE_FILTER,
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = _json.load(fh)
        except (OSError, _json.JSONDecodeError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))
            return
        viewers = data.get("viewers") if isinstance(data, dict) else data
        added = 0
        for entry in viewers or []:
            if not isinstance(entry, dict):
                continue
            vid = entry.get("viewer_id")
            label = entry.get("label", "") or ""
            if isinstance(vid, str) and vid:
                self._trust_list.add(vid, label=label)
                added += 1
        QMessageBox.information(
            self, "WebRTC",
            _t("rd_webrtc_trust_import_done").format(n=added),
        )
        self._refresh_trusted_list()

    def _refresh_trusted_list(self) -> None:
        self._trusted_list.populate(self._trust_list.list_entries())

    def _build_signaling_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "rd_webrtc_signaling_group")
        grid = QGridLayout()
        grid.addWidget(self._tr(QLabel(), "rd_webrtc_server_label"), 0, 0)
        self._server_edit = QLineEdit(_DEFAULT_SIGNALING_URL)
        grid.addWidget(self._server_edit, 0, 1, 1, 3)
        grid.addWidget(self._tr(QLabel(), "rd_webrtc_host_id_label"), 1, 0)
        self._host_id_edit = QLineEdit(generate_host_id())
        grid.addWidget(self._host_id_edit, 1, 1, 1, 2)
        regen = self._tr(QPushButton(), "rd_webrtc_regen_id")
        regen.clicked.connect(self._on_regen_id)
        grid.addWidget(regen, 1, 3)
        grid.addWidget(self._tr(QLabel(), "rd_webrtc_secret_label"), 2, 0)
        self._secret_edit = QLineEdit()
        self._secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(self._secret_edit, 2, 1, 1, 3)
        self._publish_btn = self._tr(
            QPushButton(), "rd_webrtc_publish_via_server",
        )
        self._publish_btn.clicked.connect(self._on_publish_via_server)
        grid.addWidget(self._publish_btn, 3, 0, 1, 4)
        # Read-only fingerprint label + copy button
        from je_auto_control.utils.remote_desktop.fingerprint import (
            fingerprint_for_display, load_or_create_host_fingerprint,
        )
        try:
            fp = load_or_create_host_fingerprint()
        except OSError:
            fp = ""
        grid.addWidget(self._tr(QLabel(), "rd_webrtc_my_fingerprint"), 4, 0)
        self._fingerprint_label = QLabel(
            fingerprint_for_display(fp) if fp else "",
        )
        self._fingerprint_label.setStyleSheet(
            "color: #888; font-family: 'Consolas', monospace; font-size: 10pt;",
        )
        self._fingerprint_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse,
        )
        grid.addWidget(self._fingerprint_label, 4, 1, 1, 2)
        copy_fp_btn = self._tr(QPushButton(), "rd_webrtc_copy_fingerprint")
        copy_fp_btn.clicked.connect(lambda: self._on_copy_fingerprint(fp))
        grid.addWidget(copy_fp_btn, 4, 3)
        group.setLayout(grid)
        return group

    def _on_copy_fingerprint(self, fp: str) -> None:
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(fp)

    def _build_config_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "rd_webrtc_config_group")
        grid = QGridLayout()
        grid.addWidget(self._tr(QLabel(), "rd_token_label"), 0, 0)
        self._token_edit = self._tr(QLineEdit(), "rd_token_placeholder")
        grid.addWidget(self._token_edit, 0, 1)
        grid.addWidget(self._tr(QLabel(), "rd_webrtc_monitor_label"), 1, 0)
        self._monitor_combo = QComboBox()
        self._populate_monitor_combo()
        self._monitor_combo.currentIndexChanged.connect(
            self._on_monitor_changed,
        )
        grid.addWidget(self._monitor_combo, 1, 1)
        grid.addWidget(self._tr(QLabel(), "rd_fps_label"), 2, 0)
        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(1, 60)
        self._fps_spin.setValue(_DEFAULT_FPS)
        grid.addWidget(self._fps_spin, 2, 1)
        grid.addWidget(self._tr(QLabel(), "rd_webrtc_region_label"), 11, 0)
        self._region_edit = QLineEdit()
        self._tr(self._region_edit, "rd_webrtc_region_placeholder",
                 "setPlaceholderText")
        grid.addWidget(self._region_edit, 11, 1)
        pick_region_btn = self._tr(QPushButton(), "rd_webrtc_pick_region")
        pick_region_btn.clicked.connect(self._on_pick_region)
        grid.addWidget(pick_region_btn, 11, 2)
        self._cursor_check = self._tr(QCheckBox(), "rd_webrtc_show_cursor")
        self._cursor_check.setChecked(True)
        grid.addWidget(self._cursor_check, 3, 0, 1, 2)
        self._blank_check = self._tr(QCheckBox(), "rd_webrtc_blank_screen")
        self._blank_check.setChecked(False)
        self._blank_check.toggled.connect(self._on_toggle_blanking)
        grid.addWidget(self._blank_check, 4, 0, 1, 2)
        self._readonly_check = self._tr(QCheckBox(), "rd_webrtc_read_only")
        self._readonly_check.setChecked(False)
        self._readonly_check.toggled.connect(self._on_toggle_readonly)
        grid.addWidget(self._readonly_check, 5, 0, 1, 2)
        self._adaptive_check = self._tr(QCheckBox(), "rd_webrtc_adaptive")
        self._adaptive_check.setChecked(True)
        self._adaptive_check.toggled.connect(self._on_toggle_adaptive)
        grid.addWidget(self._adaptive_check, 6, 0, 1, 2)
        self._mic_recv_check = self._tr(QCheckBox(), "rd_webrtc_recv_mic")
        self._mic_recv_check.setChecked(False)
        self._mic_recv_check.toggled.connect(self._on_toggle_mic_receive)
        grid.addWidget(self._mic_recv_check, 7, 0, 1, 2)
        self._host_voice_check = self._tr(QCheckBox(), "rd_webrtc_host_voice")
        self._host_voice_check.setChecked(False)
        grid.addWidget(self._host_voice_check, 13, 0, 1, 2)
        grid.addWidget(self._tr(QLabel(), "rd_webrtc_max_bitrate"), 10, 0)
        self._max_bitrate_spin = QSpinBox()
        self._max_bitrate_spin.setRange(0, 50000)
        self._max_bitrate_spin.setSingleStep(500)
        self._max_bitrate_spin.setSuffix(" kbps (0=∞)")
        self._max_bitrate_spin.setValue(0)
        grid.addWidget(self._max_bitrate_spin, 10, 1)
        grid.addWidget(self._tr(QLabel(), "rd_webrtc_ip_whitelist"), 12, 0)
        self._ip_whitelist_edit = QTextEdit()
        self._ip_whitelist_edit.setMaximumHeight(60)
        self._tr(self._ip_whitelist_edit, "rd_webrtc_ip_whitelist_ph",
                 "setPlaceholderText")
        grid.addWidget(self._ip_whitelist_edit, 12, 1)
        self._accept_viewer_video_check = self._tr(
            QCheckBox(), "rd_webrtc_accept_viewer_video",
        )
        self._accept_viewer_video_check.setChecked(False)
        self._accept_viewer_video_check.toggled.connect(
            self._on_toggle_accept_viewer_video,
        )
        grid.addWidget(self._accept_viewer_video_check, 8, 0, 1, 2)
        self._accept_opus_audio_check = self._tr(
            QCheckBox(), "rd_webrtc_accept_opus_audio",
        )
        self._accept_opus_audio_check.setChecked(False)
        self._accept_opus_audio_check.toggled.connect(
            self._on_toggle_accept_opus_audio,
        )
        grid.addWidget(self._accept_opus_audio_check, 9, 0, 1, 2)
        group.setLayout(grid)
        return group

    def _on_toggle_accept_viewer_video(self, value: bool) -> None:
        if self._multi_host is None:
            return
        with self._multi_host._lock:
            sessions = list(self._multi_host._sessions.values())
        for host in sessions:
            try:
                if value:
                    host.set_viewer_video_callback(
                        self._on_viewer_video_av_frame,
                    )
                    host.enable_accept_viewer_video()
                else:
                    host.disable_accept_viewer_video()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("toggle accept viewer video: %r", error)
        if not value and self._viewer_screen_window is not None:
            self._viewer_screen_window.set_image(None)
            self._viewer_screen_window.hide()

    def _on_toggle_accept_opus_audio(self, value: bool) -> None:
        if self._multi_host is None:
            return
        with self._multi_host._lock:
            sessions = list(self._multi_host._sessions.values())
        for host in sessions:
            try:
                if value:
                    host.enable_accept_viewer_audio_opus()
                else:
                    host.disable_accept_viewer_audio_opus()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("toggle accept opus: %r", error)

    def _on_toggle_mic_receive(self, value: bool) -> None:
        if self._multi_host is None:
            return
        # Apply to every active session.
        with self._multi_host._lock:
            sessions = list(self._multi_host._sessions.values())
        for host in sessions:
            try:
                if value:
                    host.enable_mic_receive()
                else:
                    host.disable_mic_receive()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("mic receive toggle: %r", error)

    def _on_toggle_adaptive(self, value: bool) -> None:
        if value:
            self._maybe_start_adaptive()
        else:
            self._stop_adaptive()

    def _populate_monitor_combo(self) -> None:
        try:
            import mss
            with mss.mss() as sct:
                monitors = sct.monitors
            for idx, mon in enumerate(monitors):
                if idx == 0:
                    label = _t("rd_webrtc_monitor_all")
                else:
                    label = f"#{idx}: {mon['width']}x{mon['height']} @"\
                            f" ({mon['left']},{mon['top']})"
                self._monitor_combo.addItem(label, idx)
        except (ImportError, RuntimeError, OSError):
            for idx in range(4):
                self._monitor_combo.addItem(f"#{idx}", idx)
        # Default to monitor #1 (the first real screen for mss)
        idx_default = self._monitor_combo.findData(_DEFAULT_MONITOR)
        if idx_default >= 0:
            self._monitor_combo.setCurrentIndex(idx_default)

    def _on_pick_region(self) -> None:
        try:
            from je_auto_control.gui.selector import open_region_selector
            region = open_region_selector(self)
        except (ImportError, RuntimeError, OSError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))
            return
        if region is None:
            return
        x, y, w, h = region
        self._region_edit.setText(f"{x},{y},{w},{h}")

    def _on_monitor_changed(self, _i: int) -> None:
        idx = self._monitor_combo.currentData()
        if idx is None or self._multi_host is None:
            return
        track = self._multi_host.screen_track()
        if track is None:
            return
        try:
            track.set_target_monitor(int(idx))
            autocontrol_logger.info("monitor switched to #%d live", int(idx))
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("set_target_monitor: %r", error)

    def _on_toggle_readonly(self, value: bool) -> None:
        if self._multi_host is not None:
            self._multi_host.set_read_only(value)

    def _on_toggle_blanking(self, checked: bool) -> None:
        if checked:
            if self._blanking is None:
                self._blanking = BlankingOverlay()
            self._blanking.show()
        elif self._blanking is not None:
            self._blanking.hide()

    def _build_manual_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "rd_webrtc_manual_group")
        layout = QVBoxLayout()
        self._generate_btn = self._tr(QPushButton(), "rd_webrtc_generate_offer")
        self._generate_btn.clicked.connect(self._on_generate_offer)
        layout.addWidget(self._generate_btn)
        layout.addWidget(self._tr(QLabel(), "rd_webrtc_offer_label"))
        self._offer_view = QTextEdit()
        self._offer_view.setReadOnly(True)
        self._offer_view.setMinimumHeight(80)
        layout.addWidget(self._offer_view)
        layout.addWidget(self._tr(QLabel(), "rd_webrtc_answer_input_label"))
        self._answer_input = QTextEdit()
        self._answer_input.setMinimumHeight(80)
        self._tr(self._answer_input, "rd_webrtc_paste_answer", "setPlaceholderText")
        layout.addWidget(self._answer_input)
        button_row = QHBoxLayout()
        self._apply_btn = self._tr(QPushButton(), "rd_webrtc_apply_answer")
        self._apply_btn.clicked.connect(self._on_apply_answer)
        button_row.addWidget(self._apply_btn)
        self._stop_btn = self._tr(QPushButton(), "rd_webrtc_stop_host")
        self._stop_btn.clicked.connect(self._on_stop)
        button_row.addWidget(self._stop_btn)
        layout.addLayout(button_row)
        group.setLayout(layout)
        return group

    def _update_availability(self) -> None:
        if not is_webrtc_available():
            for widget in (self._generate_btn, self._apply_btn,
                           self._publish_btn):
                widget.setEnabled(False)
            self._status_label.setText(_t("rd_webrtc_unavailable"))

    # --- handlers ----------------------------------------------------------

    def _on_regen_id(self) -> None:
        self._host_id_edit.setText(generate_host_id())

    def _on_tray_open(self) -> None:
        win = self.window()
        if win is None:
            return
        win.showNormal()
        win.raise_()
        win.activateWindow()

    def _on_tray_stop(self) -> None:
        self._stop_host_if_any()
        self._signals.session_count.emit(0)

    def _on_tray_quit(self) -> None:
        self._stop_host_if_any()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def _on_publish_via_server(self) -> None:
        if not self._validate_required_fields(needs_server=True):
            return
        self._stop_host_if_any()
        try:
            self._multi_host = self._build_multi_host(
                self._token_edit.text().strip(),
            )
        except (ValueError, RuntimeError, OSError) as error:
            self._show_error(error)
            return
        self._publish_loop = HostPublishLoopWorker(
            multi_host=self._multi_host,
            server_url=self._server_edit.text().strip(),
            host_id=self._host_id_edit.text().strip(),
            secret=self._secret_edit.text() or None,
        )
        self._publish_loop.offer_published.connect(self._on_loop_offer_published)
        self._publish_loop.session_connected.connect(self._on_loop_session_connected)
        self._publish_loop.failed.connect(self._on_signaling_failed)
        self._status_label.setText(_t("rd_webrtc_publishing_offer"))
        self._publish_loop.start()
        self._start_lan_advertise()

    def _start_lan_advertise(self) -> None:
        try:
            from je_auto_control.utils.remote_desktop.lan_discovery import (
                HostAdvertiser, is_discovery_available,
            )
        except ImportError:
            return
        if not is_discovery_available():
            return
        try:
            if self._lan_advertiser is not None:
                self._lan_advertiser.stop()
            self._lan_advertiser = HostAdvertiser(
                host_id=self._host_id_edit.text().strip(),
                signaling_url=self._server_edit.text().strip(),
            )
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("lan advertise: %r", error)

    def _stop_lan_advertise(self) -> None:
        if self._lan_advertiser is not None:
            try:
                self._lan_advertiser.stop()
            except (RuntimeError, OSError):
                pass
            self._lan_advertiser = None

    def _on_loop_offer_published(self, session_id: str) -> None:
        autocontrol_logger.debug("publish loop: offer for %s", session_id)
        # Optional: surface the session in the UI; for now just log.

    def _on_loop_session_connected(self, session_id: str) -> None:
        if self._multi_host is not None:
            self._signals.session_count.emit(self._multi_host.session_count())

    def _on_signaling_failed(self, message: str) -> None:
        QMessageBox.warning(self, "WebRTC", message)
        self._status_label.setText(_t("rd_webrtc_status_idle"))

    def _on_generate_offer(self) -> None:
        token = self._token_edit.text().strip()
        if not token:
            QMessageBox.warning(self, "WebRTC", _t("rd_webrtc_token_required"))
            return
        try:
            if self._multi_host is None:
                self._multi_host = self._build_multi_host(token)
        except (ValueError, RuntimeError, OSError) as error:
            self._show_error(error)
            return
        self._status_label.setText(_t("rd_webrtc_generating_offer"))
        self._offer_view.setPlainText("")
        QTimer.singleShot(0, self._produce_offer)

    def _produce_offer(self) -> None:
        try:
            session_id, offer = self._multi_host.create_session_offer()
        except (RuntimeError, OSError) as error:  # PermissionError is an OSError
            self._show_error(error)
            return
        self._manual_session_id = session_id
        self._offer_view.setPlainText(offer)
        self._status_label.setText(_t("rd_webrtc_offer_ready"))

    def _on_apply_answer(self) -> None:
        if self._multi_host is None or not self._manual_session_id:
            QMessageBox.warning(self, "WebRTC", _t("rd_webrtc_no_offer_yet"))
            return
        answer = self._answer_input.toPlainText().strip()
        if not answer:
            QMessageBox.warning(self, "WebRTC", _t("rd_webrtc_no_answer"))
            return
        try:
            self._multi_host.accept_session_answer(self._manual_session_id, answer)
            self._status_label.setText(_t("rd_webrtc_answer_applied"))
        except (ValueError, RuntimeError, OSError, KeyError) as error:
            self._show_error(error)
            return
        self._manual_session_id = None  # consumed; next Generate creates new session

    def _on_stop(self) -> None:
        self._stop_host_if_any()
        self._status_label.setText(_t("rd_webrtc_status_idle"))
        self._signals.session_count.emit(0)

    def _on_pending_viewer(self, session_id: str, viewer_id) -> None:
        if self._multi_host is None:
            return
        dialog = PendingViewerDialog(viewer_id if isinstance(viewer_id, str) else None,
                                     parent=self)
        dialog.exec()
        choice = dialog.choice()
        try:
            if choice == PendingViewerDialog.AcceptAndTrust:
                self._multi_host.trust_pending_viewer(session_id)
                self._refresh_trusted_list()
            elif choice == PendingViewerDialog.AcceptOnce:
                self._multi_host.approve_pending_viewer(session_id)
            else:
                self._multi_host.reject_pending_viewer(session_id)
        except KeyError:
            # Session may have been torn down between prompt and decision.
            return
        self._signals.session_count.emit(self._multi_host.session_count())

    def _on_session_count(self, count: int) -> None:
        self._sessions_label.setText(
            _t("rd_webrtc_sessions_count").format(n=count),
        )
        if self._tray is not None:
            self._tray.set_state(sessions=count)
        # Color the badge by load: gray=0, green=1-3, yellow=4-10, red=>10
        if count == 0:
            bg, fg = "#3a3a3a", "#888"
        elif count <= 3:
            bg, fg = "#1f4d1f", "#a6e3a6"
        elif count <= 10:
            bg, fg = "#5a4710", "#f5d99a"
        else:
            bg, fg = "#5a1010", "#ffaaaa"
        self._sessions_label.setStyleSheet(
            f"background: {bg}; color: {fg}; padding: 2px 8px;"
            "border-radius: 8px; font-weight: bold;",
        )
        self._sync_session_pollers()
        self._refresh_sessions_table()
        if count > 0:
            self._maybe_start_adaptive()
        else:
            self._stop_adaptive()
            self._reset_host_quality_dot()

    def _sync_session_pollers(self) -> None:
        """Spawn StatsPoller for new sessions; stop pollers for gone ones."""
        if self._multi_host is None:
            for poller in list(self._session_pollers.values()):  # NOSONAR python:S7504  # snapshot before clear() so a slow stop() doesn't race with the clear that follows
                poller.stop()
            self._session_pollers.clear()
            self._session_cache.reset()
            return
        active_sids = {s["session_id"] for s in self._multi_host.list_sessions()}
        # Stop pollers whose session is gone
        for sid in list(self._session_pollers.keys()):  # NOSONAR python:S7504  # the loop deletes from self._session_pollers — list() is required to avoid RuntimeError
            if sid not in active_sids:
                self._session_pollers[sid].stop()
                del self._session_pollers[sid]
                self._session_cache.drop(sid)
        # Spawn pollers for new sessions
        for sid in active_sids:
            if sid in self._session_pollers:
                continue
            pc = self._multi_host.session_pc(sid)
            if pc is None:
                continue
            poller = StatsPoller(pc, self._make_session_stats_handler(sid),
                                 interval_s=1.0)
            poller.start()
            self._session_pollers[sid] = poller

    def _make_session_stats_handler(self, session_id: str):
        """Closure capturing session_id for the per-session poller."""
        def _handle(snapshot: StatsSnapshot) -> None:
            default_webrtc_inspector().record(snapshot)
            color = self._quality_color(snapshot)
            self._session_cache.set(
                session_id, color=color, snapshot=snapshot,
            )
            # Re-paint just the dot cell for this session_id (avoid full reflow)
            self._signals.session_count.emit(self._multi_host.session_count()
                                              if self._multi_host else 0)
        return _handle

    @staticmethod
    def _format_quality_tooltip(snapshot: Optional[StatsSnapshot]) -> str:
        if snapshot is None:
            return _t("rd_webrtc_quality_unknown")
        parts = []
        if snapshot.rtt_ms is not None:
            parts.append(f"RTT {snapshot.rtt_ms:.0f}ms")
        if snapshot.packet_loss_pct is not None:
            parts.append(f"loss {snapshot.packet_loss_pct:.1f}%")
        if snapshot.fps is not None:
            parts.append(f"FPS {snapshot.fps:.1f}")
        if snapshot.bitrate_kbps is not None:
            parts.append(f"{snapshot.bitrate_kbps:.0f}kbps")
        return " | ".join(parts) if parts else _t("rd_webrtc_quality_unknown")

    @staticmethod
    def _quality_color(snapshot: StatsSnapshot) -> str:
        rtt = snapshot.rtt_ms
        loss = snapshot.packet_loss_pct or 0.0
        if rtt is None:
            return "#555"
        if rtt < 80 and loss < 1.0:
            return "#3a9c3a"
        if rtt < 200 and loss < 5.0:
            return "#c9a23a"
        return "#cc4444"

    def _refresh_sessions_table(self) -> None:
        from datetime import datetime
        from PySide6.QtGui import QColor
        if self._multi_host is None:
            self._sessions_table.setRowCount(0)
            return
        sessions = self._multi_host.list_sessions()
        self._sessions_table.setRowCount(len(sessions))
        for row, info in enumerate(sessions):
            sid = info.get("session_id", "")
            vid = info.get("pending_viewer_id") or ""
            state = info.get("state", "")
            connected = info.get("connected_at") or ""
            if connected:
                try:
                    dt = datetime.fromisoformat(connected)
                    connected = dt.astimezone().strftime("%H:%M:%S")
                except (TypeError, ValueError):
                    pass
            color = self._session_cache.get_color(sid)
            dot_item = QTableWidgetItem("●")
            dot_item.setForeground(QColor(color))
            dot_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            dot_item.setToolTip(self._format_quality_tooltip(
                self._session_cache.get_snapshot(sid),
            ))
            self._sessions_table.setItem(row, 0, dot_item)
            id_item = QTableWidgetItem(sid[:8] if sid else "")
            id_item.setData(Qt.ItemDataRole.UserRole, sid)
            self._sessions_table.setItem(row, 1, id_item)
            self._sessions_table.setItem(
                row, 2, QTableWidgetItem(vid[:12] if vid else ""),
            )
            self._sessions_table.setItem(row, 3, QTableWidgetItem(state))
            self._sessions_table.setItem(row, 4, QTableWidgetItem(connected))

    def _on_sessions_context_menu(self, position) -> None:
        from PySide6.QtWidgets import QMenu
        if self._multi_host is None:
            return
        row = self._sessions_table.rowAt(position.y())
        if row < 0:
            return
        self._sessions_table.selectRow(row)
        sid_item = self._sessions_table.item(row, 1)
        viewer_item = self._sessions_table.item(row, 2)
        if sid_item is None:
            return
        sid = sid_item.data(Qt.ItemDataRole.UserRole) or ""
        viewer_id = viewer_item.text() if viewer_item is not None else ""
        menu = QMenu(self._sessions_table)
        disc = menu.addAction(_t("rd_webrtc_disconnect_selected"))
        trust = menu.addAction(_t("rd_webrtc_sess_trust_viewer"))
        trust.setEnabled(bool(viewer_id))
        copy_id = menu.addAction(_t("rd_webrtc_sess_copy_id"))
        chosen = menu.exec(
            self._sessions_table.viewport().mapToGlobal(position),
        )
        if chosen is disc:
            self._on_disconnect_selected()
        elif chosen is trust and viewer_id:
            self._trust_session_viewer(sid)
        elif chosen is copy_id and sid:
            self._copy_session_id_to_clipboard(sid)

    def _trust_session_viewer(self, sid: str) -> None:
        try:
            with self._multi_host._lock:
                host = self._multi_host._sessions.get(sid)
            full_vid = host.pending_viewer_id if host is not None else None
            if full_vid:
                self._trust_list.add(full_vid, label=f"sess {sid[:6]}")
                self._refresh_trusted_list()
        except (RuntimeError, OSError, ValueError) as error:
            autocontrol_logger.warning("trust viewer: %r", error)

    @staticmethod
    def _copy_session_id_to_clipboard(sid: str) -> None:
        from PySide6.QtWidgets import QApplication
        clip = QApplication.clipboard()
        if clip is not None:
            clip.setText(sid)

    def _on_disconnect_selected(self) -> None:
        if self._multi_host is None:
            return
        row = self._sessions_table.currentRow()
        if row < 0:
            return
        item = self._sessions_table.item(row, 1)
        if item is None:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(sid, str) or not sid:
            return
        try:
            self._multi_host.stop_session(sid)
        except (KeyError, RuntimeError, OSError) as error:
            autocontrol_logger.warning("disconnect session: %r", error)
        self._signals.session_count.emit(self._multi_host.session_count())

    def _maybe_start_adaptive(self) -> None:
        # Always start a stats poller when sessions are active so the host
        # quality dot updates; the adaptive controller is an optional
        # consumer enabled via the checkbox.
        if self._adaptive_poller is not None or self._multi_host is None:
            return
        track = self._multi_host.screen_track()
        pc = self._multi_host.first_session_pc()
        if pc is None:
            return
        if track is not None and self._adaptive_check.isChecked():
            max_fps = int(self._fps_spin.value())
            self._adaptive_controller = AdaptiveBitrateController(
                track, max_fps=max_fps,
                max_bitrate_kbps=int(self._max_bitrate_spin.value()),
            )
        else:
            self._adaptive_controller = None
        self._adaptive_poller = StatsPoller(
            pc, self._on_host_stats, interval_s=1.0,
        )
        self._adaptive_poller.start()
        autocontrol_logger.info(
            "host stats poller active (adaptive=%s)",
            self._adaptive_controller is not None,
        )

    def _on_host_stats(self, snapshot: StatsSnapshot) -> None:
        # Fan-out: feed adaptive controller (if enabled) + update quality dot
        if self._adaptive_controller is not None:
            try:
                self._adaptive_controller.on_stats(snapshot)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("adaptive on_stats: %r", error)
        self._update_host_quality_dot(snapshot)

    def _update_host_quality_dot(self, snapshot: StatsSnapshot) -> None:
        rtt = snapshot.rtt_ms
        loss = snapshot.packet_loss_pct or 0.0
        if rtt is None:
            color = "#555"
            tip_key = "rd_webrtc_quality_unknown"
        elif rtt < 80 and loss < 1.0:
            color = "#3a9c3a"
            tip_key = "rd_webrtc_quality_good"
        elif rtt < 200 and loss < 5.0:
            color = "#c9a23a"
            tip_key = "rd_webrtc_quality_fair"
        else:
            color = "#cc4444"
            tip_key = "rd_webrtc_quality_poor"
        self._host_quality_dot.setStyleSheet(
            f"background-color: {color}; border-radius: 7px;",
        )
        self._host_quality_dot.setToolTip(_t(tip_key))

    def _reset_host_quality_dot(self) -> None:
        self._host_quality_dot.setStyleSheet(
            _QUALITY_DOT_STYLE,
        )
        self._host_quality_dot.setToolTip(_t("rd_webrtc_quality_unknown"))

    def _stop_adaptive(self) -> None:
        if self._adaptive_poller is not None:
            self._adaptive_poller.stop()
            self._adaptive_poller = None
        self._adaptive_controller = None

    def _on_remove_trust(self, viewer_id: str) -> None:
        self._trust_list.remove(viewer_id)
        self._refresh_trusted_list()

    def _on_remove_trust_button(self) -> None:
        item = self._trusted_list.currentItem()
        if item is None:
            return
        viewer_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(viewer_id, str):
            self._on_remove_trust(viewer_id)

    def _on_clear_trust(self) -> None:
        result = QMessageBox.question(
            self, "WebRTC", _t("rd_webrtc_clear_trust_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self._trust_list.clear()
        self._refresh_trusted_list()

    # --- helpers -----------------------------------------------------------

    def _validate_required_fields(self, *, needs_server: bool) -> bool:
        token = self._token_edit.text().strip()
        if not token:
            QMessageBox.warning(self, "WebRTC", _t("rd_webrtc_token_required"))
            return False
        if needs_server:
            if not self._server_edit.text().strip():
                QMessageBox.warning(
                    self, "WebRTC", _t("rd_webrtc_server_required"),
                )
                return False
            if not self._host_id_edit.text().strip():
                QMessageBox.warning(
                    self, "WebRTC", _t("rd_webrtc_host_id_required"),
                )
                return False
        return True

    def _build_multi_host(self, token: str) -> MultiViewerHost:
        whitelist_text = self._ip_whitelist_edit.toPlainText().strip()
        whitelist = [line.strip() for line in whitelist_text.splitlines()
                     if line.strip() and not line.strip().startswith("#")]
        host = MultiViewerHost(
            token=token,
            config=_read_webrtc_config(self),
            trust_list=self._trust_list,
            read_only=self._readonly_check.isChecked(),
            ip_whitelist=whitelist,
            on_annotation=self._signals.annotation.emit,
            on_session_state=lambda _sid, state: self._signals.state.emit(state),
            on_session_authenticated=self._on_session_authed,
            on_pending_viewer=self._signals.pending_viewer.emit,
        )
        return host

    def _on_annotation_event(self, data) -> None:
        if not isinstance(data, dict):
            return
        if self._annotation_overlay is None:
            self._annotation_overlay = HostAnnotationOverlay(parent=self)
        action = data.get("action")
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        if action == "begin":
            self._annotation_overlay.begin_stroke(
                x, y,
                color=data.get("color") or "#ff0000",
                width=int(data.get("width") or 3),
            )
        elif action == "point":
            self._annotation_overlay.add_point(x, y)
        elif action == "end":
            self._annotation_overlay.end_stroke()
        elif action == "clear":
            self._annotation_overlay.clear()

    def _on_session_authed(self, session_id: str) -> None:
        self._signals.auth.emit(True)
        if (self._multi_host is None
                or not self._accept_viewer_video_check.isChecked()):
            return
        # Wire viewer-video callback on this freshly-authed session
        with self._multi_host._lock:
            host = self._multi_host._sessions.get(session_id)
        if host is None:
            return
        host.set_viewer_video_callback(self._on_viewer_video_av_frame)

    def _on_viewer_video_av_frame(self, frame) -> None:
        image = _av_frame_to_qimage(frame)
        if image is not None:
            self._signals.viewer_video_frame.emit(image)

    def _on_viewer_video_image(self, image: QImage) -> None:
        if self._viewer_screen_window is None:
            self._viewer_screen_window = ViewerScreenWindow(parent=self)
            self._viewer_screen_window.closed.connect(
                self._on_viewer_screen_closed,
            )
        if not self._viewer_screen_window.isVisible():
            self._viewer_screen_window.show()
        self._viewer_screen_window.set_image(image)

    def _on_viewer_screen_closed(self) -> None:
        if self._viewer_screen_window is not None:
            self._viewer_screen_window.set_image(None)

    def _stop_host_if_any(self) -> None:
        self._stop_adaptive()
        self._stop_lan_advertise()
        if self._annotation_overlay is not None:
            self._annotation_overlay.clear()
            self._annotation_overlay.hide()
        for poller in list(self._session_pollers.values()):  # NOSONAR python:S7504  # snapshot before clear() — same reasoning as in _refresh_session_pollers
            poller.stop()
        self._session_pollers.clear()
        self._session_cache.reset()
        if self._publish_loop is not None:
            self._publish_loop.requestInterruption()
            self._publish_loop = None
        if self._viewer_screen_window is not None:
            self._viewer_screen_window.set_image(None)
            self._viewer_screen_window.hide()
        if self._multi_host is None:
            return
        try:
            self._multi_host.stop_all()
        except (RuntimeError, OSError):
            pass
        finally:
            self._multi_host = None
            self._manual_session_id = None

    def _on_state(self, state: str) -> None:
        self._status_label.setText(f"{_t('rd_webrtc_state_label')} {state}")

    def _on_auth(self, ok: bool) -> None:
        key = "rd_webrtc_auth_ok" if ok else "rd_webrtc_auth_fail"
        self._status_label.setText(_t(key))

    def _show_error(self, error: Exception) -> None:
        autocontrol_logger.warning("webrtc host panel error: %r", error)
        QMessageBox.warning(self, "WebRTC", str(error))

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)


class _WebRTCViewerPanel(TranslatableMixin, QWidget):
    """Viewer: receive screen and send input."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._viewer: Optional[WebRTCDesktopViewer] = None
        self._offer_worker: Optional[ViewerSignalingWorker] = None
        self._answer_worker: Optional[ViewerAnswerPushWorker] = None
        self._address_book = default_address_book()
        from je_auto_control.utils.remote_desktop import default_known_hosts
        self._known_hosts = default_known_hosts()
        try:
            self._viewer_id = load_or_create_viewer_id()
        except OSError as error:
            autocontrol_logger.warning("viewer_id init: %r", error)
            self._viewer_id = None
        self._recorder: Optional[SessionRecorder] = None
        self._stats_poller: Optional[StatsPoller] = None
        self._sync_engine = None
        self._auto_reconnect_attempts = 0
        self._user_initiated_disconnect = False
        self._signals = _PanelSignals()
        self._signals.frame.connect(self._on_frame_image)
        self._signals.state.connect(self._on_state)
        self._signals.auth.connect(self._on_auth)
        self._signals.stats.connect(self._on_stats)
        self._signals.inbox_listing.connect(self._on_inbox_listing)
        self._signals.inbox_op.connect(self._on_inbox_op_result)
        self._build_ui()
        self._refresh_address_book()
        self._update_availability()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(self._build_address_book_group())
        layout.addWidget(self._build_signaling_group())
        layout.addWidget(self._build_config_group())
        layout.addWidget(self._build_manual_group())
        layout.addWidget(_build_advanced_group(self))
        layout.addWidget(self._build_remote_files_group())
        layout.addWidget(self._build_sync_group())
        self._status_label = QLabel(_t("rd_webrtc_status_idle"))
        layout.addWidget(self._status_label)
        action_row = QHBoxLayout()
        self._cad_btn = self._tr(QPushButton(), "rd_webrtc_send_cad")
        self._cad_btn.clicked.connect(self._on_send_cad)
        action_row.addWidget(self._cad_btn)
        self._wol_btn = self._tr(QPushButton(), "rd_webrtc_wake_on_lan")
        self._wol_btn.clicked.connect(self._on_wake_on_lan)
        action_row.addWidget(self._wol_btn)
        self._mic_btn = self._tr(QPushButton(), "rd_webrtc_send_mic")
        self._mic_btn.setCheckable(True)
        self._mic_btn.clicked.connect(self._on_toggle_mic)
        action_row.addWidget(self._mic_btn)
        self._send_file_btn = self._tr(QPushButton(), "rd_webrtc_send_file")
        self._send_file_btn.clicked.connect(self._on_send_file)
        action_row.addWidget(self._send_file_btn)
        self._record_btn = self._tr(QPushButton(), "rd_webrtc_start_recording")
        self._record_btn.setCheckable(True)
        self._record_btn.clicked.connect(self._on_toggle_recording)
        action_row.addWidget(self._record_btn)
        self._pen_btn = self._tr(QPushButton(), "rd_webrtc_pen_off")
        self._pen_btn.setCheckable(True)
        self._pen_btn.clicked.connect(self._on_toggle_pen)
        action_row.addWidget(self._pen_btn)
        self._pen_clear_btn = self._tr(QPushButton(), "rd_webrtc_pen_clear")
        self._pen_clear_btn.clicked.connect(self._on_pen_clear)
        action_row.addWidget(self._pen_clear_btn)
        action_row.addStretch()
        layout.addLayout(action_row)
        stats_row = QHBoxLayout()
        self._quality_dot = QLabel()
        self._quality_dot.setFixedSize(14, 14)
        self._quality_dot.setStyleSheet(
            _QUALITY_DOT_STYLE,
        )
        self._quality_dot.setToolTip(_t("rd_webrtc_quality_unknown"))
        stats_row.addWidget(self._quality_dot)
        self._stats_label = QLabel(_t("rd_webrtc_stats_idle"))
        self._stats_label.setStyleSheet(
            "color: #ccaa55; font-family: 'Consolas', monospace;",
        )
        stats_row.addWidget(self._stats_label, stretch=1)
        layout.addLayout(stats_row)
        spark_row = QHBoxLayout()
        self._rtt_spark = Sparkline(line_color="#3a9c3a")
        self._rtt_spark.setToolTip("RTT (ms)")
        spark_row.addWidget(self._rtt_spark, stretch=1)
        self._bitrate_spark = Sparkline(line_color="#c97a00")
        self._bitrate_spark.setToolTip("kbps")
        spark_row.addWidget(self._bitrate_spark, stretch=1)
        layout.addLayout(spark_row)
        self._frame_display = _FrameDisplay()
        layout.addWidget(self._frame_display, stretch=1)
        self._wire_input_signals()

    def _build_sync_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "rd_webrtc_sync_group")
        layout = QGridLayout()
        layout.addWidget(self._tr(QLabel(), "rd_webrtc_sync_dir"), 0, 0)
        self._sync_dir_edit = QLineEdit()
        self._tr(self._sync_dir_edit, "rd_webrtc_sync_dir_ph",
                 "setPlaceholderText")
        layout.addWidget(self._sync_dir_edit, 0, 1)
        browse_btn = self._tr(QPushButton(), "rd_webrtc_browse")
        browse_btn.clicked.connect(self._on_sync_browse)
        layout.addWidget(browse_btn, 0, 2)
        self._sync_btn = self._tr(QPushButton(), "rd_webrtc_sync_start")
        self._sync_btn.setCheckable(True)
        self._sync_btn.clicked.connect(self._on_toggle_sync)
        layout.addWidget(self._sync_btn, 0, 3)
        group.setLayout(layout)
        return group

    def _on_sync_browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, _t("rd_webrtc_sync_dir"),
        )
        if path:
            self._sync_dir_edit.setText(path)

    def _on_toggle_sync(self, checked: bool) -> None:
        if checked:
            if self._viewer is None or not self._viewer.authenticated:
                QMessageBox.information(
                    self, "WebRTC", _t("rd_webrtc_cad_not_connected"),
                )
                self._sync_btn.setChecked(False)
                return
            path = self._sync_dir_edit.text().strip()
            if not path:
                QMessageBox.warning(
                    self, "WebRTC", _t("rd_webrtc_sync_dir_required"),
                )
                self._sync_btn.setChecked(False)
                return
            from je_auto_control.utils.remote_desktop.file_sync import (
                FolderSyncEngine,
            )
            from pathlib import Path as _Path
            try:
                self._sync_engine = FolderSyncEngine(
                    watch_dir=_Path(path),
                    sender=lambda local, name: self._viewer.send_file(
                        local, remote_name=name,
                    ),
                )
                self._sync_engine.start()
            except (RuntimeError, OSError) as error:  # FileNotFoundError is an OSError
                QMessageBox.warning(self, "WebRTC", str(error))
                self._sync_btn.setChecked(False)
                return
            self._sync_btn.setText(_t("rd_webrtc_sync_stop"))
        else:
            if self._sync_engine is not None:
                try:
                    self._sync_engine.stop()
                except (RuntimeError, OSError):
                    pass
                self._sync_engine = None
            self._sync_btn.setText(_t("rd_webrtc_sync_start"))

    def _build_remote_files_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "rd_webrtc_remote_files_group")
        layout = QVBoxLayout()
        button_row = QHBoxLayout()
        refresh_btn = self._tr(QPushButton(), "rd_webrtc_browse_refresh")
        refresh_btn.clicked.connect(self._on_browse_refresh)
        button_row.addWidget(refresh_btn)
        pull_btn = self._tr(QPushButton(), "rd_webrtc_browse_pull")
        pull_btn.clicked.connect(self._on_browse_pull_button)
        button_row.addWidget(pull_btn)
        delete_btn = self._tr(QPushButton(), "rd_webrtc_browse_delete")
        delete_btn.clicked.connect(self._on_browse_delete_button)
        button_row.addWidget(delete_btn)
        button_row.addStretch()
        layout.addLayout(button_row)
        self._remote_files_table = RemoteFilesTable()
        self._remote_files_table.pull_requested.connect(self._on_pull_names)
        self._remote_files_table.delete_requested.connect(self._on_delete_names)
        self._remote_files_table.upload_requested.connect(self._on_upload_paths)
        self._remote_files_table.copy_name_requested.connect(
            self._on_copy_name,
        )
        layout.addWidget(self._remote_files_table)
        layout.addWidget(self._tr(QLabel(), "rd_webrtc_browse_dnd_hint"))
        group.setLayout(layout)
        return group

    def _on_browse_refresh(self) -> None:
        if self._viewer is None or not self._viewer.authenticated:
            return
        try:
            self._viewer.request_inbox_listing()
        except (RuntimeError, OSError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_browse_pull_button(self) -> None:
        names = self._remote_files_table.selected_names()
        if not names:
            return
        self._on_pull_names(names)

    def _on_browse_delete_button(self) -> None:
        names = self._remote_files_table.selected_names()
        if not names:
            return
        self._on_delete_names(names)

    def _on_pull_names(self, names) -> None:
        if self._viewer is None or not self._viewer.authenticated:
            return
        try:
            for name in names:
                self._viewer.request_inbox_file(name)
        except (RuntimeError, OSError, ValueError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_delete_names(self, names) -> None:
        if not names or self._viewer is None or not self._viewer.authenticated:
            return
        confirm_text = (
            _t("rd_webrtc_browse_delete_confirm").format(name=names[0])
            if len(names) == 1
            else _t("rd_webrtc_browse_delete_many_confirm").format(n=len(names))
        )
        result = QMessageBox.question(
            self, "WebRTC", confirm_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        try:
            for name in names:
                self._viewer.delete_inbox_file(name)
        except (RuntimeError, OSError, ValueError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_upload_paths(self, paths) -> None:
        if self._viewer is None or not self._viewer.authenticated:
            QMessageBox.information(
                self, "WebRTC", _t("rd_webrtc_cad_not_connected"),
            )
            return
        sent = 0
        last_error = None
        for path in paths:
            try:
                self._viewer.send_file(path)
                sent += 1
            except (RuntimeError, OSError, ValueError) as error:
                last_error = error
                autocontrol_logger.warning("upload %s: %r", path, error)
        if sent:
            self._status_label.setText(
                _t("rd_webrtc_upload_done").format(n=sent),
            )
            QTimer.singleShot(500, self._on_browse_refresh)
        if last_error is not None and sent == 0:
            QMessageBox.warning(self, "WebRTC", str(last_error))

    def _on_copy_name(self, name: str) -> None:
        from PySide6.QtWidgets import QApplication as _QApp
        clipboard = _QApp.clipboard()
        if clipboard is not None:
            clipboard.setText(name)

    def _on_inbox_listing(self, files) -> None:
        from datetime import datetime
        if not isinstance(files, list):
            return
        def _format_mtime(value):
            try:
                return datetime.fromtimestamp(float(value)).strftime(
                    "%Y-%m-%d %H:%M:%S",
                )
            except (TypeError, ValueError, OSError):
                return str(value)
        self._remote_files_table.populate(files, _format_mtime)

    def _on_inbox_op_result(self, name: str, ok: bool, error) -> None:
        if ok:
            self._status_label.setText(
                _t("rd_webrtc_browse_op_ok").format(name=name),
            )
            # Refresh listing so the table reflects the change
            try:
                if self._viewer is not None and self._viewer.authenticated:
                    self._viewer.request_inbox_listing()
            except (RuntimeError, OSError):
                pass
        else:
            QMessageBox.warning(
                self, "WebRTC",
                _t("rd_webrtc_browse_op_failed").format(
                    name=name, error=str(error or ""),
                ),
            )

    def _on_send_cad(self) -> None:
        if self._viewer is None or not self._viewer.authenticated:
            QMessageBox.information(
                self, "WebRTC", _t("rd_webrtc_cad_not_connected"),
            )
            return
        try:
            self._viewer.request_send_sas()
        except (RuntimeError, OSError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_toggle_mic(self, checked: bool) -> None:
        if self._viewer is None or not self._viewer.authenticated:
            self._mic_btn.setChecked(False)
            QMessageBox.information(
                self, "WebRTC", _t("rd_webrtc_cad_not_connected"),
            )
            return
        try:
            if checked:
                self._viewer.enable_mic_send()
            else:
                self._viewer.disable_mic_send()
        except (RuntimeError, OSError) as error:
            self._mic_btn.setChecked(False)
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_send_file(self) -> None:
        if self._viewer is None or not self._viewer.authenticated:
            QMessageBox.information(
                self, "WebRTC", _t("rd_webrtc_cad_not_connected"),
            )
            return
        path, _filter = QFileDialog.getOpenFileName(
            self, _t("rd_webrtc_send_file"), "",
        )
        if not path:
            return
        try:
            self._viewer.send_file(path)
            self._status_label.setText(
                _t("rd_webrtc_file_sent").format(name=path),
            )
        except (RuntimeError, OSError, ValueError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_wake_on_lan(self) -> None:
        entry = self._address_list.selected_entry()
        mac = ""
        broadcast = ""
        if entry is not None:
            mac = entry.get("mac_address", "") or ""
            broadcast = entry.get("broadcast_address", "") or ""
        mac, ok = QInputDialog.getText(
            self, _t("rd_webrtc_wake_on_lan"),
            _t("rd_webrtc_wol_mac_prompt"), text=mac,
        )
        if not ok or not mac.strip():
            return
        broadcast, ok2 = QInputDialog.getText(
            self, _t("rd_webrtc_wake_on_lan"),
            _t("rd_webrtc_wol_broadcast_prompt"),
            text=broadcast or "255.255.255.255",
        )
        if not ok2:
            return
        try:
            send_magic_packet(mac.strip(),
                              broadcast_address=broadcast.strip() or None)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))
            return
        if entry is not None:
            self._address_book.upsert(
                host_id=entry.get("host_id", ""),
                server_url=entry.get("server_url", ""),
                mac_address=mac.strip(),
                broadcast_address=broadcast.strip() or None,
            )
            self._refresh_address_book()
        QMessageBox.information(
            self, _t("rd_webrtc_wake_on_lan"), _t("rd_webrtc_wol_sent"),
        )

    def _on_toggle_recording(self, checked: bool) -> None:
        if checked:
            if SessionRecorder is None:
                QMessageBox.warning(self, "WebRTC", _t("rd_webrtc_unavailable"))
                self._record_btn.setChecked(False)
                return
            path, _filter = QFileDialog.getSaveFileName(
                self, _t("rd_webrtc_recording_save_as"), "",
                "MP4 (*.mp4);;WebM (*.webm);;Matroska (*.mkv);;All (*)",
            )
            if not path:
                self._record_btn.setChecked(False)
                return
            from je_auto_control.utils.remote_desktop.session_recorder import (
                preset_for_path,
            )
            preset = preset_for_path(path)
            self._recorder = SessionRecorder(
                path,
                fps=int(self._bandwidth_combo.currentData() and
                        fps_for_preset(self._bandwidth_combo.currentData())
                        or 24),
                codec=preset.get("codec", "libx264"),
                pixel_format=preset.get("pixel_format", "yuv420p"),
            )
            self._record_btn.setText(_t("rd_webrtc_stop_recording"))
        else:
            if self._recorder is not None:
                self._recorder.stop()
                QMessageBox.information(
                    self, "WebRTC",
                    _t("rd_webrtc_recording_saved").format(
                        path=str(self._recorder.output_path),
                    ),
                )
                self._recorder = None
            self._record_btn.setText(_t("rd_webrtc_start_recording"))

    def _on_stats(self, snapshot: StatsSnapshot) -> None:
        parts = []
        if snapshot.fps is not None:
            parts.append(f"FPS {snapshot.fps:.1f}")
        if snapshot.bitrate_kbps is not None:
            parts.append(f"{snapshot.bitrate_kbps:.0f} kbps")
        if snapshot.rtt_ms is not None:
            parts.append(f"RTT {snapshot.rtt_ms:.0f} ms")
        if snapshot.packet_loss_pct is not None:
            parts.append(f"loss {snapshot.packet_loss_pct:.1f}%")
        if snapshot.jitter_ms is not None:
            parts.append(f"jitter {snapshot.jitter_ms:.1f}ms")
        if not parts:
            return
        self._stats_label.setText(" | ".join(parts))
        self._update_quality_dot(snapshot)
        if hasattr(self, "_rtt_spark"):
            self._rtt_spark.push(snapshot.rtt_ms)
            self._bitrate_spark.push(snapshot.bitrate_kbps)

    def _update_quality_dot(self, snapshot: StatsSnapshot) -> None:
        rtt = snapshot.rtt_ms
        loss = snapshot.packet_loss_pct or 0.0
        if rtt is None:
            color = "#555"
            tip_key = "rd_webrtc_quality_unknown"
        elif rtt < 80 and loss < 1.0:
            color = "#3a9c3a"
            tip_key = "rd_webrtc_quality_good"
        elif rtt < 200 and loss < 5.0:
            color = "#c9a23a"
            tip_key = "rd_webrtc_quality_fair"
        else:
            color = "#cc4444"
            tip_key = "rd_webrtc_quality_poor"
        self._quality_dot.setStyleSheet(
            f"background-color: {color}; border-radius: 7px;",
        )
        self._quality_dot.setToolTip(_t(tip_key))

    def _build_address_book_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "rd_webrtc_address_book_group")
        layout = QVBoxLayout()
        # Tag filter row
        tag_row = QHBoxLayout()
        tag_row.addWidget(self._tr(QLabel(), "rd_webrtc_tag_filter"))
        self._tag_filter_combo = QComboBox()
        self._tag_filter_combo.addItem(_t("rd_webrtc_tag_all"), "")
        self._tag_filter_combo.currentIndexChanged.connect(
            lambda _i: self._refresh_address_book(),
        )
        tag_row.addWidget(self._tag_filter_combo, stretch=1)
        layout.addLayout(tag_row)
        self._address_list = AddressBookList()
        self._address_list.chosen.connect(self._on_address_chosen)
        self._address_list.deleted.connect(self._on_address_removed)
        self._address_list.favorite_toggled.connect(self._on_address_favorite)
        self._address_list.tags_edit_requested.connect(self._on_address_tags)
        self._address_list.setMaximumHeight(120)
        layout.addWidget(self._address_list)
        button_row = QHBoxLayout()
        connect_btn = self._tr(QPushButton(), "rd_webrtc_connect_selected")
        connect_btn.clicked.connect(self._on_connect_selected_address)
        button_row.addWidget(connect_btn)
        save_btn = self._tr(QPushButton(), "rd_webrtc_save_current")
        save_btn.clicked.connect(self._on_save_current_address)
        button_row.addWidget(save_btn)
        remove_btn = self._tr(QPushButton(), "rd_webrtc_remove_selected")
        remove_btn.clicked.connect(self._on_remove_selected_address)
        button_row.addWidget(remove_btn)
        kh_btn = self._tr(QPushButton(), "rd_webrtc_manage_known_hosts")
        kh_btn.clicked.connect(self._on_manage_known_hosts)
        button_row.addWidget(kh_btn)
        ab_export = self._tr(QPushButton(), "rd_webrtc_ab_export")
        ab_export.clicked.connect(self._on_ab_export)
        button_row.addWidget(ab_export)
        ab_import = self._tr(QPushButton(), "rd_webrtc_ab_import")
        ab_import.clicked.connect(self._on_ab_import)
        button_row.addWidget(ab_import)
        ab_clear = self._tr(QPushButton(), "rd_webrtc_ab_clear")
        ab_clear.clicked.connect(self._on_ab_clear)
        button_row.addWidget(ab_clear)
        layout.addLayout(button_row)
        group.setLayout(layout)
        return group

    def _on_ab_export(self) -> None:
        import json as _json
        path, _filter = QFileDialog.getSaveFileName(
            self, _t("rd_webrtc_ab_export"), "address_book.json",
            _JSON_FILE_FILTER,
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                _json.dump({"entries": self._address_book.list_entries()},
                           fh, indent=2, ensure_ascii=False)
        except OSError as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_ab_import(self) -> None:
        import json as _json
        path, _filter = QFileDialog.getOpenFileName(
            self, _t("rd_webrtc_ab_import"), "", _JSON_FILE_FILTER,
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = _json.load(fh)
        except (OSError, _json.JSONDecodeError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))
            return
        entries = data.get("entries") if isinstance(data, dict) else data
        added = 0
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            host_id = entry.get("host_id")
            server_url = entry.get("server_url")
            if not (host_id and server_url):
                continue
            try:
                self._address_book.upsert(
                    host_id=host_id, server_url=server_url,
                    label=entry.get("label", ""),
                    mac_address=entry.get("mac_address"),
                    broadcast_address=entry.get("broadcast_address"),
                )
                added += 1
            except (ValueError, OSError) as error:
                autocontrol_logger.debug("ab import upsert: %r", error)
        QMessageBox.information(
            self, "WebRTC", _t("rd_webrtc_ab_import_done").format(n=added),
        )
        self._refresh_address_book()

    def _on_ab_clear(self) -> None:
        result = QMessageBox.question(
            self, "WebRTC", _t("rd_webrtc_ab_clear_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self._address_book.clear()
        self._refresh_address_book()

    def _on_manage_known_hosts(self) -> None:
        dialog = KnownHostsDialog(self._known_hosts, parent=self)
        dialog.exec()

    def _refresh_address_book(self) -> None:
        # Refresh tag filter combo
        current = self._tag_filter_combo.currentData() or ""
        self._tag_filter_combo.blockSignals(True)
        self._tag_filter_combo.clear()
        self._tag_filter_combo.addItem(_t("rd_webrtc_tag_all"), "")
        for tag in self._address_book.all_tags():
            self._tag_filter_combo.addItem(tag, tag)
        idx = self._tag_filter_combo.findData(current)
        if idx >= 0:
            self._tag_filter_combo.setCurrentIndex(idx)
        self._tag_filter_combo.blockSignals(False)
        # Apply filter
        active_tag = self._tag_filter_combo.currentData() or ""
        self._address_list.populate(
            self._address_book.list_entries(), tag_filter=active_tag,
        )

    def _on_address_tags(self, entry: dict) -> None:
        existing = entry.get("tags", []) or []
        text, ok = QInputDialog.getText(
            self, _t("rd_webrtc_edit_tags"),
            _t("rd_webrtc_tags_prompt"),
            text=", ".join(existing),
        )
        if not ok:
            return
        new_tags = [t.strip() for t in text.split(",") if t.strip()]
        try:
            self._address_book.set_tags(
                host_id=entry.get("host_id", ""),
                server_url=entry.get("server_url", ""),
                tags=new_tags,
            )
        except (ValueError, OSError) as error:
            autocontrol_logger.debug("set_tags: %r", error)
        self._refresh_address_book()

    def _on_address_chosen(self, entry: dict) -> None:
        self._server_edit.setText(entry.get("server_url", ""))
        self._host_id_edit.setText(entry.get("host_id", ""))
        self._on_connect_via_server()

    def _on_address_removed(self, entry: dict) -> None:
        self._address_book.remove(
            host_id=entry.get("host_id", ""),
            server_url=entry.get("server_url", ""),
        )
        self._refresh_address_book()

    def _on_address_favorite(self, entry: dict) -> None:
        try:
            self._address_book.toggle_favorite(
                host_id=entry.get("host_id", ""),
                server_url=entry.get("server_url", ""),
            )
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("toggle favorite: %r", error)
        self._refresh_address_book()

    def _on_connect_selected_address(self) -> None:
        entry = self._address_list.selected_entry()
        if entry is None:
            QMessageBox.information(
                self, "WebRTC", _t("rd_webrtc_no_address_selected"),
            )
            return
        self._on_address_chosen(entry)

    def _on_save_current_address(self) -> None:
        host_id = self._host_id_edit.text().strip()
        server_url = self._server_edit.text().strip()
        if not host_id or not server_url:
            QMessageBox.warning(
                self, "WebRTC", _t("rd_webrtc_save_address_missing_fields"),
            )
            return
        self._address_book.upsert(host_id=host_id, server_url=server_url)
        self._refresh_address_book()

    def _on_remove_selected_address(self) -> None:
        entry = self._address_list.selected_entry()
        if entry is not None:
            self._on_address_removed(entry)

    def _build_signaling_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "rd_webrtc_signaling_group")
        grid = QGridLayout()
        grid.addWidget(self._tr(QLabel(), "rd_webrtc_server_label"), 0, 0)
        self._server_edit = QLineEdit(_DEFAULT_SIGNALING_URL)
        grid.addWidget(self._server_edit, 0, 1, 1, 3)
        grid.addWidget(self._tr(QLabel(), "rd_webrtc_host_id_label"), 1, 0)
        self._host_id_edit = self._tr(QLineEdit(), "rd_webrtc_host_id_placeholder")
        grid.addWidget(self._host_id_edit, 1, 1, 1, 3)
        grid.addWidget(self._tr(QLabel(), "rd_webrtc_secret_label"), 2, 0)
        self._secret_edit = QLineEdit()
        self._secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(self._secret_edit, 2, 1, 1, 3)
        self._connect_btn = self._tr(QPushButton(), "rd_webrtc_connect_via_server")
        self._connect_btn.clicked.connect(self._on_connect_via_server)
        grid.addWidget(self._connect_btn, 3, 0, 1, 3)
        self._lan_browse_btn = self._tr(QPushButton(), "rd_webrtc_lan_browse")
        self._lan_browse_btn.clicked.connect(self._on_lan_browse)
        grid.addWidget(self._lan_browse_btn, 3, 3)
        group.setLayout(grid)
        return group

    def _on_lan_browse(self) -> None:
        dialog = LanBrowseDialog(parent=self)
        dialog.chosen.connect(self._on_lan_chosen)
        dialog.exec()

    def _on_lan_chosen(self, svc: dict) -> None:
        host_id = svc.get("host_id", "")
        signaling = svc.get("signaling_url", "")
        if host_id:
            self._host_id_edit.setText(host_id)
        if signaling:
            self._server_edit.setText(signaling)

    def _build_config_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "rd_webrtc_config_group")
        grid = QGridLayout()
        grid.addWidget(self._tr(QLabel(), "rd_token_label"), 0, 0)
        self._token_edit = self._tr(QLineEdit(), "rd_token_placeholder")
        grid.addWidget(self._token_edit, 0, 1)
        grid.addWidget(self._tr(QLabel(), "rd_webrtc_bandwidth_label"), 1, 0)
        self._bandwidth_combo = QComboBox()
        for key, info in BANDWIDTH_PRESETS.items():
            self._bandwidth_combo.addItem(info["label"], key)
        grid.addWidget(self._bandwidth_combo, 1, 1)
        self._share_my_screen_check = self._tr(
            QCheckBox(), "rd_webrtc_share_my_screen",
        )
        self._share_my_screen_check.setChecked(False)
        self._share_my_screen_check.toggled.connect(
            self._on_toggle_share_my_screen,
        )
        grid.addWidget(self._share_my_screen_check, 2, 0, 1, 2)
        self._share_opus_mic_check = self._tr(
            QCheckBox(), "rd_webrtc_share_opus_mic",
        )
        self._share_opus_mic_check.setChecked(False)
        self._share_opus_mic_check.toggled.connect(
            self._on_toggle_share_opus_mic,
        )
        grid.addWidget(self._share_opus_mic_check, 3, 0, 1, 2)
        self._auto_reconnect_check = self._tr(
            QCheckBox(), "rd_webrtc_auto_reconnect",
        )
        self._auto_reconnect_check.setChecked(False)
        grid.addWidget(self._auto_reconnect_check, 4, 0, 1, 2)
        grid.addWidget(self._tr(QLabel(), "rd_webrtc_reconnect_max"), 5, 0)
        self._reconnect_max_spin = QSpinBox()
        self._reconnect_max_spin.setRange(1, 50)
        self._reconnect_max_spin.setValue(5)
        grid.addWidget(self._reconnect_max_spin, 5, 1)
        grid.addWidget(self._tr(QLabel(), "rd_webrtc_reconnect_delay"), 6, 0)
        self._reconnect_delay_spin = QSpinBox()
        self._reconnect_delay_spin.setRange(1, 60)
        self._reconnect_delay_spin.setValue(1)
        self._reconnect_delay_spin.setSuffix(" s")
        grid.addWidget(self._reconnect_delay_spin, 6, 1)
        group.setLayout(grid)
        return group

    def _on_toggle_share_my_screen(self, value: bool) -> None:
        if self._viewer is None:
            return
        try:
            self._viewer.toggle_share_screen(value)
        except (RuntimeError, OSError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _on_toggle_share_opus_mic(self, value: bool) -> None:
        if self._viewer is None:
            return
        try:
            self._viewer.toggle_opus_mic(value)
        except (RuntimeError, OSError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))

    def _build_manual_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "rd_webrtc_manual_group")
        layout = QVBoxLayout()
        layout.addWidget(self._tr(QLabel(), "rd_webrtc_offer_input_label"))
        self._offer_input = QTextEdit()
        self._offer_input.setMinimumHeight(80)
        self._tr(self._offer_input, "rd_webrtc_paste_offer", "setPlaceholderText")
        layout.addWidget(self._offer_input)
        button_row = QHBoxLayout()
        self._answer_btn = self._tr(QPushButton(), "rd_webrtc_create_answer")
        self._answer_btn.clicked.connect(self._on_create_answer)
        button_row.addWidget(self._answer_btn)
        self._stop_btn = self._tr(QPushButton(), "rd_webrtc_stop_viewer")
        self._stop_btn.clicked.connect(self._on_stop)
        button_row.addWidget(self._stop_btn)
        layout.addLayout(button_row)
        layout.addWidget(self._tr(QLabel(), "rd_webrtc_answer_label"))
        self._answer_view = QTextEdit()
        self._answer_view.setReadOnly(True)
        self._answer_view.setMinimumHeight(80)
        layout.addWidget(self._answer_view)
        group.setLayout(layout)
        return group

    def _wire_input_signals(self) -> None:
        fd = self._frame_display
        fd.mouse_moved.connect(
            lambda x, y: self._send({"type": "mouse_move",
                                     "x": int(x), "y": int(y)}))
        fd.mouse_pressed.connect(
            lambda x, y, b: self._send({"type": "mouse_press",
                                        "x": int(x), "y": int(y),
                                        "button": b}))
        fd.mouse_released.connect(
            lambda x, y, b: self._send({"type": "mouse_release",
                                        "x": int(x), "y": int(y),
                                        "button": b}))
        fd.mouse_scrolled.connect(
            lambda x, y, a: self._send({"type": "mouse_scroll",
                                        "x": int(x), "y": int(y),
                                        "amount": int(a)}))
        fd.key_pressed.connect(
            lambda k: self._send({"type": "key_press", "keycode": k}))
        fd.key_released.connect(
            lambda k: self._send({"type": "key_release", "keycode": k}))
        fd.type_text.connect(
            lambda text: self._send({"type": "type_text", "text": text}))
        fd.annotation_event.connect(self._on_annotation_segment)

    def _on_annotation_segment(self, action: str, x: int, y: int) -> None:
        if self._viewer is None or not self._viewer.authenticated:
            return
        try:
            self._viewer._send({  # noqa: SLF001  # reason: reuse internal sender
                "type": "annotate", "action": action,
                "x": int(x), "y": int(y),
                "color": "#ff0000", "width": 3,
            })
        except (RuntimeError, OSError):
            pass

    def _on_toggle_pen(self, checked: bool) -> None:
        self._frame_display.set_pen_mode(checked)
        self._pen_btn.setText(_t("rd_webrtc_pen_on" if checked
                                 else "rd_webrtc_pen_off"))

    def _on_pen_clear(self) -> None:
        if self._viewer is None or not self._viewer.authenticated:
            return
        try:
            self._viewer._send({  # noqa: SLF001
                "type": "annotate", "action": "clear",
                "x": 0, "y": 0,
            })
        except (RuntimeError, OSError):
            pass

    def _update_availability(self) -> None:
        if not is_webrtc_available():
            for widget in (self._answer_btn, self._connect_btn):
                widget.setEnabled(False)
            self._status_label.setText(_t("rd_webrtc_unavailable"))

    # --- handlers ----------------------------------------------------------

    def _on_connect_via_server(self) -> None:
        if not self._validate_required_fields(needs_server=True):
            return
        self._user_initiated_disconnect = False
        self._stop_viewer_if_any()
        self._status_label.setText(_t("rd_webrtc_polling_offer"))
        self._offer_worker = ViewerSignalingWorker(
            server_url=self._server_edit.text().strip(),
            host_id=self._host_id_edit.text().strip(),
            secret=self._secret_edit.text() or None,
        )
        self._offer_worker.offer_ready.connect(self._on_offer_received_from_server)
        self._offer_worker.failed.connect(self._on_signaling_failed)
        self._offer_worker.start()

    def _on_offer_received_from_server(self, offer_sdp: str) -> None:
        try:
            self._viewer = self._build_viewer(self._token_edit.text().strip())
        except (ValueError, RuntimeError, OSError) as error:
            self._show_error(error)
            return
        self._status_label.setText(_t("rd_webrtc_creating_answer"))
        QTimer.singleShot(0, lambda: self._answer_and_push(offer_sdp))

    def _answer_and_push(self, offer_sdp: str) -> None:
        host_id = self._host_id_edit.text().strip()
        expected_dtls = self._known_hosts.dtls_fingerprint_for(host_id) if host_id else None
        try:
            answer = self._viewer.process_offer(
                offer_sdp, expected_dtls_fingerprint=expected_dtls,
            )
        except (ValueError, RuntimeError, OSError) as error:
            self._show_error(error)
            return
        # First-time TOFU: stash the DTLS fingerprint we just observed
        if host_id and not expected_dtls:
            from je_auto_control.utils.remote_desktop.fingerprint import (
                extract_dtls_fingerprint,
            )
            new_fp = extract_dtls_fingerprint(offer_sdp)
            if new_fp:
                self._known_hosts.remember_dtls_fingerprint(host_id, new_fp)
        self._answer_view.setPlainText(answer)
        self._status_label.setText(_t("rd_webrtc_pushing_answer"))
        self._answer_worker = ViewerAnswerPushWorker(
            server_url=self._server_edit.text().strip(),
            host_id=self._host_id_edit.text().strip(),
            secret=self._secret_edit.text() or None,
            answer_sdp=answer,
        )
        self._answer_worker.pushed.connect(
            lambda: self._status_label.setText(_t("rd_webrtc_waiting_auth")),
        )
        self._answer_worker.failed.connect(self._on_signaling_failed)
        self._answer_worker.start()

    def _on_signaling_failed(self, message: str) -> None:
        QMessageBox.warning(self, "WebRTC", message)
        self._status_label.setText(_t("rd_webrtc_status_idle"))

    def _on_create_answer(self) -> None:
        if not self._validate_required_fields(needs_server=False):
            return
        offer = self._offer_input.toPlainText().strip()
        if not offer:
            QMessageBox.warning(self, "WebRTC", _t("rd_webrtc_no_offer"))
            return
        try:
            self._stop_viewer_if_any()
            self._viewer = self._build_viewer(self._token_edit.text().strip())
        except (ValueError, RuntimeError, OSError) as error:
            self._show_error(error)
            return
        self._status_label.setText(_t("rd_webrtc_creating_answer"))
        QTimer.singleShot(0, lambda: self._produce_answer(offer))

    def _produce_answer(self, offer: str) -> None:
        try:
            answer = self._viewer.process_offer(offer)
        except (ValueError, RuntimeError, OSError) as error:
            self._show_error(error)
            return
        self._answer_view.setPlainText(answer)
        self._status_label.setText(_t("rd_webrtc_answer_ready"))

    def _on_stop(self) -> None:
        self._user_initiated_disconnect = True
        self._auto_reconnect_attempts = 0
        self._stop_viewer_if_any()
        self._frame_display.clear()
        self._status_label.setText(_t("rd_webrtc_status_idle"))

    # --- helpers -----------------------------------------------------------

    def _validate_required_fields(self, *, needs_server: bool) -> bool:
        token = self._token_edit.text().strip()
        if not token:
            QMessageBox.warning(self, "WebRTC", _t("rd_webrtc_token_required"))
            return False
        if needs_server:
            if not self._server_edit.text().strip():
                QMessageBox.warning(
                    self, "WebRTC", _t("rd_webrtc_server_required"),
                )
                return False
            if not self._host_id_edit.text().strip():
                QMessageBox.warning(
                    self, "WebRTC", _t("rd_webrtc_host_id_required"),
                )
                return False
        return True

    def _build_viewer(self, token: str) -> WebRTCDesktopViewer:
        viewer = WebRTCDesktopViewer(
            token=token,
            config=_read_webrtc_config(self),
            viewer_id=self._viewer_id,
            on_frame=self._on_av_frame,
            on_state_change=self._signals.state.emit,
            on_auth_result=self._signals.auth.emit,
        )
        viewer.set_file_received_callback(self._on_received_file)
        viewer.set_inbox_listing_callback(self._signals.inbox_listing.emit)
        viewer.set_inbox_op_result_callback(self._signals.inbox_op.emit)
        return viewer

    def _on_received_file(self, path) -> None:
        # Called from the asyncio thread; marshal to Qt via a status update.
        QTimer.singleShot(
            0, lambda: self._status_label.setText(
                _t("rd_webrtc_file_received").format(name=str(path)),
            ),
        )

    def _stop_viewer_if_any(self) -> None:
        for worker in (self._offer_worker, self._answer_worker):
            if worker is not None:
                worker.requestInterruption()
        self._offer_worker = None
        self._answer_worker = None
        if self._sync_engine is not None:
            try:
                self._sync_engine.stop()
            except (RuntimeError, OSError):
                pass
            self._sync_engine = None
            if hasattr(self, "_sync_btn"):
                self._sync_btn.setChecked(False)
                self._sync_btn.setText(_t("rd_webrtc_sync_start"))
        self._stop_stats_polling()
        if self._recorder is not None:
            self._recorder.stop()
            self._recorder = None
            self._record_btn.setChecked(False)
            self._record_btn.setText(_t("rd_webrtc_start_recording"))
        if self._viewer is None:
            return
        try:
            self._viewer.stop()
        except (RuntimeError, OSError):
            pass
        finally:
            self._viewer = None

    # called from asyncio thread
    def _on_av_frame(self, frame) -> None:
        if self._recorder is not None:
            try:
                self._recorder.write_frame(frame)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("recorder write: %r", error)
        image = _av_frame_to_qimage(frame)
        if image is not None:
            self._signals.frame.emit(image)

    def _on_frame_image(self, image: QImage) -> None:
        self._frame_display.set_image(image)

    def _on_state(self, state: str) -> None:
        self._status_label.setText(f"{_t('rd_webrtc_state_label')} {state}")
        if state in ("failed", "disconnected"):
            self._maybe_schedule_auto_reconnect()

    def _on_auth(self, ok: bool) -> None:
        key = "rd_webrtc_auth_ok" if ok else "rd_webrtc_auth_fail"
        self._status_label.setText(_t(key))
        if ok:
            self._auto_reconnect_attempts = 0  # reset on successful auth
            host_id = self._host_id_edit.text().strip()
            server_url = self._server_edit.text().strip()
            if host_id and server_url:
                try:
                    self._address_book.upsert(
                        host_id=host_id, server_url=server_url,
                    )
                    self._refresh_address_book()
                except (ValueError, OSError) as error:
                    autocontrol_logger.debug("address book upsert: %r", error)
            if host_id:
                try:
                    self._known_hosts.touch(host_id)
                except OSError as error:
                    autocontrol_logger.debug("known_hosts touch: %r", error)
            self._start_stats_polling()
        else:
            self._stop_stats_polling()

    def _maybe_schedule_auto_reconnect(self) -> None:
        if (not self._auto_reconnect_check.isChecked()
                or self._user_initiated_disconnect):
            return
        max_attempts = int(self._reconnect_max_spin.value())
        base_delay_s = int(self._reconnect_delay_spin.value())
        if self._auto_reconnect_attempts >= max_attempts:
            self._status_label.setText(_t("rd_webrtc_reconnect_giveup"))
            return
        if (not self._server_edit.text().strip()
                or not self._host_id_edit.text().strip()
                or not self._token_edit.text().strip()):
            return
        self._auto_reconnect_attempts += 1
        delay_ms = min(
            60000, 1000 * base_delay_s * (2 ** (self._auto_reconnect_attempts - 1)),
        )
        self._status_label.setText(
            _t("rd_webrtc_reconnecting").format(
                n=self._auto_reconnect_attempts, max=max_attempts,
            ),
        )
        QTimer.singleShot(delay_ms, self._on_connect_via_server)

    def _start_stats_polling(self) -> None:
        if self._viewer is None or self._viewer._pc is None:
            return
        self._stop_stats_polling()
        self._stats_poller = StatsPoller(
            self._viewer._pc, self._on_viewer_stats_sample,
        )
        self._stats_poller.start()

    def _on_viewer_stats_sample(self, snapshot: StatsSnapshot) -> None:
        default_webrtc_inspector().record(snapshot)
        self._signals.stats.emit(snapshot)

    def _stop_stats_polling(self) -> None:
        if self._stats_poller is not None:
            self._stats_poller.stop()
            self._stats_poller = None
        self._stats_label.setText(_t("rd_webrtc_stats_idle"))
        if hasattr(self, "_quality_dot"):
            self._quality_dot.setStyleSheet(
                _QUALITY_DOT_STYLE,
            )
            self._quality_dot.setToolTip(_t("rd_webrtc_quality_unknown"))
        if hasattr(self, "_rtt_spark"):
            self._rtt_spark.clear()
            self._bitrate_spark.clear()

    def _send(self, payload: dict) -> None:
        if self._viewer is None or not self._viewer.authenticated:
            return
        try:
            self._viewer.send_input(payload)
        except (RuntimeError, OSError) as error:
            logging.getLogger(__name__).debug("send_input: %r", error)

    def _show_error(self, error: Exception) -> None:
        autocontrol_logger.warning("webrtc viewer panel error: %r", error)
        QMessageBox.warning(self, "WebRTC", str(error))

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)


__all__ = ["_WebRTCHostPanel", "_WebRTCViewerPanel"]
