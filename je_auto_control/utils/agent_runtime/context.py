"""Host-owned operation context shared with local workers, never serialized model authority."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable, Iterator

from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.rbac.authorization import AuthorizationContext


@dataclass(frozen=True)
class TaskOperation:
    """The current runtime's immutable scope and live cancellation/deadline checkpoint."""

    spec: AgentTaskSpec
    checkpoint: Callable[[], None]
    owner: AuthorizationContext | None
    takeover: Callable[[], None] | None = None


_CURRENT: ContextVar[TaskOperation | None] = ContextVar("agent_task_operation", default=None)


def current_operation() -> TaskOperation | None:
    """Return the host-bound operation, or None outside managed dispatch."""
    return _CURRENT.get()


@contextmanager
def operation_scope(operation: TaskOperation | None) -> Iterator[None]:
    """Bind an explicit owner's context, replacing unrelated worker ambient state."""
    token = _CURRENT.set(operation)
    try:
        yield
    finally:
        _CURRENT.reset(token)
