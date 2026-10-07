"""Shared WebRTC panel signals and configuration/frame conversion helpers."""

# pylint: disable=protected-access  # reason: shared typed panel presentation helpers
from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtCore import QObject, Signal

# pylint: enable=no-name-in-module
# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtGui import QImage

# pylint: enable=no-name-in-module
# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QLineEdit, QMessageBox

# pylint: enable=no-name-in-module
from je_auto_control.gui.remote_desktop._helpers import _t
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop import WebRTCConfig
from je_auto_control.utils.remote_desktop.cleanup_jobs import _submit_cleanup
from je_auto_control.utils.remote_desktop.webrtc_stats import StatsSnapshot

_DEFAULT_FPS = 24
_DEFAULT_MONITOR = 1
_DEFAULT_SIGNALING_URL = "http://127.0.0.1:8765"
_QUALITY_DOT_STYLE = "background-color: #555; border-radius: 7px;"
_JSON_FILE_FILTER = "JSON (*.json);;All (*)"


def dispose_background(callbacks: Iterable[Callable[[], None]]) -> None:
    """Schedule owned cleanup off Qt, retaining failed callbacks for retry."""
    _submit_cleanup(callbacks)


def _av_frame_to_qimage(frame: Any) -> Optional[QImage]:
    """Convert an aiortc/av video frame to a Qt-owned QImage."""
    try:
        arr = frame.to_ndarray(format="rgb24")
    except (ValueError, RuntimeError) as error:
        autocontrol_logger.debug("av->QImage failed: %r", error)
        return None
    height, width, _ = arr.shape
    image = QImage(arr.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888)
    return image.copy()


class _PanelSignals(QObject):  # pylint: disable=too-few-public-methods  # reason: internal signal/slot controller
    """Bridge so asyncio-thread callbacks reach Qt safely."""

    frame = Signal(QImage)
    state = Signal(str)
    auth = Signal(bool)
    pending_viewer = Signal(str, object)
    stats = Signal(object)
    session_count = Signal(int)
    inbox_listing = Signal(object)
    inbox_op = Signal(str, bool, object)
    file_received = Signal(object)
    viewer_video_frame = Signal(QImage)
    annotation = Signal(object)


def _checked_or(panel: Any, attr: str, default: bool = False) -> bool:
    """Return ``panel.<attr>.isChecked()`` if the widget exists, else default."""
    widget = getattr(panel, attr, None)
    return widget.isChecked() if widget is not None else default


def _read_region(panel: Any) -> Optional[tuple[Any, ...]]:
    edit = getattr(panel, "_region_edit", None)
    if edit is None:
        return None
    text = edit.text().strip()
    if not text:
        return None
    try:
        parts = [int(p.strip()) for p in text.split(",")]
    except (ValueError, TypeError):
        return None
    return tuple(parts) if len(parts) == 4 else None


def _read_webrtc_config(panel: Any) -> WebRTCConfig:
    """Build a WebRTCConfig from the advanced group + monitor/fps fields."""
    # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
    from je_auto_control.utils.remote_desktop.webrtc_transport import (
        _DEFAULT_STUN_SERVERS,
    )
    # pylint: enable=import-outside-toplevel

    stun_field = panel._stun_edit.text().strip()
    ice_servers = [stun_field] if stun_field else list(_DEFAULT_STUN_SERVERS)
    monitor = (
        int(panel._monitor_combo.currentData() or _DEFAULT_MONITOR)
        if hasattr(panel, "_monitor_combo")
        else _DEFAULT_MONITOR
    )
    fps = int(panel._fps_spin.value()) if hasattr(panel, "_fps_spin") else _DEFAULT_FPS
    max_bitrate = int(panel._max_bitrate_spin.value()) if hasattr(panel, "_max_bitrate_spin") else 0
    return WebRTCConfig(
        ice_servers=ice_servers,
        turn_url=panel._turn_edit.text().strip() or None,
        turn_username=panel._turn_user_edit.text().strip() or None,
        turn_credential=panel._turn_cred_edit.text() or None,
        monitor_index=monitor,
        fps=fps,
        show_cursor=_checked_or(panel, "_cursor_check", default=True),
        accept_viewer_video=_checked_or(panel, "_accept_viewer_video_check"),
        accept_viewer_audio_opus=_checked_or(panel, "_accept_opus_audio_check"),
        share_my_screen=_checked_or(panel, "_share_my_screen_check"),
        share_my_audio_opus=_checked_or(panel, "_share_opus_mic_check"),
        max_bitrate_kbps=max_bitrate,
        region=_read_region(panel),
        host_voice=_checked_or(panel, "_host_voice_check"),
    )


def quality_indicator(snapshot: StatsSnapshot) -> tuple[str, str]:
    """Use the same quality thresholds for host and viewer indicators."""
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
    return color, tip_key


def validate_required_fields(panel: Any, *, needs_server: bool) -> bool:
    """Validate the shared token and optional signaling fields."""
    token = panel._token_edit.text().strip()
    if not token:
        QMessageBox.warning(panel, "WebRTC", _t("rd_webrtc_token_required"))
        return False
    if needs_server:
        if not panel._server_edit.text().strip():
            QMessageBox.warning(panel, "WebRTC", _t("rd_webrtc_server_required"))
            return False
        if not panel._host_id_edit.text().strip():
            QMessageBox.warning(panel, "WebRTC", _t("rd_webrtc_host_id_required"))
            return False
    return True


def signaling_grid(panel: Any) -> tuple[QGroupBox, QGridLayout]:
    """Build the common signaling address fields for either panel."""
    group = panel._tr(QGroupBox(), "rd_webrtc_signaling_group")
    grid = QGridLayout()
    grid.addWidget(panel._tr(QLabel(), "rd_webrtc_server_label"), 0, 0)
    panel._server_edit = QLineEdit(_DEFAULT_SIGNALING_URL)
    grid.addWidget(panel._server_edit, 0, 1, 1, 3)
    grid.addWidget(panel._tr(QLabel(), "rd_webrtc_host_id_label"), 1, 0)
    return group, grid


def token_grid(panel: Any) -> tuple[QGroupBox, QGridLayout]:
    """Build the common token fields for either panel."""
    group = panel._tr(QGroupBox(), "rd_webrtc_config_group")
    grid = QGridLayout()
    grid.addWidget(panel._tr(QLabel(), "rd_token_label"), 0, 0)
    panel._token_edit = panel._tr(QLineEdit(), "rd_token_placeholder")
    grid.addWidget(panel._token_edit, 0, 1)
    return group, grid


def _drain_folder_sync(engine: Any) -> None:
    """Keep a timed-out sender in the native cleanup registry for another stop attempt."""
    engine.stop()
    if engine.is_running():
        raise RuntimeError('Folder sender is still draining; retry cleanup')


def stop_folder_sync(panel: Any) -> None:
    """Revoke sends immediately, then drain off Qt while preserving the owned engine."""
    engine = panel._sync_engine
    if engine is None:
        return
    engine._request_stop()
    from functools import partial
    _submit_cleanup((partial(_drain_folder_sync, engine),))
