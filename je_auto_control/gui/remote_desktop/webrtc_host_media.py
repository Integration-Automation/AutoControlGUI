"""Monitor selection, bandwidth adaptation and viewer media for the WebRTC host panel.

One interaction group of ``webrtc_panel._WebRTCHostPanel``, kept as a mixin so the panel class
still owns every widget and slot under its original name.
"""
from __future__ import annotations


from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QMessageBox,
)

from je_auto_control.gui.remote_desktop._helpers import (
    _t,
)
from je_auto_control.gui.remote_desktop.blanking_overlay import BlankingOverlay
from je_auto_control.gui.remote_desktop.annotation_overlay import (
    HostAnnotationOverlay,
)
from je_auto_control.gui.remote_desktop.viewer_screen_window import (
    ViewerScreenWindow,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop import (
    install_hardware_codec, uninstall_hardware_codec,
)
from je_auto_control.utils.remote_desktop.adaptive_bitrate import (
    AdaptiveBitrateController,
)
from je_auto_control.utils.remote_desktop.webrtc_stats import (
    StatsPoller, StatsSnapshot,
)
from je_auto_control.gui.remote_desktop.webrtc_panel_common import (
    _DEFAULT_MONITOR, _QUALITY_DOT_STYLE, _av_frame_to_qimage,
)


class _HostMediaMixin:
    """Methods of ``_WebRTCHostPanel``; the module docstring says which group."""

    def _on_hw_codec_changed(self) -> None:
        codec = self._hw_codec_combo.currentData() or ""
        if not codec:
            uninstall_hardware_codec()
            self._status_label.setText(_t("rd_webrtc_hw_codec_off_status"))
            return
        if install_hardware_codec(codec):
            self._status_label.setText(
                _t("rd_webrtc_hw_codec_active").format(codec=codec),
            )
        else:
            self._status_label.setText(
                _t("rd_webrtc_hw_codec_failed").format(codec=codec),
            )

    def _on_toggle_accept_viewer_video(self, value: bool) -> None:
        if self._multi_host is None:
            return
        with self._multi_host._lock:
            sessions = list(self._multi_host._sessions.values())
        for host in sessions:
            try:
                if value:
                    host.set_viewer_video_callback(
                        self._on_viewer_video_av_frame,
                    )
                    host.enable_accept_viewer_video()
                else:
                    host.disable_accept_viewer_video()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("toggle accept viewer video: %r", error)
        if not value and self._viewer_screen_window is not None:
            self._viewer_screen_window.set_image(None)
            self._viewer_screen_window.hide()

    def _on_toggle_accept_opus_audio(self, value: bool) -> None:
        if self._multi_host is None:
            return
        with self._multi_host._lock:
            sessions = list(self._multi_host._sessions.values())
        for host in sessions:
            try:
                if value:
                    host.enable_accept_viewer_audio_opus()
                else:
                    host.disable_accept_viewer_audio_opus()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("toggle accept opus: %r", error)

    def _on_toggle_mic_receive(self, value: bool) -> None:
        if self._multi_host is None:
            return
        # Apply to every active session.
        with self._multi_host._lock:
            sessions = list(self._multi_host._sessions.values())
        for host in sessions:
            try:
                if value:
                    host.enable_mic_receive()
                else:
                    host.disable_mic_receive()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("mic receive toggle: %r", error)

    def _on_toggle_adaptive(self, value: bool) -> None:
        if value:
            self._maybe_start_adaptive()
        else:
            self._stop_adaptive()

    def _populate_monitor_combo(self) -> None:
        try:
            from je_auto_control.utils.cv2_utils.screen_grabber import mss_grabber
            with mss_grabber() as sct:
                monitors = sct.monitors
            for idx, mon in enumerate(monitors):
                if idx == 0:
                    label = _t("rd_webrtc_monitor_all")
                else:
                    label = f"#{idx}: {mon['width']}x{mon['height']} @"\
                            f" ({mon['left']},{mon['top']})"
                self._monitor_combo.addItem(label, idx)
        except (ImportError, RuntimeError, OSError):
            for idx in range(4):
                self._monitor_combo.addItem(f"#{idx}", idx)
        # Default to monitor #1 (the first real screen for mss)
        idx_default = self._monitor_combo.findData(_DEFAULT_MONITOR)
        if idx_default >= 0:
            self._monitor_combo.setCurrentIndex(idx_default)

    def _on_pick_region(self) -> None:
        try:
            from je_auto_control.gui.selector import open_region_selector
            region = open_region_selector(self)
        except (ImportError, RuntimeError, OSError) as error:
            QMessageBox.warning(self, "WebRTC", str(error))
            return
        if region is None:
            return
        x, y, w, h = region
        self._region_edit.setText(f"{x},{y},{w},{h}")

    def _on_monitor_changed(self, _i: int) -> None:
        idx = self._monitor_combo.currentData()
        if idx is None or self._multi_host is None:
            return
        track = self._multi_host.screen_track()
        if track is None:
            return
        try:
            track.set_target_monitor(int(idx))
            autocontrol_logger.info("monitor switched to #%d live", int(idx))
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("set_target_monitor: %r", error)

    def _on_toggle_readonly(self, value: bool) -> None:
        if self._multi_host is not None:
            self._multi_host.set_read_only(value)

    def _on_toggle_blanking(self, checked: bool) -> None:
        if checked:
            if self._blanking is None:
                self._blanking = BlankingOverlay()
            self._blanking.show()
        elif self._blanking is not None:
            self._blanking.hide()

    def _maybe_start_adaptive(self) -> None:
        # Always start a stats poller when sessions are active so the host
        # quality dot updates; the adaptive controller is an optional
        # consumer enabled via the checkbox.
        if self._adaptive_poller is not None or self._multi_host is None:
            return
        track = self._multi_host.screen_track()
        pc = self._multi_host.first_session_pc()
        if pc is None:
            return
        if track is not None and self._adaptive_check.isChecked():
            max_fps = int(self._fps_spin.value())
            self._adaptive_controller = AdaptiveBitrateController(
                track, max_fps=max_fps,
                max_bitrate_kbps=int(self._max_bitrate_spin.value()),
            )
        else:
            self._adaptive_controller = None
        self._adaptive_poller = StatsPoller(
            pc, self._on_host_stats, interval_s=1.0,
        )
        self._adaptive_poller.start()
        autocontrol_logger.info(
            "host stats poller active (adaptive=%s)",
            self._adaptive_controller is not None,
        )

    def _on_host_stats(self, snapshot: StatsSnapshot) -> None:
        # Fan-out: feed adaptive controller (if enabled) + update quality dot
        if self._adaptive_controller is not None:
            try:
                self._adaptive_controller.on_stats(snapshot)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("adaptive on_stats: %r", error)
        self._signals.stats.emit(snapshot)

    def _update_host_quality_dot(self, snapshot: StatsSnapshot) -> None:
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
        self._host_quality_dot.setStyleSheet(
            f"background-color: {color}; border-radius: 7px;",
        )
        self._host_quality_dot.setToolTip(_t(tip_key))

    def _reset_host_quality_dot(self) -> None:
        self._host_quality_dot.setStyleSheet(
            _QUALITY_DOT_STYLE,
        )
        self._host_quality_dot.setToolTip(_t("rd_webrtc_quality_unknown"))

    def _stop_adaptive(self) -> None:
        if self._adaptive_poller is not None:
            self._adaptive_poller.stop()
            self._adaptive_poller = None
        self._adaptive_controller = None

    def _on_annotation_event(self, data) -> None:
        if not isinstance(data, dict):
            return
        if self._annotation_overlay is None:
            self._annotation_overlay = HostAnnotationOverlay(parent=self)
        self._annotation_overlay.apply(data)

    def _on_session_authed(self, session_id: str) -> None:
        self._signals.auth.emit(True)
        if (self._multi_host is None
                or not self._accept_viewer_video_check.isChecked()):
            return
        # Wire viewer-video callback on this freshly-authed session
        with self._multi_host._lock:
            host = self._multi_host._sessions.get(session_id)
        if host is None:
            return
        host.set_viewer_video_callback(self._on_viewer_video_av_frame)

    def _on_viewer_video_av_frame(self, frame) -> None:
        image = _av_frame_to_qimage(frame)
        if image is not None:
            self._signals.viewer_video_frame.emit(image)

    def _on_viewer_video_image(self, image: QImage) -> None:
        if self._viewer_screen_window is None:
            self._viewer_screen_window = ViewerScreenWindow(parent=self)
            self._viewer_screen_window.closed.connect(
                self._on_viewer_screen_closed,
            )
        if not self._viewer_screen_window.isVisible():
            self._viewer_screen_window.show()
        self._viewer_screen_window.set_image(image)

    def _on_viewer_screen_closed(self) -> None:
        if self._viewer_screen_window is not None:
            self._viewer_screen_window.set_image(None)


__all__ = ["_HostMediaMixin"]
