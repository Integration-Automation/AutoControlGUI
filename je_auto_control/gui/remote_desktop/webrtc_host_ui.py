"""Widget construction for the WebRTC host panel.

One interaction group of ``webrtc_panel._WebRTCHostPanel``, kept as a mixin so the panel class
still owns every widget and slot under its original name.
"""
from __future__ import annotations


from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QSpinBox, QTableWidget, QTextEdit, QVBoxLayout,
)

from je_auto_control.gui.remote_desktop._helpers import (
    _t,
)
from je_auto_control.gui.remote_desktop.advanced_group import (
    build_advanced_group,
)
from je_auto_control.gui.remote_desktop.trusted_group import (
    build_trusted_group,
)
from je_auto_control.gui.remote_desktop.webrtc_workers import (
    generate_host_id,
)
from je_auto_control.gui.remote_desktop.webrtc_panel_common import (
    _PanelPart,
    _DEFAULT_FPS, _DEFAULT_SIGNALING_URL, _QUALITY_DOT_STYLE,
)


class _HostUiMixin(_PanelPart):
    """Methods of ``_WebRTCHostPanel``; the module docstring says which group."""

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(self._build_signaling_group())
        layout.addWidget(self._build_config_group())
        layout.addWidget(self._build_manual_group())
        layout.addWidget(build_advanced_group(self, include_hw_codec=True))
        layout.addWidget(build_trusted_group(self))
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
        # Hint at a comfortable starting height, but let the table
        # grow with the window instead of pinning it at 140 px even
        # when the operator has a 4K monitor's worth of space.
        self._sessions_table.setMinimumHeight(140)
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


__all__ = ["_HostUiMixin"]
