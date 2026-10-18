"""Explicit run capture and parent propagation at executor action boundaries."""
from __future__ import annotations

import time
from asyncio import CancelledError
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterator, Mapping, Optional, Sequence, TypedDict, cast
from uuid import uuid4

from je_auto_control.utils.action_journal.events import ActionEvent, ActionJournalError, EventStatus
from je_auto_control.utils.action_journal.redaction import sanitize_event
from je_auto_control.utils.action_journal.store import ActionJournal
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.path_guard.path_guard import validate_path
from je_auto_control.utils.script_vars.execution import execution_scope
from je_auto_control.utils.run_history.context import current_history


@dataclass(frozen=True)
class JournalBinding:
    """An immutable run/parent binding that workers may explicitly inherit."""

    journal: ActionJournal
    run_id: str
    parent_id: Optional[str] = None
    device_id: Optional[str] = None
    session_id: Optional[str] = None


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
                  device_id: Optional[str] = None, session_id: Optional[str] = None) -> Iterator[JournalBinding]:
    """Capture enclosed executor calls in one explicit run, restoring any outer run.

    Worker helpers carry the binding explicitly. A new scope starts a new root;
    nested action bodies share the current binding until their call returns.
    """
    identity = uuid4().hex if run_id is None else run_id
    if not isinstance(identity, str) or not identity:
        raise ActionJournalError("journal run ID must be a non-empty string")
    binding = JournalBinding(journal, identity, device_id=device_id, session_id=session_id)
    history = current_history()
    if history is not None and not history.store.attach_journal(history.run_id, str(journal.path.resolve()), identity):
        raise ActionJournalError("cannot attach journal to a missing history run")
    with bound_journal(binding):
        yield binding


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
    # pylint: disable-next=import-outside-toplevel  # reason: MCP imports the executor during facade setup
    from je_auto_control.utils.mcp_server.context import OperationCancelledError
    if isinstance(error, (LoopBreak, LoopContinue)):
        return "ok"  # the enclosing loop consumes the signal
    if isinstance(error, (KeyboardInterrupt, SystemExit, GeneratorExit, CancelledError, OperationCancelledError)):
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
    binding.journal.append(event)  # durable start precedes every device effect
    step, before = _CapturedStep(), _failure_count()
    error: Optional[BaseException] = None
    with bound_journal(replace(binding, parent_id=event.step_id)):
        try:
            yield step
        except BaseException as failure:  # reason: settle capture, then propagate the original control flow
            error = failure
            raise
        finally:
            try:
                binding.journal.append(_completion(event, step, before, error, dry_run))
            except ActionJournalError:
                if error is None:
                    raise
                # Preserve a cancellation or original failure. Its durable start
                # stays incomplete if completion could not be written.
                autocontrol_logger.error("action journal completion unavailable; preserving original exception")


def execute_action_with_journal(action_list: Sequence[object] | Mapping[str, object], path: Path, *,
                                run_id: Optional[str] = None,
                                variables: Optional[Mapping[str, object]] = None, dry_run: bool = False,
                                device_id: Optional[str] = None, session_id: Optional[str] = None) -> JournalRunResult:
    """Run actions with fresh variables and explicit journal capture on the module executor.

    Returns the run ID, canonical journal path, original executor record and this
    run's failure-count delta. Direct private executors can use ``journal_scope``
    to capture their existing scope without changing ownership of their variables.
    """
    # pylint: disable-next=import-outside-toplevel  # reason: breaks the capture/executor import cycle
    from je_auto_control.utils.executor.action_executor import executor
    journal = ActionJournal(validate_path(path))
    with execution_scope(variables), journal_scope(journal, run_id=run_id,
                                                  device_id=device_id, session_id=session_id) as binding:
        before = _failure_count()
        actions = dict(action_list) if isinstance(action_list, Mapping) else list(action_list)
        record: dict[str, object] = dict(executor.execute_action(actions, dry_run=dry_run))
    return {"run_id": binding.run_id, "journal_path": str(journal.path), "record": record,
            "failed_actions": _failure_count() - before}
