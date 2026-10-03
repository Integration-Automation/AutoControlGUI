"""WebRTC host features controller; session and widget ownership stays on the panel."""
# pylint: disable=protected-access  # reason: typed controllers share their owning panel state

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtCore import Qt

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
from je_auto_control.gui.remote_desktop._helpers import _read_import_entries, _t
from je_auto_control.gui.remote_desktop.annotation_overlay import HostAnnotationOverlay
from je_auto_control.gui.remote_desktop.blanking_overlay import BlankingOverlay
from je_auto_control.gui.remote_desktop.viewer_screen_window import ViewerScreenWindow
from je_auto_control.gui.remote_desktop.webrtc_common import (
    _JSON_FILE_FILTER,
    _QUALITY_DOT_STYLE,
    _av_frame_to_qimage,
    quality_indicator,
)
from je_auto_control.gui.remote_desktop.webrtc_dialogs import AuditLogDialog
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.adaptive_bitrate import AdaptiveBitrateController
from je_auto_control.utils.remote_desktop.webrtc_stats import StatsPoller, StatsSnapshot

if TYPE_CHECKING:
    from je_auto_control.gui.remote_desktop.webrtc_host_panel import _WebRTCHostPanel


class WebRTCHostFeaturesController:  # pylint: disable=too-few-public-methods  # reason: internal signal/slot controller
    """Host features interactions on a typed owned panel."""

    def __init__(self, panel: _WebRTCHostPanel) -> None:
        self._panel = panel

    def _on_view_audit(self) -> None:
        # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
        from je_auto_control.utils.remote_desktop.audit_log import (
            default_audit_log,
        )
        # pylint: enable=import-outside-toplevel

        AuditLogDialog(default_audit_log(), parent=self._panel).exec()

    def _on_push_file(self) -> None:
        if self._panel._multi_host is None or self._panel._multi_host.session_count() == 0:
            QMessageBox.information(self._panel, "WebRTC", _t("rd_webrtc_no_viewers"))
            return
        path, _filter = QFileDialog.getOpenFileName(self._panel, _t("rd_webrtc_push_file"), "")
        if not path:
            return
        try:
            sent = self._panel._multi_host.broadcast_file(path)
            QMessageBox.information(self._panel, "WebRTC", _t("rd_webrtc_push_done").format(n=sent, name=path))
        except (RuntimeError, OSError, ValueError) as error:
            QMessageBox.warning(self._panel, "WebRTC", str(error))

    def _on_export_trust(self) -> None:
        # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
        import json as _json
        # pylint: enable=import-outside-toplevel

        path, _filter = QFileDialog.getSaveFileName(
            self._panel, _t("rd_webrtc_trust_export"), "trusted_viewers.json", _JSON_FILE_FILTER
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                _json.dump({"viewers": self._panel._trust_list.list_entries()}, fh, indent=2, ensure_ascii=False)
        except OSError as error:
            QMessageBox.warning(self._panel, "WebRTC", str(error))

    def _on_import_trust(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self._panel, _t("rd_webrtc_trust_import"), "", _JSON_FILE_FILTER)
        if not path:
            return
        try:
            viewers = _read_import_entries(path, "viewers")
        except (OSError, ValueError) as error:
            QMessageBox.warning(self._panel, "WebRTC", str(error))
            return
        added = 0
        for entry in viewers:
            vid, label = (entry.get("viewer_id"), entry.get("label"))
            if isinstance(vid, str) and vid:
                self._panel._trust_list.add(vid, label=label if isinstance(label, str) else "")
                added += 1
        QMessageBox.information(self._panel, "WebRTC", _t("rd_webrtc_trust_import_done").format(n=added))
        self._panel._refresh_trusted_list()

    def _refresh_trusted_list(self) -> None:
        self._panel._trusted_list.populate(self._panel._trust_list.list_entries())

    def _on_toggle_accept_viewer_video(self, value: bool) -> None:
        if self._panel._multi_host is None:
            return
        with self._panel._multi_host._lock:
            sessions = list(self._panel._multi_host._sessions.values())
        for host in sessions:
            try:
                if value:
                    host.set_viewer_video_callback(self._panel._on_viewer_video_av_frame)
                    host.enable_accept_viewer_video()
                else:
                    host.disable_accept_viewer_video()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("toggle accept viewer video: %r", error)
        if not value and self._panel._viewer_screen_window is not None:
            self._panel._viewer_screen_window.set_image(None)
            self._panel._viewer_screen_window.hide()

    def _on_toggle_accept_opus_audio(self, value: bool) -> None:
        if self._panel._multi_host is None:
            return
        with self._panel._multi_host._lock:
            sessions = list(self._panel._multi_host._sessions.values())
        for host in sessions:
            try:
                if value:
                    host.enable_accept_viewer_audio_opus()
                else:
                    host.disable_accept_viewer_audio_opus()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("toggle accept opus: %r", error)

    def _on_toggle_mic_receive(self, value: bool) -> None:
        if self._panel._multi_host is None:
            return
        with self._panel._multi_host._lock:
            sessions = list(self._panel._multi_host._sessions.values())
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
            self._panel._maybe_start_adaptive()
        else:
            self._panel._stop_adaptive()

    def _on_toggle_readonly(self, value: bool) -> None:
        if self._panel._multi_host is not None:
            self._panel._multi_host.set_read_only(value)

    def _on_toggle_blanking(self, checked: bool) -> None:
        if checked:
            if self._panel._blanking is None:
                self._panel._blanking = BlankingOverlay()
            self._panel._blanking.show()
        elif self._panel._blanking is not None:
            self._panel._blanking.hide()

    @staticmethod
    def _format_quality_tooltip(snapshot: Optional[StatsSnapshot]) -> str:
        if snapshot is None:
            return _t("rd_webrtc_quality_unknown")
        parts = []
        if snapshot.rtt_ms is not None:
            parts.append(f"RTT {snapshot.rtt_ms:.0f}ms")
        if snapshot.packet_loss_pct is not None:
            parts.append(f"loss {snapshot.packet_loss_pct:.1f}%")
        if snapshot.fps is not None:
            parts.append(f"FPS {snapshot.fps:.1f}")
        if snapshot.bitrate_kbps is not None:
            parts.append(f"{snapshot.bitrate_kbps:.0f}kbps")
        return " | ".join(parts) if parts else _t("rd_webrtc_quality_unknown")

    @staticmethod
    def _quality_color(snapshot: StatsSnapshot) -> str:
        rtt = snapshot.rtt_ms
        loss = snapshot.packet_loss_pct or 0.0
        if rtt is None:
            return "#555"
        if rtt < 80 and loss < 1.0:
            return "#3a9c3a"
        if rtt < 200 and loss < 5.0:
            return "#c9a23a"
        return "#cc4444"

    def _maybe_start_adaptive(self) -> None:
        if self._panel._adaptive_poller is not None or self._panel._multi_host is None:
            return
        track = self._panel._multi_host.screen_track()
        pc = self._panel._multi_host.first_session_pc()
        if pc is None:
            return
        if track is not None and self._panel._adaptive_check.isChecked():
            max_fps = int(self._panel._fps_spin.value())
            self._panel._adaptive_controller = AdaptiveBitrateController(
                track, max_fps=max_fps, max_bitrate_kbps=int(self._panel._max_bitrate_spin.value())
            )
        else:
            self._panel._adaptive_controller = None
        self._panel._adaptive_poller = StatsPoller(
            pc, self._panel._sessions.callback("host", self._panel._on_host_stats), interval_s=1.0
        )
        self._panel._adaptive_poller.start()
        autocontrol_logger.info("host stats poller active (adaptive=%s)", self._panel._adaptive_controller is not None)

    def _on_host_stats(self, snapshot: StatsSnapshot) -> None:
        if self._panel._adaptive_controller is not None:
            try:
                self._panel._adaptive_controller.on_stats(snapshot)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("adaptive on_stats: %r", error)
        self._panel._signals.stats.emit(snapshot)

    def _update_host_quality_dot(self, snapshot: StatsSnapshot) -> None:
        color, tip_key = quality_indicator(snapshot)
        self._panel._host_quality_dot.setStyleSheet(f"background-color: {color}; border-radius: 7px;")
        self._panel._host_quality_dot.setToolTip(_t(tip_key))

    def _reset_host_quality_dot(self) -> None:
        self._panel._host_quality_dot.setStyleSheet(_QUALITY_DOT_STYLE)
        self._panel._host_quality_dot.setToolTip(_t("rd_webrtc_quality_unknown"))

    def _stop_adaptive(self) -> None:
        if self._panel._adaptive_poller is not None:
            self._panel._adaptive_poller.stop()
            self._panel._adaptive_poller = None
        self._panel._adaptive_controller = None

    def _on_remove_trust(self, viewer_id: str) -> None:
        self._panel._trust_list.remove(viewer_id)
        self._panel._refresh_trusted_list()

    def _on_remove_trust_button(self) -> None:
        item = self._panel._trusted_list.currentItem()
        if item is None:
            return
        viewer_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(viewer_id, str):
            self._panel._on_remove_trust(viewer_id)

    def _on_clear_trust(self) -> None:
        result = QMessageBox.question(
            self._panel,
            "WebRTC",
            _t("rd_webrtc_clear_trust_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self._panel._trust_list.clear()
        self._panel._refresh_trusted_list()

    def _on_annotation_event(self, data) -> None:
        if not isinstance(data, dict):
            return
        if self._panel._annotation_overlay is None:
            self._panel._annotation_overlay = HostAnnotationOverlay(parent=self._panel)
        self._panel._annotation_overlay.apply(data)

    def _on_session_authed(self, session_id: str) -> None:
        self._panel._signals.auth.emit(True)
        if self._panel._multi_host is None or not self._panel._accept_viewer_video_check.isChecked():
            return
        with self._panel._multi_host._lock:
            host = self._panel._multi_host._sessions.get(session_id)
        if host is None:
            return
        host.set_viewer_video_callback(
            self._panel._sessions.callback(
                "host", self._panel._signals.viewer_video_frame.emit, transform=self._panel._viewer_video_arguments
            )
        )

    def _viewer_video_arguments(self, frame) -> Optional[tuple]:
        image = _av_frame_to_qimage(frame)
        return None if image is None else (image,)

    def _on_viewer_video_av_frame(self, frame) -> None:
        image = _av_frame_to_qimage(frame)
        if image is not None:
            self._panel._signals.viewer_video_frame.emit(image)

    def _on_viewer_video_image(self, image: QImage) -> None:
        if self._panel._viewer_screen_window is None:
            self._panel._viewer_screen_window = ViewerScreenWindow(parent=self._panel)
            self._panel._viewer_screen_window.closed.connect(self._panel._on_viewer_screen_closed)
        if not self._panel._viewer_screen_window.isVisible():
            self._panel._viewer_screen_window.show()
        self._panel._viewer_screen_window.set_image(image)

    def _on_viewer_screen_closed(self) -> None:
        if self._panel._viewer_screen_window is not None:
            self._panel._viewer_screen_window.set_image(None)
