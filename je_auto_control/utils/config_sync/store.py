"""Lazy SQLite configuration buckets with atomic revision checks and durable operation receipts."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, cast

from je_auto_control.utils.config_sync.client import ConfigBucket, ConfigSyncError
from je_auto_control.utils.config_sync.database import SyncDatabase
from je_auto_control.utils.config_sync.contract import (
    ConfigRevisionConflict, ConfigStoreError, ConfigStoreFull, _MAX_REVISION, _encoded, _identifier, _revision,
)

if TYPE_CHECKING:
    from sqlite3 import Connection

def _bucket_body(user_id: str, bucket: ConfigBucket) -> str:
    if bucket.user_id != user_id:
        raise ConfigSyncError("bucket user_id mismatch")
    _revision(bucket.revision)
    body = bucket.to_dict()
    encoded = _encoded(body)
    parsed = ConfigBucket.from_dict(json.loads(encoded))
    if parsed.to_dict() != body:
        raise ConfigSyncError("config bucket keys must retain their JSON identity")
    return encoded


def _parse_bucket(body: dict[str, object]) -> ConfigBucket:
    _revision(cast(int, body.get("revision", 0)))
    if not isinstance(body.get("sections", {}), dict):
        raise ConfigSyncError("bucket sections must be an object")
    encoded = _encoded(body)
    if json.loads(encoded) != body:
        raise ConfigSyncError("config bucket keys must retain their JSON identity")
    return ConfigBucket.from_dict(body)


class ConfigStore:
    """Persist account-isolated buckets; construction neither resolves a default path nor opens SQLite.

    The first operation resolves AUTOCONTROL_CONFIG_STORE or
    ~/.autocontrol/config-sync.sqlite3. Each operation owns and closes a connection.
    Separate instances/processes serialize commits through BEGIN IMMEDIATE, so
    comparing the base, storing data and saving its retry receipt are one transaction.
    """

    def __init__(self, path: Optional[str | Path] = None, *, max_users: int = 1024) -> None:
        if isinstance(max_users, bool) or not isinstance(max_users, int) or max_users < 1:
            raise ConfigSyncError("max_users must be a positive integer")
        self._database = SyncDatabase(path, "AUTOCONTROL_CONFIG_STORE", "config-sync.sqlite3", _initialize)
        self._max_users = max_users

    def get(self, user_id: str) -> Optional[ConfigBucket]:
        """Read an independent typed bucket at its server-committed revision, or None."""
        body = self.get_document(user_id)
        _require_plain(body)
        return ConfigBucket.from_dict(body) if body is not None else None

    def get_document(self, user_id: str) -> Optional[dict[str, object]]:
        """Read the committed JSON document, including opaque legacy fields without aliasing storage."""
        _identifier(user_id, "user_id")
        with self._database.connection() as connection:
            row = connection.execute("SELECT revision, body FROM config_buckets WHERE user_id = ?",
                                     (user_id,)).fetchone()
        if row is None:
            return None
        body = cast(dict[str, object], json.loads(row[1]))
        body["revision"] = row[0]
        return body

    def commit(self, user_id: str, bucket: ConfigBucket, *, base_revision: int, operation_id: str) -> int:
        """Commit against one base; an identical operation retry returns its original revision.

        Receipts survive later commits and restarts. Reusing an ID with different
        content or base raises ConfigRevisionConflict, even if the base is current.
        The input bucket is never mutated and its revision does not choose the next revision.
        """
        body = _bucket_body(user_id, bucket)
        return self._commit_document(user_id, body, base_revision, operation_id, _plain_document)

    def _commit_document(self, user_id: str, body: str, base_revision: int, operation_id: str,
                         transform: Callable[[Optional[dict[str, object]], int], str]) -> int:
        _identifier(user_id, "user_id")
        _identifier(operation_id, "operation_id")
        _revision(base_revision)
        digest = sha256(body.encode("ascii")).hexdigest()
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = _current_revision(connection, user_id)
            receipt = connection.execute(
                "SELECT base_revision, payload_sha, revision FROM config_operations "
                "WHERE user_id = ? AND operation_id = ?",
                (user_id, operation_id),
            ).fetchone()
            if receipt is not None:
                if receipt[:2] != (base_revision, digest):
                    raise ConfigRevisionConflict(current, "operation_id already identifies a different config request",
                                                 code="operation_id_conflict")
                connection.execute("COMMIT")
                return int(receipt[2])
            if current != base_revision or current >= _MAX_REVISION:
                raise ConfigRevisionConflict(current)
            row = connection.execute("SELECT body FROM config_buckets WHERE user_id = ?", (user_id,)).fetchone()
            previous = json.loads(row[0]) if row else None
            if previous is not None:
                previous["revision"] = current
            stored = transform(previous, current + 1)
            revision = self._write(connection, user_id, stored or body, current, base_revision)
            connection.execute("INSERT INTO config_operations VALUES (?, ?, ?, ?, ?)",
                               (user_id, operation_id, base_revision, digest, revision))
            connection.execute("COMMIT")
            return revision

    def put_legacy(self, user_id: str, body: dict[str, object]) -> int:
        """Perform an explicit blind compatibility write; the HTTP route must separately opt in.

        Legacy documents retain opaque JSON fields, while revision remains server-owned.
        This operation offers no retry identity and is never selected by v2 clients.
        """
        _identifier(user_id, "user_id")
        if body.get("user_id", user_id) != user_id:
            raise ConfigSyncError("bucket user_id mismatch")
        encoded = _encoded(dict(body, user_id=user_id))
        _require_plain(body)
        with self._database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = _current_revision(connection, user_id)
            row = connection.execute("SELECT body FROM config_buckets WHERE user_id = ?", (user_id,)).fetchone()
            _require_plain(json.loads(row[0]) if row else None)
            revision = self._write(connection, user_id, encoded, current, current)
            connection.execute("COMMIT")
            return revision

    def _write(self, connection: Connection, user_id: str, body: str, current: int, base: int) -> int:
        if current != base or current >= _MAX_REVISION:
            raise ConfigRevisionConflict(current)
        if current == 0 and connection.execute("SELECT count(*) FROM config_buckets").fetchone()[0] >= self._max_users:
            raise ConfigStoreFull("config account capacity reached")
        revision = current + 1
        connection.execute("INSERT INTO config_buckets VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
                           "revision = excluded.revision, body = excluded.body", (user_id, revision, body))
        return revision


def _current_revision(connection: Connection, user_id: str) -> int:
    row = connection.execute("SELECT revision FROM config_buckets WHERE user_id = ?", (user_id,)).fetchone()
    return int(row[0]) if row is not None else 0


def _require_plain(body: Optional[dict[str, object]]) -> None:
    if body is not None and body.get("kind") == "autocontrol.causal":
        raise ConfigRevisionConflict(cast(int, body.get("revision", 0)), "causal protocol required for this account",
                                     code="causal_protocol_required")


def _plain_document(previous: Optional[dict[str, object]], _revision_number: int) -> str:
    _require_plain(previous)
    return ""


def _initialize(connection: Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, 1):
        raise ConfigStoreError("unsupported config database schema")
    if version == 1:
        return
    connection.executescript(
        "BEGIN IMMEDIATE;"
        "CREATE TABLE IF NOT EXISTS config_buckets "
        "(user_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL);"
        "CREATE TABLE IF NOT EXISTS config_operations (user_id TEXT NOT NULL, operation_id TEXT NOT NULL, "
        "base_revision INTEGER NOT NULL, payload_sha TEXT NOT NULL, revision INTEGER NOT NULL, "
        "PRIMARY KEY (user_id, operation_id));"
        "PRAGMA user_version = 1; COMMIT;"
    )
