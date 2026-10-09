"""SQLite-backed, revision-checked store for config-sync buckets.

The signaling server kept each user's bucket in a dict: a restart lost every
bucket, and a ``PUT`` replaced whatever was there, so two machines pushing at
the same moment silently dropped one side's changes. :class:`ConfigStore`
keeps the buckets in one SQLite file and only accepts a write that names the
revision it was based on -- the comparison and the write happen inside one
``BEGIN IMMEDIATE`` transaction, so two writers (threads or processes) cannot
both pass the check.

A write also carries an ``operation_id``. A client that never saw the reply
to a commit (timeout, dropped connection) repeats it with the same id and is
answered with the revision the first attempt produced instead of a conflict
against its own write. The store keeps a hash of what each operation wrote,
so an id reused for *different* content is refused with
:class:`~je_auto_control.utils.config_sync.bucket.OperationMismatchError`
rather than reported as committed.

Pure standard library; imports no ``PySide6``.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, ContextManager, Optional

from je_auto_control.utils.config_sync.bucket import (
    ConfigBucket, ConfigSyncError, OperationMismatchError,
)
from je_auto_control.utils.sqlite_support import autocommit_connection, sqlite_errors_as

#: How many distinct users may hold a bucket in one store.
DEFAULT_MAX_USERS = 1024
#: Operation ids remembered per user for retry de-duplication. A retry older
#: than this many commits is answered as a revision conflict, which is safe:
#: the client fetches, merges and pushes again.
DEFAULT_MAX_OPERATIONS = 256
_MAX_OPERATION_ID_CHARS = 128

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS buckets ("
    " user_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,"
    " body TEXT NOT NULL, updated_at REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS operations ("
    " seq INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,"
    " operation_id TEXT NOT NULL, revision INTEGER NOT NULL,"
    " content_hash TEXT NOT NULL DEFAULT '',"
    " UNIQUE (user_id, operation_id))",
)
#: Added to an ``operations`` table created before the content hash existed.
#: Its old rows keep an empty hash, which matches any content: there is
#: nothing to compare a write from before the upgrade against.
_ADD_CONTENT_HASH = "ALTER TABLE operations ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''"


class ConfigStoreError(ConfigSyncError):
    """The bucket database could not be opened, read or written."""


class RevisionConflictError(ConfigStoreError):
    """A commit named a ``base_revision`` that is no longer the current one."""

    def __init__(self, user_id: str, base_revision: int, current_revision: int) -> None:
        super().__init__(
            f"bucket {user_id!r} is at revision {current_revision}, "
            f"not the base revision {base_revision} this write was built on")
        self.user_id = user_id
        self.base_revision = base_revision
        self.current_revision = current_revision


class StoreCapacityError(ConfigStoreError):
    """A new user's bucket would exceed the store's user limit."""


def default_store_path() -> Path:
    """``~/.je_auto_control/config_sync.sqlite3``, resolved at call time."""
    return Path.home() / ".je_auto_control" / "config_sync.sqlite3"


def _checked_revision(base_revision: Any) -> int:
    if isinstance(base_revision, bool) or not isinstance(base_revision, int) or base_revision < 0:
        raise ConfigStoreError(f"base_revision must be an integer >= 0, got {base_revision!r}")
    return base_revision


def operation_content_hash(bucket: ConfigBucket, base_revision: int) -> str:
    """The SHA-256 naming what one write puts on the server.

    Covers the base revision and the whole bucket except its ``revision``
    field, which the store overwrites with the committed one -- so a resend
    hashes the same whatever revision the client believed it was at.
    """
    body = bucket.to_dict()
    body.pop("revision", None)
    canonical = json.dumps([int(base_revision), body], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _checked_operation_id(operation_id: Any) -> str:
    if (not isinstance(operation_id, str) or not operation_id
            or len(operation_id) > _MAX_OPERATION_ID_CHARS or not operation_id.isprintable()):
        raise ConfigStoreError(
            f"operation_id must be 1-{_MAX_OPERATION_ID_CHARS} printable characters")
    return operation_id


class ConfigStore:
    """Persistent map of user id -> bucket with compare-and-set commits.

    ``db_path`` of ``None`` means :func:`default_store_path`. Neither that
    path nor the file is touched until the first read or write, so building
    a store (as ``create_app`` does) has no side effect on disk.
    """

    def __init__(self, db_path: str | Path | None = None, *,
                 max_users: int = DEFAULT_MAX_USERS,
                 max_operations: int = DEFAULT_MAX_OPERATIONS) -> None:
        self._configured_path = db_path
        self._max_users = int(max_users)
        self._max_operations = max(1, int(max_operations))
        self._resolved_path: Optional[str] = None

    @property
    def path(self) -> Path:
        """Where the database lives (resolving the default if none was given)."""
        configured = self._configured_path
        return Path(configured) if configured is not None else default_store_path()

    def _connection(self) -> ContextManager[Any]:
        if self._resolved_path is None:
            path = self.path
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise ConfigStoreError(f"cannot create {path.parent}: {error}") from error
            with autocommit_connection(str(path)) as connection:
                for statement in _SCHEMA:
                    connection.execute(statement)
                columns = {row["name"] for row in connection.execute(
                    "PRAGMA table_info(operations)").fetchall()}
                if "content_hash" not in columns:
                    connection.execute(_ADD_CONTENT_HASH)
            self._resolved_path = str(path)
        return autocommit_connection(self._resolved_path)

    @sqlite_errors_as(ConfigStoreError)
    def get(self, user_id: str) -> Optional[ConfigBucket]:
        """The user's bucket with ``revision`` set to the committed revision."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT revision, body FROM buckets WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        try:
            bucket = ConfigBucket.from_dict(json.loads(row["body"]))
        except (json.JSONDecodeError, RecursionError) as error:
            raise ConfigStoreError(f"stored bucket for {user_id!r} is not JSON") from error
        bucket.revision = int(row["revision"])
        return bucket

    @sqlite_errors_as(ConfigStoreError)
    def revision(self, user_id: str) -> int:
        """The committed revision of the user's bucket; ``0`` when there is none."""
        with self._connection() as connection:
            return self._current_revision(connection, user_id)

    @sqlite_errors_as(ConfigStoreError)
    def commit(self, user_id: str, bucket: ConfigBucket, *,
               base_revision: int, operation_id: str) -> int:
        """Write ``bucket`` if the store is still at ``base_revision``.

        Returns the committed revision (``base_revision + 1``). A repeated
        ``operation_id`` carrying the same write returns the revision its
        first commit produced and writes nothing; carrying a different
        bucket or base revision it raises
        :class:`~je_auto_control.utils.config_sync.bucket.OperationMismatchError`.
        Raises :class:`RevisionConflictError` when another write got there
        first -- ``base_revision`` ``0`` means "no bucket yet" -- and
        :class:`StoreCapacityError` when a new user would exceed the user
        limit.
        """
        base = _checked_revision(base_revision)
        operation = _checked_operation_id(operation_id)
        self._require_owner(user_id, bucket)
        content = operation_content_hash(bucket, base)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            done = connection.execute(
                "SELECT revision, content_hash FROM operations "
                "WHERE user_id = ? AND operation_id = ?", (user_id, operation)).fetchone()
            if done is not None:
                connection.execute("COMMIT")
                return self._replayed(operation, done, content)
            current = self._current_revision(connection, user_id)
            if current != base:
                raise RevisionConflictError(user_id, base, current)
            revision = self._write(connection, user_id, bucket, current)
            self._remember(connection, user_id, operation, revision, content)
            connection.execute("COMMIT")
        return revision

    @staticmethod
    def _replayed(operation: str, done: Any, content: str) -> int:
        """The revision of a repeated operation, if it is the same write."""
        revision = int(done["revision"])
        recorded = str(done["content_hash"] or "")
        if recorded and recorded != content:
            raise OperationMismatchError(
                f"operation id {operation!r} already committed revision {revision} "
                "with different content; push again under a fresh id",
                operation_id=operation, revision=revision)
        return revision

    @sqlite_errors_as(ConfigStoreError)
    def overwrite(self, user_id: str, bucket: ConfigBucket) -> int:
        """Replace the bucket without a revision check; returns the new revision.

        This is the pre-version-2 behaviour and can silently drop a
        concurrent writer's changes; the signaling server only reaches it
        when started with the explicit compatibility setting.
        """
        self._require_owner(user_id, bucket)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            revision = self._write(
                connection, user_id, bucket, self._current_revision(connection, user_id))
            connection.execute("COMMIT")
        return revision

    @staticmethod
    def _require_owner(user_id: str, bucket: ConfigBucket) -> None:
        if bucket.user_id != user_id:
            raise ConfigStoreError(
                f"bucket belongs to {bucket.user_id!r}, not to {user_id!r}")

    @staticmethod
    def _current_revision(connection: Any, user_id: str) -> int:
        row = connection.execute(
            "SELECT revision FROM buckets WHERE user_id = ?", (user_id,)).fetchone()
        return 0 if row is None else int(row["revision"])

    def _write(self, connection: Any, user_id: str, bucket: ConfigBucket, current: int) -> int:
        if current == 0:
            # Revisions start at 1, so 0 means this user has no row yet.
            users = connection.execute("SELECT COUNT(*) AS n FROM buckets").fetchone()["n"]
            if int(users) >= self._max_users:
                raise StoreCapacityError(f"store already holds {users} users")
        revision = current + 1
        body = bucket.to_dict()
        body["revision"] = revision
        connection.execute(
            "INSERT INTO buckets (user_id, revision, body, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET revision = excluded.revision, "
            "body = excluded.body, updated_at = excluded.updated_at",
            (user_id, revision, json.dumps(body, sort_keys=True), time.time()))
        return revision

    def _remember(self, connection: Any, user_id: str, operation: str, revision: int,
                  content: str) -> None:
        connection.execute(
            "INSERT INTO operations (user_id, operation_id, revision, content_hash) "
            "VALUES (?, ?, ?, ?)", (user_id, operation, revision, content))
        connection.execute(
            "DELETE FROM operations WHERE user_id = ? AND seq NOT IN ("
            " SELECT seq FROM operations WHERE user_id = ? ORDER BY seq DESC LIMIT ?)",
            (user_id, user_id, self._max_operations))


__all__ = [
    "ConfigStore", "ConfigStoreError", "DEFAULT_MAX_OPERATIONS", "DEFAULT_MAX_USERS",
    "RevisionConflictError", "StoreCapacityError", "default_store_path",
    "operation_content_hash",
]
