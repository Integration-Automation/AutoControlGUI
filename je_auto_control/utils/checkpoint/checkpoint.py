"""Flow checkpoint & resume — durable execution for long action lists.

A multi-hour unattended flow that dies at step 400 should not restart from
zero. After each executed step this persists ``{run_id, step_index,
variables}`` to a pluggable store (SQLite by default); on a later run with
the same ``run_id`` it fast-forwards past completed steps and rehydrates the
script variables, so execution resumes where it stopped.

Pure standard library (``sqlite3`` / ``json``); imports no ``PySide6``. The
store is injectable, so resume logic is unit-tested deterministically
without a real crash.
"""
import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ContextManager, Dict, List, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.sqlite_support import autocommit_connection, sqlite_errors_as

if TYPE_CHECKING:  # reason: sqlite3 types are named only in annotations
    import sqlite3


@dataclass
class Checkpoint:
    """A persisted run position: next step to execute + variable snapshot."""
    run_id: str
    step_index: int
    variables: Dict[str, Any] = field(default_factory=dict)
    updated: float = 0.0


class CheckpointStoreError(AutoControlException):
    """The checkpoint database could not be opened or used."""


class CheckpointStore:
    """SQLite-backed store of one checkpoint per ``run_id``."""

    @sqlite_errors_as(CheckpointStoreError)
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._ensure_schema()

    def _connect(self) -> ContextManager["sqlite3.Connection"]:
        return autocommit_connection(self._db_path)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS checkpoints ("
                "run_id TEXT PRIMARY KEY, step_index INTEGER NOT NULL, "
                "variables TEXT NOT NULL, updated REAL NOT NULL)")

    @sqlite_errors_as(CheckpointStoreError)
    def save(self, run_id: str, step_index: int,
             variables: Dict[str, Any]) -> None:
        """Persist (or overwrite) the checkpoint for ``run_id``."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO checkpoints (run_id, step_index, variables, "
                "updated) VALUES (?, ?, ?, ?) ON CONFLICT(run_id) DO UPDATE "
                "SET step_index=excluded.step_index, "
                "variables=excluded.variables, updated=excluded.updated",
                (str(run_id), int(step_index), json.dumps(variables),
                 time.time()))

    @sqlite_errors_as(CheckpointStoreError)
    def load(self, run_id: str) -> Optional[Checkpoint]:
        """Return the checkpoint for ``run_id`` or ``None``."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE run_id=?",
                (str(run_id),)).fetchone()
        if row is None:
            return None
        return Checkpoint(run_id=row["run_id"], step_index=row["step_index"],
                          variables=json.loads(row["variables"]),
                          updated=row["updated"])

    @sqlite_errors_as(CheckpointStoreError)
    def clear(self, run_id: str) -> bool:
        """Delete the checkpoint for ``run_id``; return whether it existed."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM checkpoints WHERE run_id=?",
                               (str(run_id),))
            return cur.rowcount > 0


def _new_executor() -> Any:
    from je_auto_control.utils.executor.action_executor import Executor
    return Executor()


def run_resumable(actions: List[Any], *, run_id: str, store: CheckpointStore,
                  executor: Any = None,
                  variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run ``actions``, checkpointing after each step; resume if interrupted.

    On entry, any saved checkpoint for ``run_id`` fast-forwards past
    completed steps and rehydrates variables. On normal completion the
    checkpoint is cleared. Returns ``{completed, total, resumed_from,
    record}``. A failing step raises and leaves the checkpoint on that step,
    so the next call retries it.
    """
    runner = executor or _new_executor()
    existing = store.load(run_id)
    start = existing.step_index if existing else 0
    if existing:
        runner.variables.update_many(existing.variables)
    elif variables:
        runner.variables.update_many(variables)
    record: Dict[str, Any] = {}
    for index in range(start, len(actions)):
        # Without raise_on_error a failed step is recorded and returned
        # normally, so it was checkpointed as done and never run again.
        record.update(runner.execute_action([actions[index]],
                                            raise_on_error=True))
        store.save(run_id, index + 1, runner.variables.as_dict())
    store.clear(run_id)
    return {"completed": True, "total": len(actions),
            "resumed_from": start, "record": record}
