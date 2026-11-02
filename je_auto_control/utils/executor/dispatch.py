"""Shared raw-result command dispatch and nested, context-local execution guards."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator, Mapping, Optional, TYPE_CHECKING

from je_auto_control.utils.exception.cancellation import cancellation_checkpoint

if TYPE_CHECKING:
    from je_auto_control.utils.executor.action_executor import Executor

CommandGuard = Callable[[str, Any], None]
_GUARDS: ContextVar[tuple[CommandGuard, ...]] = ContextVar("autocontrol_command_guards", default=())


@contextmanager
def command_guard(guard: CommandGuard) -> Iterator[None]:
    """Intersect a guard with enclosing guards, including nested action bodies."""
    binding = _GUARDS.set((*_GUARDS.get(), guard))
    try:
        yield
    finally:
        _GUARDS.reset(binding)


def dispatch_checkpoint(name: str, arguments: Any) -> None:
    """Check cancellation and every enclosing guard before an actual dispatch."""
    cancellation_checkpoint()
    for guard in _GUARDS.get():
        guard(name, arguments)


def capture_command_guards() -> tuple[CommandGuard, ...]:
    """Capture the complete immutable guard chain for an explicitly owned local worker."""
    return _GUARDS.get()


@contextmanager
def bound_command_guards(guards: tuple[CommandGuard, ...]) -> Iterator[None]:
    """Bind the parent's exact chain, replacing unrelated worker ambient state."""
    binding = _GUARDS.set(guards)
    try:
        yield
    finally:
        _GUARDS.reset(binding)


def execute_one(executor: Executor, name: str, arguments: Optional[Mapping[str, Any]] = None) -> Any:
    """Execute one validated public command, returning its raw value and propagating failures."""
    from je_auto_control.utils.action_journal.capture import action_step
    from je_auto_control.utils.executor.action_executor import _RUNNING, _STRICT_BODIES
    from je_auto_control.utils.logging.secret_scope import secret_log_scope

    action = _prepare(executor, name, arguments)
    _authorize(name)
    previous = getattr(_RUNNING, "value", None)
    strict = getattr(_STRICT_BODIES, "value", False)
    _RUNNING.value, _STRICT_BODIES.value = executor, True
    try:
        with secret_log_scope(), action_step(action) as captured:
            record: dict[str, Any] = {}
            executor._run_one_action(action, record, True, name)
            result = record[name]
            if captured is not None:
                captured.outcome = result
            return result
    finally:
        _RUNNING.value, _STRICT_BODIES.value = previous, strict


def _prepare(executor: Executor, name: str, arguments: Optional[Mapping[str, Any]]) -> list:
    from je_auto_control.utils.executor.action_schema import validate_actions

    if not isinstance(name, str) or name not in executor.known_commands():
        raise ValueError(f"unknown AC command: {name!r}")
    if arguments is not None and not isinstance(arguments, Mapping):
        raise ValueError("command arguments must be an object")
    params = dict(arguments or {})
    if any(not isinstance(key, str) or key.startswith("_") for key in params):
        raise ValueError("private command arguments are not accepted")
    action = [name, params]
    validate_actions([action], executor.known_commands())
    return action


def _authorize(name: str) -> None:
    from je_auto_control.utils.rbac.authorization import AuthorizationError, current_authorization
    from je_auto_control.utils.rbac.policy import capability_for_command

    cancellation_checkpoint()
    identity = current_authorization()
    needed = capability_for_command(name)
    if identity is not None and not identity.allows(needed):
        raise AuthorizationError(f"{name} needs {needed!r}", capability=needed)
