"""WebRTC viewer session controller; session and widget ownership stays on the panel."""
# pylint: disable=protected-access  # reason: typed controllers share their owning panel state

from __future__ import annotations

import logging
from functools import partial
from typing import TYPE_CHECKING, Callable, Optional

# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtCore import QTimer

# pylint: enable=no-name-in-module
# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtGui import QImage

# pylint: enable=no-name-in-module
# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtWidgets import (
    QFileDialog,
    QMessageBox,
)

# pylint: enable=no-name-in-module
from je_auto_control.gui.remote_desktop._helpers import _t
from je_auto_control.gui.remote_desktop.remote_screen_window import RemoteScreenWindow
from je_auto_control.gui.remote_desktop.webrtc_common import (
    _QUALITY_DOT_STYLE,
    _av_frame_to_qimage,
    quality_indicator,
    stop_folder_sync,
)
from je_auto_control.gui.remote_desktop.webrtc_workers import (
    ViewerAnswerPushWorker,
    ViewerSignalingWorker,
    retire_worker,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.gui._panel_tasks import start_native
from je_auto_control.utils.remote_desktop import SessionRecorder, WebRTCDesktopViewer
from je_auto_control.utils.remote_desktop.webrtc_inspector import default_webrtc_inspector
from je_auto_control.utils.remote_desktop.webrtc_stats import StatsPoller, StatsSnapshot
from je_auto_control.utils.remote_desktop.webrtc_transport import fps_for_preset
from je_auto_control.gui.task_controller import CancellationToken, TaskController, TaskError, TaskHandle, TaskResult
from je_auto_control.gui.remote_desktop._task_work import (
    AnswerRequest, SignalingTarget, ViewerAnswer, create_answer, run_in_session,
)
from je_auto_control.utils.remote_desktop.cleanup_jobs import _submit_cleanup

def _finish_recording(recorder: NativeRecorder, token: CancellationToken) -> object:
    token.checkpoint()
    try:
        recorder.stop()
    except BaseException:
        _submit_cleanup((recorder.stop,))
        raise
    return recorder


if TYPE_CHECKING:
    from je_auto_control.utils.remote_desktop.session_recorder import SessionRecorder as NativeRecorder
    from je_auto_control.gui.remote_desktop.webrtc_viewer_panel import _WebRTCViewerPanel


class WebRTCViewerSessionController:  # pylint: disable=too-few-public-methods  # reason: internal signal/slot controller
    """Viewer session interactions on a typed owned panel."""

    def __init__(self, panel: _WebRTCViewerPanel) -> None:
        self._panel = panel
        self._tasks = TaskController(timeout_s=60)
        self._record_tasks = TaskController(timeout_s=30)
        self._task: Optional[TaskHandle] = None
        self._reconnect_callback: Optional[Callable[[], None]] = None

    def reconnect_if_current(self) -> None:
        """Consume the retry belonging to the original session, including queued timer delivery."""
        callback, self._reconnect_callback = self._reconnect_callback, None
        if callback is not None:
            callback()

    def _cancel_reconnect(self) -> None:
        self._reconnect_callback = None
        self._panel._reconnect_timer.stop()

    def _on_send_cad(self) -> None:
        if self._panel._viewer is None or not self._panel._viewer.authenticated:
            QMessageBox.information(self._panel, "WebRTC", _t("rd_webrtc_cad_not_connected"))
            return
        try:
            self._panel._viewer.request_send_sas()
        except (RuntimeError, OSError) as error:
            QMessageBox.warning(self._panel, "WebRTC", str(error))

    def _on_toggle_mic(self, checked: bool) -> None:
        if self._panel._viewer is None or not self._panel._viewer.authenticated:
            self._panel._mic_btn.setChecked(False)
            QMessageBox.information(self._panel, "WebRTC", _t("rd_webrtc_cad_not_connected"))
            return
        try:
            if checked:
                self._panel._viewer.enable_mic_send()
            else:
                self._panel._viewer.disable_mic_send()
        except (RuntimeError, OSError) as error:
            self._panel._mic_btn.setChecked(False)
            QMessageBox.warning(self._panel, "WebRTC", str(error))

    def _on_toggle_recording(self, checked: bool) -> None:
        if checked and self._panel._recorder is not None:
            return
        if checked:
            if SessionRecorder is None:
                QMessageBox.warning(self._panel, "WebRTC", _t("rd_webrtc_unavailable"))
                self._panel._record_btn.setChecked(False)
                return
            path, _filter = QFileDialog.getSaveFileName(
                self._panel,
                _t("rd_webrtc_recording_save_as"),
                "",
                "MP4 (*.mp4);;WebM (*.webm);;Matroska (*.mkv);;All (*)",
            )
            if not path:
                self._panel._record_btn.setChecked(False)
                return
            # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
            from je_auto_control.utils.remote_desktop.session_recorder import (
                preset_for_path,
            )
            # pylint: enable=import-outside-toplevel

            preset = preset_for_path(path)
            self._panel._recorder = SessionRecorder(
                path,
                fps=int(
                    self._panel._bandwidth_combo.currentData()
                    and fps_for_preset(self._panel._bandwidth_combo.currentData())
                    or 24
                ),
                codec=preset.get("codec", "libx264"),
                pixel_format=preset.get("pixel_format", "yuv420p"),
            )
            self._panel._record_btn.setText(_t("rd_webrtc_stop_recording"))
        else:
            recorder = self._panel._recorder
            if recorder is not None:
                job = self._record_tasks.submit(partial(_finish_recording, recorder), owner=self._panel)
                job.completed.connect(self._record_cleanup_ready)
                job.failed.connect(self._record_cleanup_failed)
            self._panel._record_btn.setText(_t("rd_webrtc_start_recording"))

    def _record_cleanup_ready(self, result: TaskResult) -> None:
        recorder = result.value
        current = self._panel._recorder
        if current is not None and current is recorder:
            key = 'rd_webrtc_recording_saved' if current.has_output else 'rd_webrtc_recording_empty'
            self._panel._recorder = None
            QMessageBox.information(self._panel, 'WebRTC', _t(key).format(path=str(current.output_path)))

    def _record_cleanup_failed(self, error: TaskError) -> None:
        self._panel._record_btn.setChecked(True)
        self._task_failed(error)

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
        self._panel._stats_label.setText(" | ".join(parts))
        self._panel._update_quality_dot(snapshot)
        if hasattr(self._panel, "_rtt_spark"):
            self._panel._rtt_spark.push(snapshot.rtt_ms)
            self._panel._bitrate_spark.push(snapshot.bitrate_kbps)

    def _update_quality_dot(self, snapshot: StatsSnapshot) -> None:
        color, tip_key = quality_indicator(snapshot)
        self._panel._quality_dot.setStyleSheet(f"background-color: {color}; border-radius: 7px;")
        self._panel._quality_dot.setToolTip(_t(tip_key))

    def _on_toggle_share_my_screen(self, value: bool) -> None:
        if self._panel._viewer is None:
            return
        try:
            self._panel._viewer.toggle_share_screen(value)
        except (RuntimeError, OSError) as error:
            QMessageBox.warning(self._panel, "WebRTC", str(error))

    def _on_toggle_share_opus_mic(self, value: bool) -> None:
        if self._panel._viewer is None:
            return
        try:
            self._panel._viewer.toggle_opus_mic(value)
        except (RuntimeError, OSError) as error:
            QMessageBox.warning(self._panel, "WebRTC", str(error))

    def _on_annotation_segment(self, action: str, x: int, y: int) -> None:
        if self._panel._viewer is None or not self._panel._viewer.authenticated:
            return
        try:
            self._panel._viewer._send(
                {"type": "annotate", "action": action, "x": int(x), "y": int(y), "color": "#ff0000", "width": 3}
            )
        except (RuntimeError, OSError):
            pass

    def _on_toggle_pen(self, checked: bool) -> None:
        self._panel._frame_display.set_pen_mode(checked)
        if self._panel._screen_window is not None:
            self._panel._screen_window.set_pen_mode(checked)
        self._panel._pen_btn.setText(_t("rd_webrtc_pen_on" if checked else "rd_webrtc_pen_off"))

    def _on_pen_clear(self) -> None:
        if self._panel._viewer is None or not self._panel._viewer.authenticated:
            return
        try:
            self._panel._viewer._send({"type": "annotate", "action": "clear", "x": 0, "y": 0})
        except (RuntimeError, OSError):
            pass

    def _on_connect_via_server(self) -> None:
        if not self._panel._validate_required_fields(needs_server=True):
            return
        self._panel._user_initiated_disconnect = False
        self._panel._stop_viewer_if_any()
        self._panel._sessions.reserve("webrtc", "viewer")
        self._panel._status_label.setText(_t("rd_webrtc_polling_offer"))
        self._panel._offer_worker = ViewerSignalingWorker(
            server_url=self._panel._server_edit.text().strip(),
            host_id=self._panel._host_id_edit.text().strip(),
            secret=self._panel._secret_edit.text() or None,
        )
        self._panel._offer_worker.offer_ready.connect(
            self._panel._sessions.callback("viewer", self._panel._on_offer_received_from_server)
        )
        self._panel._offer_worker.failed.connect(
            self._panel._sessions.callback("viewer", self._panel._on_signaling_failed)
        )
        self._panel._offer_worker.start()

    def _on_offer_received_from_server(self, offer_sdp: str) -> None:
        try:
            self._panel._viewer = self._panel._build_viewer(self._panel._token_edit.text().strip())
        except (ValueError, RuntimeError, OSError) as error:
            self._panel._show_error(error)
            return
        self._panel._status_label.setText(_t("rd_webrtc_creating_answer"))
        QTimer.singleShot(
            0, self._panel, self._panel._sessions.callback("viewer", lambda: self._panel._answer_and_push(offer_sdp))
        )

    def _answer_and_push(self, offer_sdp: str) -> None:
        self._submit_answer(offer_sdp, push=True)

    def _submit_answer(self, offer: str, *, push: bool) -> None:
        try:
            viewer = self._require_viewer()
            identifier = self._panel._sessions.id('viewer')
            if identifier is None:
                raise RuntimeError('WebRTC viewer has no owned session')
            directory = self._panel._sessions.directory
            session = directory.get_session(identifier, owner=self._panel._sessions.owner)
            cleanup = partial(directory.disconnect_session, identifier, owner=session.owner)
            current = partial(directory.session_is_current, identifier, session.generation, owner=session.owner)
            target = SignalingTarget(self._panel._server_edit.text().strip(),
                                     self._panel._host_id_edit.text().strip(),
                                     self._panel._secret_edit.text() or None) if push else None
            request = AnswerRequest(viewer, identifier, offer, cleanup, target,
                                    self._panel._known_hosts if push else None, current)
        except (ValueError, RuntimeError, OSError) as error:
            self._panel._show_error(error)
            return
        work = partial(run_in_session, directory, session, partial(create_answer, request))
        self._task = self._tasks.submit(work, owner=self._panel)
        self._task.completed.connect(self._answer_ready)
        self._task.failed.connect(self._task_failed)

    def _task_failed(self, error: TaskError) -> None:
        self._panel._show_error(RuntimeError(error.message))

    def _answer_ready(self, result: TaskResult) -> None:
        answer = result.value
        if not isinstance(answer, ViewerAnswer):
            return
        request = answer.request
        if (self._panel._viewer is not request.viewer
                or self._panel._sessions.id('viewer') != request.owner_session_id):
            _submit_cleanup((request.cleanup,))
            return
        self._panel._answer_view.setPlainText(answer.sdp)
        target = request.target
        if target is None:
            self._panel._status_label.setText(_t('rd_webrtc_answer_ready'))
            return
        self._panel._status_label.setText(_t('rd_webrtc_pushing_answer'))
        self._panel._answer_worker = ViewerAnswerPushWorker(
            server_url=target.server, host_id=target.host_id, secret=target.secret, answer_sdp=answer.sdp)
        self._panel._answer_worker.pushed.connect(
            self._panel._sessions.callback('viewer', self._panel._on_answer_pushed))
        self._panel._answer_worker.failed.connect(
            self._panel._sessions.callback('viewer', self._panel._on_signaling_failed))
        self._panel._answer_worker.start()

    def _on_answer_pushed(self) -> None:
        self._panel._status_label.setText(_t("rd_webrtc_waiting_auth"))

    def _on_signaling_failed(self, message: str) -> None:
        QMessageBox.warning(self._panel, "WebRTC", message)
        self._panel._status_label.setText(_t("rd_webrtc_status_idle"))

    def _on_create_answer(self) -> None:
        if not self._panel._validate_required_fields(needs_server=False):
            return
        offer = self._panel._offer_input.toPlainText().strip()
        if not offer:
            QMessageBox.warning(self._panel, "WebRTC", _t("rd_webrtc_no_offer"))
            return
        try:
            self._panel._stop_viewer_if_any()
            self._panel._viewer = self._panel._build_viewer(self._panel._token_edit.text().strip())
        except (ValueError, RuntimeError, OSError) as error:
            self._panel._show_error(error)
            return
        self._panel._status_label.setText(_t("rd_webrtc_creating_answer"))
        QTimer.singleShot(
            0, self._panel, self._panel._sessions.callback("viewer", lambda: self._panel._produce_answer(offer))
        )

    def _require_viewer(self) -> WebRTCDesktopViewer:
        """Return the live viewer, or say it is not connected yet."""
        viewer = self._panel._viewer
        if viewer is None:
            raise RuntimeError(_t("rd_webrtc_not_connected"))
        return viewer

    def _produce_answer(self, offer: str) -> None:
        self._submit_answer(offer, push=False)

    def _on_stop(self) -> None:
        self._panel._user_initiated_disconnect = True
        self._panel._auto_reconnect_attempts = 0
        self._panel._reconnect_timer.stop()
        self._panel._stop_viewer_if_any()
        self._panel._frame_display.clear()
        self._panel._close_screen_window()
        self._panel._status_label.setText(_t("rd_webrtc_status_idle"))

    def _ensure_screen_window(self) -> RemoteScreenWindow:
        if self._panel._screen_window is not None:
            return self._panel._screen_window
        host_id = self._panel._host_id_edit.text().strip()
        title = (
            _t("rd_remote_screen_title_with_id").replace("{host_id}", host_id)
            if host_id
            else _t("rd_remote_screen_title")
        )
        window = RemoteScreenWindow(title, parent=self._panel)
        self._panel._wire_display_input(window)
        window.set_pen_mode(self._panel._pen_btn.isChecked())
        window.closed.connect(self._panel._on_screen_window_closed)
        self._panel._screen_window = window
        return window

    def _close_screen_window(self) -> None:
        window = self._panel._screen_window
        self._panel._screen_window = None
        if window is not None:
            try:
                window.closed.disconnect(self._panel._on_screen_window_closed)
            except (RuntimeError, TypeError):
                pass
            window.hide()
            window.deleteLater()

    def _on_screen_window_closed(self) -> None:
        if self._panel._viewer is not None:
            self._panel._on_stop()

    def _on_session_ended(self, role: str) -> None:
        if role == "viewer":
            self._panel._stop_viewer_if_any()
            self._panel._close_screen_window()

    def dispose_background(self) -> None:
        """Stop background objects without touching any disposed Qt widget."""
        self._reconnect_callback = None
        # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
        from je_auto_control.gui.remote_desktop.webrtc_common import (
            dispose_background,
        )
        # pylint: enable=import-outside-toplevel

        self._tasks.cancel_owner(self._panel)
        self._record_tasks.cancel_owner(self._panel)
        for worker in (self._panel._offer_worker, self._panel._answer_worker):
            retire_worker(worker)
        callbacks: list[Callable[[], None]] = []
        callbacks.extend(
            resource.stop
            for resource in (self._panel._stats_poller, self._panel._recorder, self._panel._sync_engine)
            if resource is not None
        )
        dispose_background(callbacks)

    def _stop_viewer_if_any(self) -> None:
        self._tasks.cancel_owner(self._panel)
        self._record_tasks.cancel_owner(self._panel)
        self._cancel_reconnect()
        owned = self._panel._sessions.id("viewer") is not None
        if owned:
            self._panel._sessions.close("viewer")
        for worker in (self._panel._offer_worker, self._panel._answer_worker):
            retire_worker(worker)
        self._panel._offer_worker = None
        self._panel._answer_worker = None
        stop_folder_sync(self._panel)
        if hasattr(self._panel, "_sync_btn"):
            self._panel._sync_btn.setChecked(False)
            self._panel._sync_btn.setText(_t("rd_webrtc_sync_start"))
        self._panel._stop_stats_polling()
        if self._panel._recorder is not None:
            _submit_cleanup((self._panel._recorder.stop,))
            self._panel._recorder = None
            self._panel._record_btn.setChecked(False)
            self._panel._record_btn.setText(_t("rd_webrtc_start_recording"))
        if self._panel._viewer is None:
            return
        if not owned:
            _submit_cleanup((self._panel._viewer.stop,))
        self._panel._viewer = None

    def _on_av_frame(self, frame) -> None:
        arguments = self._panel._frame_arguments(frame)
        if arguments is not None:
            self._panel._signals.frame.emit(*arguments)

    def _frame_arguments(self, frame) -> Optional[tuple]:
        if self._panel._recorder is not None:
            try:
                self._panel._recorder.write_frame(frame)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("recorder write: %r", error)
        image = _av_frame_to_qimage(frame)
        return None if image is None else (image,)

    def _on_frame_image(self, image: QImage) -> None:
        if self._panel._screen_window is not None:
            self._panel._screen_window.set_image(image)
        else:
            self._panel._frame_display.set_image(image)

    def _on_state(self, state: str) -> None:
        self._panel._status_label.setText(f"{_t('rd_webrtc_state_label')} {state}")
        if state in ("failed", "disconnected"):
            self._panel._maybe_schedule_auto_reconnect()

    def _on_auth(self, ok: bool) -> None:
        key = "rd_webrtc_auth_ok" if ok else "rd_webrtc_auth_fail"
        self._panel._status_label.setText(_t(key))
        if ok:
            self._cancel_reconnect()
            self._panel._auto_reconnect_attempts = 0
            host_id = self._panel._host_id_edit.text().strip()
            server_url = self._panel._server_edit.text().strip()
            if host_id and server_url:
                try:
                    self._panel._address_book.upsert(host_id=host_id, server_url=server_url)
                    self._panel._refresh_address_book()
                except (ValueError, OSError) as error:
                    autocontrol_logger.debug("address book upsert: %r", error)
            if host_id:
                try:
                    self._panel._known_hosts.touch(host_id)
                except OSError as error:
                    autocontrol_logger.debug("known_hosts touch: %r", error)
            self._panel._start_stats_polling()
            window = self._panel._ensure_screen_window()
            window.show()
            window.raise_()
            window.activateWindow()
        else:
            self._panel._stop_stats_polling()

    def _maybe_schedule_auto_reconnect(self) -> None:
        if self._panel._sessions.id('viewer') is None:
            return
        if not self._panel._auto_reconnect_check.isChecked() or self._panel._user_initiated_disconnect:
            return
        max_attempts = int(self._panel._reconnect_max_spin.value())
        base_delay_s = int(self._panel._reconnect_delay_spin.value())
        if self._panel._auto_reconnect_attempts >= max_attempts:
            self._panel._status_label.setText(_t("rd_webrtc_reconnect_giveup"))
            return
        if (
            not self._panel._server_edit.text().strip()
            or not self._panel._host_id_edit.text().strip()
            or (not self._panel._token_edit.text().strip())
        ):
            return
        self._panel._auto_reconnect_attempts += 1
        delay_ms = min(60000, 1000 * base_delay_s * 2 ** (self._panel._auto_reconnect_attempts - 1))
        self._panel._status_label.setText(
            _t("rd_webrtc_reconnecting").format(n=self._panel._auto_reconnect_attempts, max=max_attempts)
        )
        self._reconnect_callback = self._panel._sessions.callback('viewer', self._panel._on_connect_via_server)
        self._panel._reconnect_timer.start(delay_ms)

    def _start_stats_polling(self) -> None:
        if self._panel._viewer is None or self._panel._viewer._pc is None:
            return
        self._panel._stop_stats_polling()
        self._panel._stats_poller = StatsPoller(
            self._panel._viewer._pc, self._panel._sessions.callback("viewer", self._panel._on_viewer_stats_sample)
        )
        start_native(self._panel._stats_poller.start, self._panel)

    def _on_viewer_stats_sample(self, snapshot: StatsSnapshot) -> None:
        default_webrtc_inspector().record(snapshot)
        self._panel._signals.stats.emit(snapshot)

    def _stop_stats_polling(self) -> None:
        if self._panel._stats_poller is not None:
            self._panel._stats_poller.stop()
            self._panel._stats_poller = None
        self._panel._stats_label.setText(_t("rd_webrtc_stats_idle"))
        if hasattr(self._panel, "_quality_dot"):
            self._panel._quality_dot.setStyleSheet(_QUALITY_DOT_STYLE)
            self._panel._quality_dot.setToolTip(_t("rd_webrtc_quality_unknown"))
        if hasattr(self._panel, "_rtt_spark"):
            self._panel._rtt_spark.clear()
            self._panel._bitrate_spark.clear()

    def _send(self, payload: dict) -> None:
        if self._panel._viewer is None or not self._panel._viewer.authenticated:
            return
        try:
            self._panel._viewer.send_input(payload)
        except (RuntimeError, OSError) as error:
            logging.getLogger(__name__).debug("send_input: %r", error)

    def _show_error(self, error: Exception) -> None:
        autocontrol_logger.warning("webrtc viewer panel error: %r", error)
        QMessageBox.warning(self._panel, "WebRTC", str(error))
