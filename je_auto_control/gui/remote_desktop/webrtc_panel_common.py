"""Signals, defaults and config readers shared by the WebRTC host and viewer panels."""
from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QWidget

from je_auto_control.gui.remote_desktop._webrtc_types import AvFrameT, WebRTCConfigT
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._slow_op import StopQueue
from je_auto_control.gui.remote_desktop._helpers import _t

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop import (
    WebRTCConfig,
)


_DEFAULT_FPS = 24
_DEFAULT_MONITOR = 1
# Plain http:// is intentional: the bundled signaling server defaults
# to localhost without TLS, and operators put TLS in front via nginx /
# Caddy. Hotspot S5332 acknowledged on a per-line basis; see callers.
_DEFAULT_SIGNALING_URL = "http://127.0.0.1:8765"  # NOSONAR python:S5332

_QUALITY_DOT_STYLE = "background-color: #555; border-radius: 7px;"
_JSON_FILE_FILTER = "JSON (*.json);;All (*)"


def _av_frame_to_qimage(frame: AvFrameT) -> Optional[QImage]:
    """Convert an aiortc/av video frame to a Qt-owned QImage."""
    try:
        arr = frame.to_ndarray(format="rgb24")
    except (ValueError, RuntimeError) as error:
        autocontrol_logger.debug("av->QImage failed: %r", error)
        return None
    height, width, _ = arr.shape
    image = QImage(
        arr.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888,
    )
    return image.copy()


class _PanelSignals(QObject):
    """Bridge so asyncio-thread callbacks reach Qt safely."""
    frame = Signal(QImage)
    state = Signal(str)
    auth = Signal(bool)
    # Host-side: (session_id, viewer_id-or-None) per pending viewer prompt.
    pending_viewer = Signal(str, object)
    stats = Signal(object)  # StatsSnapshot
    session_count = Signal(int)
    # Viewer-side file browser: list and op result.
    inbox_listing = Signal(object)  # list[dict]
    inbox_op = Signal(str, bool, object)  # name, ok, error
    # Viewer-side: a file finished transferring (fired from the asyncio thread).
    file_received = Signal(object)  # path
    # Host-side: incoming viewer-shared screen frame
    viewer_video_frame = Signal(QImage)
    # Host-side: incoming annotation event from viewer
    annotation = Signal(object)  # dict


class _PanelPart(TranslatableMixin, QWidget):
    """Base of every WebRTC panel mixin: each one is a slice of a translatable ``QWidget``.

    It is what lets a mixin use the widget API, ``_tr`` and the attributes its
    sibling mixins set, the way the methods did while they all sat in one class
    body. The one thing it adds is what both panels need around a shutdown that
    left the GUI thread: the queue it goes to and the text shown meanwhile.
    """

    # Set by each panel's __init__: shutdowns of sessions the panel let go of.
    _stops: StopQueue

    def _show_idle(self) -> None:
        """Show "idle" -- or "stopping" while a session this panel let go of is still closing."""
        key = "gui_op_stopping" if self._stops.pending else "rd_webrtc_status_idle"
        self._status_label.setText(_t(key))

    def _on_stops_drained(self) -> None:
        """GUI thread: the last shutdown reported; a "stopping" still on show becomes "idle"."""
        if self._status_label.text() == _t("gui_op_stopping"):
            self._status_label.setText(_t("rd_webrtc_status_idle"))


def _checked_or(panel: QWidget, attr: str, default: bool = False) -> bool:
    """Return ``panel.<attr>.isChecked()`` if the widget exists, else default."""
    widget = getattr(panel, attr, None)
    return widget.isChecked() if widget is not None else default


def _read_region(panel: QWidget) -> Optional[Tuple[int, ...]]:
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


def _read_webrtc_config(panel: QWidget) -> WebRTCConfigT:
    """Build a WebRTCConfig from the advanced group + monitor/fps fields."""
    from je_auto_control.utils.remote_desktop.webrtc_transport import (
        _DEFAULT_STUN_SERVERS,
    )
    stun_field = panel._stun_edit.text().strip()
    ice_servers = [stun_field] if stun_field else list(_DEFAULT_STUN_SERVERS)
    monitor = (
        int(panel._monitor_combo.currentData() or _DEFAULT_MONITOR)
        if hasattr(panel, "_monitor_combo") else _DEFAULT_MONITOR
    )
    fps = (int(panel._fps_spin.value())
           if hasattr(panel, "_fps_spin") else _DEFAULT_FPS)
    max_bitrate = (
        int(panel._max_bitrate_spin.value())
        if hasattr(panel, "_max_bitrate_spin") else 0
    )
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

