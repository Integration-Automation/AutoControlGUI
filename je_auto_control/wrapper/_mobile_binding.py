"""Execution-local mobile bindings without importing SDK clients or session factories."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Optional, Protocol, TYPE_CHECKING

from je_auto_control.wrapper._mobile_models import DeviceContext, DeviceSessionError

if TYPE_CHECKING:
    from je_auto_control.wrapper.device_frame import DeviceFrame
    from je_auto_control.wrapper.mobile_gesture import Gesture


class _BoundDevice(Protocol):
    """Minimum session contract required by compatible implicit helpers."""

    @property
    def context(self) -> DeviceContext:
        """Frozen identity/configuration."""

    def ensure_open(self) -> None:
        """Reject a cancelled owner."""

    def adapter(self, kind: str) -> Any:
        """Return an owned lazy backend client."""

    def capture(self) -> DeviceFrame:
        """Return native frame evidence for this device."""

    def perform(self, gesture: Gesture) -> None:
        """Send one native-point gesture to this device."""


_CURRENT: ContextVar[Optional[_BoundDevice]] = ContextVar('mobile_device_session', default=None)


@contextmanager
def bind_device(session: _BoundDevice) -> Iterator[None]:
    """Reset even failed/nested bindings without changing any process defaults."""
    token = _CURRENT.set(session)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def bound_device(platform: str) -> Optional[_BoundDevice]:
    """A closed or wrong-platform owner must never fall back to another device."""
    session = _CURRENT.get()
    if session is not None:
        session.ensure_open()
        if session.context.platform != platform:
            raise DeviceSessionError('active device context belongs to a different platform')
    return session


def active_device() -> Optional[_BoundDevice]:
    """Return the active mobile owner without selecting a desktop or default device."""
    session = _CURRENT.get()
    if session is not None:
        session.ensure_open()
    return session


def resolve_client(platform: str, kind: str, client: Any) -> Any:
    """A Python helper's explicit client must belong to the active binding."""
    session = bound_device(platform)
    if session is None:
        return client
    owned = session.adapter(kind)
    if client is not None and client is not owned:
        raise DeviceSessionError('explicit client does not belong to the active device context')
    return owned
