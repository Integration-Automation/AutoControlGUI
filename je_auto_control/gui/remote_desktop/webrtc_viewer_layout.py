"""WebRTC viewer layout controller; session and widget ownership stays on the panel."""
# pylint: disable=protected-access  # reason: typed controllers share their owning panel state

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

# pylint: enable=no-name-in-module
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.remote_desktop._helpers import _CollapsibleSection, _t
from je_auto_control.gui.remote_desktop.advanced_group import build_advanced_group
from je_auto_control.gui.remote_desktop.frame_display import _FrameDisplay
from je_auto_control.gui.remote_desktop.sparkline import Sparkline
from je_auto_control.gui.remote_desktop.webrtc_common import (
    _QUALITY_DOT_STYLE,
    signaling_grid,
    token_grid,
    validate_required_fields,
)
from je_auto_control.gui.remote_desktop.webrtc_dialogs import AddressBookList, RemoteFilesTable
from je_auto_control.utils.remote_desktop import is_webrtc_available
from je_auto_control.utils.remote_desktop.webrtc_transport import BANDWIDTH_PRESETS

if TYPE_CHECKING:
    from je_auto_control.gui.remote_desktop.webrtc_viewer_panel import _WebRTCViewerPanel


class WebRTCViewerLayoutController:  # pylint: disable=too-few-public-methods  # reason: internal signal/slot controller
    """Viewer layout interactions on a typed owned panel."""

    def __init__(self, panel: _WebRTCViewerPanel) -> None:
        self._panel = panel

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self._panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self._panel._build_address_book_group())
        layout.addWidget(self._panel._build_signaling_group())
        layout.addWidget(self._panel._build_config_group())
        layout.addWidget(self._panel._wrap_collapsed(self._panel._build_manual_group(), "rd_webrtc_manual_group"))
        layout.addWidget(build_advanced_group(self._panel))
        layout.addWidget(self._panel._wrap_collapsed(self._panel._build_remote_files_group(), "rd_webrtc_files_group"))
        layout.addWidget(self._panel._wrap_collapsed(self._panel._build_sync_group(), "rd_webrtc_sync_group"))
        self._panel._status_label = QLabel(_t("rd_webrtc_status_idle"))
        layout.addWidget(self._panel._status_label)
        self._build_action_controls(layout)
        self._build_statistics_views(layout)
        self._panel._frame_display = _FrameDisplay()
        self._panel._frame_display.setVisible(False)
        layout.addWidget(self._panel._frame_display)
        layout.addStretch(1)
        self._panel._wire_input_signals()

    def _build_sync_group(self) -> QGroupBox:
        group = self._panel._tr(QGroupBox(), "rd_webrtc_sync_group")
        layout = QGridLayout()
        layout.addWidget(self._panel._tr(QLabel(), "rd_webrtc_sync_dir"), 0, 0)
        self._panel._sync_dir_edit = QLineEdit()
        self._panel._tr(self._panel._sync_dir_edit, "rd_webrtc_sync_dir_ph", "setPlaceholderText")
        layout.addWidget(self._panel._sync_dir_edit, 0, 1)
        browse_btn = self._panel._tr(QPushButton(), "rd_webrtc_browse")
        browse_btn.clicked.connect(self._panel._on_sync_browse)
        layout.addWidget(browse_btn, 0, 2)
        self._panel._sync_btn = self._panel._tr(QPushButton(), "rd_webrtc_sync_start")
        self._panel._sync_btn.setCheckable(True)
        self._panel._sync_btn.clicked.connect(self._panel._on_toggle_sync)
        layout.addWidget(self._panel._sync_btn, 0, 3)
        group.setLayout(layout)
        return group

    def _build_remote_files_group(self) -> QGroupBox:
        group = self._panel._tr(QGroupBox(), "rd_webrtc_remote_files_group")
        layout = QVBoxLayout()
        button_row = QHBoxLayout()
        refresh_btn = self._panel._tr(QPushButton(), "rd_webrtc_browse_refresh")
        refresh_btn.clicked.connect(self._panel._on_browse_refresh)
        button_row.addWidget(refresh_btn)
        pull_btn = self._panel._tr(QPushButton(), "rd_webrtc_browse_pull")
        pull_btn.clicked.connect(self._panel._on_browse_pull_button)
        button_row.addWidget(pull_btn)
        delete_btn = self._panel._tr(QPushButton(), "rd_webrtc_browse_delete")
        delete_btn.clicked.connect(self._panel._on_browse_delete_button)
        button_row.addWidget(delete_btn)
        button_row.addStretch()
        layout.addLayout(button_row)
        self._panel._remote_files_table = RemoteFilesTable()
        self._panel._remote_files_table.pull_requested.connect(self._panel._on_pull_names)
        self._panel._remote_files_table.delete_requested.connect(self._panel._on_delete_names)
        self._panel._remote_files_table.upload_requested.connect(self._panel._on_upload_paths)
        self._panel._remote_files_table.copy_name_requested.connect(self._panel._on_copy_name)
        layout.addWidget(self._panel._remote_files_table)
        layout.addWidget(self._panel._tr(QLabel(), "rd_webrtc_browse_dnd_hint"))
        group.setLayout(layout)
        return group

    def _wrap_collapsed(self, inner: QGroupBox, title_key: str) -> _CollapsibleSection:
        """Wrap an existing groupbox in a collapsed-by-default container.

        The inner group keeps its own translated title, so we just pass
        it through the wrapper's body. Heavy / rarely-used groups
        (manual SDP, remote files, sync) hide their bodies by default
        so the panel doesn't scroll past the fold on a normal display.
        """
        section = _CollapsibleSection()
        self._panel._tr(section, title_key, setter="setTitle")
        inner.setStyleSheet("QGroupBox { border: none; margin-top: 0px; }")
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(inner)
        section.set_body_layout(body)
        return section

    def _build_address_book_group(self) -> QGroupBox:
        group = self._panel._tr(QGroupBox(), "rd_webrtc_address_book_group")
        layout = QVBoxLayout()
        tag_row = QHBoxLayout()
        tag_row.addWidget(self._panel._tr(QLabel(), "rd_webrtc_tag_filter"))
        self._panel._tag_filter_combo = QComboBox()
        self._panel._tag_filter_combo.addItem(_t("rd_webrtc_tag_all"), "")
        self._panel._tag_filter_combo.currentIndexChanged.connect(lambda _i: self._panel._refresh_address_book())
        tag_row.addWidget(self._panel._tag_filter_combo, stretch=1)
        layout.addLayout(tag_row)
        self._panel._address_list = AddressBookList()
        self._panel._address_list.chosen.connect(self._panel._on_address_chosen)
        self._panel._address_list.deleted.connect(self._panel._on_address_removed)
        self._panel._address_list.favorite_toggled.connect(self._panel._on_address_favorite)
        self._panel._address_list.tags_edit_requested.connect(self._panel._on_address_tags)
        self._panel._address_list.setMaximumHeight(120)
        layout.addWidget(self._panel._address_list)
        button_row = QHBoxLayout()
        connect_btn = self._panel._tr(QPushButton(), "rd_webrtc_connect_selected")
        connect_btn.clicked.connect(self._panel._on_connect_selected_address)
        button_row.addWidget(connect_btn)
        save_btn = self._panel._tr(QPushButton(), "rd_webrtc_save_current")
        save_btn.clicked.connect(self._panel._on_save_current_address)
        button_row.addWidget(save_btn)
        remove_btn = self._panel._tr(QPushButton(), "rd_webrtc_remove_selected")
        remove_btn.clicked.connect(self._panel._on_remove_selected_address)
        button_row.addWidget(remove_btn)
        kh_btn = self._panel._tr(QPushButton(), "rd_webrtc_manage_known_hosts")
        kh_btn.clicked.connect(self._panel._on_manage_known_hosts)
        button_row.addWidget(kh_btn)
        ab_export = self._panel._tr(QPushButton(), "rd_webrtc_ab_export")
        ab_export.clicked.connect(self._panel._on_ab_export)
        button_row.addWidget(ab_export)
        ab_import = self._panel._tr(QPushButton(), "rd_webrtc_ab_import")
        ab_import.clicked.connect(self._panel._on_ab_import)
        button_row.addWidget(ab_import)
        ab_clear = self._panel._tr(QPushButton(), "rd_webrtc_ab_clear")
        ab_clear.clicked.connect(self._panel._on_ab_clear)
        button_row.addWidget(ab_clear)
        layout.addLayout(button_row)
        group.setLayout(layout)
        return group

    def _build_signaling_group(self) -> QGroupBox:
        group, grid = signaling_grid(self._panel)
        self._panel._host_id_edit = self._panel._tr(QLineEdit(), "rd_webrtc_host_id_placeholder")
        grid.addWidget(self._panel._host_id_edit, 1, 1, 1, 3)
        grid.addWidget(self._panel._tr(QLabel(), "rd_webrtc_secret_label"), 2, 0)
        self._panel._secret_edit = QLineEdit()
        self._panel._secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(self._panel._secret_edit, 2, 1, 1, 3)
        self._panel._connect_btn = self._panel._tr(QPushButton(), "rd_webrtc_connect_via_server")
        self._panel._connect_btn.clicked.connect(self._panel._on_connect_via_server)
        grid.addWidget(self._panel._connect_btn, 3, 0, 1, 3)
        self._panel._lan_browse_btn = self._panel._tr(QPushButton(), "rd_webrtc_lan_browse")
        self._panel._lan_browse_btn.clicked.connect(self._panel._on_lan_browse)
        grid.addWidget(self._panel._lan_browse_btn, 3, 3)
        group.setLayout(grid)
        return group

    def prefill(
        self, host_id: Optional[str] = None, token: Optional[str] = None, signaling_url: Optional[str] = None
    ) -> None:
        """Hand-off entry point used by the Quick Connect screen.

        Populates the signaling-flow fields without auto-clicking
        Connect so the operator can sanity-check before the session
        starts. Empty strings are ignored so callers can fill only the
        fields they actually know.
        """
        if host_id:
            self._panel._host_id_edit.setText(host_id)
        if token:
            self._panel._token_edit.setText(token)
        if signaling_url:
            self._panel._server_edit.setText(signaling_url)

    def _build_config_group(self) -> QGroupBox:
        group, grid = token_grid(self._panel)
        grid.addWidget(self._panel._tr(QLabel(), "rd_webrtc_bandwidth_label"), 1, 0)
        self._panel._bandwidth_combo = QComboBox()
        for key, info in BANDWIDTH_PRESETS.items():
            self._panel._bandwidth_combo.addItem(info["label"], key)
        grid.addWidget(self._panel._bandwidth_combo, 1, 1)
        self._panel._share_my_screen_check = self._panel._tr(QCheckBox(), "rd_webrtc_share_my_screen")
        self._panel._share_my_screen_check.setChecked(False)
        self._panel._share_my_screen_check.toggled.connect(self._panel._on_toggle_share_my_screen)
        grid.addWidget(self._panel._share_my_screen_check, 2, 0, 1, 2)
        self._panel._share_opus_mic_check = self._panel._tr(QCheckBox(), "rd_webrtc_share_opus_mic")
        self._panel._share_opus_mic_check.setChecked(False)
        self._panel._share_opus_mic_check.toggled.connect(self._panel._on_toggle_share_opus_mic)
        grid.addWidget(self._panel._share_opus_mic_check, 3, 0, 1, 2)
        self._panel._auto_reconnect_check = self._panel._tr(QCheckBox(), "rd_webrtc_auto_reconnect")
        self._panel._auto_reconnect_check.setChecked(False)
        grid.addWidget(self._panel._auto_reconnect_check, 4, 0, 1, 2)
        grid.addWidget(self._panel._tr(QLabel(), "rd_webrtc_reconnect_max"), 5, 0)
        self._panel._reconnect_max_spin = QSpinBox()
        self._panel._reconnect_max_spin.setRange(1, 50)
        self._panel._reconnect_max_spin.setValue(5)
        grid.addWidget(self._panel._reconnect_max_spin, 5, 1)
        grid.addWidget(self._panel._tr(QLabel(), "rd_webrtc_reconnect_delay"), 6, 0)
        self._panel._reconnect_delay_spin = QSpinBox()
        self._panel._reconnect_delay_spin.setRange(1, 60)
        self._panel._reconnect_delay_spin.setValue(1)
        self._panel._reconnect_delay_spin.setSuffix(" s")
        grid.addWidget(self._panel._reconnect_delay_spin, 6, 1)
        group.setLayout(grid)
        return group

    def _build_manual_group(self) -> QGroupBox:
        group = self._panel._tr(QGroupBox(), "rd_webrtc_manual_group")
        layout = QVBoxLayout()
        layout.addWidget(self._panel._tr(QLabel(), "rd_webrtc_offer_input_label"))
        self._panel._offer_input = QTextEdit()
        self._panel._offer_input.setMinimumHeight(80)
        self._panel._tr(self._panel._offer_input, "rd_webrtc_paste_offer", "setPlaceholderText")
        layout.addWidget(self._panel._offer_input)
        button_row = QHBoxLayout()
        self._panel._answer_btn = self._panel._tr(QPushButton(), "rd_webrtc_create_answer")
        self._panel._answer_btn.clicked.connect(self._panel._on_create_answer)
        button_row.addWidget(self._panel._answer_btn)
        self._panel._stop_btn = self._panel._tr(QPushButton(), "rd_webrtc_stop_viewer")
        self._panel._stop_btn.clicked.connect(self._panel._on_stop)
        button_row.addWidget(self._panel._stop_btn)
        layout.addLayout(button_row)
        layout.addWidget(self._panel._tr(QLabel(), "rd_webrtc_answer_label"))
        self._panel._answer_view = QTextEdit()
        self._panel._answer_view.setReadOnly(True)
        self._panel._answer_view.setMinimumHeight(80)
        layout.addWidget(self._panel._answer_view)
        group.setLayout(layout)
        return group

    def _wire_input_signals(self) -> None:
        self._panel._wire_display_input(self._panel._frame_display)

    def _wire_display_input(self, source: Any) -> None:
        """Wire mouse / keyboard / annotation signals from ``source``.

        ``source`` can be a :class:`_FrameDisplay` or a
        :class:`RemoteScreenWindow` — both expose the same Signal
        names with matching shapes.
        """
        source.mouse_moved.connect(lambda x, y: self._panel._send({"type": "mouse_move", "x": int(x), "y": int(y)}))
        source.mouse_pressed.connect(
            lambda x, y, b: self._panel._send({"type": "mouse_press", "x": int(x), "y": int(y), "button": b})
        )
        source.mouse_released.connect(
            lambda x, y, b: self._panel._send({"type": "mouse_release", "x": int(x), "y": int(y), "button": b})
        )
        source.mouse_scrolled.connect(
            lambda x, y, a: self._panel._send({"type": "mouse_scroll", "x": int(x), "y": int(y), "amount": int(a)})
        )
        source.key_pressed.connect(lambda k: self._panel._send({"type": "key_press", "keycode": k}))
        source.key_released.connect(lambda k: self._panel._send({"type": "key_release", "keycode": k}))
        source.type_text.connect(lambda text: self._panel._send({"type": "type_text", "text": text}))
        source.annotation_event.connect(self._panel._on_annotation_segment)

    def _update_availability(self) -> None:
        if not is_webrtc_available():
            for widget in (self._panel._answer_btn, self._panel._connect_btn):
                widget.setEnabled(False)
            self._panel._status_label.setText(_t("rd_webrtc_unavailable"))

    def _validate_required_fields(self, *, needs_server: bool) -> bool:
        return validate_required_fields(self._panel, needs_server=needs_server)

    def retranslate(self) -> None:
        """Refresh the owning panel translations."""
        TranslatableMixin.retranslate(self._panel)

    def _build_action_controls(self, layout: QVBoxLayout) -> None:
        action_row = QHBoxLayout()
        self._panel._cad_btn = self._panel._tr(QPushButton(), "rd_webrtc_send_cad")
        self._panel._cad_btn.clicked.connect(self._panel._on_send_cad)
        action_row.addWidget(self._panel._cad_btn)
        self._panel._wol_btn = self._panel._tr(QPushButton(), "rd_webrtc_wake_on_lan")
        self._panel._wol_btn.clicked.connect(self._panel._on_wake_on_lan)
        action_row.addWidget(self._panel._wol_btn)
        self._panel._mic_btn = self._panel._tr(QPushButton(), "rd_webrtc_send_mic")
        self._panel._mic_btn.setCheckable(True)
        self._panel._mic_btn.clicked.connect(self._panel._on_toggle_mic)
        action_row.addWidget(self._panel._mic_btn)
        self._panel._send_file_btn = self._panel._tr(QPushButton(), "rd_webrtc_send_file")
        self._panel._send_file_btn.clicked.connect(self._panel._on_send_file)
        action_row.addWidget(self._panel._send_file_btn)
        self._panel._record_btn = self._panel._tr(QPushButton(), "rd_webrtc_start_recording")
        self._panel._record_btn.setCheckable(True)
        self._panel._record_btn.clicked.connect(self._panel._on_toggle_recording)
        action_row.addWidget(self._panel._record_btn)
        self._panel._pen_btn = self._panel._tr(QPushButton(), "rd_webrtc_pen_off")
        self._panel._pen_btn.setCheckable(True)
        self._panel._pen_btn.clicked.connect(self._panel._on_toggle_pen)
        action_row.addWidget(self._panel._pen_btn)
        self._panel._pen_clear_btn = self._panel._tr(QPushButton(), "rd_webrtc_pen_clear")
        self._panel._pen_clear_btn.clicked.connect(self._panel._on_pen_clear)
        action_row.addWidget(self._panel._pen_clear_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

    def _build_statistics_views(self, layout: QVBoxLayout) -> None:
        stats_row = QHBoxLayout()
        self._panel._quality_dot = QLabel()
        self._panel._quality_dot.setFixedSize(14, 14)
        self._panel._quality_dot.setStyleSheet(_QUALITY_DOT_STYLE)
        self._panel._quality_dot.setToolTip(_t("rd_webrtc_quality_unknown"))
        stats_row.addWidget(self._panel._quality_dot)
        self._panel._stats_label = QLabel(_t("rd_webrtc_stats_idle"))
        self._panel._stats_label.setStyleSheet("color: #ccaa55; font-family: 'Consolas', monospace;")
        stats_row.addWidget(self._panel._stats_label, stretch=1)
        layout.addLayout(stats_row)
        spark_row = QHBoxLayout()
        self._panel._rtt_spark = Sparkline(line_color="#3a9c3a")
        self._panel._rtt_spark.setToolTip("RTT (ms)")
        spark_row.addWidget(self._panel._rtt_spark, stretch=1)
        self._panel._bitrate_spark = Sparkline(line_color="#c97a00")
        self._panel._bitrate_spark.setToolTip("kbps")
        spark_row.addWidget(self._panel._bitrate_spark, stretch=1)
        layout.addLayout(spark_row)
