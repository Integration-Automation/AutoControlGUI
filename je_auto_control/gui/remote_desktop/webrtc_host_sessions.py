"""Session table, per-session quality and disconnect for the WebRTC host panel.

One interaction group of ``webrtc_panel._WebRTCHostPanel``, kept as a mixin so the panel class
still owns every widget and slot under its original name.
"""
from __future__ import annotations

import functools
from typing import Callable, Dict, Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QTableWidgetItem,
)

from je_auto_control.gui.remote_desktop._webrtc_types import MultiViewerHostT
from je_auto_control.gui.remote_desktop._helpers import (
    _t,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.webrtc_inspector import (
    default_webrtc_inspector,
)
from je_auto_control.utils.remote_desktop.webrtc_stats import (
    StatsPoller, StatsSnapshot,
)
from je_auto_control.gui.remote_desktop.webrtc_panel_common import _PanelPart


def _stop_session(host: MultiViewerHostT, sid: str) -> None:
    """Worker thread: close one session; one that is already gone is not an error."""
    try:
        host.stop_session(sid)
    except (KeyError, RuntimeError, OSError) as error:
        autocontrol_logger.warning("disconnect session: %r", error)


class _HostSessionsMixin(_PanelPart):
    """Methods of ``_WebRTCHostPanel``; the module docstring says which group."""

    def _on_session_count(self, count: int) -> None:
        self._sessions_label.setText(
            _t("rd_webrtc_sessions_count").format(n=count),
        )
        if self._tray is not None:
            self._tray.set_state(sessions=count)
        # Color the badge by load: gray=0, green=1-3, yellow=4-10, red=>10
        if count == 0:
            bg, fg = "#3a3a3a", "#888"
        elif count <= 3:
            bg, fg = "#1f4d1f", "#a6e3a6"
        elif count <= 10:
            bg, fg = "#5a4710", "#f5d99a"
        else:
            bg, fg = "#5a1010", "#ffaaaa"
        self._sessions_label.setStyleSheet(
            f"background: {bg}; color: {fg}; padding: 2px 8px;"
            "border-radius: 8px; font-weight: bold;",
        )
        self._sync_session_pollers()
        self._refresh_sessions_table()
        if count > 0:
            self._maybe_start_adaptive()
        else:
            self._stop_adaptive()
            self._reset_host_quality_dot()

    def _sync_session_pollers(self) -> None:
        """Spawn StatsPoller for new sessions; stop pollers for gone ones."""
        if self._multi_host is None:
            # Snapshot before clear() so a slow stop() doesn't race with the
            # clear that follows.
            for poller in list(self._session_pollers.values()):  # NOSONAR python:S7504
                poller.stop()
            self._session_pollers.clear()
            self._session_cache.reset()
            return
        active_sids = {s["session_id"] for s in self._multi_host.list_sessions()}
        # Stop pollers whose session is gone
        # The loop deletes from self._session_pollers, so list() is required
        # to avoid a RuntimeError.
        for sid in list(self._session_pollers.keys()):  # NOSONAR python:S7504
            if sid not in active_sids:
                self._session_pollers[sid].stop()
                del self._session_pollers[sid]
                self._session_cache.drop(sid)
        # Spawn pollers for new sessions
        for sid in active_sids:
            if sid in self._session_pollers:
                continue
            pc = self._multi_host.session_pc(sid)
            if pc is None:
                continue
            poller = StatsPoller(pc, self._make_session_stats_handler(sid),
                                 interval_s=1.0)
            poller.start()
            self._session_pollers[sid] = poller

    def _make_session_stats_handler(self, session_id: str) -> Callable[[StatsSnapshot], None]:
        """Closure capturing session_id for the per-session poller."""
        def _handle(snapshot: StatsSnapshot) -> None:
            default_webrtc_inspector().record(snapshot)
            color = self._quality_color(snapshot)
            self._session_cache.set(
                session_id, color=color, snapshot=snapshot,
            )
            # Re-paint just the dot cell for this session_id (avoid full reflow).
            # One read: the GUI thread can clear it between a check and a call.
            host = self._multi_host
            self._signals.session_count.emit(host.session_count() if host else 0)
        return _handle

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

    def _refresh_sessions_table(self) -> None:
        from datetime import datetime
        from PySide6.QtGui import QColor
        if self._multi_host is None:
            self._sessions_table.setRowCount(0)
            return
        sessions = self._multi_host.list_sessions()
        self._sessions_table.setRowCount(len(sessions))
        for row, info in enumerate(sessions):
            sid = info.get("session_id", "")
            vid = info.get("pending_viewer_id") or ""
            state = info.get("state", "")
            connected = info.get("connected_at") or ""
            if connected:
                try:
                    dt = datetime.fromisoformat(connected)
                    connected = dt.astimezone().strftime("%H:%M:%S")
                except (TypeError, ValueError):
                    pass
            color = self._session_cache.get_color(sid)
            dot_item = QTableWidgetItem("●")
            dot_item.setForeground(QColor(color))
            dot_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            dot_item.setToolTip(self._format_quality_tooltip(
                self._session_cache.get_snapshot(sid),
            ))
            self._sessions_table.setItem(row, 0, dot_item)
            id_item = QTableWidgetItem(sid[:8] if sid else "")
            id_item.setData(Qt.ItemDataRole.UserRole, sid)
            self._sessions_table.setItem(row, 1, id_item)
            self._sessions_table.setItem(
                row, 2, QTableWidgetItem(vid[:12] if vid else ""),
            )
            self._sessions_table.setItem(row, 3, QTableWidgetItem(state))
            self._sessions_table.setItem(row, 4, QTableWidgetItem(connected))

    def _on_sessions_context_menu(self, position: QPoint) -> None:
        from PySide6.QtWidgets import QMenu
        if self._multi_host is None:
            return
        row = self._sessions_table.rowAt(position.y())
        if row < 0:
            return
        self._sessions_table.selectRow(row)
        sid_item = self._sessions_table.item(row, 1)
        viewer_item = self._sessions_table.item(row, 2)
        if sid_item is None:
            return
        sid = sid_item.data(Qt.ItemDataRole.UserRole) or ""
        viewer_id = viewer_item.text() if viewer_item is not None else ""
        menu = QMenu(self._sessions_table)
        actions = {
            "disconnect": menu.addAction(_t("rd_webrtc_disconnect_selected")),
            "trust": menu.addAction(_t("rd_webrtc_sess_trust_viewer")),
            "copy": menu.addAction(_t("rd_webrtc_sess_copy_id")),
        }
        actions["trust"].setEnabled(bool(viewer_id))
        chosen = menu.exec(
            self._sessions_table.viewport().mapToGlobal(position),
        )
        self._dispatch_session_menu(chosen, actions, sid, viewer_id)

    def _dispatch_session_menu(self, chosen: object, actions: Dict[str, object],
                               sid: str, viewer_id: str) -> None:
        """Run the action chosen from the sessions context menu."""
        if chosen is actions["disconnect"]:
            self._on_disconnect_selected()
        elif chosen is actions["trust"] and viewer_id:
            self._trust_session_viewer(sid)
        elif chosen is actions["copy"] and sid:
            self._copy_session_id_to_clipboard(sid)

    @staticmethod
    def _copy_session_id_to_clipboard(sid: str) -> None:
        from PySide6.QtWidgets import QApplication
        clip = QApplication.clipboard()
        if clip is not None:
            clip.setText(sid)

    def _on_disconnect_selected(self) -> None:
        if self._multi_host is None:
            return
        row = self._sessions_table.currentRow()
        if row < 0:
            return
        item = self._sessions_table.item(row, 1)
        if item is None:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(sid, str) or not sid:
            return
        if sid in self._stopping_sessions:     # a second click on a session already closing
            return
        host = self._multi_host
        self._stopping_sessions.add(sid)
        # stop_session waits for the peer connection to close (seconds).
        self._stops.retire(functools.partial(_stop_session, host, sid),
                           on_done=self._on_session_stopped, args=(host, sid))

    def _on_session_stopped(self, host: MultiViewerHostT, sid: str, _outcome: object = None) -> None:
        """GUI thread: the session closed -- count again unless the host was stopped meanwhile."""
        self._stopping_sessions.discard(sid)
        if self._multi_host is host:
            self._signals.session_count.emit(host.session_count())


__all__ = ["_HostSessionsMixin"]
