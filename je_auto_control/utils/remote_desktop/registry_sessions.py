"""Session ownership operations shared by transport-specific registry adapters."""

from __future__ import annotations

from typing import Any, Callable, Optional
from contextlib import AbstractContextManager

from je_auto_control.utils.remote_desktop.sessions import (
    RemoteSession,
    RemoteSessionError,
    SessionDirectory,
    SessionStatus,
)


class RegistrySessions:
    """Keep GUI ownership independent from legacy script transport aliases."""

    _sessions: SessionDirectory
    _operation_lock: Any

    def reserve_session(
        self, *, owner: str, transport: str, role: str, session_id: Optional[str] = None, script_default: bool = False
    ) -> RemoteSession:
        """Reserve callback identity before starting a connection."""
        return self._sessions.reserve(
            owner=owner, transport=transport, role=role, session_id=session_id, script_default=script_default
        )

    def register_session(
        self,
        resource: Any,
        *,
        owner: str,
        transport: str,
        role: str,
        session_id: Optional[str] = None,
        script_default: bool = False,
    ) -> RemoteSession:
        """Adopt an already allocated resource into an independent owned session."""
        session = self.reserve_session(
            owner=owner, transport=transport, role=role, session_id=session_id, script_default=script_default
        )
        return self._sessions.attach(session.id, resource)

    def attach_session(self, session_id: str, resource: Any, *, active: bool = True) -> RemoteSession:
        """Attach transport state to a reserved identity."""
        return self._sessions.attach(session_id, resource, active=active)

    def activate_session(self, session_id: str) -> RemoteSession:
        """Confirm transport setup without reviving a closed connection."""
        return self._sessions.activate(session_id)

    def get_session(self, session_id: str, *, owner: Optional[str] = None) -> RemoteSession:
        """Read an immutable owned session snapshot."""
        return self._sessions.get(session_id, owner=owner)

    def disconnect_session(
        self, session_id: str, *, owner: Optional[str] = None, timeout: float = 2.0
    ) -> SessionStatus:
        """End only the named session, validating supplied ownership before side effects."""
        return self._sessions.close(session_id, owner=owner, timeout=timeout)

    def _deferred_disconnect(self, session_id: str, *, owner: str) -> Callable[[], SessionStatus]:
        """Revoke an owned GUI identity now; its captured native cleanup can run off Qt."""
        return self._sessions._deferred_close(session_id, owner=owner)

    def _session_operation(self, session: RemoteSession) -> AbstractContextManager[None]:
        """Keep an in-flight native allocation ordered before this session's owned cleanup."""
        return self._sessions._resource_operation(session)

    def script_session_id(self, transport: str, role: str) -> Optional[str]:
        """Read the script transport alias without selecting a GUI resource."""
        return self._sessions.default_id(transport, role)

    def session_events(self, *, owner: Optional[str] = None):
        """Read bounded owner-addressed lifecycle evidence."""
        return self._sessions.events(owner=owner)

    def subscribe_sessions(self, owner: str, callback: Callable[..., Any]) -> Callable[[], None]:
        """Subscribe to lifecycle notifications addressed only to this owner."""
        return self._sessions.subscribe(owner, callback)

    def bind_callback(self, session_id: str, callback: Callable[..., Any]) -> Callable[..., Any]:
        """Retain generation and request limits for one transport callback."""
        return self._sessions.bind(session_id, callback)

    def session_is_current(self, session_id: str, generation: int, *, owner: Optional[str] = None) -> bool:
        """Check the exact session at delivery time, after any queued handoff."""
        return self._sessions.is_current(session_id, generation, owner=owner)

    def session_resource(self, session_id: str, *, owner: Optional[str] = None) -> Any:
        """Read only the named owned transport for GUI operations."""
        session = self.get_session(session_id, owner=owner)
        return self._sessions.resource(session_id, session.transport, session.role)

    def session_snapshot(self, session_id: Optional[str], *, role: str = "viewer") -> dict:
        """Read a GUI-owned transport snapshot; no identity means no owned connection."""
        if session_id is None:
            return {
                "running": False,
                "connected": False,
                "active": False,
                "authenticated": False,
                "port": 0,
                "connected_clients": 0,
                "host_id": None,
            }
        session = self.get_session(session_id)
        prefix = "" if session.transport == "tcp" else session.transport + "_"
        if role != session.role:
            raise RemoteSessionError("session role mismatch")
        getter = getattr(self, prefix + session.role + "_status")
        return getter(session_id=session_id)

    def _resource(self, session_id: Optional[str], transport: str, role: str) -> Any:
        return self._sessions.resource(session_id, transport, role)

    def _disconnect_alias(self, transport: str, role: str, session_id: Optional[str], timeout: float = 2.0) -> None:
        identifier = session_id if session_id is not None else self.script_session_id(transport, role)
        if identifier is not None:
            session = self.get_session(identifier)
            if (session.transport, session.role) != (transport, role):
                raise RemoteSessionError("session transport or role mismatch")
            self.disconnect_session(identifier, timeout=timeout)

    def _status_identity(self, status: dict, transport: str, role: str, session_id: Optional[str]) -> dict:
        identifier = session_id if session_id is not None else self.script_session_id(transport, role)
        if identifier is not None:
            session = self.get_session(identifier)
            status.update(session_id=session.id, owner=session.owner, session_state=session.state)
        return status

    def _compat_slot(self, transport: str, role: str, resource: Any) -> None:
        # Historical private assignment does not take cleanup ownership from its caller.
        self._sessions.replace_compat(transport, role, resource)

    def _allocate_resource(
        self,
        transport: str,
        role: str,
        session_id: Optional[str],
        factory: Callable[[str], Any],
        starter: Callable[[Any], None],
    ) -> str:
        """Serialize script replacements, reserve before setup, and clean up failed/stale setup."""
        with self._operation_lock:
            if session_id is None:
                self._disconnect_alias(transport, role, None)
            session = self.reserve_session(
                owner="script", transport=transport, role=role, session_id=session_id, script_default=session_id is None
            )
            resource = None
            attached = False
            try:
                resource = factory(session.id)
                self.attach_session(session.id, resource, active=False)
                attached = True
                starter(resource)
                self.activate_session(session.id)
            except BaseException:
                try:
                    if resource is not None and not attached:
                        self._sessions.close_resource(resource, session, 2.0)
                finally:
                    self.disconnect_session(session.id)
                raise
            return session.id

    @property
    def _host(self) -> Any:
        return self._resource(None, "tcp", "host")

    @_host.setter
    def _host(self, resource: Any) -> None:
        self._compat_slot("tcp", "host", resource)

    @property
    def _viewer(self) -> Any:
        return self._resource(None, "tcp", "viewer")

    @_viewer.setter
    def _viewer(self, resource: Any) -> None:
        self._compat_slot("tcp", "viewer", resource)

    @property
    def _ws_host(self) -> Any:
        return self._resource(None, "ws", "host")

    @_ws_host.setter
    def _ws_host(self, resource: Any) -> None:
        self._compat_slot("ws", "host", resource)

    @property
    def _ws_viewer(self) -> Any:
        return self._resource(None, "ws", "viewer")

    @_ws_viewer.setter
    def _ws_viewer(self, resource: Any) -> None:
        self._compat_slot("ws", "viewer", resource)

    @property
    def _webrtc_host(self) -> Any:
        return self._resource(None, "webrtc", "host")

    @_webrtc_host.setter
    def _webrtc_host(self, resource: Any) -> None:
        self._compat_slot("webrtc", "host", resource)

    @property
    def _webrtc_viewer(self) -> Any:
        return self._resource(None, "webrtc", "viewer")

    @_webrtc_viewer.setter
    def _webrtc_viewer(self, resource: Any) -> None:
        self._compat_slot("webrtc", "viewer", resource)
