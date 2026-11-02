"""Host-owned operation context shared with local workers, never serialized model authority."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.presence_pool import PresenceReference
from je_auto_control.utils.rbac.authorization import AuthorizationContext
from je_auto_control.utils.script_vars.ref_guard import _vault_guard
from je_auto_control.utils.agent_runtime.errors import AgentTaskError


@dataclass(frozen=True)
class TaskOperation:
    """The current runtime's immutable scope and live cancellation/deadline checkpoint."""

    spec: AgentTaskSpec
    checkpoint: Callable[[], None]
    owner: AuthorizationContext | None
    takeover: Callable[[], None] | None = None
    presence: Callable[[], PresenceReference] | None = None


_CURRENT: ContextVar[TaskOperation | None] = ContextVar("agent_task_operation", default=None)
_READY_TAKEOVER: ContextVar[tuple[TaskOperation, Callable[[], None]] | None] = ContextVar(
    "agent_task_ready_takeover", default=None)


def current_operation() -> TaskOperation | None:
    """Return the host-bound operation, or None outside managed dispatch."""
    return _CURRENT.get()


def current_takeover() -> Callable[[], None] | None:
    """Read only the current operation's host readiness callback, never a nested scope's authority."""
    operation, binding = current_operation(), _READY_TAKEOVER.get()
    if operation is None:
        return None
    return binding[1] if binding is not None and binding[0] is operation else operation.takeover


def ready_with_takeover(target: Any, spec: AgentTaskSpec, takeover: Callable[[], Any]) -> tuple[bool, str]:
    """Bind a host callback for the exact acquired control lease before configuring any target helper."""
    operation = current_operation()
    if operation is None:
        raise AgentTaskError('target readiness requires a managed host operation')
    def notify() -> None:
        takeover()
    token = _READY_TAKEOVER.set((operation, notify))
    try:
        return target.ready(spec)
    finally:
        _READY_TAKEOVER.reset(token)


def _deny_ambient_secret(_name: str) -> None:
    raise AgentTaskError("managed task scope does not grant access to the ambient secret vault")


@contextmanager
def operation_scope(operation: TaskOperation | None) -> Iterator[None]:
    """Bind an explicit owner's context, replacing unrelated worker ambient state."""
    token = _CURRENT.set(operation)
    try:
        if operation is None:
            yield
        else:
            with _vault_guard(_deny_ambient_secret):
                yield
    finally:
        _CURRENT.reset(token)
