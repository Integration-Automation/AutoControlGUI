"""Transactional task metadata, durable action receipts and input ownership."""
from __future__ import annotations

import json
import hashlib
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
CREATE TABLE IF NOT EXISTS agent_completion (
 task_id TEXT PRIMARY KEY REFERENCES agent_tasks(id) ON DELETE CASCADE,
 contract INTEGER NOT NULL, confirmed REAL NOT NULL);
CREATE TABLE IF NOT EXISTS agent_reviews (
 action_id TEXT PRIMARY KEY REFERENCES agent_actions(id), task_id TEXT NOT NULL REFERENCES agent_tasks(id),
 decision TEXT NOT NULL, note TEXT NOT NULL, original_result TEXT, reviewed REAL NOT NULL, actor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_evidence (
 task_id TEXT PRIMARY KEY REFERENCES agent_tasks(id) ON DELETE CASCADE,
 history_id INTEGER NOT NULL, journal_path TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_request_keys (
 owner_key TEXT NOT NULL, key_hash TEXT NOT NULL, spec_hash TEXT NOT NULL,
 task_id TEXT NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
 PRIMARY KEY(owner_key,key_hash));
CREATE TABLE IF NOT EXISTS agent_triggers (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, spec TEXT NOT NULL, owner TEXT NOT NULL,
 config TEXT NOT NULL, enabled INTEGER NOT NULL, next_run REAL NOT NULL, last_event TEXT NOT NULL,
 max_pending INTEGER NOT NULL, error TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS agent_trigger_events (
 trigger_id TEXT NOT NULL REFERENCES agent_triggers(id), event_hash TEXT NOT NULL, payload_hash TEXT NOT NULL,
 task_id TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(trigger_id,event_hash));
CREATE TABLE IF NOT EXISTS agent_evidence_pending (
 task_id TEXT PRIMARY KEY REFERENCES agent_tasks(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS agent_skill_candidates (
 id TEXT PRIMARY KEY, skill_id TEXT NOT NULL, name TEXT NOT NULL, owner TEXT NOT NULL,
 spec TEXT NOT NULL, parameters TEXT NOT NULL, provenance TEXT NOT NULL, digest TEXT NOT NULL,
 state TEXT NOT NULL, version INTEGER NOT NULL, created REAL NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS agent_skill_versions ON agent_skill_candidates(skill_id,version) WHERE version > 0;
CREATE TABLE IF NOT EXISTS agent_skill_trials (
 task_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES agent_skill_candidates(id),
 spec_hash TEXT NOT NULL, purpose TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS agent_skill_publications (
 candidate_id TEXT PRIMARY KEY REFERENCES agent_skill_candidates(id), task_id TEXT NOT NULL,
 actor TEXT NOT NULL, note TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS agent_action_grounding (
 action_id TEXT PRIMARY KEY REFERENCES agent_actions(id) ON DELETE CASCADE, details TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_target_profiles (
 name TEXT PRIMARY KEY, config TEXT NOT NULL, digest TEXT NOT NULL, created REAL NOT NULL, actor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_target_controls (name TEXT PRIMARY KEY, enabled INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS agent_task_recoveries (
 task_id TEXT PRIMARY KEY, source_task TEXT NOT NULL UNIQUE REFERENCES agent_tasks(id) ON DELETE CASCADE,
 snapshot TEXT NOT NULL, note TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS agent_task_authorizations (
 task_id TEXT PRIMARY KEY REFERENCES agent_task_recoveries(task_id) ON DELETE CASCADE, details TEXT NOT NULL);
"""


def _open_connection(driver: Any, path: str) -> Any:
    try:
        return driver.connect(path, timeout=5, isolation_level=None)
    except driver.Error as error:
        raise AgentTaskError("agent runtime database could not be opened") from error


def _request_identity(owner: dict, key: str) -> tuple[str, str]:
    if not isinstance(key, str) or not key or len(key) > 256:
        raise AgentTaskError("idempotency_key requires between one and 256 characters")
    owner_key = json.dumps([owner.get("user_id"), owner.get("store_path")])
    try:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    except UnicodeError:
        raise AgentTaskError("idempotency_key requires valid Unicode") from None
    return owner_key, digest


def _request_key(connection: Any, owner: dict, key: str, spec: dict, identifier: str) -> str | None:
    owner_key, digest = _request_identity(owner, key)
    spec_hash = request_spec_digest(spec)
    row = connection.execute("SELECT task_id,spec_hash FROM agent_request_keys WHERE owner_key=? AND key_hash=?",
                             (owner_key, digest)).fetchone()
    if row is not None:
        if row["spec_hash"] != spec_hash:
            raise AgentTaskError("idempotency_key was already used for a different task specification")
        return str(row["task_id"])
    # The deferred foreign key is satisfied by the task inserted in this transaction.
    connection.execute("INSERT INTO agent_request_keys VALUES (?,?,?,?)", (owner_key, digest, spec_hash, identifier))
    return None


def request_spec_digest(spec: dict) -> str:
    """Hash the exact normalized specification used by accepted request keys."""
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode("utf-8")).hexdigest()


def _bind_trigger_event(connection: Any, event: tuple[str, str, str] | None, task_id: str, now: float) -> None:
    if event is not None:
        connection.execute("INSERT INTO agent_trigger_events VALUES (?,?,?,?,?)", (*event, task_id, now))


class AgentTaskStore:
    """A lazy, per-operation SQLite store; reads never expose live mutable state."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(Path(path).resolve())
        self._ready = False

    @contextmanager
    def connection(self, *, write: bool = False) -> Iterator[Any]:
        """Own a connection and atomically commit or roll back a write transaction."""
        driver = require_sqlite3()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = _open_connection(driver, self.path)
        try:
            Path(self.path).chmod(0o600)
            connection.row_factory = driver.Row
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

    def create(self, spec: dict, owner: dict, *, idempotency_key: str | None = None,
               trigger_event: tuple[str, str, str] | None = None,
               recovery: tuple[str, str, str] | None = None, authorization: dict | None = None) -> str:
        """Persist an immutable authorized task snapshot before it can execute."""
        identifier = uuid.uuid4().hex
        now = time.time()
        with self.connection(write=True) as connection:
            if idempotency_key is not None:
                existing = _request_key(connection, owner, idempotency_key, spec, identifier)
                if existing is not None:
                    _bind_trigger_event(connection, trigger_event, existing, now)
                    return existing
            connection.execute("INSERT INTO agent_tasks(id,spec,owner,state,created,updated) VALUES (?,?,?,?,?,?)",
                               (identifier, json.dumps(spec), json.dumps(owner), "queued", now, now))
            _bind_trigger_event(connection, trigger_event, identifier, now)
            if recovery is not None:
                connection.execute("INSERT INTO agent_task_recoveries VALUES (?,?,?,?,?)",
                                   (identifier, *recovery, now))
            if authorization is not None:
                if recovery is None:
                    raise AgentTaskError("successor authorization requires a recovery link")
                connection.execute("INSERT INTO agent_task_authorizations VALUES (?,?)",
                                   (identifier, json.dumps(authorization)))
        return identifier

    def lookup_request(self, owner: dict, key: str) -> str | None:
        """Read the exact owner's request key without creating or resubmitting a task."""
        record = self.request_record(owner, key)
        return record["task_id"] if record else None

    def request_record(self, owner: dict, key: str) -> dict[str, Any] | None:
        """Read accepted identity and immutable spec digest from the same request snapshot."""
        identity = _request_identity(owner, key)
        with self.connection() as connection:
            row = connection.execute(
                "SELECT task_id,spec_hash FROM agent_request_keys "
                "WHERE owner_key=? AND key_hash=?", identity).fetchone()
        return dict(row) if row else None

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

    def transition(self, task_id: str, expected: str, state: str, *,
                   reason: str = "", verification: Any = None) -> bool:
        """Compare and publish nonterminal state without overwriting concurrent control requests."""
        if expected not in STATES - TERMINAL or state not in STATES:
            raise AgentTaskError("invalid conditional task transition")
        reports = json.dumps(detached(verification or []))
        with self.connection(write=True) as connection:
            cursor = connection.execute(
                "UPDATE agent_tasks SET state=?,reason=?,updated=?,verification=? WHERE id=? AND state=?",
                (state, reason, time.time(), reports, task_id, expected))
            if cursor.rowcount == 1 and expected == "verifying" and state == "succeeded":
                connection.execute("INSERT OR REPLACE INTO agent_completion VALUES (?,1,?)", (task_id, time.time()))
            return cursor.rowcount == 1

    def start(self, task_id: str) -> None:
        """Set the durable start time once, so restarts do not reset the wall budget."""
        with self.connection(write=True) as connection:
            cursor = connection.execute(
                "UPDATE agent_tasks SET started=COALESCE(started,?),state='running' "
                "WHERE id=? AND state IN ('queued','running','verifying')", (time.time(), task_id))
            if cursor.rowcount != 1:
                raise AgentTaskError("task stopped before control activation")

    def prepare(self, task_id: str, command: str, arguments: dict, *, grounding: dict | None = None) -> str:
        """Durably record the next operation before any external side effect."""
        identifier = uuid.uuid4().hex
        with self.connection(write=True) as connection:
            connection.execute("INSERT INTO agent_actions VALUES (?,?,?,?,?,?,?)",
                               (identifier, task_id, command, json.dumps(arguments), "prepared", None, time.time()))
            if grounding is not None:
                connection.execute("INSERT INTO agent_action_grounding VALUES (?,?)",
                                   (identifier, json.dumps(detached(grounding), allow_nan=False)))
        return identifier

    def settle(self, action_id: str, status: str, result: Any = None) -> None:
        """Publish one action outcome and count its first terminal receipt only once."""
        with self.connection(write=True) as connection:
            row = connection.execute("SELECT task_id,status FROM agent_actions WHERE id=?", (action_id,)).fetchone()
            if row is None:
                raise AgentTaskError("unknown action receipt")
            allowed = {"prepared": {"dispatched", "failed"}, "dispatched": {"confirmed", "uncertain", "failed"}}
            if status not in allowed.get(row["status"], set()):
                raise AgentTaskError("action receipt cannot change after its outcome was committed")
            connection.execute("UPDATE agent_actions SET status=?,result=? WHERE id=?",
                               (status, json.dumps(detached(result)), action_id))
            if status in {"confirmed", "uncertain", "failed"} and row["status"] in {"prepared", "dispatched"}:
                connection.execute("UPDATE agent_tasks SET steps=steps+1,updated=? WHERE id=?",
                                   (time.time(), row["task_id"]))

    def actions(self, task_id: str) -> List[dict[str, Any]]:
        """Return independent action receipts in their original execution order."""
        with self.connection() as connection:
            rows = connection.execute("SELECT a.*,r.actor AS reviewed_by,r.decision AS review_decision,"
                                      "g.details AS grounding "
                                      "FROM agent_actions a LEFT JOIN agent_reviews r ON a.id=r.action_id "
                                      "LEFT JOIN agent_action_grounding g ON a.id=g.action_id "
                                      "WHERE a.task_id=? ORDER BY a.created,a.rowid",
                                      (task_id,)).fetchall()
        return [_receipt(row) for row in rows]

    def recover(self) -> None:
        """Mark abandoned live work for review; never replay an uncertain effect."""
        with self.connection(write=True) as connection:
            connection.execute("UPDATE agent_actions SET status='uncertain' WHERE status='dispatched'")
            connection.execute("UPDATE agent_actions SET status='failed' WHERE status='prepared'")
            connection.execute("UPDATE agent_tasks SET steps=MAX(steps,(SELECT COUNT(*) FROM agent_actions "
                               "WHERE task_id=agent_tasks.id "
                               "AND status IN ('confirmed','uncertain','failed','not_applied')))")
            connection.execute("UPDATE agent_tasks SET state='recovering',reason='runtime restarted' "
                               "WHERE state IN ('running','verifying','pausing','cancelling')")
            connection.execute("UPDATE agent_control SET owner=''")


def _receipt(row: Any) -> dict:
    result = dict(row)
    result["arguments"] = json.loads(result["arguments"])
    result["result"] = json.loads(result["result"]) if result["result"] is not None else None
    grounding = result.pop("grounding", None)
    if grounding is not None:
        result["grounding"] = json.loads(grounding)
    return result
