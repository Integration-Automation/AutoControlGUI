"""Microphone, recording, statistics and annotation for the WebRTC viewer panel.

One interaction group of ``webrtc_panel._WebRTCViewerPanel``, kept as a mixin so the panel class
still owns every widget and slot under its original name.
"""
from __future__ import annotations

from typing import Optional


from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QFileDialog, QMessageBox,
)

from je_auto_control.gui.remote_desktop._webrtc_types import AvFrameT, SessionRecorderT
from je_auto_control.gui.remote_desktop._helpers import (
    _t,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop import (
    SessionRecorder,
)
from je_auto_control.utils.remote_desktop.webrtc_inspector import (
    default_webrtc_inspector,
)
from je_auto_control.utils.remote_desktop.webrtc_stats import (
    StatsPoller, StatsSnapshot,
)
from je_auto_control.utils.remote_desktop.webrtc_transport import (
    fps_for_preset,
)
from je_auto_control.gui.remote_desktop.webrtc_panel_common import (
    _PanelPart,
    _QUALITY_DOT_STYLE, _av_frame_to_qimage,
)


class _ViewerMediaMixin(_PanelPart):
    """Methods of ``_WebRTCViewerPanel``; the module docstring says which group."""

    # State this group owns; the panel's __init__ sets the starting values.
    _recorder: Optional[SessionRecorderT]
    _stats_poller: Optional[StatsPoller]

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
            recorder, self._recorder = self._recorder, None
            if recorder is None:
                self._record_btn.setText(_t("rd_webrtc_start_recording"))
                return
            # stop() drains the frame queue and finalises the file; until it
            # reports the button says so and takes no click.
            self._record_btn.setText(_t("gui_op_stopping"))
            self._record_btn.setEnabled(False)
            self._stops.retire(recorder.stop, on_done=self._on_recording_stopped, args=(recorder,))

    def _on_recording_stopped(self, recorder: SessionRecorderT, _outcome: object = None) -> None:
        """GUI thread: the recording is on disk (or no frame ever arrived)."""
        self._record_btn.setEnabled(True)
        if self._recorder is None:
            self._record_btn.setText(_t("rd_webrtc_start_recording"))
        # "Saved" was reported for a file that no frame ever created.
        key = "rd_webrtc_recording_saved" if recorder.has_output else "rd_webrtc_recording_empty"
        QMessageBox.information(self, "WebRTC", _t(key).format(path=str(recorder.output_path)))

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
        if self._screen_window is not None:
            self._screen_window.set_pen_mode(checked)
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

    # called from asyncio thread
    def _on_av_frame(self, frame: AvFrameT) -> None:
        if self._recorder is not None:
            try:
                self._recorder.write_frame(frame)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("recorder write: %r", error)
        image = _av_frame_to_qimage(frame)
        if image is not None:
            self._signals.frame.emit(image)

    def _on_frame_image(self, image: QImage) -> None:
        # When the popup is open it owns the visible display; while
        # closed (pre-auth or after stop), the hidden inline display
        # still renders so debugging tools / screenshots work.
        if self._screen_window is not None:
            self._screen_window.set_image(image)
        else:
            self._frame_display.set_image(image)

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


__all__ = ["_ViewerMediaMixin"]
