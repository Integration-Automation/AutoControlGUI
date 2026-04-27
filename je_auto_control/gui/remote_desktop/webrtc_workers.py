"""Background QThread workers for the WebRTC signaling-server flow.

The signaling client is sync (urllib + polling), so we can't call it from
the Qt thread without freezing the UI. These workers wrap the calls and
emit thread-safe signals carrying the SDP strings or any error message.
"""
from __future__ import annotations

import secrets
from typing import Optional

from PySide6.QtCore import QThread, Signal

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop import signaling_client


def generate_host_id() -> str:
    """Return an 8-char alphanumeric host_id (collision-resistant for casual use)."""
    return secrets.token_hex(4)


class HostSignalingWorker(QThread):
    """Host side: push an offer, poll for an answer."""

    answer_ready = Signal(str)
    failed = Signal(str)

    def __init__(self, *, server_url: str, host_id: str, secret: Optional[str],
                 offer_sdp: str, timeout_s: float = 60.0,
                 parent=None) -> None:
        super().__init__(parent)
        self._server_url = server_url
        self._host_id = host_id
        self._secret = secret
        self._offer_sdp = offer_sdp
        self._timeout_s = timeout_s

    def run(self) -> None:
        try:
            signaling_client.push_offer(
                self._server_url, self._host_id, self._offer_sdp,
                secret=self._secret,
            )
            answer = signaling_client.wait_for_answer(
                self._server_url, self._host_id,
                secret=self._secret, timeout_s=self._timeout_s,
            )
        except signaling_client.SignalingError as error:
            autocontrol_logger.warning("host signaling: %r", error)
            self.failed.emit(str(error))
            return
        self.answer_ready.emit(answer)


class ViewerSignalingWorker(QThread):
    """Viewer side: poll for the host's offer (so the host can prepare it)."""

    offer_ready = Signal(str)
    failed = Signal(str)

    def __init__(self, *, server_url: str, host_id: str, secret: Optional[str],
                 timeout_s: float = 60.0, parent=None) -> None:
        super().__init__(parent)
        self._server_url = server_url
        self._host_id = host_id
        self._secret = secret
        self._timeout_s = timeout_s

    def run(self) -> None:
        try:
            offer = signaling_client.wait_for_offer(
                self._server_url, self._host_id,
                secret=self._secret, timeout_s=self._timeout_s,
            )
        except signaling_client.SignalingError as error:
            autocontrol_logger.warning("viewer signaling: %r", error)
            self.failed.emit(str(error))
            return
        self.offer_ready.emit(offer)


class ViewerAnswerPushWorker(QThread):
    """Viewer side: push the generated answer back to the signaling server."""

    pushed = Signal()
    failed = Signal(str)

    def __init__(self, *, server_url: str, host_id: str, secret: Optional[str],
                 answer_sdp: str, parent=None) -> None:
        super().__init__(parent)
        self._server_url = server_url
        self._host_id = host_id
        self._secret = secret
        self._answer_sdp = answer_sdp

    def run(self) -> None:
        try:
            ok = signaling_client.push_answer(
                self._server_url, self._host_id, self._answer_sdp,
                secret=self._secret,
            )
        except signaling_client.SignalingError as error:
            self.failed.emit(str(error))
            return
        if not ok:
            self.failed.emit("server reported no offer to match")
            return
        self.pushed.emit()


class HostPublishLoopWorker(QThread):
    """Multi-viewer host loop: publish offer → wait answer → accept → repeat.

    Each iteration mints a fresh ``session_id`` via
    ``MultiViewerHost.create_session_offer()`` and serves it through the
    same signaling slot. Because signaling stores at most one pending
    offer per ``host_id``, this serializes new viewers (one connect at a
    time) but supports any number of established sessions.
    """

    offer_published = Signal(str)        # session_id
    session_connected = Signal(str)      # session_id (after accept_answer)
    failed = Signal(str)

    def __init__(self, *, multi_host, server_url: str, host_id: str,
                 secret: Optional[str],
                 wait_timeout_s: float = 600.0,
                 retry_delay_s: float = 2.0,
                 parent=None) -> None:
        super().__init__(parent)
        self._multi_host = multi_host
        self._server_url = server_url
        self._host_id = host_id
        self._secret = secret
        self._wait_timeout_s = wait_timeout_s
        self._retry_delay_s = retry_delay_s

    def run(self) -> None:
        while not self.isInterruptionRequested():
            session_id = None
            try:
                session_id, offer = self._multi_host.create_session_offer()
                signaling_client.push_offer(
                    self._server_url, self._host_id, offer,
                    secret=self._secret,
                )
                self.offer_published.emit(session_id)
                answer = signaling_client.wait_for_answer(
                    self._server_url, self._host_id,
                    secret=self._secret, timeout_s=self._wait_timeout_s,
                )
                self._multi_host.accept_session_answer(session_id, answer)
                self.session_connected.emit(session_id)
            except signaling_client.SignalingError as error:
                # Timeout waiting for answer is expected when no one connects.
                if "no answer" in str(error):
                    if session_id is not None:
                        self._safe_stop_session(session_id)
                    continue
                self.failed.emit(str(error))
                if session_id is not None:
                    self._safe_stop_session(session_id)
                return
            except (ValueError, RuntimeError, OSError) as error:
                autocontrol_logger.warning("publish loop: %r", error)
                self.failed.emit(str(error))
                if session_id is not None:
                    self._safe_stop_session(session_id)
                return

    def _safe_stop_session(self, session_id: str) -> None:
        try:
            self._multi_host.stop_session(session_id)
        except (KeyError, RuntimeError, OSError) as error:
            autocontrol_logger.debug("loop session cleanup: %r", error)


__all__ = [
    "generate_host_id",
    "HostSignalingWorker",
    "ViewerSignalingWorker",
    "ViewerAnswerPushWorker",
    "HostPublishLoopWorker",
]
