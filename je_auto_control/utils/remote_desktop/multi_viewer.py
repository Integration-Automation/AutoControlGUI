"""Coordinator that runs one ``WebRTCDesktopHost`` per connected viewer.

Capture (mss + cursor + cursor overlay) happens once; aiortc's
:class:`MediaRelay` distributes the same frames to every active
PeerConnection. Each viewer gets its own DataChannel for input + auth, so
trust list, read-only mode, and accept/reject all keep working unchanged
on a per-viewer basis.
"""
from __future__ import annotations

import secrets
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

try:
    from aiortc.contrib.media import MediaRelay  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Multi-viewer host requires the 'webrtc' extra (aiortc).",
    ) from exc

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.input_dispatch import dispatch_input
from je_auto_control.utils.remote_desktop.permissions import SessionPermissions
from je_auto_control.utils.remote_desktop.trust_list import TrustList
from je_auto_control.utils.remote_desktop.webrtc_host import WebRTCDesktopHost
from je_auto_control.utils.remote_desktop.webrtc_transport import (
    ScreenVideoTrack, WebRTCConfig,
)


SessionStateCallback = Callable[[str, str], None]
SessionAuthCallback = Callable[[str], None]
SessionPendingCallback = Callable[[str, Optional[str]], None]


class _ScreenSource:
    """Owns a single ScreenVideoTrack + MediaRelay for distribution."""

    def __init__(self, config: WebRTCConfig) -> None:
        self._track = ScreenVideoTrack(
            monitor_index=config.monitor_index,
            fps=config.fps,
            region=config.region,
            show_cursor=config.show_cursor,
        )
        self._relay = MediaRelay()

    def subscribe(self):
        return self._relay.subscribe(self._track)

    def stop(self) -> None:
        self._track.stop()


class MultiViewerHost:
    """Runs N concurrent ``WebRTCDesktopHost`` instances over one capture.

    Use :meth:`create_session_offer` per incoming viewer to mint a fresh
    session; pass the returned ``session_id`` back into
    :meth:`accept_session_answer`. Existing single-viewer GUI flows can
    keep using ``WebRTCDesktopHost`` directly.
    """

    def __init__(self, *, token: str,
                 config: Optional[WebRTCConfig] = None,
                 trust_list: Optional[TrustList] = None,
                 read_only: bool = False,
                 permissions: Optional[SessionPermissions] = None,
                 input_dispatcher: Optional[Callable[[Mapping[str, Any]], Any]] = None,
                 ip_whitelist: Optional[list] = None,
                 on_annotation: Optional[Callable[[dict], None]] = None,
                 on_session_state: Optional[SessionStateCallback] = None,
                 on_session_authenticated: Optional[SessionAuthCallback] = None,
                 on_pending_viewer: Optional[SessionPendingCallback] = None,
                 ) -> None:
        if not token:
            raise ValueError("MultiViewerHost requires a non-empty token")
        self._token = token
        self._config = config or WebRTCConfig()
        self._trust_list = trust_list
        self._permissions = (
            permissions if permissions is not None
            else SessionPermissions.from_read_only(read_only)
        )
        self._dispatch = input_dispatcher or dispatch_input
        self._ip_whitelist = list(ip_whitelist) if ip_whitelist else []
        self._on_annotation = on_annotation
        self._on_session_state = on_session_state
        self._on_session_authenticated = on_session_authenticated
        self._on_pending_viewer = on_pending_viewer
        self._sessions: Dict[str, WebRTCDesktopHost] = {}
        self._session_meta: Dict[str, dict] = {}
        self._source: Optional[_ScreenSource] = None
        self._lock = threading.Lock()

    # --- session lifecycle --------------------------------------------------

    def create_session_offer(self) -> Tuple[str, str]:
        """Mint a new session: returns ``(session_id, offer_sdp)``."""
        with self._lock:
            if self._source is None:
                self._source = _ScreenSource(self._config)
            session_id = secrets.token_hex(8)
            host = WebRTCDesktopHost(
                token=self._token,
                config=self._config,
                trust_list=self._trust_list,
                permissions=self._permissions,
                input_dispatcher=self._dispatch,
                ip_whitelist=self._ip_whitelist,
                on_annotation=self._on_annotation,
                external_video_track=self._source.subscribe(),
                on_state_change=self._wrap_state_callback(session_id),
                on_authenticated=self._wrap_auth_callback(session_id),
                on_pending_viewer=self._wrap_pending_callback(session_id),
            )
            self._sessions[session_id] = host
        offer = host.create_offer(peer_label=f"viewer-{session_id[:6]}")
        return session_id, offer

    def accept_session_answer(self, session_id: str, answer_sdp: str) -> None:
        host = self._require_session(session_id)
        host.accept_answer(answer_sdp)

    def stop_session(self, session_id: str) -> None:
        with self._lock:
            host = self._sessions.pop(session_id, None)
            self._session_meta.pop(session_id, None)
        if host is not None:
            try:
                host.stop()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("stop session %s: %r", session_id, error)
        self._maybe_release_source()

    def stop_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.items())
            self._sessions.clear()
            self._session_meta.clear()
        for session_id, host in sessions:
            try:
                host.stop()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("stop_all %s: %r", session_id, error)
        self._maybe_release_source()

    def _maybe_release_source(self) -> None:
        with self._lock:
            if self._sessions or self._source is None:
                return
            source = self._source
            self._source = None
        source.stop()

    # --- per-session controls -----------------------------------------------

    def approve_pending_viewer(self, session_id: str) -> None:
        self._require_session(session_id).approve_pending_viewer()

    def reject_pending_viewer(self, session_id: str) -> None:
        self._require_session(session_id).reject_pending_viewer()

    def trust_pending_viewer(self, session_id: str, label: str = "") -> None:
        self._require_session(session_id).trust_pending_viewer(label=label)

    def pending_viewer_id(self, session_id: str) -> Optional[str]:
        return self._require_session(session_id).pending_viewer_id

    def set_read_only(self, value: bool) -> None:
        """Backwards-compat shim around :meth:`set_permissions`."""
        self.set_permissions(SessionPermissions.from_read_only(bool(value)))

    def set_permissions(self, permissions: SessionPermissions) -> None:
        """Update permissions for new sessions and propagate to active ones."""
        self._permissions = permissions
        with self._lock:
            sessions = list(self._sessions.values())
        for host in sessions:
            try:
                host.set_permissions(permissions)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("permissions set: %r", error)

    @property
    def permissions(self) -> SessionPermissions:
        return self._permissions

    def disable_accept_viewer_video(self) -> None:
        """Inactivate the recvonly video slot on every active session."""
        with self._lock:
            sessions = list(self._sessions.values())
        for host in sessions:
            try:
                host.disable_accept_viewer_video()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("disable accept video: %r", error)

    def disable_accept_viewer_audio_opus(self) -> None:
        """Inactivate the recvonly audio slot on every active session."""
        with self._lock:
            sessions = list(self._sessions.values())
        for host in sessions:
            try:
                host.disable_accept_viewer_audio_opus()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("disable accept audio: %r", error)

    def broadcast_file(self, local_path, remote_name=None) -> int:
        """Push a file to every authenticated viewer; returns recipient count."""
        with self._lock:
            sessions = list(self._sessions.values())
        sent = 0
        for host in sessions:
            if not host.authenticated:
                continue
            try:
                host.push_file(local_path, remote_name=remote_name)
                sent += 1
            except (RuntimeError, OSError, ValueError) as error:
                autocontrol_logger.warning("broadcast_file: %r", error)
        return sent

    # --- introspection ------------------------------------------------------

    def list_sessions(self) -> List[dict]:
        with self._lock:
            return [
                {
                    "session_id": sid,
                    "authenticated": host.authenticated,
                    "state": host.connection_state,
                    "pending_viewer_id": host.pending_viewer_id,
                    "connected_at": (
                        self._session_meta.get(sid, {}).get("connected_at")
                    ),
                }
                for sid, host in self._sessions.items()
            ]

    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def screen_track(self):
        """Return the underlying ``ScreenVideoTrack`` (or None if no source)."""
        with self._lock:
            return None if self._source is None else self._source._track

    def first_session_pc(self):
        """Return the first session's RTCPeerConnection, or None."""
        with self._lock:
            for host in self._sessions.values():
                if host._pc is not None:
                    return host._pc
            return None

    def session_pc(self, session_id: str):
        """Return the named session's RTCPeerConnection, or None if gone."""
        with self._lock:
            host = self._sessions.get(session_id)
        return host._pc if host is not None else None

    def _require_session(self, session_id: str) -> WebRTCDesktopHost:
        with self._lock:
            host = self._sessions.get(session_id)
        if host is None:
            raise KeyError(f"unknown session_id: {session_id}")
        return host

    # --- callback wrappers --------------------------------------------------

    def _wrap_state_callback(self, session_id: str):
        cb = self._on_session_state
        if cb is None:
            return None
        def _emit(state: str) -> None:
            try:
                cb(session_id, state)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("session state cb: %r", error)
        return _emit

    def _wrap_auth_callback(self, session_id: str):
        cb = self._on_session_authenticated
        def _emit() -> None:
            with self._lock:
                meta = self._session_meta.setdefault(session_id, {})
                meta["connected_at"] = datetime.now(timezone.utc).isoformat()
            if cb is None:
                return
            try:
                cb(session_id)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("session auth cb: %r", error)
        return _emit

    def _wrap_pending_callback(self, session_id: str):
        cb = self._on_pending_viewer
        if cb is None:
            return None
        def _emit() -> None:
            host = self._sessions.get(session_id)
            viewer_id = host.pending_viewer_id if host is not None else None
            try:
                cb(session_id, viewer_id)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("pending cb: %r", error)
        return _emit


__all__ = ["MultiViewerHost"]
