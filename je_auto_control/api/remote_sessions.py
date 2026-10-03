"""Beta owned remote session identities and lifecycle operations."""

from je_auto_control.utils.remote_desktop.sessions import (
    RemoteSession,
    RemoteSessionError,
    SessionEvent,
    SessionOwnershipError,
    SessionStatus,
    disconnect_session,
    get_remote_session,
    list_remote_session_events,
)

__all__ = [
    "RemoteSession",
    "SessionStatus",
    "SessionEvent",
    "RemoteSessionError",
    "SessionOwnershipError",
    "disconnect_session",
    "get_remote_session",
    "list_remote_session_events",
]
