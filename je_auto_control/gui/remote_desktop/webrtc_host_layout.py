"""WebRTC host layout controller; session and widget ownership stays on the panel."""
# pylint: disable=protected-access  # reason: typed controllers share their owning panel state

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtCore import Qt

# pylint: enable=no-name-in-module
# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
)

# pylint: enable=no-name-in-module
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.remote_desktop._helpers import _t
from je_auto_control.gui.remote_desktop.advanced_group import build_advanced_group
from je_auto_control.gui.remote_desktop.trusted_group import build_trusted_group
from je_auto_control.gui.remote_desktop.webrtc_common import (
    _DEFAULT_FPS,
    _DEFAULT_MONITOR,
    _QUALITY_DOT_STYLE,
    signaling_grid,
    token_grid,
    validate_required_fields,
)
from je_auto_control.gui.remote_desktop.webrtc_workers import generate_host_id
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop import install_hardware_codec, is_webrtc_available, uninstall_hardware_codec

if TYPE_CHECKING:
    from je_auto_control.gui.remote_desktop.webrtc_host_panel import _WebRTCHostPanel


class WebRTCHostLayoutController:  # pylint: disable=too-few-public-methods  # reason: internal signal/slot controller
    """Host layout interactions on a typed owned panel."""

    def __init__(self, panel: _WebRTCHostPanel) -> None:
        self._panel = panel

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self._panel)
        layout.addWidget(self._panel._build_signaling_group())
        layout.addWidget(self._panel._build_config_group())
        layout.addWidget(self._panel._build_manual_group())
        layout.addWidget(build_advanced_group(self._panel, include_hw_codec=True))
        layout.addWidget(build_trusted_group(self._panel))
        self._panel._status_label = QLabel(_t("rd_webrtc_status_idle"))
        layout.addWidget(self._panel._status_label)
        sessions_row = QHBoxLayout()
        self._panel._host_quality_dot = QLabel()
        self._panel._host_quality_dot.setFixedSize(14, 14)
        self._panel._host_quality_dot.setStyleSheet(_QUALITY_DOT_STYLE)
        self._panel._host_quality_dot.setToolTip(_t("rd_webrtc_quality_unknown"))
        sessions_row.addWidget(self._panel._host_quality_dot)
        self._panel._sessions_label = QLabel(_t("rd_webrtc_sessions_count").format(n=0))
        sessions_row.addWidget(self._panel._sessions_label, stretch=1)
        layout.addLayout(sessions_row)
        self._panel._sessions_table = QTableWidget(0, 5)
        self._panel._sessions_table.setHorizontalHeaderLabels(
            [
                "",
                _t("rd_webrtc_sess_col_id"),
                _t("rd_webrtc_sess_col_viewer"),
                _t("rd_webrtc_sess_col_state"),
                _t("rd_webrtc_sess_col_connected"),
            ]
        )
        self._panel._sessions_table.setColumnWidth(0, 18)
        self._panel._sessions_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._panel._sessions_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._panel._sessions_table.setMinimumHeight(140)
        self._panel._sessions_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._panel._sessions_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._panel._sessions_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._panel._sessions_table.customContextMenuRequested.connect(self._panel._on_sessions_context_menu)
        layout.addWidget(self._panel._sessions_table)
        sessions_btn_row = QHBoxLayout()
        self._panel._disconnect_btn = self._panel._tr(QPushButton(), "rd_webrtc_disconnect_selected")
        self._panel._disconnect_btn.clicked.connect(self._panel._on_disconnect_selected)
        sessions_btn_row.addWidget(self._panel._disconnect_btn)
        sessions_btn_row.addStretch()
        layout.addLayout(sessions_btn_row)
        push_row = QHBoxLayout()
        self._panel._push_file_btn = self._panel._tr(QPushButton(), "rd_webrtc_push_file")
        self._panel._push_file_btn.clicked.connect(self._panel._on_push_file)
        push_row.addWidget(self._panel._push_file_btn)
        audit_btn = self._panel._tr(QPushButton(), "rd_webrtc_view_audit")
        audit_btn.clicked.connect(self._panel._on_view_audit)
        push_row.addWidget(audit_btn)
        push_row.addStretch()
        layout.addLayout(push_row)

    def _on_hw_codec_changed(self) -> None:
        codec = self._panel._hw_codec_combo.currentData() or ""
        if not codec:
            uninstall_hardware_codec()
            self._panel._status_label.setText(_t("rd_webrtc_hw_codec_off_status"))
            return
        if install_hardware_codec(codec):
            self._panel._status_label.setText(_t("rd_webrtc_hw_codec_active").format(codec=codec))
        else:
            self._panel._status_label.setText(_t("rd_webrtc_hw_codec_failed").format(codec=codec))

    def _build_signaling_group(self) -> QGroupBox:
        group, grid = signaling_grid(self._panel)
        self._panel._host_id_edit = QLineEdit(generate_host_id())
        grid.addWidget(self._panel._host_id_edit, 1, 1, 1, 2)
        regen = self._panel._tr(QPushButton(), "rd_webrtc_regen_id")
        regen.clicked.connect(self._panel._on_regen_id)
        grid.addWidget(regen, 1, 3)
        grid.addWidget(self._panel._tr(QLabel(), "rd_webrtc_secret_label"), 2, 0)
        self._panel._secret_edit = QLineEdit()
        self._panel._secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(self._panel._secret_edit, 2, 1, 1, 3)
        self._panel._publish_btn = self._panel._tr(QPushButton(), "rd_webrtc_publish_via_server")
        self._panel._publish_btn.clicked.connect(self._panel._on_publish_via_server)
        grid.addWidget(self._panel._publish_btn, 3, 0, 1, 4)
        # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
        from je_auto_control.utils.remote_desktop.fingerprint import (
            fingerprint_for_display,
            load_or_create_host_fingerprint,
        )
        # pylint: enable=import-outside-toplevel

        try:
            fp = load_or_create_host_fingerprint()
        except OSError:
            fp = ""
        grid.addWidget(self._panel._tr(QLabel(), "rd_webrtc_my_fingerprint"), 4, 0)
        self._panel._fingerprint_label = QLabel(fingerprint_for_display(fp) if fp else "")
        self._panel._fingerprint_label.setStyleSheet(
            "color: #888; font-family: 'Consolas', monospace; font-size: 10pt;"
        )
        self._panel._fingerprint_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(self._panel._fingerprint_label, 4, 1, 1, 2)
        copy_fp_btn = self._panel._tr(QPushButton(), "rd_webrtc_copy_fingerprint")
        copy_fp_btn.clicked.connect(lambda: self._panel._on_copy_fingerprint(fp))
        grid.addWidget(copy_fp_btn, 4, 3)
        group.setLayout(grid)
        return group

    def _on_copy_fingerprint(self, fp: str) -> None:
        # pylint: disable=no-name-in-module,import-outside-toplevel  # reason: lazy optional/cyclic boundary
        from PySide6.QtWidgets import (
            QApplication,
        )
        # pylint: enable=no-name-in-module,import-outside-toplevel

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(fp)

    def _build_config_group(self) -> QGroupBox:
        group, grid = token_grid(self._panel)
        grid.addWidget(self._panel._tr(QLabel(), "rd_webrtc_monitor_label"), 1, 0)
        self._panel._monitor_combo = QComboBox()
        self._panel._populate_monitor_combo()
        self._panel._monitor_combo.currentIndexChanged.connect(self._panel._on_monitor_changed)
        grid.addWidget(self._panel._monitor_combo, 1, 1)
        grid.addWidget(self._panel._tr(QLabel(), "rd_fps_label"), 2, 0)
        self._panel._fps_spin = QSpinBox()
        self._panel._fps_spin.setRange(1, 60)
        self._panel._fps_spin.setValue(_DEFAULT_FPS)
        grid.addWidget(self._panel._fps_spin, 2, 1)
        self._build_media_controls(grid)
        group.setLayout(grid)
        return group

    def _populate_monitor_combo(self) -> None:
        try:
            # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
            from je_auto_control.utils.cv2_utils.screen_grabber import (
                mss_grabber,
            )
            # pylint: enable=import-outside-toplevel

            with mss_grabber() as sct:
                monitors = sct.monitors
            for idx, mon in enumerate(monitors):
                if idx == 0:
                    label = _t("rd_webrtc_monitor_all")
                else:
                    label = f"#{idx}: {mon['width']}x{mon['height']} @ ({mon['left']},{mon['top']})"
                self._panel._monitor_combo.addItem(label, idx)
        except (ImportError, RuntimeError, OSError):
            for idx in range(4):
                self._panel._monitor_combo.addItem(f"#{idx}", idx)
        idx_default = self._panel._monitor_combo.findData(_DEFAULT_MONITOR)
        if idx_default >= 0:
            self._panel._monitor_combo.setCurrentIndex(idx_default)

    def _on_pick_region(self) -> None:
        try:
            # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
            from je_auto_control.gui.selector import (
                open_region_selector,
            )
            # pylint: enable=import-outside-toplevel

            region = open_region_selector(self._panel)
        except (ImportError, RuntimeError, OSError) as error:
            QMessageBox.warning(self._panel, "WebRTC", str(error))
            return
        if region is None:
            return
        x, y, w, h = tuple(region)
        self._panel._region_edit.setText(f"{x},{y},{w},{h}")

    def _on_monitor_changed(self, _i: int) -> None:
        idx = self._panel._monitor_combo.currentData()
        if idx is None or self._panel._multi_host is None:
            return
        track = self._panel._multi_host.screen_track()
        if track is None:
            return
        try:
            track.set_target_monitor(int(idx))
            autocontrol_logger.info("monitor switched to #%d live", int(idx))
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("set_target_monitor: %r", error)

    def _build_manual_group(self) -> QGroupBox:
        group = self._panel._tr(QGroupBox(), "rd_webrtc_manual_group")
        layout = QVBoxLayout()
        self._panel._generate_btn = self._panel._tr(QPushButton(), "rd_webrtc_generate_offer")
        self._panel._generate_btn.clicked.connect(self._panel._on_generate_offer)
        layout.addWidget(self._panel._generate_btn)
        layout.addWidget(self._panel._tr(QLabel(), "rd_webrtc_offer_label"))
        self._panel._offer_view = QTextEdit()
        self._panel._offer_view.setReadOnly(True)
        self._panel._offer_view.setMinimumHeight(80)
        layout.addWidget(self._panel._offer_view)
        layout.addWidget(self._panel._tr(QLabel(), "rd_webrtc_answer_input_label"))
        self._panel._answer_input = QTextEdit()
        self._panel._answer_input.setMinimumHeight(80)
        self._panel._tr(self._panel._answer_input, "rd_webrtc_paste_answer", "setPlaceholderText")
        layout.addWidget(self._panel._answer_input)
        button_row = QHBoxLayout()
        self._panel._apply_btn = self._panel._tr(QPushButton(), "rd_webrtc_apply_answer")
        self._panel._apply_btn.clicked.connect(self._panel._on_apply_answer)
        button_row.addWidget(self._panel._apply_btn)
        self._panel._stop_btn = self._panel._tr(QPushButton(), "rd_webrtc_stop_host")
        self._panel._stop_btn.clicked.connect(self._panel._on_stop)
        button_row.addWidget(self._panel._stop_btn)
        layout.addLayout(button_row)
        group.setLayout(layout)
        return group

    def _update_availability(self) -> None:
        if not is_webrtc_available():
            for widget in (self._panel._generate_btn, self._panel._apply_btn, self._panel._publish_btn):
                widget.setEnabled(False)
            self._panel._status_label.setText(_t("rd_webrtc_unavailable"))

    def prefill(
        self, token: Optional[str] = None, host_id: Optional[str] = None, signaling_url: Optional[str] = None
    ) -> None:
        """Hand-off entry point used by the Quick Connect screen.

        Populates the signaling-flow fields so the operator can click
        "Publish & wait for viewer" without retyping a token they
        already shared on the Quick Connect tab.
        """
        if token:
            self._panel._token_edit.setText(token)
        if host_id:
            self._panel._host_id_edit.setText(host_id)
        if signaling_url and hasattr(self._panel, "_server_edit"):
            self._panel._server_edit.setText(signaling_url)

    def _on_regen_id(self) -> None:
        self._panel._host_id_edit.setText(generate_host_id())

    def _validate_required_fields(self, *, needs_server: bool) -> bool:
        return validate_required_fields(self._panel, needs_server=needs_server)

    def retranslate(self) -> None:
        """Refresh the owning panel translations."""
        TranslatableMixin.retranslate(self._panel)

    def _build_media_controls(self, grid: QGridLayout) -> None:
        grid.addWidget(self._panel._tr(QLabel(), "rd_webrtc_region_label"), 11, 0)
        self._panel._region_edit = QLineEdit()
        self._panel._tr(self._panel._region_edit, "rd_webrtc_region_placeholder", "setPlaceholderText")
        grid.addWidget(self._panel._region_edit, 11, 1)
        pick_region_btn = self._panel._tr(QPushButton(), "rd_webrtc_pick_region")
        pick_region_btn.clicked.connect(self._panel._on_pick_region)
        grid.addWidget(pick_region_btn, 11, 2)
        self._panel._cursor_check = self._panel._tr(QCheckBox(), "rd_webrtc_show_cursor")
        self._panel._cursor_check.setChecked(True)
        grid.addWidget(self._panel._cursor_check, 3, 0, 1, 2)
        self._panel._blank_check = self._panel._tr(QCheckBox(), "rd_webrtc_blank_screen")
        self._panel._blank_check.setChecked(False)
        self._panel._blank_check.toggled.connect(self._panel._on_toggle_blanking)
        grid.addWidget(self._panel._blank_check, 4, 0, 1, 2)
        self._panel._readonly_check = self._panel._tr(QCheckBox(), "rd_webrtc_read_only")
        self._panel._readonly_check.setChecked(False)
        self._panel._readonly_check.toggled.connect(self._panel._on_toggle_readonly)
        grid.addWidget(self._panel._readonly_check, 5, 0, 1, 2)
        self._panel._adaptive_check = self._panel._tr(QCheckBox(), "rd_webrtc_adaptive")
        self._panel._adaptive_check.setChecked(True)
        self._panel._adaptive_check.toggled.connect(self._panel._on_toggle_adaptive)
        grid.addWidget(self._panel._adaptive_check, 6, 0, 1, 2)
        self._panel._mic_recv_check = self._panel._tr(QCheckBox(), "rd_webrtc_recv_mic")
        self._panel._mic_recv_check.setChecked(False)
        self._panel._mic_recv_check.toggled.connect(self._panel._on_toggle_mic_receive)
        grid.addWidget(self._panel._mic_recv_check, 7, 0, 1, 2)
        self._panel._host_voice_check = self._panel._tr(QCheckBox(), "rd_webrtc_host_voice")
        self._panel._host_voice_check.setChecked(False)
        grid.addWidget(self._panel._host_voice_check, 13, 0, 1, 2)
        grid.addWidget(self._panel._tr(QLabel(), "rd_webrtc_max_bitrate"), 10, 0)
        self._panel._max_bitrate_spin = QSpinBox()
        self._panel._max_bitrate_spin.setRange(0, 50000)
        self._panel._max_bitrate_spin.setSingleStep(500)
        self._panel._max_bitrate_spin.setSuffix(" kbps (0=∞)")
        self._panel._max_bitrate_spin.setValue(0)
        grid.addWidget(self._panel._max_bitrate_spin, 10, 1)
        grid.addWidget(self._panel._tr(QLabel(), "rd_webrtc_ip_whitelist"), 12, 0)
        self._panel._ip_whitelist_edit = QTextEdit()
        self._panel._ip_whitelist_edit.setMaximumHeight(60)
        self._panel._tr(self._panel._ip_whitelist_edit, "rd_webrtc_ip_whitelist_ph", "setPlaceholderText")
        grid.addWidget(self._panel._ip_whitelist_edit, 12, 1)
        self._panel._accept_viewer_video_check = self._panel._tr(QCheckBox(), "rd_webrtc_accept_viewer_video")
        self._panel._accept_viewer_video_check.setChecked(False)
        self._panel._accept_viewer_video_check.toggled.connect(self._panel._on_toggle_accept_viewer_video)
        grid.addWidget(self._panel._accept_viewer_video_check, 8, 0, 1, 2)
        self._panel._accept_opus_audio_check = self._panel._tr(QCheckBox(), "rd_webrtc_accept_opus_audio")
        self._panel._accept_opus_audio_check.setChecked(False)
        self._panel._accept_opus_audio_check.toggled.connect(self._panel._on_toggle_accept_opus_audio)
        grid.addWidget(self._panel._accept_opus_audio_check, 9, 0, 1, 2)
