"""Typed WebRTC viewer panel composing layout, feature and lifecycle controllers."""
# pylint: disable=protected-access  # reason: typed controllers share their owning panel state

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtCore import QTimer

# pylint: enable=no-name-in-module
# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtGui import QImage

# pylint: enable=no-name-in-module
# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtWidgets import QGroupBox, QWidget

# pylint: enable=no-name-in-module
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.remote_desktop._helpers import _CollapsibleSection
from je_auto_control.gui.remote_desktop.remote_screen_window import RemoteScreenWindow
from je_auto_control.gui.remote_desktop.session_owner import PanelSessions
from je_auto_control.gui.remote_desktop.webrtc_common import _PanelSignals, _read_webrtc_config
from je_auto_control.gui.remote_desktop.webrtc_viewer_layout import WebRTCViewerLayoutController
from je_auto_control.gui.remote_desktop.webrtc_viewer_session import WebRTCViewerSessionController
from je_auto_control.gui.remote_desktop.webrtc_viewer_transfers import WebRTCViewerTransfersController
from je_auto_control.gui.remote_desktop.webrtc_workers import ViewerAnswerPushWorker, ViewerSignalingWorker
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop import (
    SessionRecorder,
    WebRTCDesktopViewer,
    default_address_book,
    load_or_create_viewer_id,
)
from je_auto_control.utils.remote_desktop.registry import registry
from je_auto_control.utils.remote_desktop.webrtc_stats import StatsPoller, StatsSnapshot

if TYPE_CHECKING:
    from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine
if TYPE_CHECKING:
    import je_auto_control.gui.remote_desktop.frame_display
    import je_auto_control.gui.remote_desktop.remote_screen_window
    import je_auto_control.gui.remote_desktop.session_owner
    import je_auto_control.gui.remote_desktop.sparkline
    import je_auto_control.gui.remote_desktop.webrtc_common
    import je_auto_control.gui.remote_desktop.webrtc_dialogs
    import je_auto_control.gui.remote_desktop.webrtc_workers
    import je_auto_control.utils.remote_desktop.address_book
    import je_auto_control.utils.remote_desktop.file_sync
    import je_auto_control.utils.remote_desktop.fingerprint
    import je_auto_control.utils.remote_desktop.webrtc_stats


class _WebRTCViewerPanel(TranslatableMixin, QWidget):  # pylint: disable=too-many-instance-attributes  # reason: explicit owned lifecycle/widget state
    """Viewer: receive screen and send input."""

    _sessions: je_auto_control.gui.remote_desktop.session_owner.PanelSessions
    _viewer: Any | None
    _offer_worker: je_auto_control.gui.remote_desktop.webrtc_workers.ViewerSignalingWorker | None
    _answer_worker: je_auto_control.gui.remote_desktop.webrtc_workers.ViewerAnswerPushWorker | None
    _address_book: je_auto_control.utils.remote_desktop.address_book.AddressBook
    _known_hosts: je_auto_control.utils.remote_desktop.fingerprint.KnownHosts
    _viewer_id: str | None
    _recorder: Any | None
    _stats_poller: je_auto_control.utils.remote_desktop.webrtc_stats.StatsPoller | None
    _sync_engine: je_auto_control.utils.remote_desktop.file_sync.FolderSyncEngine | None
    _auto_reconnect_attempts: int
    _user_initiated_disconnect: bool
    _reconnect_timer: Any
    _screen_window: je_auto_control.gui.remote_desktop.remote_screen_window.RemoteScreenWindow | None
    _signals: je_auto_control.gui.remote_desktop.webrtc_common._PanelSignals
    _status_label: Any
    _cad_btn: Any
    _wol_btn: Any
    _mic_btn: Any
    _send_file_btn: Any
    _record_btn: Any
    _pen_btn: Any
    _pen_clear_btn: Any
    _quality_dot: Any
    _stats_label: Any
    _rtt_spark: je_auto_control.gui.remote_desktop.sparkline.Sparkline
    _bitrate_spark: je_auto_control.gui.remote_desktop.sparkline.Sparkline
    _frame_display: je_auto_control.gui.remote_desktop.frame_display._FrameDisplay
    _sync_dir_edit: Any
    _sync_btn: Any
    _remote_files_table: je_auto_control.gui.remote_desktop.webrtc_dialogs.RemoteFilesTable
    _tag_filter_combo: Any
    _address_list: je_auto_control.gui.remote_desktop.webrtc_dialogs.AddressBookList
    _server_edit: Any
    _host_id_edit: Any
    _secret_edit: Any
    _connect_btn: Any
    _lan_browse_btn: Any
    _token_edit: Any
    _bandwidth_combo: Any
    _share_my_screen_check: Any
    _share_opus_mic_check: Any
    _auto_reconnect_check: Any
    _reconnect_max_spin: Any
    _reconnect_delay_spin: Any
    _offer_input: Any
    _answer_btn: Any
    _stop_btn: Any
    _answer_view: Any

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._layout_controller = WebRTCViewerLayoutController(self)
        self._transfers_controller = WebRTCViewerTransfersController(self)
        self._session_controller = WebRTCViewerSessionController(self)
        self._tr_init()
        self._sessions = PanelSessions(self, registry)
        self._sessions.ended.connect(self._on_session_ended)
        self._viewer: Optional[WebRTCDesktopViewer] = None
        self._offer_worker: Optional[ViewerSignalingWorker] = None
        self._answer_worker: Optional[ViewerAnswerPushWorker] = None
        self._address_book = default_address_book()
        # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
        from je_auto_control.utils.remote_desktop import (
            default_known_hosts,
        )
        # pylint: enable=import-outside-toplevel

        self._known_hosts = default_known_hosts()
        try:
            self._viewer_id: Optional[str] = load_or_create_viewer_id()
        except OSError as error:
            autocontrol_logger.warning("viewer_id init: %r", error)
            self._viewer_id = None
        self._recorder: Optional[SessionRecorder] = None
        self._stats_poller: Optional[StatsPoller] = None
        self._sync_engine: Optional["FolderSyncEngine"] = None
        self._auto_reconnect_attempts = 0
        self._user_initiated_disconnect = False
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._session_controller.reconnect_if_current)
        self._screen_window: Optional[RemoteScreenWindow] = None
        self._signals = _PanelSignals(self)
        self._signals.frame.connect(self._on_frame_image)
        self._signals.state.connect(self._on_state)
        self._signals.auth.connect(self._on_auth)
        self._signals.stats.connect(self._on_stats)
        self._signals.inbox_listing.connect(self._on_inbox_listing)
        self._signals.inbox_op.connect(self._on_inbox_op_result)
        self._signals.file_received.connect(self._on_file_received_ui)
        self._build_ui()
        self._refresh_address_book()
        self._update_availability()
        self._sessions.add_cleanup(self._session_controller.dispose_background)

    def _build_viewer(self, token: str) -> WebRTCDesktopViewer:
        identifier = self._sessions.id("viewer")
        session = (
            self._sessions.reserve("webrtc", "viewer")
            if identifier is None
            else registry.get_session(identifier, owner=self._sessions.owner)
        )
        viewer = WebRTCDesktopViewer(
            token=token,
            config=_read_webrtc_config(self),
            viewer_id=self._viewer_id,
            on_frame=self._sessions.callback("viewer", self._signals.frame.emit, transform=self._frame_arguments),
            on_state_change=self._sessions.callback("viewer", self._signals.state.emit),
            on_auth_result=self._sessions.callback("viewer", self._signals.auth.emit),
        )
        deliver_file = self._sessions.callback("viewer", self._signals.file_received.emit)
        viewer.set_file_received_callback(
            registry.bind_callback(session.id, lambda path: self._on_received_file(path, deliver=deliver_file))
        )
        viewer.set_inbox_listing_callback(self._sessions.callback("viewer", self._signals.inbox_listing.emit))
        viewer.set_inbox_op_result_callback(self._sessions.callback("viewer", self._signals.inbox_op.emit))
        self._sessions.attach(viewer, "viewer")
        return viewer

    def _on_received_file(self, path, *, deliver: Optional[Callable] = None) -> None:
        engine = self._sync_engine
        if engine is not None:
            engine.mark_received(path)
        (self._signals.file_received.emit if deliver is None else deliver)(path)

    def _build_ui(self) -> None:
        return self._layout_controller._build_ui()

    def _build_sync_group(self) -> QGroupBox:
        return self._layout_controller._build_sync_group()

    def _build_remote_files_group(self) -> QGroupBox:
        return self._layout_controller._build_remote_files_group()

    def _wrap_collapsed(self, inner: QGroupBox, title_key: str) -> _CollapsibleSection:
        """Wrap an existing groupbox in a collapsed-by-default container.

        The inner group keeps its own translated title, so we just pass
        it through the wrapper's body. Heavy / rarely-used groups
        (manual SDP, remote files, sync) hide their bodies by default
        so the panel doesn't scroll past the fold on a normal display.
        """
        return self._layout_controller._wrap_collapsed(inner, title_key)

    def _build_address_book_group(self) -> QGroupBox:
        return self._layout_controller._build_address_book_group()

    def _build_signaling_group(self) -> QGroupBox:
        return self._layout_controller._build_signaling_group()

    def prefill(
        self, host_id: Optional[str] = None, token: Optional[str] = None, signaling_url: Optional[str] = None
    ) -> None:
        """Hand-off entry point used by the Quick Connect screen.

        Populates the signaling-flow fields without auto-clicking
        Connect so the operator can sanity-check before the session
        starts. Empty strings are ignored so callers can fill only the
        fields they actually know.
        """
        return self._layout_controller.prefill(host_id, token, signaling_url)

    def _build_config_group(self) -> QGroupBox:
        return self._layout_controller._build_config_group()

    def _build_manual_group(self) -> QGroupBox:
        return self._layout_controller._build_manual_group()

    def _wire_input_signals(self) -> None:
        return self._layout_controller._wire_input_signals()

    def _wire_display_input(self, source) -> None:
        """Wire mouse / keyboard / annotation signals from ``source``.

        ``source`` can be a :class:`_FrameDisplay` or a
        :class:`RemoteScreenWindow` — both expose the same Signal
        names with matching shapes.
        """
        return self._layout_controller._wire_display_input(source)

    def _update_availability(self) -> None:
        return self._layout_controller._update_availability()

    def _validate_required_fields(self, *, needs_server: bool) -> bool:
        return self._layout_controller._validate_required_fields(needs_server=needs_server)

    def retranslate(self) -> None:
        """Refresh the owning panel translations."""
        return self._layout_controller.retranslate()

    def _on_sync_browse(self) -> None:
        return self._transfers_controller._on_sync_browse()

    def _on_toggle_sync(self, checked: bool) -> None:
        return self._transfers_controller._on_toggle_sync(checked)

    def _on_browse_refresh(self) -> None:
        return self._transfers_controller._on_browse_refresh()

    def _on_browse_pull_button(self) -> None:
        return self._transfers_controller._on_browse_pull_button()

    def _on_browse_delete_button(self) -> None:
        return self._transfers_controller._on_browse_delete_button()

    def _on_pull_names(self, names) -> None:
        return self._transfers_controller._on_pull_names(names)

    def _on_delete_names(self, names) -> None:
        return self._transfers_controller._on_delete_names(names)

    def _on_upload_paths(self, paths) -> None:
        return self._transfers_controller._on_upload_paths(paths)

    def _on_copy_name(self, name: str) -> None:
        return self._transfers_controller._on_copy_name(name)

    def _on_inbox_listing(self, files) -> None:
        return self._transfers_controller._on_inbox_listing(files)

    def _on_inbox_op_result(self, name: str, ok: bool, error) -> None:
        return self._transfers_controller._on_inbox_op_result(name, ok, error)

    def _on_send_file(self) -> None:
        return self._transfers_controller._on_send_file()

    @staticmethod
    def _wol_defaults(entry) -> tuple[str, str]:
        """Return (mac, broadcast) pre-fill values from a book entry."""
        return WebRTCViewerTransfersController._wol_defaults(entry)

    def _persist_wol_entry(self, entry, mac: str, broadcast: str) -> None:
        """Save the MAC / broadcast just used back onto the book entry."""
        return self._transfers_controller._persist_wol_entry(entry, mac, broadcast)

    def _on_wake_on_lan(self) -> None:
        return self._transfers_controller._on_wake_on_lan()

    def _on_ab_export(self) -> None:
        return self._transfers_controller._on_ab_export()

    def _on_ab_import(self) -> None:
        return self._transfers_controller._on_ab_import()

    def _on_ab_clear(self) -> None:
        return self._transfers_controller._on_ab_clear()

    def _on_manage_known_hosts(self) -> None:
        return self._transfers_controller._on_manage_known_hosts()

    def _refresh_address_book(self) -> None:
        return self._transfers_controller._refresh_address_book()

    def _on_address_tags(self, entry: dict) -> None:
        return self._transfers_controller._on_address_tags(entry)

    def _on_address_chosen(self, entry: dict) -> None:
        return self._transfers_controller._on_address_chosen(entry)

    def _on_address_removed(self, entry: dict) -> None:
        return self._transfers_controller._on_address_removed(entry)

    def _on_address_favorite(self, entry: dict) -> None:
        return self._transfers_controller._on_address_favorite(entry)

    def _on_connect_selected_address(self) -> None:
        return self._transfers_controller._on_connect_selected_address()

    def _on_save_current_address(self) -> None:
        return self._transfers_controller._on_save_current_address()

    def _on_remove_selected_address(self) -> None:
        return self._transfers_controller._on_remove_selected_address()

    def _on_lan_browse(self) -> None:
        return self._transfers_controller._on_lan_browse()

    def _on_lan_chosen(self, svc: dict) -> None:
        return self._transfers_controller._on_lan_chosen(svc)

    def _on_file_received_ui(self, path) -> None:
        return self._transfers_controller._on_file_received_ui(path)

    def _on_send_cad(self) -> None:
        return self._session_controller._on_send_cad()

    def _on_toggle_mic(self, checked: bool) -> None:
        return self._session_controller._on_toggle_mic(checked)

    def _on_toggle_recording(self, checked: bool) -> None:
        return self._session_controller._on_toggle_recording(checked)

    def _on_stats(self, snapshot: StatsSnapshot) -> None:
        return self._session_controller._on_stats(snapshot)

    def _update_quality_dot(self, snapshot: StatsSnapshot) -> None:
        return self._session_controller._update_quality_dot(snapshot)

    def _on_toggle_share_my_screen(self, value: bool) -> None:
        return self._session_controller._on_toggle_share_my_screen(value)

    def _on_toggle_share_opus_mic(self, value: bool) -> None:
        return self._session_controller._on_toggle_share_opus_mic(value)

    def _on_annotation_segment(self, action: str, x: int, y: int) -> None:
        return self._session_controller._on_annotation_segment(action, x, y)

    def _on_toggle_pen(self, checked: bool) -> None:
        return self._session_controller._on_toggle_pen(checked)

    def _on_pen_clear(self) -> None:
        return self._session_controller._on_pen_clear()

    def _on_connect_via_server(self) -> None:
        return self._session_controller._on_connect_via_server()

    def _on_offer_received_from_server(self, offer_sdp: str) -> None:
        return self._session_controller._on_offer_received_from_server(offer_sdp)

    def _answer_and_push(self, offer_sdp: str) -> None:
        return self._session_controller._answer_and_push(offer_sdp)

    def _on_answer_pushed(self) -> None:
        return self._session_controller._on_answer_pushed()

    def _on_signaling_failed(self, message: str) -> None:
        return self._session_controller._on_signaling_failed(message)

    def _on_create_answer(self) -> None:
        return self._session_controller._on_create_answer()

    def _require_viewer(self) -> WebRTCDesktopViewer:
        """Return the live viewer, or say it is not connected yet."""
        return self._session_controller._require_viewer()

    def _produce_answer(self, offer: str) -> None:
        return self._session_controller._produce_answer(offer)

    def _on_stop(self) -> None:
        return self._session_controller._on_stop()

    def _ensure_screen_window(self) -> RemoteScreenWindow:
        return self._session_controller._ensure_screen_window()

    def _close_screen_window(self) -> None:
        return self._session_controller._close_screen_window()

    def _on_screen_window_closed(self) -> None:
        return self._session_controller._on_screen_window_closed()

    def _on_session_ended(self, role: str) -> None:
        return self._session_controller._on_session_ended(role)

    def _stop_viewer_if_any(self) -> None:
        return self._session_controller._stop_viewer_if_any()

    def _on_av_frame(self, frame) -> None:
        return self._session_controller._on_av_frame(frame)

    def _frame_arguments(self, frame) -> Optional[tuple]:
        return self._session_controller._frame_arguments(frame)

    def _on_frame_image(self, image: QImage) -> None:
        return self._session_controller._on_frame_image(image)

    def _on_state(self, state: str) -> None:
        return self._session_controller._on_state(state)

    def _on_auth(self, ok: bool) -> None:
        return self._session_controller._on_auth(ok)

    def _maybe_schedule_auto_reconnect(self) -> None:
        return self._session_controller._maybe_schedule_auto_reconnect()

    def _start_stats_polling(self) -> None:
        return self._session_controller._start_stats_polling()

    def _on_viewer_stats_sample(self, snapshot: StatsSnapshot) -> None:
        return self._session_controller._on_viewer_stats_sample(snapshot)

    def _stop_stats_polling(self) -> None:
        return self._session_controller._stop_stats_polling()

    def _send(self, payload: dict) -> None:
        return self._session_controller._send(payload)

    def _show_error(self, error: Exception) -> None:
        return self._session_controller._show_error(error)
