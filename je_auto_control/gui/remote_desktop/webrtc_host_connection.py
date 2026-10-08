"""Publishing, manual SDP exchange and shutdown for the WebRTC host panel.

One interaction group of ``webrtc_panel._WebRTCHostPanel``, kept as a mixin so the panel class
still owns every widget and slot under its original name.
"""
from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Optional, Tuple

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QMessageBox,
)

from je_auto_control.gui.remote_desktop._helpers import (
    _t,
)
from je_auto_control.gui.remote_desktop.webrtc_workers import (
    HostPublishLoopWorker, generate_host_id, retire_worker,
)
from je_auto_control.gui.task_controller import CancellationToken, task_controller
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop import (
    MultiViewerHost,
)
from je_auto_control.gui.remote_desktop.webrtc_panel_common import (
    _PanelPart,
    _read_webrtc_config,
)

if TYPE_CHECKING:  # imported lazily at runtime to keep startup cheap
    from je_auto_control.utils.remote_desktop.lan_discovery import HostAdvertiser


def _create_offer(host: MultiViewerHost, _token: CancellationToken) -> Tuple[str, str]:
    """Worker thread: mint a session and its offer (ICE gathering, up to 12 s)."""
    return host.create_session_offer()


def _drop_offer(host: MultiViewerHost, outcome: Tuple[str, str]) -> None:
    """End the session of an offer nobody will show."""
    try:
        host.stop_session(outcome[0])
    except (KeyError, RuntimeError, OSError) as error:
        autocontrol_logger.debug("dropping an unused offer: %r", error)


class _HostConnectionMixin(_PanelPart):
    """Methods of ``_WebRTCHostPanel``; the module docstring says which group."""

    # State this group owns; the panel's __init__ sets the starting values.
    _publish_loop: Optional[HostPublishLoopWorker]
    _manual_session_id: Optional[str]
    _lan_advertiser: Optional[HostAdvertiser]

    def _on_regen_id(self) -> None:
        self._host_id_edit.setText(generate_host_id())

    def _on_publish_via_server(self) -> None:
        if not self._validate_required_fields(needs_server=True):
            return
        self._stop_host_if_any()
        try:
            self._multi_host = self._build_multi_host(
                self._token_edit.text().strip(),
            )
        except (ValueError, RuntimeError, OSError) as error:
            self._show_error(error)
            return
        self._set_hosting(True)
        self._publish_loop = HostPublishLoopWorker(
            multi_host=self._multi_host,
            server_url=self._server_edit.text().strip(),
            host_id=self._host_id_edit.text().strip(),
            secret=self._secret_edit.text() or None,
        )
        self._publish_loop.offer_published.connect(self._on_loop_offer_published)
        self._publish_loop.session_connected.connect(self._on_loop_session_connected)
        self._publish_loop.failed.connect(self._on_signaling_failed)
        self._status_label.setText(_t("rd_webrtc_publishing_offer"))
        self._publish_loop.start()
        self._start_lan_advertise()

    def _start_lan_advertise(self) -> None:
        try:
            from je_auto_control.utils.remote_desktop.lan_discovery import (
                HostAdvertiser, is_discovery_available,
            )
        except ImportError:
            return
        if not is_discovery_available():
            return
        try:
            if self._lan_advertiser is not None:
                self._lan_advertiser.stop()
            self._lan_advertiser = HostAdvertiser(
                host_id=self._host_id_edit.text().strip(),
                signaling_url=self._server_edit.text().strip(),
            )
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("lan advertise: %r", error)

    def _stop_lan_advertise(self) -> None:
        if self._lan_advertiser is not None:
            try:
                self._lan_advertiser.stop()
            except (RuntimeError, OSError):
                pass
            self._lan_advertiser = None

    def _on_loop_offer_published(self, session_id: str) -> None:
        autocontrol_logger.debug("publish loop: offer for %s", session_id)

        # Optional: surface the session in the UI; for now just log.

    def _on_loop_session_connected(self, session_id: str) -> None:
        if self._multi_host is not None:
            self._signals.session_count.emit(self._multi_host.session_count())

    def _on_signaling_failed(self, message: str) -> None:
        QMessageBox.warning(self, "WebRTC", message)
        self._status_label.setText(_t("rd_webrtc_status_idle"))

    def _on_generate_offer(self) -> None:
        token = self._token_edit.text().strip()
        if not token:
            QMessageBox.warning(self, "WebRTC", _t("rd_webrtc_token_required"))
            return
        try:
            if self._multi_host is None:
                self._multi_host = self._build_multi_host(token)
        except (ValueError, RuntimeError, OSError) as error:
            self._show_error(error)
            return
        self._set_hosting(True)
        self._status_label.setText(_t("rd_webrtc_generating_offer"))
        self._offer_view.setPlainText("")
        QTimer.singleShot(0, self, self._produce_offer)

    def _require_multi_host(self) -> MultiViewerHost:
        """Return the running host, or say the session is not up yet."""
        host = self._multi_host
        if host is None:
            raise RuntimeError(_t("rd_webrtc_not_started"))
        return host

    def _produce_offer(self) -> None:
        try:
            host = self._require_multi_host()
        except RuntimeError as error:
            self._show_error(error)
            return
        # create_session_offer waits for ICE gathering (up to 12 s), which
        # used to freeze the window; the backend takes no timeout or cancel.
        task = task_controller().submit(functools.partial(_create_offer, host), owner=self,
                                        discard=functools.partial(_drop_offer, host))
        task.result.connect(functools.partial(self._show_offer, host))
        task.error.connect(functools.partial(self._show_offer_error, host))

    def _show_offer_error(self, host: MultiViewerHost, error: Exception) -> None:
        if self._multi_host is host:        # a host stopped meanwhile fails by design
            self._show_error(error)

    def _show_offer(self, host: MultiViewerHost, outcome: Tuple[str, str]) -> None:
        """GUI thread: the offer is ready -- unless the host was stopped or replaced meanwhile."""
        if self._multi_host is not host:
            _drop_offer(host, outcome)
            return
        session_id, offer = outcome
        self._manual_session_id = session_id
        self._offer_view.setPlainText(offer)
        self._status_label.setText(_t("rd_webrtc_offer_ready"))

    def _on_apply_answer(self) -> None:
        if self._multi_host is None or not self._manual_session_id:
            QMessageBox.warning(self, "WebRTC", _t("rd_webrtc_no_offer_yet"))
            return
        answer = self._answer_input.toPlainText().strip()
        if not answer:
            QMessageBox.warning(self, "WebRTC", _t("rd_webrtc_no_answer"))
            return
        try:
            self._multi_host.accept_session_answer(self._manual_session_id, answer)
            self._status_label.setText(_t("rd_webrtc_answer_applied"))
        except (ValueError, RuntimeError, OSError, KeyError) as error:
            self._show_error(error)
            return
        self._manual_session_id = None  # consumed; next Generate creates new session

    def _on_stop(self) -> None:
        self._stop_host_if_any()
        self._status_label.setText(_t("rd_webrtc_status_idle"))
        self._signals.session_count.emit(0)

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

    def _build_multi_host(self, token: str) -> MultiViewerHost:
        whitelist_text = self._ip_whitelist_edit.toPlainText().strip()
        whitelist = [line.strip() for line in whitelist_text.splitlines()
                     if line.strip() and not line.strip().startswith("#")]
        host = MultiViewerHost(
            token=token,
            config=_read_webrtc_config(self),
            trust_list=self._trust_list,
            read_only=self._readonly_check.isChecked(),
            ip_whitelist=whitelist,
            on_annotation=self._signals.annotation.emit,
            on_session_state=lambda _sid, state: self._signals.state.emit(state),
            on_session_authenticated=self._on_session_authed,
            on_pending_viewer=self._signals.pending_viewer.emit,
        )
        return host

    def _stop_host_if_any(self) -> None:
        self._stop_adaptive()
        self._stop_lan_advertise()
        if self._annotation_overlay is not None:
            self._annotation_overlay.clear()
            self._annotation_overlay.hide()
        # Snapshot before clear(), as in _refresh_session_pollers.
        for poller in list(self._session_pollers.values()):  # NOSONAR python:S7504
            poller.stop()
        self._session_pollers.clear()
        self._session_cache.reset()
        retire_worker(self._publish_loop)
        self._publish_loop = None
        if self._viewer_screen_window is not None:
            self._viewer_screen_window.set_image(None)
            self._viewer_screen_window.hide()
        if self._multi_host is None:
            return
        try:
            self._multi_host.stop_all()
        except (RuntimeError, OSError):
            pass
        finally:
            self._multi_host = None
            self._manual_session_id = None
            self._set_hosting(False)


__all__ = ["_HostConnectionMixin"]
