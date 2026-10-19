"""Identify and initialize only an owned SQLite sync-outbox database."""
from __future__ import annotations

from typing import TYPE_CHECKING

from je_auto_control.utils.config_sync.contract import ConfigStoreError

if TYPE_CHECKING:
    from sqlite3 import Connection

_APPLICATION = 1094931289
_TABLES = (
    "CREATE TABLE sync_namespaces (endpoint TEXT NOT NULL, user_id TEXT NOT NULL, origin TEXT NOT NULL, "
    "epoch INTEGER NOT NULL DEFAULT 0, confirmed_revision INTEGER NOT NULL DEFAULT 0, snapshot TEXT, "
    "PRIMARY KEY (endpoint, user_id))",
    "CREATE TABLE sync_operations (sequence INTEGER PRIMARY KEY AUTOINCREMENT, endpoint TEXT NOT NULL, "
    "user_id TEXT NOT NULL, operation_id TEXT NOT NULL, wire TEXT NOT NULL, digest TEXT NOT NULL, "
    "status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, "
    "next_attempt REAL NOT NULL DEFAULT 0, last_attempt REAL NOT NULL DEFAULT 0, prepared TEXT, "
    "lease_owner TEXT NOT NULL DEFAULT '', lease_until REAL NOT NULL DEFAULT 0, "
    "error TEXT NOT NULL DEFAULT '', delivered_revision INTEGER, UNIQUE(endpoint, user_id, operation_id))",
)
_CONTROL_TABLE = (
    "CREATE TABLE sync_controls (endpoint TEXT NOT NULL, user_id TEXT NOT NULL, operation_id TEXT NOT NULL, "
    "kind TEXT NOT NULL, wire TEXT NOT NULL, digest TEXT NOT NULL, prepared TEXT, "
    "status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, "
    "next_attempt REAL NOT NULL DEFAULT 0, last_attempt REAL NOT NULL DEFAULT 0, "
    "lease_owner TEXT NOT NULL DEFAULT '', lease_until REAL NOT NULL DEFAULT 0, "
    "error TEXT NOT NULL DEFAULT '', receipt_revision INTEGER, PRIMARY KEY(endpoint,user_id))"
)
_CONTROL_RECEIPTS = (
    "CREATE TABLE sync_control_receipts (endpoint TEXT NOT NULL, user_id TEXT NOT NULL, operation_id TEXT NOT NULL, "
    "wire TEXT NOT NULL, digest TEXT NOT NULL, revision INTEGER NOT NULL, PRIMARY KEY(endpoint,user_id,operation_id))"
)


def initialize_outbox(connection: Connection) -> None:
    """Reject foreign/future databases before modifying tables; serialize first-use initialization."""
    if _version(connection) == (_APPLICATION, 2):
        return
    connection.execute("BEGIN IMMEDIATE")
    version = _version(connection)
    if version == (_APPLICATION, 2):
        connection.execute("COMMIT")
        return
    if version == (_APPLICATION, 1):
        _require_version_one_tables(connection)
        connection.execute(_CONTROL_TABLE)
        connection.execute(_CONTROL_RECEIPTS)
        connection.execute("PRAGMA user_version = 2")
        connection.execute("COMMIT")
        return
    tables = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    if version != (0, 0) or tables:
        raise ConfigStoreError("not a supported sync-outbox database")
    for statement in _TABLES:
        connection.execute(statement)
    connection.execute(_CONTROL_TABLE)
    connection.execute(_CONTROL_RECEIPTS)
    connection.execute(f"PRAGMA application_id = {_APPLICATION}")
    connection.execute("PRAGMA user_version = 2")
    connection.execute("COMMIT")


def _version(connection: Connection) -> tuple[int, int]:
    return (connection.execute("PRAGMA application_id").fetchone()[0],
            connection.execute("PRAGMA user_version").fetchone()[0])


def _require_version_one_tables(connection: Connection) -> None:
    expected = {
        "sync_namespaces": {"endpoint", "user_id", "origin", "epoch", "confirmed_revision", "snapshot"},
        "sync_operations": {"sequence", "endpoint", "user_id", "operation_id", "wire", "digest", "status", "attempts",
                            "next_attempt", "last_attempt", "prepared", "lease_owner", "lease_until", "error",
                            "delivered_revision"},
    }
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                                  "AND name NOT LIKE 'sqlite_%'")}
    if tables != set(expected):
        raise ConfigStoreError("invalid owned version-one outbox schema")
    for name, columns in expected.items():
        # Names are fixed schema literals above, never user-supplied SQL identifiers.
        actual = {row[1] for row in connection.execute(f"PRAGMA table_info({name})")}
        if actual != columns:
            raise ConfigStoreError("invalid owned version-one outbox columns")
