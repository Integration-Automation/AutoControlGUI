"""Typed WebRTC host panel composing layout, feature and lifecycle controllers."""
# pylint: disable=protected-access  # reason: typed controllers share their owning panel state

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtGui import QImage

# pylint: enable=no-name-in-module
# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtWidgets import QGroupBox, QWidget

# pylint: enable=no-name-in-module
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.remote_desktop.annotation_overlay import HostAnnotationOverlay
from je_auto_control.gui.remote_desktop.blanking_overlay import BlankingOverlay
from je_auto_control.gui.remote_desktop.session_owner import PanelSessions
from je_auto_control.gui.remote_desktop.tray_icon import install_host_tray
from je_auto_control.gui.remote_desktop.viewer_screen_window import ViewerScreenWindow
from je_auto_control.gui.remote_desktop.webrtc_common import _PanelSignals, _read_webrtc_config
from je_auto_control.gui.remote_desktop.webrtc_dialogs import PendingViewerDialog
from je_auto_control.gui.remote_desktop.webrtc_host_features import WebRTCHostFeaturesController
from je_auto_control.gui.remote_desktop.webrtc_host_layout import WebRTCHostLayoutController
from je_auto_control.gui.remote_desktop.webrtc_host_session import WebRTCHostSessionController
from je_auto_control.gui.remote_desktop.webrtc_workers import HostPublishLoopWorker
from je_auto_control.utils.remote_desktop import MultiViewerHost, default_trust_list
from je_auto_control.utils.remote_desktop.adaptive_bitrate import AdaptiveBitrateController
from je_auto_control.utils.remote_desktop.registry import registry
from je_auto_control.utils.remote_desktop.session_quality_cache import SessionQualityCache
from je_auto_control.utils.remote_desktop.webrtc_stats import StatsPoller, StatsSnapshot

if TYPE_CHECKING:
    from je_auto_control.utils.remote_desktop.lan_discovery import HostAdvertiser
if TYPE_CHECKING:
    import je_auto_control.gui.remote_desktop.annotation_overlay
    import je_auto_control.gui.remote_desktop.blanking_overlay
    import je_auto_control.gui.remote_desktop.session_owner
    import je_auto_control.gui.remote_desktop.tray_icon
    import je_auto_control.gui.remote_desktop.viewer_screen_window
    import je_auto_control.gui.remote_desktop.webrtc_common
    import je_auto_control.gui.remote_desktop.webrtc_workers
    import je_auto_control.utils.remote_desktop.adaptive_bitrate
    import je_auto_control.utils.remote_desktop.lan_discovery
    import je_auto_control.utils.remote_desktop.session_quality_cache
    import je_auto_control.utils.remote_desktop.trust_list
    import je_auto_control.utils.remote_desktop.webrtc_stats


class _WebRTCHostPanel(TranslatableMixin, QWidget):  # pylint: disable=too-many-instance-attributes  # reason: explicit owned lifecycle/widget state
    """Host: stream this machine's screen and accept viewer input."""

    _sessions: je_auto_control.gui.remote_desktop.session_owner.PanelSessions
    _multi_host: Any | None
    _publish_loop: je_auto_control.gui.remote_desktop.webrtc_workers.HostPublishLoopWorker | None
    _manual_session_id: str | None
    _adaptive_controller: je_auto_control.utils.remote_desktop.adaptive_bitrate.AdaptiveBitrateController | None
    _adaptive_poller: je_auto_control.utils.remote_desktop.webrtc_stats.StatsPoller | None
    _session_pollers: dict[Any, Any]
    _session_cache: je_auto_control.utils.remote_desktop.session_quality_cache.SessionQualityCache
    _trust_list: je_auto_control.utils.remote_desktop.trust_list.TrustList
    _blanking: je_auto_control.gui.remote_desktop.blanking_overlay.BlankingOverlay | None
    _viewer_screen_window: je_auto_control.gui.remote_desktop.viewer_screen_window.ViewerScreenWindow | None
    _lan_advertiser: je_auto_control.utils.remote_desktop.lan_discovery.HostAdvertiser | None
    _annotation_overlay: je_auto_control.gui.remote_desktop.annotation_overlay.HostAnnotationOverlay | None
    _tray: je_auto_control.gui.remote_desktop.tray_icon.HostTrayIcon | None
    _signals: je_auto_control.gui.remote_desktop.webrtc_common._PanelSignals
    _status_label: Any
    _host_quality_dot: Any
    _sessions_label: Any
    _sessions_table: Any
    _disconnect_btn: Any
    _push_file_btn: Any
    _server_edit: Any
    _host_id_edit: Any
    _secret_edit: Any
    _publish_btn: Any
    _fingerprint_label: Any
    _token_edit: Any
    _monitor_combo: Any
    _fps_spin: Any
    _region_edit: Any
    _cursor_check: Any
    _blank_check: Any
    _readonly_check: Any
    _adaptive_check: Any
    _mic_recv_check: Any
    _host_voice_check: Any
    _max_bitrate_spin: Any
    _ip_whitelist_edit: Any
    _accept_viewer_video_check: Any
    _accept_opus_audio_check: Any
    _generate_btn: Any
    _offer_view: Any
    _answer_input: Any
    _apply_btn: Any
    _stop_btn: Any

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._layout_controller = WebRTCHostLayoutController(self)
        self._features_controller = WebRTCHostFeaturesController(self)
        self._session_controller = WebRTCHostSessionController(self)
        self._tr_init()
        self._sessions = PanelSessions(self, registry)
        self._sessions.ended.connect(self._on_session_ended)
        self._multi_host: Optional[MultiViewerHost] = None
        self._publish_loop: Optional[HostPublishLoopWorker] = None
        self._manual_session_id: Optional[str] = None
        self._adaptive_controller: Optional[AdaptiveBitrateController] = None
        self._adaptive_poller: Optional[StatsPoller] = None
        self._session_pollers: dict = {}
        self._session_cache = SessionQualityCache()
        self._trust_list = default_trust_list()
        self._blanking: Optional[BlankingOverlay] = None
        self._viewer_screen_window: Optional[ViewerScreenWindow] = None
        self._lan_advertiser: Optional["HostAdvertiser"] = None
        self._annotation_overlay: Optional[HostAnnotationOverlay] = None
        self._tray = install_host_tray(
            on_open=self._on_tray_open, on_stop=self._on_tray_stop, on_quit=self._on_tray_quit, parent=self
        )
        self._signals = _PanelSignals(self)
        self._signals.state.connect(self._on_state)
        self._signals.auth.connect(self._on_auth)
        self._signals.pending_viewer.connect(self._on_pending_viewer)
        self._signals.session_count.connect(self._on_session_count)
        self._signals.viewer_video_frame.connect(self._on_viewer_video_image)
        self._signals.annotation.connect(self._on_annotation_event)
        self._signals.stats.connect(self._update_host_quality_dot)
        self._build_ui()
        self._refresh_trusted_list()
        self._update_availability()
        self._sessions.add_cleanup(self._session_controller.dispose_background)

    def _on_pending_viewer(self, session_id: str, viewer_id) -> None:
        original_host = self._multi_host
        if original_host is None:
            return
        dialog = PendingViewerDialog(viewer_id if isinstance(viewer_id, str) else None, parent=self)
        dialog.exec()
        choice = dialog.choice()
        host = self._multi_host
        if host is not original_host:
            return
        try:
            if choice == PendingViewerDialog.AcceptAndTrust:
                host.trust_pending_viewer(session_id)
                self._refresh_trusted_list()
            elif choice == PendingViewerDialog.AcceptOnce:
                host.approve_pending_viewer(session_id)
            else:
                host.reject_pending_viewer(session_id)
        except KeyError:
            return
        self._signals.session_count.emit(host.session_count())

    def _build_multi_host(self, token: str) -> MultiViewerHost:
        self._sessions.reserve("webrtc", "host")
        whitelist_text = self._ip_whitelist_edit.toPlainText().strip()
        whitelist = [
            line.strip() for line in whitelist_text.splitlines() if line.strip() and (not line.strip().startswith("#"))
        ]
        host = MultiViewerHost(
            token=token,
            config=_read_webrtc_config(self),
            trust_list=self._trust_list,
            read_only=self._readonly_check.isChecked(),
            ip_whitelist=whitelist,
            on_annotation=self._sessions.callback("host", self._signals.annotation.emit),
            on_session_state=self._sessions.callback("host", lambda _sid, state: self._signals.state.emit(state)),
            on_session_authenticated=self._sessions.callback("host", self._on_session_authed),
            on_pending_viewer=self._sessions.callback("host", self._signals.pending_viewer.emit),
        )
        self._sessions.attach(host, "host")
        return host

    def _build_ui(self) -> None:
        return self._layout_controller._build_ui()

    def _on_hw_codec_changed(self) -> None:
        return self._layout_controller._on_hw_codec_changed()

    def _build_signaling_group(self) -> QGroupBox:
        return self._layout_controller._build_signaling_group()

    def _on_copy_fingerprint(self, fp: str) -> None:
        return self._layout_controller._on_copy_fingerprint(fp)

    def _build_config_group(self) -> QGroupBox:
        return self._layout_controller._build_config_group()

    def _populate_monitor_combo(self) -> None:
        return self._layout_controller._populate_monitor_combo()

    def _on_pick_region(self) -> None:
        return self._layout_controller._on_pick_region()

    def _on_monitor_changed(self, _i: int) -> None:
        return self._layout_controller._on_monitor_changed(_i)

    def _build_manual_group(self) -> QGroupBox:
        return self._layout_controller._build_manual_group()

    def _update_availability(self) -> None:
        return self._layout_controller._update_availability()

    def prefill(
        self, token: Optional[str] = None, host_id: Optional[str] = None, signaling_url: Optional[str] = None
    ) -> None:
        """Hand-off entry point used by the Quick Connect screen.

        Populates the signaling-flow fields so the operator can click
        "Publish & wait for viewer" without retyping a token they
        already shared on the Quick Connect tab.
        """
        return self._layout_controller.prefill(token, host_id, signaling_url)

    def _on_regen_id(self) -> None:
        return self._layout_controller._on_regen_id()

    def _validate_required_fields(self, *, needs_server: bool) -> bool:
        return self._layout_controller._validate_required_fields(needs_server=needs_server)

    def retranslate(self) -> None:
        """Refresh the owning panel translations."""
        return self._layout_controller.retranslate()

    def _on_view_audit(self) -> None:
        return self._features_controller._on_view_audit()

    def _on_push_file(self) -> None:
        return self._features_controller._on_push_file()

    def _on_export_trust(self) -> None:
        return self._features_controller._on_export_trust()

    def _on_import_trust(self) -> None:
        return self._features_controller._on_import_trust()

    def _refresh_trusted_list(self) -> None:
        return self._features_controller._refresh_trusted_list()

    def _on_toggle_accept_viewer_video(self, value: bool) -> None:
        return self._features_controller._on_toggle_accept_viewer_video(value)

    def _on_toggle_accept_opus_audio(self, value: bool) -> None:
        return self._features_controller._on_toggle_accept_opus_audio(value)

    def _on_toggle_mic_receive(self, value: bool) -> None:
        return self._features_controller._on_toggle_mic_receive(value)

    def _on_toggle_adaptive(self, value: bool) -> None:
        return self._features_controller._on_toggle_adaptive(value)

    def _on_toggle_readonly(self, value: bool) -> None:
        return self._features_controller._on_toggle_readonly(value)

    def _on_toggle_blanking(self, checked: bool) -> None:
        return self._features_controller._on_toggle_blanking(checked)

    @staticmethod
    def _format_quality_tooltip(snapshot: Optional[StatsSnapshot]) -> str:
        return WebRTCHostFeaturesController._format_quality_tooltip(snapshot)

    @staticmethod
    def _quality_color(snapshot: StatsSnapshot) -> str:
        return WebRTCHostFeaturesController._quality_color(snapshot)

    def _maybe_start_adaptive(self) -> None:
        return self._features_controller._maybe_start_adaptive()

    def _on_host_stats(self, snapshot: StatsSnapshot) -> None:
        return self._features_controller._on_host_stats(snapshot)

    def _update_host_quality_dot(self, snapshot: StatsSnapshot) -> None:
        return self._features_controller._update_host_quality_dot(snapshot)

    def _reset_host_quality_dot(self) -> None:
        return self._features_controller._reset_host_quality_dot()

    def _stop_adaptive(self) -> None:
        return self._features_controller._stop_adaptive()

    def _on_remove_trust(self, viewer_id: str) -> None:
        return self._features_controller._on_remove_trust(viewer_id)

    def _on_remove_trust_button(self) -> None:
        return self._features_controller._on_remove_trust_button()

    def _on_clear_trust(self) -> None:
        return self._features_controller._on_clear_trust()

    def _on_annotation_event(self, data) -> None:
        return self._features_controller._on_annotation_event(data)

    def _on_session_authed(self, session_id: str) -> None:
        return self._features_controller._on_session_authed(session_id)

    def _viewer_video_arguments(self, frame) -> Optional[tuple]:
        return self._features_controller._viewer_video_arguments(frame)

    def _on_viewer_video_av_frame(self, frame) -> None:
        return self._features_controller._on_viewer_video_av_frame(frame)

    def _on_viewer_video_image(self, image: QImage) -> None:
        return self._features_controller._on_viewer_video_image(image)

    def _on_viewer_screen_closed(self) -> None:
        return self._features_controller._on_viewer_screen_closed()

    def _on_tray_open(self) -> None:
        return self._session_controller._on_tray_open()

    def _on_tray_stop(self) -> None:
        return self._session_controller._on_tray_stop()

    def _on_tray_quit(self) -> None:
        return self._session_controller._on_tray_quit()

    def _on_publish_via_server(self) -> None:
        return self._session_controller._on_publish_via_server()

    def _start_lan_advertise(self) -> None:
        return self._session_controller._start_lan_advertise()

    def _stop_lan_advertise(self) -> None:
        return self._session_controller._stop_lan_advertise()

    def _on_loop_offer_published(self, session_id: str) -> None:
        return self._session_controller._on_loop_offer_published(session_id)

    def _on_loop_session_connected(self, session_id: str) -> None:
        return self._session_controller._on_loop_session_connected(session_id)

    def _on_signaling_failed(self, message: str) -> None:
        return self._session_controller._on_signaling_failed(message)

    def _on_generate_offer(self) -> None:
        return self._session_controller._on_generate_offer()

    def _require_multi_host(self) -> MultiViewerHost:
        """Return the running host, or say the session is not up yet."""
        return self._session_controller._require_multi_host()

    def _produce_offer(self) -> None:
        return self._session_controller._produce_offer()

    def _on_apply_answer(self) -> None:
        return self._session_controller._on_apply_answer()

    def _on_stop(self) -> None:
        return self._session_controller._on_stop()

    def _on_session_count(self, count: int) -> None:
        return self._session_controller._on_session_count(count)

    def _sync_session_pollers(self) -> None:
        """Spawn StatsPoller for new sessions; stop pollers for gone ones."""
        return self._session_controller._sync_session_pollers()

    def _make_session_stats_handler(self, session_id: str):
        """Closure capturing session_id for the per-session poller."""
        return self._session_controller._make_session_stats_handler(session_id)

    def _refresh_sessions_table(self) -> None:
        return self._session_controller._refresh_sessions_table()

    def _on_sessions_context_menu(self, position) -> None:
        return self._session_controller._on_sessions_context_menu(position)

    def _dispatch_session_menu(self, chosen, actions: dict, sid: str, viewer_id: str) -> None:
        """Run the action chosen from the sessions context menu."""
        return self._session_controller._dispatch_session_menu(chosen, actions, sid, viewer_id)

    def _trust_session_viewer(self, sid: str) -> None:
        return self._session_controller._trust_session_viewer(sid)

    @staticmethod
    def _copy_session_id_to_clipboard(sid: str) -> None:
        return WebRTCHostSessionController._copy_session_id_to_clipboard(sid)

    def _on_disconnect_selected(self) -> None:
        return self._session_controller._on_disconnect_selected()

    def _on_session_ended(self, role: str) -> None:
        return self._session_controller._on_session_ended(role)

    def _stop_host_if_any(self) -> None:
        return self._session_controller._stop_host_if_any()

    def _set_hosting(self, hosting: bool) -> None:
        return self._session_controller._set_hosting(hosting)

    def _on_state(self, state: str) -> None:
        return self._session_controller._on_state(state)

    def _on_auth(self, ok: bool) -> None:
        return self._session_controller._on_auth(ok)

    def _show_error(self, error: Exception) -> None:
        return self._session_controller._show_error(error)
