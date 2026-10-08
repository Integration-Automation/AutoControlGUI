"""Connecting, manual SDP exchange, auto-reconnect and shutdown for the WebRTC viewer panel.

One interaction group of ``webrtc_panel._WebRTCViewerPanel``, kept as a mixin so the panel class
still owns every widget and slot under its original name.
"""
from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QMessageBox,
)

from je_auto_control.gui.remote_desktop._webrtc_types import SessionRecorderT, WebRTCDesktopViewerT
from je_auto_control.gui.remote_desktop._helpers import (
    _t,
)
from je_auto_control.gui.remote_desktop.webrtc_workers import (
    ViewerAnswerPushWorker, ViewerSignalingWorker,
    retire_worker,
)
from je_auto_control.gui.task_controller import CancellationToken, task_controller
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop import (
    WebRTCDesktopViewer,
)
from je_auto_control.gui.remote_desktop.webrtc_panel_common import (
    _PanelPart,
    _read_webrtc_config,
)

if TYPE_CHECKING:  # imported lazily at runtime to keep startup cheap
    from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine


def _process_offer(viewer: WebRTCDesktopViewerT, offer_sdp: str, expected_dtls: Optional[str],
                   _token: CancellationToken) -> str:
    """Worker thread: answer the host's offer (up to 12 s; the backend takes no timeout or cancel)."""
    return viewer.process_offer(offer_sdp, expected_dtls_fingerprint=expected_dtls)


class _ViewerConnectionMixin(_PanelPart):
    """Methods of ``_WebRTCViewerPanel``; the module docstring says which group."""

    # State this group owns; the panel's __init__ sets the starting values.
    _viewer: Optional[WebRTCDesktopViewerT]
    _offer_worker: Optional[ViewerSignalingWorker]
    _answer_worker: Optional[ViewerAnswerPushWorker]
    # Owned by the files and media groups; stopped here with the session.
    _sync_engine: Optional[FolderSyncEngine]
    _recorder: Optional[SessionRecorderT]

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
        QTimer.singleShot(0, self, lambda: self._answer_and_push(offer_sdp))

    def _answer_and_push(self, offer_sdp: str) -> None:
        host_id = self._host_id_edit.text().strip()
        expected_dtls = self._known_hosts.dtls_fingerprint_for(host_id) if host_id else None
        self._answer_off_thread(
            offer_sdp, expected_dtls,
            functools.partial(self._push_answer, host_id, expected_dtls, offer_sdp))

    def _answer_off_thread(self, offer_sdp: str, expected_dtls: Optional[str],
                           on_answer: Callable[[str], None]) -> None:
        """Run ``process_offer`` on a worker; ``on_answer(answer)`` only if this viewer is still current."""
        try:
            viewer = self._require_viewer()
        except RuntimeError as error:
            self._show_error(error)
            return

        def deliver(answer: str) -> None:
            if self._viewer is viewer:      # not stopped or replaced while the answer was made
                on_answer(answer)

        def fail(error: Exception) -> None:
            if self._viewer is viewer:      # a viewer stopped meanwhile fails by design
                self._show_error(error)

        task = task_controller().submit(
            functools.partial(_process_offer, viewer, offer_sdp, expected_dtls), owner=self)
        task.result.connect(deliver)
        task.error.connect(fail)

    def _push_answer(self, host_id: str, expected_dtls: Optional[str], offer_sdp: str, answer: str) -> None:
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
        self._answer_worker.pushed.connect(self._on_answer_pushed)
        self._answer_worker.failed.connect(self._on_signaling_failed)
        self._answer_worker.start()

    def _on_answer_pushed(self) -> None:
        self._status_label.setText(_t("rd_webrtc_waiting_auth"))

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
        QTimer.singleShot(0, self, lambda: self._produce_answer(offer))

    def _require_viewer(self) -> WebRTCDesktopViewerT:
        """Return the live viewer, or say it is not connected yet."""
        viewer = self._viewer
        if viewer is None:
            raise RuntimeError(_t("rd_webrtc_not_connected"))
        return viewer

    def _produce_answer(self, offer: str) -> None:
        self._answer_off_thread(offer, None, self._show_manual_answer)

    def _show_manual_answer(self, answer: str) -> None:
        self._answer_view.setPlainText(answer)
        self._status_label.setText(_t("rd_webrtc_answer_ready"))

    def _on_stop(self) -> None:
        self._user_initiated_disconnect = True
        self._auto_reconnect_attempts = 0
        self._reconnect_timer.stop()
        self._stop_viewer_if_any()
        self._frame_display.clear()
        self._close_screen_window()
        self._status_label.setText(_t("rd_webrtc_status_idle"))

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

    def _build_viewer(self, token: str) -> WebRTCDesktopViewerT:
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

    def _stop_viewer_if_any(self) -> None:
        for worker in (self._offer_worker, self._answer_worker):
            retire_worker(worker)
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
            # AnyDesk-style: surface the live screen in its own window
            # so the workspace isn't fighting the control panel for
            # vertical space.
            window = self._ensure_screen_window()
            window.show()
            window.raise_()
            window.activateWindow()
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
        self._reconnect_timer.start(delay_ms)


__all__ = ["_ViewerConnectionMixin"]
