"""Widget construction for the WebRTC viewer panel.

One interaction group of ``webrtc_panel._WebRTCViewerPanel``, kept as a mixin so the panel class
still owns every widget and slot under its original name.
"""
from __future__ import annotations


from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QTextEdit, QVBoxLayout,
)

from je_auto_control.gui.remote_desktop._helpers import (
    _CollapsibleSection, _t,
)
from je_auto_control.gui.remote_desktop.advanced_group import (
    build_advanced_group,
)
from je_auto_control.gui.remote_desktop.frame_display import _FrameDisplay
from je_auto_control.gui.remote_desktop.sparkline import Sparkline
from je_auto_control.gui.remote_desktop.webrtc_dialogs import (
    AddressBookList, RemoteFilesTable,
)
from je_auto_control.utils.remote_desktop.webrtc_transport import (
    BANDWIDTH_PRESETS,
)
from je_auto_control.gui.remote_desktop.webrtc_panel_common import (
    _DEFAULT_SIGNALING_URL, _QUALITY_DOT_STYLE,
)


class _ViewerUiMixin:
    """Methods of ``_WebRTCViewerPanel``; the module docstring says which group."""

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        # Essentials always visible: address book + recommended
        # signaling-server flow + WebRTC config.
        layout.addWidget(self._build_address_book_group())
        layout.addWidget(self._build_signaling_group())
        layout.addWidget(self._build_config_group())
        # Heavy / rarely-used groups now collapse by default so the
        # tab fits on a normal display without scrolling.
        layout.addWidget(self._wrap_collapsed(
            self._build_manual_group(),
            "rd_webrtc_manual_group",
        ))
        layout.addWidget(build_advanced_group(self))
        layout.addWidget(self._wrap_collapsed(
            self._build_remote_files_group(),
            "rd_webrtc_files_group",
        ))
        layout.addWidget(self._wrap_collapsed(
            self._build_sync_group(),
            "rd_webrtc_sync_group",
        ))
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
        # Hidden _FrameDisplay placeholder kept around so the rest of
        # the class (pen mode toggle, image setter) doesn't have to
        # branch between "popup open" and "popup closed". It also lets
        # the panel decode frames before the operator opens the popup.
        # When the popup IS open, frames + input round-trip through
        # the popup's display instead.
        self._frame_display = _FrameDisplay()
        self._frame_display.setVisible(False)
        layout.addWidget(self._frame_display)
        layout.addStretch(1)
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

    def _wrap_collapsed(self, inner: QGroupBox,
                        title_key: str) -> _CollapsibleSection:
        """Wrap an existing groupbox in a collapsed-by-default container.

        The inner group keeps its own translated title, so we just pass
        it through the wrapper's body. Heavy / rarely-used groups
        (manual SDP, remote files, sync) hide their bodies by default
        so the panel doesn't scroll past the fold on a normal display.
        """
        section = _CollapsibleSection()
        # Translate the wrapper title; the inner groupbox already has
        # its own header so we strip its frame to avoid double chrome.
        self._tr(section, title_key, setter="setTitle")
        inner.setStyleSheet("QGroupBox { border: none; margin-top: 0px; }")
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(inner)
        section.set_body_layout(body)
        return section

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


__all__ = ["_ViewerUiMixin"]
