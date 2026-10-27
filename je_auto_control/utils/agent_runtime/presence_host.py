"""Lazy host-owned source lifetimes and fixed per-helper capabilities, never task-selected authority."""
from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.presence_pool import PresenceReference, shared_reference


def require_windows() -> None:
    """Refuse unsupported native sources before a standard desktop helper acquires input resources."""
    if sys.platform != 'win32':
        raise AgentControlBusy('persistent desktop presence requires a supported Windows console session')


class RuntimePresence:
    """One explicit runtime lifetime, lazy under its existing construction/close mutex."""

    def __init__(self, mutex: Any, closed: Callable[[], bool]) -> None:
        self._mutex, self._closed = mutex, closed
        self._reference: PresenceReference | None = None

    def reference(self) -> PresenceReference:
        """Bind only a fresh input lifetime; failed existing helpers retain their old capabilities."""
        require_windows()
        with self._mutex:
            if self._closed():
                raise AgentTaskError('runtime is closed')
            if self._reference is not None and self._reference.status()['state'] in {'closed', 'unavailable'}:
                if not self._reference.retired:
                    raise AgentTaskError('previous runtime presence source has not retired')
                self._reference.close()
                self._reference = None
            if self._reference is None:
                self._reference = shared_reference()
            return self._reference

    def close(self) -> None:
        """Close after actual input retirement; failed retirement remains owned for explicit retry."""
        with self._mutex:
            if self._reference is not None:
                self._reference.close()
                self._reference = None

    def status(self) -> dict:
        """Report this runtime's passive binding state without creating any shared reference."""
        with self._mutex:
            if self._reference is None:
                return {'state': 'not_started', 'native_evidence': 'not_recorded'}
            return self._reference.status()


@dataclass
class _Grant:
    reference: PresenceReference
    binding: dict
    channel: Any
    spec: Any


class TargetPresence:
    """A capability remains fixed until the exact input helper and its held input have retired."""

    def __init__(self) -> None:
        self._grant: _Grant | None = None

    @staticmethod
    def check_platform() -> None:
        """Refuse unsupported defaults without starting helper, input journal or source."""
        require_windows()

    def bind(self, operation: Any, channel: Any, timeout: float) -> dict:
        """Accept only the actual immutable host operation supplied by NativeDesktopTarget."""
        if self._grant is not None:
            if channel is not self._grant.channel or operation.spec != self._grant.spec:
                raise AgentTaskError('presence binding requires prior input/helper retirement')
            return dict(self._grant.binding)
        provider = operation.presence
        if provider is None:
            raise AgentTaskError('standard desktop worker requires a host presence provider')
        reference = provider()
        binding = reference.acquire(operation.checkpoint, timeout)
        self._grant = _Grant(reference, dict(binding), channel, operation.spec)
        return dict(binding)

    def release(self) -> None:
        """Schedule owned token release only after proven input/helper cleanup, never certify input."""
        if self._grant is not None:
            if not self._grant.reference.retired:
                self._grant.reference.release(self._grant.binding)
            self._grant = None

    def status(self) -> dict:
        """Expose only coarse binding/source availability; never query or disclose capability identifiers."""
        if self._grant is None:
            return {'state': 'not_bound' if sys.platform == 'win32' else 'not_supported',
                    'native_evidence': 'not_recorded'}
        return {'state': self._grant.reference.status()['state'], 'lease': 'bound', 'native_evidence': 'not_recorded'}
