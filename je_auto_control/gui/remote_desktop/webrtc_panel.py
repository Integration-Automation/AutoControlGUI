"""WebRTC sub-tabs for the Remote Desktop tab.

Two sections per panel:
  * Signaling server flow — the AnyDesk-style "type host ID and connect"
    UX, backed by ``signaling_server.py``. Recommended for daily use.
  * Manual SDP exchange — copy/paste fallback when no server is reachable.

An advanced collapsible group below exposes STUN/TURN servers; defaults
to Google's public STUN, which is enough for most LAN/home-network
scenarios. Mobile / strict-NAT users will want to add a TURN server.

The two panel classes own the state, the signal wiring and the handful of slots
other code patches by name here; each interaction group lives in a mixin module:
``webrtc_host_{ui,connection,sessions,media,trust}`` and
``webrtc_viewer_{ui,connection,media,files,address_book}``. Signals, defaults
and the config reader they share are in ``webrtc_panel_common``.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QMessageBox, QWidget,
)

from je_auto_control.gui.remote_desktop._webrtc_types import MultiViewerHostT, SessionRecorderT, WebRTCDesktopViewerT
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._slow_op import StopQueue
from je_auto_control.gui.remote_desktop._helpers import (
    _t,
)
from je_auto_control.gui.remote_desktop.blanking_overlay import BlankingOverlay
from je_auto_control.gui.remote_desktop.remote_screen_window import (
    RemoteScreenWindow,
)
from je_auto_control.gui.remote_desktop.annotation_overlay import (
    HostAnnotationOverlay,
)
from je_auto_control.gui.remote_desktop.tray_icon import install_host_tray
from je_auto_control.gui.remote_desktop.viewer_screen_window import (
    ViewerScreenWindow,
)
from je_auto_control.gui.remote_desktop.webrtc_dialogs import (
    PendingViewerDialog,
)
from je_auto_control.gui.remote_desktop.webrtc_workers import (
    HostPublishLoopWorker, ViewerAnswerPushWorker, ViewerSignalingWorker,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop import (
    default_address_book,
    default_trust_list, is_webrtc_available,
    load_or_create_viewer_id,
)
from je_auto_control.utils.remote_desktop.adaptive_bitrate import (
    AdaptiveBitrateController,
)
from je_auto_control.utils.remote_desktop.session_quality_cache import (
    SessionQualityCache,
)
from je_auto_control.utils.remote_desktop.webrtc_stats import (
    StatsPoller,
)
from je_auto_control.gui.remote_desktop.webrtc_panel_common import (
    _PanelSignals,
)
from je_auto_control.gui.remote_desktop.webrtc_host_ui import _HostUiMixin
from je_auto_control.gui.remote_desktop.webrtc_host_trust import _HostTrustMixin
from je_auto_control.gui.remote_desktop.webrtc_host_media import _HostMediaMixin
from je_auto_control.gui.remote_desktop.webrtc_host_sessions import _HostSessionsMixin
from je_auto_control.gui.remote_desktop.webrtc_host_connection import _HostConnectionMixin
from je_auto_control.gui.remote_desktop.webrtc_viewer_ui import _ViewerUiMixin
from je_auto_control.gui.remote_desktop.webrtc_viewer_files import _ViewerFilesMixin
from je_auto_control.gui.remote_desktop.webrtc_viewer_address_book import _ViewerAddressBookMixin
from je_auto_control.gui.remote_desktop.webrtc_viewer_media import _ViewerMediaMixin
from je_auto_control.gui.remote_desktop.webrtc_viewer_connection import _ViewerConnectionMixin

if TYPE_CHECKING:  # imported lazily at runtime to keep startup cheap
    from je_auto_control.utils.remote_desktop.file_sync import (
        FolderSyncEngine,
    )
    from je_auto_control.utils.remote_desktop.lan_discovery import (
        HostAdvertiser,
    )


class _WebRTCHostPanel(_HostUiMixin, _HostTrustMixin, _HostMediaMixin, _HostSessionsMixin,
                       _HostConnectionMixin):
    """Host: stream this machine's screen and accept viewer input."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._multi_host: Optional[MultiViewerHostT] = None
        self._publish_loop: Optional[HostPublishLoopWorker] = None
        self._manual_session_id: Optional[str] = None
        self._stops = StopQueue(self)
        self._stops.drained.connect(self._on_stops_drained)
        self._stopping_sessions: set = set()
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
        self._lan_advertiser: Optional["HostAdvertiser"] = None
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
        self._signals.stats.connect(self._update_host_quality_dot)
        self._build_ui()
        self._refresh_trusted_list()
        self._update_availability()

    def _update_availability(self) -> None:
        if not is_webrtc_available():
            for widget in (self._generate_btn, self._apply_btn,
                           self._publish_btn):
                widget.setEnabled(False)
            self._status_label.setText(_t("rd_webrtc_unavailable"))

    def prefill(self, token: Optional[str] = None,
                host_id: Optional[str] = None,
                signaling_url: Optional[str] = None) -> None:
        """Hand-off entry point used by the Quick Connect screen.

        Populates the signaling-flow fields so the operator can click
        "Publish & wait for viewer" without retyping a token they
        already shared on the Quick Connect tab.
        """
        if token:
            self._token_edit.setText(token)
        if host_id:
            self._host_id_edit.setText(host_id)
        if signaling_url and hasattr(self, "_server_edit"):
            self._server_edit.setText(signaling_url)

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

    def _on_pending_viewer(self, session_id: str, viewer_id) -> None:
        if self._multi_host is None:
            return
        dialog = PendingViewerDialog(viewer_id if isinstance(viewer_id, str) else None,
                                     parent=self)
        dialog.exec()
        choice = dialog.choice()
        # The host can stop while the dialog is open (Stop, the tray): the
        # answer then raised AttributeError on a host that was gone.
        host = self._multi_host
        if host is None:
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
            # Session may have been torn down between prompt and decision.
            return
        self._signals.session_count.emit(host.session_count())

    def _set_hosting(self, hosting: bool) -> None:
        if self._tray is not None:
            self._tray.set_hosting(hosting)

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


class _WebRTCViewerPanel(_ViewerUiMixin, _ViewerFilesMixin, _ViewerAddressBookMixin, _ViewerMediaMixin,
                         _ViewerConnectionMixin):
    """Viewer: receive screen and send input."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._viewer: Optional[WebRTCDesktopViewerT] = None
        self._offer_worker: Optional[ViewerSignalingWorker] = None
        self._answer_worker: Optional[ViewerAnswerPushWorker] = None
        self._stops = StopQueue(self)
        self._stops.drained.connect(self._on_stops_drained)
        self._address_book = default_address_book()
        from je_auto_control.utils.remote_desktop import default_known_hosts
        self._known_hosts = default_known_hosts()
        try:
            self._viewer_id: Optional[str] = load_or_create_viewer_id()
        except OSError as error:
            autocontrol_logger.warning("viewer_id init: %r", error)
            self._viewer_id = None
        self._recorder: Optional[SessionRecorderT] = None
        self._stats_poller: Optional[StatsPoller] = None
        self._sync_engine: Optional["FolderSyncEngine"] = None
        self._auto_reconnect_attempts = 0
        self._user_initiated_disconnect = False
        # One timer, so Stop can cancel a reconnect that is waiting out its
        # back-off: a singleShot could not be, and reconnected after Stop.
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._on_connect_via_server)
        # AnyDesk-style pop-out: created on auth_ok, hidden on stop.
        # Set by _ensure_screen_window().
        self._screen_window: Optional[RemoteScreenWindow] = None
        self._signals = _PanelSignals()
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

    def prefill(self, host_id: Optional[str] = None,
                token: Optional[str] = None,
                signaling_url: Optional[str] = None) -> None:
        """Hand-off entry point used by the Quick Connect screen.

        Populates the signaling-flow fields without auto-clicking
        Connect so the operator can sanity-check before the session
        starts. Empty strings are ignored so callers can fill only the
        fields they actually know.
        """
        if host_id:
            self._host_id_edit.setText(host_id)
        if token:
            self._token_edit.setText(token)
        if signaling_url:
            self._server_edit.setText(signaling_url)

    def _wire_input_signals(self) -> None:
        # Wire the hidden inline _FrameDisplay too, even though it
        # never gets focus while the popup is open — leaves the slots
        # in place if the panel ever reverts to inline display in the
        # future.
        self._wire_display_input(self._frame_display)

    def _wire_display_input(self, source) -> None:
        """Wire mouse / keyboard / annotation signals from ``source``.

        ``source`` can be a :class:`_FrameDisplay` or a
        :class:`RemoteScreenWindow` — both expose the same Signal
        names with matching shapes.
        """
        source.mouse_moved.connect(
            lambda x, y: self._send({"type": "mouse_move",
                                     "x": int(x), "y": int(y)}))
        source.mouse_pressed.connect(
            lambda x, y, b: self._send({"type": "mouse_press",
                                        "x": int(x), "y": int(y),
                                        "button": b}))
        source.mouse_released.connect(
            lambda x, y, b: self._send({"type": "mouse_release",
                                        "x": int(x), "y": int(y),
                                        "button": b}))
        source.mouse_scrolled.connect(
            lambda x, y, a: self._send({"type": "mouse_scroll",
                                        "x": int(x), "y": int(y),
                                        "amount": int(a)}))
        source.key_pressed.connect(
            lambda k: self._send({"type": "key_press", "keycode": k}))
        source.key_released.connect(
            lambda k: self._send({"type": "key_release", "keycode": k}))
        source.type_text.connect(
            lambda text: self._send({"type": "type_text", "text": text}))
        source.annotation_event.connect(self._on_annotation_segment)

    def _update_availability(self) -> None:
        if not is_webrtc_available():
            for widget in (self._answer_btn, self._connect_btn):
                widget.setEnabled(False)
            self._status_label.setText(_t("rd_webrtc_unavailable"))

    def _ensure_screen_window(self) -> RemoteScreenWindow:
        if self._screen_window is not None:
            return self._screen_window
        host_id = self._host_id_edit.text().strip()
        title = (
            _t("rd_remote_screen_title_with_id").replace("{host_id}", host_id)
            if host_id else _t("rd_remote_screen_title")
        )
        window = RemoteScreenWindow(title, parent=self)
        # Wire the popup's input signals so mouse/keyboard inside the
        # popup feed the WebRTC control channel just like the hidden
        # inline display would.
        self._wire_display_input(window)
        # With the pen already on, a new window drew nothing: every stroke
        # reached the host as real clicks and drags.
        window.set_pen_mode(self._pen_btn.isChecked())
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
        if self._viewer is not None:
            self._on_stop()

    def _on_state(self, state: str) -> None:
        self._status_label.setText(f"{_t('rd_webrtc_state_label')} {state}")
        if state in ("failed", "disconnected"):
            self._maybe_schedule_auto_reconnect()

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


__all__ = ["_PanelSignals", "_WebRTCHostPanel", "_WebRTCViewerPanel"]
