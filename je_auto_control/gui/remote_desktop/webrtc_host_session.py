"""WebRTC host session controller; session and widget ownership stays on the panel."""
# pylint: disable=protected-access  # reason: typed controllers share their owning panel state

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any, Callable, Optional

# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction

# pylint: enable=no-name-in-module
# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtWidgets import (
    QMessageBox,
    QTableWidgetItem,
)

from je_auto_control.gui._panel_tasks import start_native

# pylint: enable=no-name-in-module
from je_auto_control.gui.remote_desktop._helpers import _t
from je_auto_control.gui.remote_desktop._task_work import HostOffer, apply_answer, create_offer, run_in_session
from je_auto_control.gui.remote_desktop.webrtc_workers import HostPublishLoopWorker, retire_worker
from je_auto_control.gui.task_controller import TaskController, TaskError, TaskHandle, TaskResult
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop import MultiViewerHost
from je_auto_control.utils.remote_desktop.cleanup_jobs import _submit_cleanup
from je_auto_control.utils.remote_desktop.webrtc_inspector import default_webrtc_inspector
from je_auto_control.utils.remote_desktop.webrtc_stats import StatsPoller, StatsSnapshot

if TYPE_CHECKING:
    from je_auto_control.gui.remote_desktop.webrtc_host_panel import _WebRTCHostPanel


class WebRTCHostSessionController:  # pylint: disable=too-few-public-methods  # reason: internal signal/slot controller
    """Host session interactions on a typed owned panel."""

    def __init__(self, panel: _WebRTCHostPanel) -> None:
        self._panel = panel
        self._tasks = TaskController(timeout_s=60)
        self._task: Optional[TaskHandle] = None

    def _on_tray_open(self) -> None:
        win = self._panel.window()
        if win is None:
            return
        win.showNormal()
        win.raise_()
        win.activateWindow()

    def _on_tray_stop(self) -> None:
        self._panel._stop_host_if_any()
        self._panel._signals.session_count.emit(0)

    def _on_tray_quit(self) -> None:
        self._panel._stop_host_if_any()
        # pylint: disable=no-name-in-module,import-outside-toplevel  # reason: lazy optional/cyclic boundary
        from PySide6.QtWidgets import (
            QApplication,
        )
        # pylint: enable=no-name-in-module,import-outside-toplevel

        QApplication.quit()

    def _on_publish_via_server(self) -> None:
        if not self._panel._validate_required_fields(needs_server=True):
            return
        self._panel._stop_host_if_any()
        try:
            self._panel._multi_host = self._panel._build_multi_host(self._panel._token_edit.text().strip())
        except (ValueError, RuntimeError, OSError) as error:
            self._panel._show_error(error)
            return
        self._panel._set_hosting(True)
        self._panel._publish_loop = HostPublishLoopWorker(
            multi_host=self._panel._multi_host,
            server_url=self._panel._server_edit.text().strip(),
            host_id=self._panel._host_id_edit.text().strip(),
            secret=self._panel._secret_edit.text() or None,
        )
        self._panel._publish_loop.offer_published.connect(
            self._panel._sessions.callback("host", self._panel._on_loop_offer_published)
        )
        self._panel._publish_loop.session_connected.connect(
            self._panel._sessions.callback("host", self._panel._on_loop_session_connected)
        )
        self._panel._publish_loop.failed.connect(
            self._panel._sessions.callback("host", self._panel._on_signaling_failed)
        )
        self._panel._status_label.setText(_t("rd_webrtc_publishing_offer"))
        self._panel._publish_loop.start()
        self._panel._start_lan_advertise()

    def _start_lan_advertise(self) -> None:
        try:
            # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
            from je_auto_control.utils.remote_desktop.lan_discovery import (
                HostAdvertiser,
                is_discovery_available,
            )
            # pylint: enable=import-outside-toplevel
        except ImportError:
            return
        if not is_discovery_available():
            return
        try:
            if self._panel._lan_advertiser is not None:
                _submit_cleanup((self._panel._lan_advertiser.stop,))
            self._panel._lan_advertiser = HostAdvertiser(
                host_id=self._panel._host_id_edit.text().strip(), signaling_url=self._panel._server_edit.text().strip()
            )
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("lan advertise: %r", error)

    def _stop_lan_advertise(self) -> None:
        if self._panel._lan_advertiser is not None:
            _submit_cleanup((self._panel._lan_advertiser.stop,))
            self._panel._lan_advertiser = None

    def _on_loop_offer_published(self, session_id: str) -> None:
        autocontrol_logger.debug("publish loop: offer for %s", session_id)

    def _on_loop_session_connected(self, _session_id: str) -> None:
        if self._panel._multi_host is not None:
            self._panel._signals.session_count.emit(self._panel._multi_host.session_count())

    def _on_signaling_failed(self, message: str) -> None:
        QMessageBox.warning(self._panel, "WebRTC", message)
        self._panel._status_label.setText(_t("rd_webrtc_status_idle"))

    def _on_generate_offer(self) -> None:
        token = self._panel._token_edit.text().strip()
        if not token:
            QMessageBox.warning(self._panel, "WebRTC", _t("rd_webrtc_token_required"))
            return
        try:
            if self._panel._multi_host is None:
                self._panel._multi_host = self._panel._build_multi_host(token)
        except (ValueError, RuntimeError, OSError) as error:
            self._panel._show_error(error)
            return
        self._panel._set_hosting(True)
        self._panel._status_label.setText(_t("rd_webrtc_generating_offer"))
        self._panel._offer_view.setPlainText("")
        QTimer.singleShot(0, self._panel, self._panel._sessions.callback("host", self._panel._produce_offer))

    def _require_multi_host(self) -> MultiViewerHost:
        """Return the running host, or say the session is not up yet."""
        host = self._panel._multi_host
        if host is None:
            raise RuntimeError(_t("rd_webrtc_not_started"))
        return host

    def _produce_offer(self) -> None:
        try:
            host = self._require_multi_host()
            identifier = self._panel._sessions.id('host')
            if identifier is None:
                raise RuntimeError('WebRTC host has no owned session')
            directory = self._panel._sessions.directory
            session = directory.get_session(identifier, owner=self._panel._sessions.owner)
            current = partial(directory.session_is_current, identifier, session.generation, owner=session.owner)
        except (RuntimeError, OSError) as error:
            self._panel._show_error(error)
            return
        work = partial(run_in_session, directory, session, partial(create_offer, host, identifier, current))
        self._task = self._tasks.submit(work, owner=self._panel)
        self._task.completed.connect(self._offer_ready)
        self._task.failed.connect(self._task_failed)

    def _offer_ready(self, result: TaskResult) -> None:
        offer = result.value
        if not isinstance(offer, HostOffer):
            return
        if self._panel._multi_host is not offer.host or self._panel._sessions.id('host') != offer.owner_session_id:
            _submit_cleanup((partial(offer.host.stop_session, offer.peer_id),))
            return
        self._panel._manual_session_id = offer.peer_id
        self._panel._offer_view.setPlainText(offer.sdp)
        self._panel._status_label.setText(_t("rd_webrtc_offer_ready"))

    def _task_failed(self, error: TaskError) -> None:
        self._panel._show_error(RuntimeError(error.message))

    def _on_apply_answer(self) -> None:
        if self._panel._multi_host is None or not self._panel._manual_session_id:
            QMessageBox.warning(self._panel, "WebRTC", _t("rd_webrtc_no_offer_yet"))
            return
        answer = self._panel._answer_input.toPlainText().strip()
        if not answer:
            QMessageBox.warning(self._panel, "WebRTC", _t("rd_webrtc_no_answer"))
            return
        identifier = self._panel._sessions.id('host')
        if identifier is None:
            return
        offer = HostOffer(self._panel._multi_host, identifier, self._panel._manual_session_id, '')
        directory = self._panel._sessions.directory
        session = directory.get_session(identifier, owner=self._panel._sessions.owner)
        current = partial(directory.session_is_current, identifier, session.generation, owner=session.owner)
        work = partial(run_in_session, directory, session, partial(apply_answer, offer, answer, current))
        self._task = self._tasks.submit(work, owner=self._panel)
        self._task.completed.connect(self._answer_applied)
        self._task.failed.connect(self._task_failed)

    def _answer_applied(self, result: TaskResult) -> None:
        offer = result.value
        if (isinstance(offer, HostOffer) and self._panel._multi_host is offer.host
                and self._panel._sessions.id('host') == offer.owner_session_id
                and self._panel._manual_session_id == offer.peer_id):
            self._panel._status_label.setText(_t('rd_webrtc_answer_applied'))
            self._panel._manual_session_id = None

    def _on_stop(self) -> None:
        self._panel._stop_host_if_any()
        self._panel._status_label.setText(_t("rd_webrtc_status_idle"))
        self._panel._signals.session_count.emit(0)

    def _on_session_count(self, count: int) -> None:
        self._panel._sessions_label.setText(_t("rd_webrtc_sessions_count").format(n=count))
        if self._panel._tray is not None:
            self._panel._tray.set_state(sessions=count)
        if count == 0:
            bg, fg = ("#3a3a3a", "#888")
        elif count <= 3:
            bg, fg = ("#1f4d1f", "#a6e3a6")
        elif count <= 10:
            bg, fg = ("#5a4710", "#f5d99a")
        else:
            bg, fg = ("#5a1010", "#ffaaaa")
        self._panel._sessions_label.setStyleSheet(
            f"background: {bg}; color: {fg}; padding: 2px 8px;border-radius: 8px; font-weight: bold;"
        )
        self._panel._sync_session_pollers()
        self._panel._refresh_sessions_table()
        if count > 0:
            self._panel._maybe_start_adaptive()
        else:
            self._panel._stop_adaptive()
            self._panel._reset_host_quality_dot()

    def _sync_session_pollers(self) -> None:
        """Spawn StatsPoller for new sessions; stop pollers for gone ones."""
        if self._panel._multi_host is None:
            for poller in list(self._panel._session_pollers.values()):
                poller.stop()
            self._panel._session_pollers.clear()
            self._panel._session_cache.reset()
            return
        active_sids = {s["session_id"] for s in self._panel._multi_host.list_sessions()}
        for sid in list(self._panel._session_pollers.keys()):
            if sid not in active_sids:
                self._panel._session_pollers[sid].stop()
                del self._panel._session_pollers[sid]
                self._panel._session_cache.drop(sid)
        for sid in active_sids:
            if sid in self._panel._session_pollers:
                continue
            pc = self._panel._multi_host.session_pc(sid)
            if pc is None:
                continue
            poller = StatsPoller(
                pc, self._panel._sessions.callback("host", self._panel._make_session_stats_handler(sid)), interval_s=1.0
            )
            start_native(poller.start, self._panel)
            self._panel._session_pollers[sid] = poller

    def _make_session_stats_handler(self, session_id: str) -> Callable[[StatsSnapshot], None]:
        """Closure capturing session_id for the per-session poller."""

        def _handle(snapshot: StatsSnapshot) -> None:
            default_webrtc_inspector().record(snapshot)
            color = self._panel._quality_color(snapshot)
            self._panel._session_cache.set(session_id, color=color, snapshot=snapshot)
            host = self._panel._multi_host
            self._panel._signals.session_count.emit(host.session_count() if host else 0)

        return _handle

    def _refresh_sessions_table(self) -> None:
        # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
        from datetime import (
            datetime,
        )

        # pylint: enable=import-outside-toplevel
        # pylint: disable=no-name-in-module,import-outside-toplevel  # reason: lazy optional/cyclic boundary
        from PySide6.QtGui import (
            QColor,
        )
        # pylint: enable=no-name-in-module,import-outside-toplevel

        if self._panel._multi_host is None:
            self._panel._sessions_table.setRowCount(0)
            return
        sessions = self._panel._multi_host.list_sessions()
        self._panel._sessions_table.setRowCount(len(sessions))
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
            color = self._panel._session_cache.get_color(sid)
            dot_item = QTableWidgetItem("●")
            dot_item.setForeground(QColor(color))
            dot_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            dot_item.setToolTip(self._panel._format_quality_tooltip(self._panel._session_cache.get_snapshot(sid)))
            self._panel._sessions_table.setItem(row, 0, dot_item)
            id_item = QTableWidgetItem(sid[:8] if sid else "")
            id_item.setData(Qt.ItemDataRole.UserRole, sid)
            self._panel._sessions_table.setItem(row, 1, id_item)
            self._panel._sessions_table.setItem(row, 2, QTableWidgetItem(vid[:12] if vid else ""))
            self._panel._sessions_table.setItem(row, 3, QTableWidgetItem(state))
            self._panel._sessions_table.setItem(row, 4, QTableWidgetItem(connected))

    def _on_sessions_context_menu(self, position: QPoint) -> None:
        # pylint: disable=no-name-in-module,import-outside-toplevel  # reason: lazy optional/cyclic boundary
        from PySide6.QtWidgets import (
            QMenu,
        )
        # pylint: enable=no-name-in-module,import-outside-toplevel

        if self._panel._multi_host is None:
            return
        row = self._panel._sessions_table.rowAt(position.y())
        if row < 0:
            return
        self._panel._sessions_table.selectRow(row)
        sid_item = self._panel._sessions_table.item(row, 1)
        viewer_item = self._panel._sessions_table.item(row, 2)
        if sid_item is None:
            return
        sid = sid_item.data(Qt.ItemDataRole.UserRole) or ""
        viewer_id = viewer_item.text() if viewer_item is not None else ""
        menu = QMenu(self._panel._sessions_table)
        actions = {
            "disconnect": menu.addAction(_t("rd_webrtc_disconnect_selected")),
            "trust": menu.addAction(_t("rd_webrtc_sess_trust_viewer")),
            "copy": menu.addAction(_t("rd_webrtc_sess_copy_id")),
        }
        actions["trust"].setEnabled(bool(viewer_id))
        chosen = menu.exec(self._panel._sessions_table.viewport().mapToGlobal(position))
        self._panel._dispatch_session_menu(chosen, actions, sid, viewer_id)

    def _dispatch_session_menu(self, chosen: Optional[QAction], actions: dict[str, Any],
                               sid: str, viewer_id: str) -> None:
        """Run the action chosen from the sessions context menu."""
        if chosen is actions["disconnect"]:
            self._panel._on_disconnect_selected()
        elif chosen is actions["trust"] and viewer_id:
            self._panel._trust_session_viewer(sid)
        elif chosen is actions["copy"] and sid:
            self._panel._copy_session_id_to_clipboard(sid)

    def _trust_session_viewer(self, sid: str) -> None:
        try:
            multi_host = self._panel._require_multi_host()
            with multi_host._lock:
                host = multi_host._sessions.get(sid)
            full_vid = host.pending_viewer_id if host is not None else None
            if full_vid:
                self._panel._trust_list.add(full_vid, label=f"sess {sid[:6]}")
                self._panel._refresh_trusted_list()
        except (RuntimeError, OSError, ValueError) as error:
            autocontrol_logger.warning("trust viewer: %r", error)

    @staticmethod
    def _copy_session_id_to_clipboard(sid: str) -> None:
        # pylint: disable=no-name-in-module,import-outside-toplevel  # reason: lazy optional/cyclic boundary
        from PySide6.QtWidgets import (
            QApplication,
        )
        # pylint: enable=no-name-in-module,import-outside-toplevel

        clip = QApplication.clipboard()
        if clip is not None:
            clip.setText(sid)

    def _on_disconnect_selected(self) -> None:
        if self._panel._multi_host is None:
            return
        row = self._panel._sessions_table.currentRow()
        if row < 0:
            return
        item = self._panel._sessions_table.item(row, 1)
        if item is None:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(sid, str) or not sid:
            return
        try:
            self._panel._multi_host.stop_session(sid)
        except (KeyError, RuntimeError, OSError) as error:
            autocontrol_logger.warning("disconnect session: %r", error)
        self._panel._signals.session_count.emit(self._panel._multi_host.session_count())

    def _on_session_ended(self, role: str) -> None:
        if role == "host":
            self._panel._stop_host_if_any()

    def dispose_background(self) -> None:
        """Stop owned publication and pollers without accessing disposed widgets."""
        # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
        from je_auto_control.gui.remote_desktop.webrtc_common import (
            dispose_background,
        )
        # pylint: enable=import-outside-toplevel

        self._tasks.cancel_owner(self._panel)
        retire_worker(self._panel._publish_loop)
        callbacks: list[Callable[[], None]] = []
        callbacks.extend(
            resource.stop
            for resource in (
                self._panel._adaptive_poller,
                self._panel._lan_advertiser,
                *self._panel._session_pollers.values(),
            )
            if resource is not None
        )
        dispose_background(callbacks)

    def _stop_host_if_any(self) -> None:
        self._tasks.cancel_owner(self._panel)
        owned = self._panel._sessions.id("host") is not None
        if owned:
            self._panel._sessions.close("host")
        self._panel._stop_adaptive()
        self._panel._stop_lan_advertise()
        if self._panel._annotation_overlay is not None:
            self._panel._annotation_overlay.clear()
            self._panel._annotation_overlay.hide()
        for poller in list(self._panel._session_pollers.values()):
            poller.stop()
        self._panel._session_pollers.clear()
        self._panel._session_cache.reset()
        retire_worker(self._panel._publish_loop)
        self._panel._publish_loop = None
        if self._panel._viewer_screen_window is not None:
            self._panel._viewer_screen_window.set_image(None)
            self._panel._viewer_screen_window.hide()
        if self._panel._multi_host is None:
            return
        if not owned:
            _submit_cleanup((self._panel._multi_host.stop_all,))
        self._panel._multi_host = None
        self._panel._manual_session_id = None
        self._panel._set_hosting(False)

    def _set_hosting(self, hosting: bool) -> None:
        if self._panel._tray is not None:
            self._panel._tray.set_hosting(hosting)

    def _on_state(self, state: str) -> None:
        self._panel._status_label.setText(f"{_t('rd_webrtc_state_label')} {state}")

    def _on_auth(self, ok: bool) -> None:
        key = "rd_webrtc_auth_ok" if ok else "rd_webrtc_auth_fail"
        self._panel._status_label.setText(_t(key))

    def _show_error(self, error: Exception) -> None:
        autocontrol_logger.warning("webrtc host panel error: %r", error)
        QMessageBox.warning(self._panel, "WebRTC", str(error))
