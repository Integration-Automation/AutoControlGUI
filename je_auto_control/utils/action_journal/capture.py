"""Explicit run capture and parent propagation at executor action boundaries."""
from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterator, Mapping, Optional, Sequence, TypedDict, cast
from uuid import uuid4

from je_auto_control.utils.action_journal.events import ActionEvent, ActionJournalError, EventStatus
from je_auto_control.utils.action_journal.redaction import sanitize_event
from je_auto_control.utils.action_journal.store import ActionJournal
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.logging.secret_scope import scrub_secret_text
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.run_history.context import current_history
from je_auto_control.utils.run_history.run_outcome import is_run_interruption


@dataclass(frozen=True)
class JournalBinding:
    """An immutable run/parent binding that workers may explicitly inherit."""

    journal: ActionJournal
    run_id: str
    parent_id: Optional[str] = None
    device_id: Optional[str] = None
    session_id: Optional[str] = None
    observers: tuple[Callable[[EventStatus], None], ...] = ()
    path_policies: tuple[PathPolicy, ...] = ()


class JournalRunResult(TypedDict):
    """The captured run's identity, location and original execution outcomes."""

    run_id: str
    journal_path: str
    record: dict[str, object]
    failed_actions: int


@dataclass
class _CapturedStep:
    outcome: object = None


_CURRENT: ContextVar[Optional[JournalBinding]] = ContextVar("je_auto_control_journal", default=None)


def current_journal() -> Optional[JournalBinding]:
    """Return this context's active run/parent binding, without opening a log."""
    return _CURRENT.get()


@contextmanager
def bound_journal(binding: Optional[JournalBinding]) -> Iterator[None]:
    """Bind a captured run in a worker; ``None`` clears ambient capture."""
    token = _CURRENT.set(binding)
    try:
        yield
    finally:
        _CURRENT.reset(token)


@contextmanager
def journal_scope(journal: ActionJournal, *, run_id: Optional[str] = None,
                  device_id: Optional[str] = None, session_id: Optional[str] = None,
                  observer: Optional[Callable[[EventStatus], None]] = None,
                  path_policy: Optional[PathPolicy] = None) -> Iterator[JournalBinding]:
    """Capture enclosed executor calls in one explicit run, restoring any outer run.

    Worker helpers carry the binding explicitly. A new scope starts a new root;
    nested action bodies share the current binding until their call returns.
    Identifiers and destinations containing secrets known to the enclosing run
    are refused before history linking, file creation or body execution.
    Nested scopes retain enclosing observers and intersect path policies.
    Observers receive ``incomplete`` before dispatch and the final status only
    after durable completion; joined workers invoke them on their own threads.
    """
    identity = _scope_identity(journal, run_id, device_id, session_id)
    parent = current_journal()
    observers = parent.observers if parent is not None else ()
    if observer is not None and all(item is not observer for item in observers):
        observers += (observer,)
    policies = _effective_path_policies(path_policy)
    for policy in policies:
        policy.validate(journal.path, operation="journal capture")
    binding = JournalBinding(journal, identity, device_id=device_id, session_id=session_id,
                             observers=observers, path_policies=policies)
    history = current_history()
    if history is not None and not history.store.attach_journal(history.run_id, str(journal.path.resolve()), identity):
        raise ActionJournalError("cannot attach journal to a missing history run")
    with bound_journal(binding):
        yield binding


def _scope_identity(journal: ActionJournal, run_id: Optional[str], device_id: Optional[str],
                    session_id: Optional[str]) -> str:
    """Validate public metadata before any provenance link or file effect."""
    identity = uuid4().hex if run_id is None else run_id
    if not isinstance(identity, str) or not identity:
        raise ActionJournalError("journal run ID must be a non-empty string")
    for value in (identity, device_id, session_id, str(journal.path)):
        if isinstance(value, str) and scrub_secret_text(value) != value:
            raise ActionJournalError("journal identifiers and destination cannot contain a resolved secret")
    return identity


def _effective_path_policies(policy: Optional[PathPolicy]) -> tuple[PathPolicy, ...]:
    """Intersect explicit roots with every enclosing captured run's roots."""
    parent = current_journal()
    policies = parent.path_policies if parent is not None else ()
    if policy is not None and all(item is not policy for item in policies):
        policies += (policy,)
    return policies


def _snapshot(action: list[object], binding: JournalBinding) -> ActionEvent:
    command = action[0] if action and isinstance(action[0], str) else "<invalid>"
    parameters = action[1] if len(action) == 2 and isinstance(action[1], dict) else {"args": action[1:]}
    event = ActionEvent(run_id=binding.run_id, step_id=uuid4().hex, command=command,
                        parameters=parameters, started_at=time.time(), parent_id=binding.parent_id,
                        device_id=binding.device_id, session_id=binding.session_id)
    event.validate()
    payload = sanitize_event(event)
    # A finite JSON copy freezes inputs before dispatch; no user payload deepcopy
    # or repr is called, and a command cannot rewrite its source snapshot later.
    return replace(event, parameters=cast(dict[str, object], payload["parameters"]),
                   non_replayable=tuple(cast(list[str], payload["non_replayable"])))


def _failure_count() -> int:
    # pylint: disable-next=import-outside-toplevel  # reason: breaks the capture/executor import cycle
    from je_auto_control.utils.executor.action_executor import recorded_failures
    return recorded_failures()


def _exception_status(error: BaseException) -> EventStatus:
    # pylint: disable-next=import-outside-toplevel  # reason: flow_control imports this capture adapter
    from je_auto_control.utils.executor.flow_control import LoopBreak, LoopContinue
    if isinstance(error, (LoopBreak, LoopContinue)):
        return "ok"  # the enclosing loop consumes the signal
    if is_run_interruption(error):
        return "cancelled"
    return "error"


def _completion(event: ActionEvent, step: _CapturedStep, before: int,
                error: Optional[BaseException], dry_run: bool) -> ActionEvent:
    status: EventStatus = "dry_run" if dry_run else "ok"
    if error is not None:
        status = _exception_status(error)
    elif _failure_count() > before:
        status = "error"
    reasons = event.non_replayable + (("not_executed",) if dry_run else ())
    return replace(event, finished_at=max(event.started_at, time.time()), status=status,
                   outcome=step.outcome, error="action did not complete" if status in {"error", "cancelled"} else None,
                   non_replayable=reasons)


@contextmanager
def action_step(action: list[object], *, dry_run: bool = False) -> Iterator[Optional[_CapturedStep]]:
    """Capture one attempted action; without a binding, leave execution untouched."""
    binding = current_journal()
    if binding is None:
        yield None
        return
    event = _snapshot(action, binding)
    _notify_observers(binding, event.status)
    _append_event(binding, event)  # durable start precedes every device effect
    step, before = _CapturedStep(), _failure_count()
    error: Optional[BaseException] = None
    with bound_journal(replace(binding, parent_id=event.step_id)):
        try:
            yield step
        except BaseException as failure:  # reason: settle capture, then propagate the original control flow
            error = failure
            raise
        finally:
            _finish_step(binding, _completion(event, step, before, error, dry_run), error)


def _append_event(binding: JournalBinding, event: ActionEvent) -> None:
    """Check current roots at each append, including client-root revocation."""
    for policy in binding.path_policies:
        policy.validate(binding.journal.path, operation="journal append")
    binding.journal.append(event)


def _notify_observers(binding: JournalBinding, status: EventStatus, error: Optional[BaseException] = None) -> None:
    """Notify observers while preserving any original failure or control signal."""
    try:
        for observer in binding.observers:
            observer(status)
    except BaseException:  # pylint: disable=broad-exception-caught  # reason: retain the pending original signal
        if error is None:
            raise
        autocontrol_logger.error("action journal observer unavailable; preserving original exception")


def _finish_step(binding: JournalBinding, event: ActionEvent, error: Optional[BaseException]) -> None:
    """Notify completion only after persistence; retain a pending hard signal."""
    try:
        _append_event(binding, event)
    except AutoControlException:
        if error is None:
            raise
        autocontrol_logger.error("action journal completion unavailable; preserving original exception")
    else:
        _notify_observers(binding, event.status, error)


def execute_action_with_journal(action_list: Sequence[object] | Mapping[str, object], path: Path, *,
                                run_id: Optional[str] = None,
                                variables: Optional[Mapping[str, object]] = None, dry_run: bool = False,
                                device_id: Optional[str] = None, session_id: Optional[str] = None) -> JournalRunResult:
    """Run actions with fresh variables and explicit journal capture on the module executor.

    Returns the run ID, canonical journal path, original executor record and this
    run's failure-count delta. Direct private executors can use ``journal_scope``
    to capture their existing scope without changing ownership of their variables.
    """
    # pylint: disable-next=import-outside-toplevel  # reason: the options runner imports this capture boundary
    from je_auto_control.utils.action_journal.run import JournalRunOptions, execute_journal_run
    return execute_journal_run(action_list, path, options=JournalRunOptions(
        variables=variables, dry_run=dry_run, run_id=run_id, device_id=device_id, session_id=session_id))
