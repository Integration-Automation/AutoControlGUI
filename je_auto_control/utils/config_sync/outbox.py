"""Durable queue of local changes that have not reached the sync server yet.

A change made while the server is unreachable used to exist only in the
caller's memory: closing the program lost it, and the caller had no way to
know which pushes had landed. :class:`SyncOutbox` keeps every pending
:class:`~je_auto_control.utils.config_sync.versions.SyncOperation` in SQLite
under its operation id, so it survives a restart and is sent again -- with
the same id, which makes the resend harmless when the first attempt did
arrive -- until the server has taken it.

Failed attempts back off exponentially up to a ceiling, a drain makes a
bounded number of attempts, and every wait can be cancelled. One database
can serve several accounts and servers: each ``(account, endpoint)`` pair has
its own queue and its own remembered state.

Pure standard library; imports no ``PySide6``.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, ContextManager, List, Optional, Sequence, Union

from je_auto_control.utils.config_sync.client import (
    ConfigBucket, ConfigSyncError, FullResyncRequired,
)
from je_auto_control.utils.config_sync.versions import SyncOperation
from je_auto_control.utils.sqlite_support import autocommit_connection, sqlite_errors_as

DEFAULT_BASE_DELAY_S = 2.0
DEFAULT_MAX_DELAY_S = 300.0
DEFAULT_DRAIN_ATTEMPTS = 5
_BASELINE = "baseline"
_GO = "go"
_EMPTY = "empty"
_CANCELLED = ""

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS operations ("
    " seq INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL, endpoint TEXT NOT NULL,"
    " operation_id TEXT NOT NULL, body TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,"
    " next_attempt REAL NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '',"
    " UNIQUE (account, endpoint, operation_id))",
    "CREATE TABLE IF NOT EXISTS state ("
    " account TEXT NOT NULL, endpoint TEXT NOT NULL, name TEXT NOT NULL, value TEXT NOT NULL,"
    " PRIMARY KEY (account, endpoint, name))",
)


class OutboxError(ConfigSyncError):
    """The outbox database could not be opened, read or written."""


def default_outbox_path() -> Path:
    """``~/.je_auto_control/config_sync_outbox.sqlite3``, resolved at call time."""
    return Path.home() / ".je_auto_control" / "config_sync_outbox.sqlite3"


@dataclass(frozen=True)
class DrainReport:
    """How a :meth:`SyncOutbox.drain` ended.

    ``sent`` operations were accepted, ``pending`` are still queued,
    ``attempts`` sends were made. ``offline`` is true when the last attempt
    failed (``error`` says why); ``cancelled`` when the cancel event ended it.
    """
    sent: int = 0
    pending: int = 0
    attempts: int = 0
    offline: bool = False
    cancelled: bool = False
    error: str = ""


class SyncOutbox:
    """The pending operations of one account on one sync endpoint."""

    def __init__(self, db_path: Union[str, Path, None] = None, *, account: str, endpoint: str,
                 base_delay_s: float = DEFAULT_BASE_DELAY_S,
                 max_delay_s: float = DEFAULT_MAX_DELAY_S) -> None:
        if not account or not endpoint:
            raise OutboxError("an outbox needs an account and an endpoint")
        self._configured_path = db_path
        self._scope = (str(account), str(endpoint).rstrip("/"))
        self._base_delay = max(0.0, float(base_delay_s))
        self._max_delay = max(self._base_delay, float(max_delay_s))
        self._resolved_path: Optional[str] = None

    def _connection(self) -> ContextManager[Any]:
        if self._resolved_path is None:
            configured = self._configured_path
            path = Path(configured) if configured is not None else default_outbox_path()
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise OutboxError(f"cannot create {path.parent}: {error}") from error
            with autocommit_connection(str(path)) as connection:
                for statement in _SCHEMA:
                    connection.execute(statement)
            self._resolved_path = str(path)
        return autocommit_connection(self._resolved_path)

    @sqlite_errors_as(OutboxError)
    def enqueue(self, operation: SyncOperation) -> None:
        """Queue ``operation``; queueing the same operation id again is a no-op."""
        if not operation.operation_id:
            raise OutboxError("an operation needs an operation id to be queued")
        with self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO operations (account, endpoint, operation_id, body) "
                "VALUES (?, ?, ?, ?)",
                (*self._scope, operation.operation_id, json.dumps(operation.to_dict())))

    @sqlite_errors_as(OutboxError)
    def pending(self) -> List[SyncOperation]:
        """Every queued operation, oldest first."""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT body FROM operations WHERE account = ? AND endpoint = ? ORDER BY seq",
                self._scope).fetchall()
        return [SyncOperation.from_dict(json.loads(row["body"])) for row in rows]

    @sqlite_errors_as(OutboxError)
    def acknowledge(self, operation_ids: Sequence[str]) -> None:
        """Remove operations the server has accepted."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(
                "DELETE FROM operations WHERE account = ? AND endpoint = ? AND operation_id = ?",
                [(*self._scope, operation_id) for operation_id in operation_ids])
            connection.execute("COMMIT")

    def retry_delay(self, attempts: int) -> float:
        """Seconds to wait after ``attempts`` failures: doubling, never above the ceiling."""
        if attempts <= 0:
            return 0.0
        return min(self._max_delay, self._base_delay * (2 ** min(attempts - 1, 32)))

    @sqlite_errors_as(OutboxError)
    def record_failure(self, operation_ids: Sequence[str], *, now: float, error: str = "") -> None:
        """Count a failed send and schedule the next attempt for those operations."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for operation_id in operation_ids:
                row = connection.execute(
                    "SELECT attempts FROM operations WHERE account = ? AND endpoint = ? "
                    "AND operation_id = ?", (*self._scope, operation_id)).fetchone()
                if row is None:
                    continue
                attempts = int(row["attempts"]) + 1
                connection.execute(
                    "UPDATE operations SET attempts = ?, next_attempt = ?, last_error = ? "
                    "WHERE account = ? AND endpoint = ? AND operation_id = ?",
                    (attempts, now + self.retry_delay(attempts), error[:500],
                     *self._scope, operation_id))
            connection.execute("COMMIT")

    @sqlite_errors_as(OutboxError)
    def seconds_until_due(self, now: float) -> Optional[float]:
        """How long until the queue may be sent again; ``None`` when it is empty.

        The whole queue goes out together and in order, so it waits for the
        operation that has to wait longest.
        """
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n, MAX(next_attempt) AS due FROM operations "
                "WHERE account = ? AND endpoint = ?", self._scope).fetchone()
        if not row["n"]:
            return None
        return max(0.0, float(row["due"]) - now)

    @sqlite_errors_as(OutboxError)
    def clear(self) -> List[SyncOperation]:
        """Empty the queue and return what was in it (for a full resync)."""
        discarded = self.pending()
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM operations WHERE account = ? AND endpoint = ?", self._scope)
        return discarded

    @sqlite_errors_as(OutboxError)
    def get_state(self, name: str) -> Optional[Any]:
        """A remembered JSON value for this account and endpoint, or ``None``."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM state WHERE account = ? AND endpoint = ? AND name = ?",
                (*self._scope, name)).fetchone()
        return None if row is None else json.loads(row["value"])

    @sqlite_errors_as(OutboxError)
    def set_state(self, name: str, value: Any) -> None:
        """Remember a JSON value for this account and endpoint."""
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO state (account, endpoint, name, value) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(account, endpoint, name) DO UPDATE SET value = excluded.value",
                (*self._scope, name, json.dumps(value)))

    def load_baseline(self) -> Optional[ConfigBucket]:
        """The bucket this device last merged, or ``None`` before its first sync."""
        body = self.get_state(_BASELINE)
        return None if body is None else ConfigBucket.from_dict(body)

    def save_baseline(self, bucket: ConfigBucket) -> None:
        """Remember ``bucket`` as the state local changes are measured against."""
        self.set_state(_BASELINE, bucket.to_dict())

    def drain(self, send: Callable[[List[SyncOperation]], Any], *,
              cancel: Optional[threading.Event] = None,
              max_attempts: int = DEFAULT_DRAIN_ATTEMPTS, wait: bool = True,
              clock: Callable[[], float] = time.time) -> DrainReport:
        """Send the queue through ``send`` until it is empty or attempts run out.

        ``send(operations)`` must raise :class:`ConfigSyncError` when the
        operations did not (or may not have) arrived; they stay queued under
        the same ids and are tried again after the back-off delay. With
        ``wait`` false a queue that is still backing off is left alone.
        Setting ``cancel`` ends the drain at the next check, including in the
        middle of a wait. :class:`FullResyncRequired` is not retried.
        """
        stop = cancel if cancel is not None else threading.Event()
        sent = attempts = 0
        error = ""
        while attempts < max(1, int(max_attempts)):
            turn = self._await_turn(stop, wait, clock())
            if turn == _EMPTY:
                return DrainReport(sent=sent, attempts=attempts)
            if turn != _GO:
                error = error or turn
                break
            batch = self.pending()
            attempts += 1
            error = self._send(send, batch, clock)
            if not error:
                sent += len(batch)
        return DrainReport(sent=sent, pending=len(self.pending()), attempts=attempts,
                           offline=bool(error), cancelled=stop.is_set(), error=error)

    def _await_turn(self, stop: threading.Event, wait: bool, now: float) -> str:
        """Wait out the back-off: ``_GO``, ``_EMPTY``, or why the drain must stop."""
        delay = self.seconds_until_due(now)
        if delay is None:
            return _EMPTY
        if delay > 0 and not wait:
            return "waiting to retry after an earlier failure"
        if stop.is_set() or (delay > 0 and stop.wait(delay)):
            return _CANCELLED
        return _GO

    def _send(self, send: Callable[[List[SyncOperation]], Any], batch: List[SyncOperation],
              clock: Callable[[], float]) -> str:
        """Send one batch; ``""`` when it was accepted, else the failure text."""
        ids = [operation.operation_id for operation in batch]
        try:
            send(batch)
        except FullResyncRequired:
            raise
        except ConfigSyncError as failure:
            self.record_failure(ids, now=clock(), error=str(failure))
            return str(failure) or "send failed"
        self.acknowledge(ids)
        return ""


__all__ = [
    "DEFAULT_BASE_DELAY_S", "DEFAULT_DRAIN_ATTEMPTS", "DEFAULT_MAX_DELAY_S",
    "DrainReport", "OutboxError", "SyncOutbox", "default_outbox_path",
]
