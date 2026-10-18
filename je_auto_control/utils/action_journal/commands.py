"""Executor adapters for explicit nested journal capture."""
from typing import Optional
from pathlib import Path  # pylint: disable=unused-import  # reason: runtime resolution of the forward path annotation

from je_auto_control.utils.action_journal.capture import JournalRunResult, journal_scope
from je_auto_control.utils.action_journal.store import ActionJournal
from je_auto_control.utils.executor.action_schema import validate_actions
from je_auto_control.utils.path_guard.path_guard import validate_path


def _capture_body(*, body: list[object], path: str, run_id: Optional[str] = None,
                  device_id: Optional[str] = None, session_id: Optional[str] = None) -> JournalRunResult:
    """Capture named body arguments on their executor without eager interpolation."""
    # pylint: disable-next=import-outside-toplevel  # reason: executor registers this adapter
    from je_auto_control.utils.executor.action_executor import _running_executor, recorded_failures
    runner = _running_executor()
    validate_actions(body, runner.known_commands())
    journal = ActionJournal(validate_path(path))
    with journal_scope(journal, run_id=run_id, device_id=device_id, session_id=session_id) as binding:
        before = recorded_failures()
        record: dict[str, object] = dict(runner.execute_action(body, _validated=True))
    return {"run_id": binding.run_id, "journal_path": str(journal.path), "record": record,
            "failed_actions": recorded_failures() - before}


def _read_journal(path: "str | Path", *, run_id: Optional[str] = None, limit: int = 100) -> list[dict[str, object]]:
    """Return bounded sanitized snapshots under the enclosing journal roots."""
    # pylint: disable-next=import-outside-toplevel  # reason: the reader imports capture helpers lazily
    from je_auto_control.utils.action_journal.inspection import inspect_journal
    return inspect_journal(path, run_id=run_id, limit=limit)
