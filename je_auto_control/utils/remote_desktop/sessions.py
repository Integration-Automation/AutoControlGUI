"""Owned remote resources, script aliases and bounded lifecycle evidence."""
# pylint: disable=cyclic-import  # reason: lazy public wrappers resolve the initialized registry singleton

from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.request_context import RequestBinding
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.rbac.authorization import require_command


class RemoteSessionError(AutoControlException, ValueError):
    """A session identity, role, transport or lifecycle transition is invalid."""


class SessionOwnershipError(AutoControlException, PermissionError):
    """The supplied lifecycle owner does not own the requested session."""


@dataclass(frozen=True)
class RemoteSession:
    """Immutable connection identity; resources and credentials stay private."""

    id: str
    owner: str
    transport: str
    role: str
    state: str
    generation: int

    @property
    def connected(self) -> bool:
        """Whether the session has completed its local allocation/connection."""
        return self.state == "active"


SessionStatus = RemoteSession


@dataclass(frozen=True)
class SessionEvent:
    """Owner-addressed lifecycle evidence, without resource or authorization data."""

    session_id: str
    owner: str
    transport: str
    role: str
    state: str
    generation: int


class SessionDirectory:  # pylint: disable=too-many-instance-attributes  # reason: explicit owned lifecycle/widget state
    """Serialize ownership changes; keep independent defaults for each script transport."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, RemoteSession] = {}
        self._resources: Dict[str, Any] = {}
        self._bindings: Dict[str, RequestBinding] = {}
        self._aliases: Dict[Tuple[str, str], str] = {}
        self._events: deque[SessionEvent] = deque(maxlen=1024)
        self._generation = 0
        self._listeners: Dict[str, Tuple[str, RequestBinding, Callable[[SessionEvent], None]]] = {}

    def reserve(
        self, *, owner: str, transport: str, role: str, session_id: Optional[str] = None, script_default: bool = False
    ) -> RemoteSession:
        """Allocate a fresh connecting identity before wiring any transport callbacks."""
        require_command("remote_session_create")
        self._validate_identity(owner, transport, role)
        identifier = uuid.uuid4().hex if session_id is None else session_id
        if not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 256:
            raise RemoteSessionError("session ID must be a nonempty bounded string")
        with self._lock:
            if identifier in self._sessions:
                raise RemoteSessionError("session ID already allocated")
            self._generation += 1
            session = RemoteSession(identifier, owner, transport, role, "connecting", self._generation)
            self._sessions[identifier] = session
            self._bindings[identifier] = RequestBinding.capture()
            if script_default:
                self._aliases[transport, role] = identifier
            self._prune()
            return session

    @staticmethod
    def _validate_identity(owner: str, transport: str, role: str) -> None:
        if not isinstance(owner, str) or not owner.strip():
            raise RemoteSessionError("session owner must be a nonempty string")
        if transport not in {"tcp", "ws", "webrtc"} or role not in {"host", "viewer"}:
            raise RemoteSessionError("invalid session transport or role")

    def attach(self, session_id: str, resource: Any, *, active: bool = True) -> RemoteSession:
        """Attach exactly one resource; a cancelled allocation cannot acquire a new resource."""
        require_command("remote_session_create")
        with self._lock:
            session = self.get(session_id)
            if session.state != "connecting" or session_id in self._resources:
                raise RemoteSessionError("session cannot acquire this resource")
            self._resources[session_id] = resource
            return self._transition(session_id, "active") if active else session

    def activate(self, session_id: str) -> RemoteSession:
        """Confirm a still-owned connection after transport setup has completed."""
        with self._lock:
            if self.get(session_id).state != "connecting" or session_id not in self._resources:
                raise RemoteSessionError("connection completed after its session ended")
            return self._transition(session_id, "active")

    def get(self, session_id: str, *, owner: Optional[str] = None) -> RemoteSession:
        """Read a known session, checking its owner when supplied."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise RemoteSessionError("unknown remote session")
            if owner is not None and owner != session.owner:
                raise SessionOwnershipError("remote session owner mismatch")
            return session

    def resource(self, session_id: Optional[str], transport: str, role: str) -> Any:
        """Resolve a named resource or its script alias without changing any default."""
        with self._lock:
            identifier = session_id if session_id is not None else self._aliases.get((transport, role))
            if identifier is None:
                return None
            session = self.get(identifier)
            if (session.transport, session.role) != (transport, role):
                raise RemoteSessionError("session transport or role mismatch")
            return self._resources.get(identifier) if session.state in {"connecting", "active"} else None

    def default_id(self, transport: str, role: str) -> Optional[str]:
        """Return only the script default, never the most recently opened GUI session."""
        with self._lock:
            return self._aliases.get((transport, role))

    def replace_compat(self, transport: str, role: str, resource: Any) -> None:
        """Preserve private-slot injection; the assigning caller owns old-resource cleanup."""
        with self._lock:
            previous = self.default_id(transport, role)
            if previous is not None:
                self._resources.pop(previous, None)
                self._transition(previous, "closed")
                self._aliases.pop((transport, role), None)
            if resource is not None:
                session = self.reserve(owner="script", transport=transport, role=role, script_default=True)
                self.attach(session.id, resource)
            self._prune()

    def close(self, session_id: str, *, owner: Optional[str] = None, timeout: float = 2.0) -> SessionStatus:
        """Revoke delivery first, then stop only the named owned transport resource."""
        require_command("remote_session_disconnect")
        with self._lock:
            session = self.get(session_id, owner=owner)
            if session.state in {"closing", "closed"}:
                return session
            resource = self._resources.get(session_id)
            binding = self._bindings[session_id]
            self._transition(session_id, "closing")
        try:
            if resource is not None:
                binding.run(self.close_resource, resource, session, timeout)
        except BaseException:
            with self._lock:
                self._transition(session_id, "failed")
            raise
        with self._lock:
            self._resources.pop(session_id, None)
            result = self._transition(session_id, "closed")
            self._prune()
            return result

    @staticmethod
    def close_resource(resource: Any, session: RemoteSession, timeout: float) -> None:
        """Close one transport resource using its concrete lifecycle protocol."""
        if callable(getattr(resource, "stop_all", None)):
            resource.stop_all()
        elif session.transport == "webrtc":
            resource.stop()
        elif session.role == "host":
            resource.stop(timeout=timeout)
        else:
            resource.disconnect(timeout=timeout)

    def bind(self, session_id: str, callback: Callable[..., Any]) -> Callable[..., Any]:
        """Bind a delivery to its exact generation and captured request limits."""
        session = self.get(session_id)
        binding = self._bindings[session_id]

        def deliver(*args: Any, **kwargs: Any) -> Any:
            if not self.is_current(session_id, session.generation, owner=session.owner):
                return None
            return binding.run(callback, *args, **kwargs)

        return deliver

    def is_current(self, session_id: str, generation: int, *, owner: Optional[str] = None) -> bool:
        """Validate at the delivery boundary, including after a queued GUI handoff."""
        with self._lock:
            session = self._sessions.get(session_id)
            return bool(
                session is not None
                and session.generation == generation
                and session.state in {"connecting", "active"}
                and (owner is None or owner == session.owner)
            )

    def events(self, *, owner: Optional[str] = None) -> Tuple[SessionEvent, ...]:
        """Read bounded lifecycle evidence for a specific owner or all sessions."""
        with self._lock:
            return tuple(event for event in self._events if owner is None or event.owner == owner)

    def subscribe(self, owner: str, callback: Callable[[SessionEvent], None]) -> Callable[[], None]:
        """Deliver only the subscriber owner's events and return explicit unsubscription."""
        require_command("remote_session_events")
        identifier = uuid.uuid4().hex
        with self._lock:
            self._listeners[identifier] = (owner, RequestBinding.capture(), callback)

        def remove() -> None:
            with self._lock:
                self._listeners.pop(identifier, None)

        return remove

    def _transition(self, session_id: str, state: str) -> RemoteSession:
        session = replace(self._sessions[session_id], state=state)
        self._sessions[session_id] = session
        event = SessionEvent(session.id, session.owner, session.transport, session.role, state, session.generation)
        self._events.append(event)
        for owner, binding, callback in tuple(self._listeners.values()):
            if owner == event.owner:
                try:
                    binding.run(callback, event)
                # Contain observer/destruction failures so every owned cleanup is attempted.
                except Exception as error:  # pylint: disable=broad-exception-caught  # reason: cleanup boundary
                    autocontrol_logger.warning("remote lifecycle observer failed: %s", type(error).__name__)
        return session

    def _prune(self) -> None:
        retained = set(self._aliases.values()) | set(self._resources)
        terminals = [
            identifier
            for identifier, session in self._sessions.items()
            if session.state == "closed" and identifier not in retained
        ]
        for identifier in terminals[:-256]:
            del self._sessions[identifier]
            self._bindings.pop(identifier, None)


def disconnect_session(session_id: str, *, owner: Optional[str] = None) -> SessionStatus:
    """Disconnect a named process-local session after optional owner validation."""
    # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
    from je_auto_control.utils.remote_desktop.registry import (
        registry,
    )
    # pylint: enable=import-outside-toplevel

    return registry.disconnect_session(session_id, owner=owner)


def get_remote_session(session_id: str, *, owner: Optional[str] = None) -> RemoteSession:
    """Read immutable process-local session metadata after optional owner validation."""
    require_command("remote_session_status")
    # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
    from je_auto_control.utils.remote_desktop.registry import (
        registry,
    )
    # pylint: enable=import-outside-toplevel

    return registry.get_session(session_id, owner=owner)


def list_remote_session_events(*, owner: Optional[str] = None) -> Tuple[SessionEvent, ...]:
    """Read bounded process-local lifecycle events, optionally filtered by owner."""
    # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
    from je_auto_control.utils.remote_desktop.registry import (
        registry,
    )
    # pylint: enable=import-outside-toplevel

    return registry.session_events(owner=owner)
