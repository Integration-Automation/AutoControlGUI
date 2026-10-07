"""Panel-owned remote sessions and generation checks at the queued Qt boundary."""

from __future__ import annotations

import uuid
import weakref
from typing import Any, Callable, Dict, Optional

# pylint: disable=no-name-in-module  # reason: native Qt binding
from PySide6.QtCore import QObject, Signal

# pylint: enable=no-name-in-module
from je_auto_control.utils.executor.request_context import RequestBinding
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.registry_sessions import RegistrySessions
from je_auto_control.utils.remote_desktop.sessions import RemoteSession, SessionEvent
from je_auto_control.utils.remote_desktop.cleanup_jobs import _CleanupJob, _submit_cleanup


class PanelSessions(QObject):
    """Own a panel's host/viewer separately; dispose subscriptions with the panel."""

    ended = Signal(str)
    _delivery = Signal(object, object, object, object)
    _lifecycle = Signal(object)

    def __init__(self, parent: QObject, directory: RegistrySessions) -> None:
        super().__init__(parent)
        self.directory = directory
        self.owner = "gui:" + uuid.uuid4().hex
        self._current: Dict[str, RemoteSession] = {}
        self._closing: dict[str, tuple[RemoteSession, _CleanupJob]] = {}
        self._delivery.connect(self._deliver)
        self._lifecycle.connect(self._on_lifecycle)
        reference = weakref.ref(self)

        def receive(event: SessionEvent) -> None:
            relay = reference()
            if relay is not None:
                try:
                    relay._lifecycle.emit(event)  # pylint: disable=protected-access  # reason: same-class weak relay
                except RuntimeError:
                    pass  # QObject has already been disposed; teardown revoked every owned session.

        remove = directory.subscribe_sessions(self.owner, receive)
        current, owner, closing = self._current, self.owner, self._closing
        self._cleanup: list[Callable[[], None]] = []
        cleanup = self._cleanup
        disposed = [False]

        def dispose() -> None:
            if disposed[0]:
                return
            disposed[0] = True
            remove()
            sessions = tuple(current.values())
            current.clear()
            for _session, job in tuple(closing.values()):
                job.retry()
            closing.clear()
            for session in sessions:
                try:
                    _submit_cleanup((directory._deferred_disconnect(session.id, owner=owner),))
                # Contain observer/destruction failures so every owned cleanup is attempted.
                except Exception as error:  # pylint: disable=broad-exception-caught  # reason: cleanup boundary
                    autocontrol_logger.warning("remote disposal failed: %s", type(error).__name__)
            for callback in tuple(cleanup):
                try:
                    callback()
                # Contain observer/destruction failures so every owned cleanup is attempted.
                except Exception as error:  # pylint: disable=broad-exception-caught  # reason: cleanup boundary
                    autocontrol_logger.warning("remote background disposal failed: %s", type(error).__name__)
            cleanup.clear()

        self._dispose_callback = dispose
        parent.destroyed.connect(dispose)

    def dispose(self) -> None:
        """Revoke subscriptions and independently attempt all owned cleanup exactly once."""
        self._dispose_callback()

    def add_cleanup(self, callback: Callable[[], None]) -> None:
        """Register a background-resource cleanup that must avoid accessing disposed widgets."""
        self._cleanup.append(callback)

    def reserve(self, transport: str, role: str) -> RemoteSession:
        """End this panel's previous role, then reserve a fresh callback identity."""
        self.close(role)
        session = self.directory.reserve_session(owner=self.owner, transport=transport, role=role)
        self._current[role] = session
        return session

    def attach(self, resource: Any, role: str, *, active: bool = True) -> RemoteSession:
        """Attach one transport to the current generation."""
        session = self._current[role]
        return self.directory.attach_session(session.id, resource, active=active)

    def activate(self, role: str) -> RemoteSession:
        """Confirm successful setup without claiming an ended session."""
        return self.directory.activate_session(self._current[role].id)

    def id(self, role: str) -> Optional[str]:
        """Return the current identity or a retained failed cleanup identity for retry."""
        session = self._current.get(role)
        if session is not None:
            return session.id
        for identifier, (retained, job) in tuple(self._closing.items()):
            if not job.pending:
                self._closing.pop(identifier, None)
            elif retained.role == role and self.directory.get_session(identifier, owner=self.owner).state == 'failed':
                return identifier
        return None

    def resource(self, role: str) -> Any:
        """Get this panel's own resource; never consult script aliases."""
        identifier = self.id(role)
        return None if identifier is None else self.directory.session_resource(identifier, owner=self.owner)

    def status(self, role: str) -> dict:
        """Read the owned transport state, including an empty panel with no connection."""
        return self.directory.session_snapshot(self.id(role), role=role)

    def close(self, role: str) -> None:
        """Revoke queued delivery before stopping the owned resource."""
        session = self._current.pop(role, None)
        if session is not None:
            try:
                job = _submit_cleanup((self.directory._deferred_disconnect(session.id, owner=self.owner),))
                self._closing[session.id] = (session, job)
            except BaseException:
                self._current[role] = session
                raise
        else:
            for retained, job in tuple(self._closing.values()):
                if retained.role == role:
                    job.retry()

    def callback(
        self, role: str, callback: Callable[..., Any], *, transform: Optional[Callable[..., Optional[tuple]]] = None
    ) -> Callable[..., None]:
        """Queue a captured delivery and recheck generation on the GUI thread."""
        session = self._current[role]
        binding = RequestBinding.capture()
        reference = weakref.ref(self)
        directory = self.directory

        def receive(*args: Any) -> None:
            relay = reference()
            if relay is None or not directory.session_is_current(session.id, session.generation, owner=session.owner):
                return
            if transform is not None:
                converted = binding.run(transform, *args)
                if converted is None:
                    return
                args = converted
            try:
                relay._delivery.emit(session, binding, callback, args)  # pylint: disable=protected-access
            except RuntimeError:
                pass  # A queued network completion after QObject disposal has no live receiver.

        return receive

    def _deliver(
        self, session: RemoteSession, binding: RequestBinding, callback: Callable[..., Any], args: tuple
    ) -> None:
        current = self._current.get(session.role)
        if (
            current is None
            or current.id != session.id
            or current.generation != session.generation
            or not self.directory.session_is_current(session.id, session.generation, owner=self.owner)
        ):
            return
        binding.run(callback, *args)

    def _on_lifecycle(self, event: SessionEvent) -> None:
        session = self._current.get(event.role)
        if (
            event.state != "closed"
            or session is None
            or session.id != event.session_id
            or session.generation != event.generation
        ):
            return
        self._current.pop(event.role, None)
        self.ended.emit(event.role)
