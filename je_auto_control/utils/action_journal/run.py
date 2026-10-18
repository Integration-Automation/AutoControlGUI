"""Isolated journal runs with typed controls and per-run metadata."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from je_auto_control.utils.action_journal.capture import JournalRunResult, _failure_count, journal_scope
from je_auto_control.utils.action_journal.events import EventStatus
from je_auto_control.utils.action_journal.store import ActionJournal
from je_auto_control.utils.logging.secret_scope import secret_log_scope
from je_auto_control.utils.path_guard.path_guard import validate_path
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.script_vars.execution import execution_scope


@dataclass(frozen=True)
class JournalRunOptions:
    """Seeds, preview mode and inherited controls for one isolated run.

    The variable mapping is copied when the run starts. Observers can raise to cancel at
    action boundaries and may run on joined worker threads. Nested captures
    retain the controls; an explicit policy can only add restrictions.
    """

    variables: Optional[Mapping[str, object]] = None
    dry_run: bool = False
    run_id: Optional[str] = None
    device_id: Optional[str] = None
    session_id: Optional[str] = None
    observer: Optional[Callable[[EventStatus], None]] = None
    path_policy: Optional[PathPolicy] = None


@secret_log_scope()
def execute_journal_run(actions: Sequence[object] | Mapping[str, object], path: str | Path, *,
                        options: Optional[JournalRunOptions] = None) -> JournalRunResult:
    """Run with fresh variables, durable capture and optional cooperative controls.

    The result matches ``execute_action_with_journal``. Capture opens no history
    row/database implicitly; an existing owner receives the provenance link.
    Native calls already in progress are not forcibly interrupted.
    """
    # pylint: disable-next=import-outside-toplevel  # reason: the executor imports capture boundaries
    from je_auto_control.utils.executor.action_executor import executor
    settings = options if options is not None else JournalRunOptions()
    journal = ActionJournal(validate_path(path))
    with execution_scope(settings.variables), journal_scope(
            journal, run_id=settings.run_id, device_id=settings.device_id, session_id=settings.session_id,
            observer=settings.observer, path_policy=settings.path_policy) as binding:
        before = _failure_count()
        payload = dict(actions) if isinstance(actions, Mapping) else list(actions)
        record: dict[str, object] = dict(executor.execute_action(payload, dry_run=settings.dry_run))
    return {"run_id": binding.run_id, "journal_path": str(journal.path), "record": record,
            "failed_actions": _failure_count() - before}
