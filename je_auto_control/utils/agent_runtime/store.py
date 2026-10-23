"""Transactional task metadata, durable action receipts and input ownership."""
from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, List

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import STATES, TERMINAL, detached
from je_auto_control.utils.sqlite_support import require_sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_schema (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO agent_schema VALUES (1);
CREATE TABLE IF NOT EXISTS agent_tasks (
 id TEXT PRIMARY KEY, spec TEXT NOT NULL, owner TEXT NOT NULL, state TEXT NOT NULL,
 reason TEXT NOT NULL DEFAULT '', steps INTEGER NOT NULL DEFAULT 0,
 created REAL NOT NULL, updated REAL NOT NULL, started REAL, verification TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS agent_actions (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES agent_tasks(id), command TEXT NOT NULL,
 arguments TEXT NOT NULL, status TEXT NOT NULL, result TEXT, created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS agent_actions_task ON agent_actions(task_id,created);
CREATE TABLE IF NOT EXISTS agent_control (
 target TEXT PRIMARY KEY, owner TEXT NOT NULL, generation INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS agent_clocks (
 task_id TEXT PRIMARY KEY REFERENCES agent_tasks(id) ON DELETE CASCADE,
 started REAL NOT NULL, last_seen REAL NOT NULL, spent REAL NOT NULL);
"""


class AgentTaskStore:
    """A lazy, per-operation SQLite store; reads never expose live mutable state."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(Path(path).resolve())
        self._ready = False

    @contextmanager
    def connection(self, *, write: bool = False) -> Iterator[Any]:
        """Own a connection and atomically commit or roll back a write transaction."""
        driver = require_sqlite3()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = driver.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = driver.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            if not self._ready:
                connection.executescript(_SCHEMA)
                versions = [row[0] for row in connection.execute("SELECT version FROM agent_schema")]
                if versions != [1]:
                    raise AgentTaskError("unsupported agent runtime schema")
                self._ready = True
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.execute("COMMIT")
        except driver.Error as error:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise AgentTaskError("agent runtime database operation failed") from error
        except BaseException:  # reason: transaction ownership requires rollback, then original controls propagate
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def create(self, spec: dict, owner: dict) -> str:
        """Persist an immutable authorized task snapshot before it can execute."""
        identifier = uuid.uuid4().hex
        now = time.time()
        with self.connection(write=True) as connection:
            connection.execute("INSERT INTO agent_tasks(id,spec,owner,state,created,updated) VALUES (?,?,?,?,?,?)",
                               (identifier, json.dumps(spec), json.dumps(owner), "queued", now, now))
        return identifier

    def get(self, task_id: str) -> dict[str, Any]:
        """Return one task or fail without revealing another identifier's data."""
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise AgentTaskError("task does not exist or is not owned by this caller")
        result = dict(row)
        for name in ("spec", "owner", "verification"):
            result[name] = json.loads(result[name])
        return result

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return bounded task metadata in creation order."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise AgentTaskError("task limit must be between 1 and 1000")
        with self.connection() as connection:
            identifiers = [row[0] for row in connection.execute(
                "SELECT id FROM agent_tasks ORDER BY created DESC LIMIT ?", (limit,))]
        return [self.get(identifier) for identifier in identifiers]

    def update(self, task_id: str, state: str, *, reason: str = "", verification: Any = None) -> None:
        """Atomically publish state without touching an already committed terminal state."""
        if state not in STATES:
            raise AgentTaskError("invalid task state")
        with self.connection(write=True) as connection:
            row = connection.execute("SELECT state FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
            if row is None or (row["state"] in TERMINAL and row["state"] != state):
                raise AgentTaskError("terminal or missing task cannot change state")
            connection.execute("UPDATE agent_tasks SET state=?,reason=?,updated=?,verification=? WHERE id=?",
                               (state, reason, time.time(), json.dumps(detached(verification or [])), task_id))

    def start(self, task_id: str) -> None:
        """Set the durable start time once, so restarts do not reset the wall budget."""
        with self.connection(write=True) as connection:
            cursor = connection.execute(
                "UPDATE agent_tasks SET started=COALESCE(started,?),state='running' "
                "WHERE id=? AND state IN ('queued','running','verifying')", (time.time(), task_id))
            if cursor.rowcount != 1:
                raise AgentTaskError("task stopped before control activation")

    def prepare(self, task_id: str, command: str, arguments: dict) -> str:
        """Durably record the next operation before any external side effect."""
        identifier = uuid.uuid4().hex
        with self.connection(write=True) as connection:
            connection.execute("INSERT INTO agent_actions VALUES (?,?,?,?,?,?,?)",
                               (identifier, task_id, command, json.dumps(arguments), "prepared", None, time.time()))
        return identifier

    def settle(self, action_id: str, status: str, result: Any = None) -> None:
        """Publish one action outcome and count its first terminal receipt only once."""
        with self.connection(write=True) as connection:
            row = connection.execute("SELECT task_id,status FROM agent_actions WHERE id=?", (action_id,)).fetchone()
            if row is None:
                raise AgentTaskError("unknown action receipt")
            connection.execute("UPDATE agent_actions SET status=?,result=? WHERE id=?",
                               (status, json.dumps(detached(result)), action_id))
            if status in {"confirmed", "uncertain", "failed"} and row["status"] in {"prepared", "dispatched"}:
                connection.execute("UPDATE agent_tasks SET steps=steps+1,updated=? WHERE id=?",
                                   (time.time(), row["task_id"]))

    def actions(self, task_id: str) -> List[dict[str, Any]]:
        """Return independent action receipts in their original execution order."""
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM agent_actions WHERE task_id=? ORDER BY created,rowid",
                                      (task_id,)).fetchall()
        return [{**dict(row), "arguments": json.loads(row["arguments"]),
                 "result": json.loads(row["result"]) if row["result"] is not None else None} for row in rows]

    def recover(self) -> None:
        """Mark abandoned live work for review; never replay an uncertain effect."""
        with self.connection(write=True) as connection:
            connection.execute("UPDATE agent_actions SET status='uncertain' WHERE status='dispatched'")
            connection.execute("UPDATE agent_tasks SET state='recovering',reason='runtime restarted' "
                               "WHERE state IN ('running','verifying','pausing','cancelling')")
            connection.execute("UPDATE agent_control SET owner=''")
