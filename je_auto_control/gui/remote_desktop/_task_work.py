"""Qt-free WebRTC task snapshots and native operations with late-allocation cleanup."""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Callable, Optional, Protocol

from je_auto_control.gui._task_state import CancellationToken, TaskCancelled
from je_auto_control.utils.remote_desktop.cleanup_jobs import _submit_cleanup
from je_auto_control.utils.remote_desktop.registry_sessions import RegistrySessions
from je_auto_control.utils.remote_desktop.sessions import RemoteSession


def run_in_session(directory: RegistrySessions, session: RemoteSession,
                   work: Callable[[CancellationToken], object], token: CancellationToken) -> object:
    """Serialize this native worker with its original session's cleanup, entirely off Qt."""
    token.checkpoint()
    with directory._session_operation(session):  # pylint: disable=protected-access  # reason: internal session allocation/cleanup gate
        return work(token)


def connect_owned(directory: RegistrySessions, session: RemoteSession,
                  connect: Callable[[float], object], token: CancellationToken) -> object:
    """Connect off Qt; revocation prevents new allocation and cleanup waits for this bounded attempt."""
    try:
        with directory._session_operation(session):  # pylint: disable=protected-access  # reason: internal session allocation/cleanup gate
            token.checkpoint()
            connect(min(5.0, token.remaining_s()))
            token.checkpoint()
            if not directory.session_is_current(session.id, session.generation, owner=session.owner):
                raise TaskCancelled('remote connection was revoked')
            directory.activate_session(session.id)
        return session.id
    except BaseException:
        _submit_cleanup((partial(directory.disconnect_session, session.id, owner=session.owner),))
        raise


class HostOperations(Protocol):
    """Native coordinator operations needed by an offer/answer worker."""

    def create_session_offer(self) -> tuple[str, str]:
        """Create one owned peer and its SDP."""

    def accept_session_answer(self, session_id: str, answer_sdp: str) -> None:
        """Apply the reply to the same peer."""

    def stop_session(self, session_id: str) -> None:
        """Release that peer without affecting other sessions."""


class ViewerOperations(Protocol):  # pylint: disable=too-few-public-methods  # reason: one native offer seam
    """Native viewer seam containing no widgets."""

    def process_offer(self, offer_sdp: str, expected_dtls_fingerprint: Optional[str] = None) -> str:
        """Validate the expected fingerprint and return the generated answer."""


class KnownHosts(Protocol):
    """Headless fingerprint store used only for the snapshotted signaling host."""

    def dtls_fingerprint_for(self, host_id: str) -> Optional[str]:
        """Read an existing pin."""

    def remember_dtls_fingerprint(self, host_id: str, fingerprint: str) -> None:
        """Remember a successfully processed offer's pin."""


@dataclass(frozen=True)
class HostOffer:
    """Allocated peer plus the exact native host and GUI directory identity."""

    host: HostOperations
    owner_session_id: str
    peer_id: str
    sdp: str


@dataclass(frozen=True)
class SignalingTarget:
    """Original endpoint and credentials, captured before a native wait."""

    server: str
    host_id: str
    secret: Optional[str]


@dataclass(frozen=True)
class AnswerRequest:
    """Copied request data and independently owned native collaborators, never a widget."""

    viewer: ViewerOperations
    owner_session_id: str
    offer: str
    cleanup: Callable[[], object]
    target: Optional[SignalingTarget] = None
    known_hosts: Optional[KnownHosts] = None
    is_current: Callable[[], bool] = lambda: True


@dataclass(frozen=True)
class ViewerAnswer:
    """The answer tied to the original request, not edited GUI endpoint fields."""

    request: AnswerRequest
    sdp: str


def create_offer(host: HostOperations, owner_session_id: str, current: Callable[[], bool],
                 token: CancellationToken) -> object:
    """Create off Qt and release a peer whose completion becomes cancelled."""
    token.checkpoint()
    if not current():
        raise TaskCancelled('WebRTC host session was revoked')
    peer_id, sdp = host.create_session_offer()
    try:
        token.checkpoint()
        if not current():
            raise TaskCancelled('WebRTC host session was revoked')
    except BaseException:
        _submit_cleanup((partial(host.stop_session, peer_id),))
        raise
    return HostOffer(host, owner_session_id, peer_id, sdp)


def apply_answer(offer: HostOffer, answer: str, current: Callable[[], bool], token: CancellationToken) -> object:
    """Apply only to the allocated peer; cancelled completion cannot retain that peer."""
    token.checkpoint()
    if not current():
        raise TaskCancelled('WebRTC host session was revoked')
    offer.host.accept_session_answer(offer.peer_id, answer)
    try:
        token.checkpoint()
        if not current():
            raise TaskCancelled('WebRTC host session was revoked')
    except BaseException:
        _submit_cleanup((partial(offer.host.stop_session, offer.peer_id),))
        raise
    return offer


def create_answer(request: AnswerRequest, token: CancellationToken) -> object:
    """Read pins/process native SDP off Qt and close only the original owned viewer on cancellation."""
    token.checkpoint()
    if not request.is_current():
        raise TaskCancelled('WebRTC viewer session was revoked')
    known, target = request.known_hosts, request.target
    expected = known.dtls_fingerprint_for(target.host_id) if known is not None and target is not None else None
    try:
        sdp = request.viewer.process_offer(request.offer, expected_dtls_fingerprint=expected)
        token.checkpoint()
        if not request.is_current():
            raise TaskCancelled('WebRTC viewer session was revoked')
        if not expected:
            _remember_pin(request)
        token.checkpoint()
        if not request.is_current():
            raise TaskCancelled('WebRTC viewer session was revoked')
    except BaseException:
        _submit_cleanup((request.cleanup,))
        raise
    return ViewerAnswer(request, sdp)


def _remember_pin(request: AnswerRequest) -> None:
    known, target = request.known_hosts, request.target
    if known is None or target is None:
        return
    # pylint: disable=import-outside-toplevel  # reason: optional native fingerprint parsing
    from je_auto_control.utils.remote_desktop.fingerprint import extract_dtls_fingerprint
    # pylint: enable=import-outside-toplevel
    fingerprint = extract_dtls_fingerprint(request.offer)
    if fingerprint:
        known.remember_dtls_fingerprint(target.host_id, fingerprint)
