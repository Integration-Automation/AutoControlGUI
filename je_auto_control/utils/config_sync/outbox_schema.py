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


def initialize_outbox(connection: Connection) -> None:
    """Reject foreign/future databases before modifying tables; serialize first-use initialization."""
    if _version(connection) == (_APPLICATION, 1):
        return
    connection.execute("BEGIN IMMEDIATE")
    version = _version(connection)
    if version == (_APPLICATION, 1):
        connection.execute("COMMIT")
        return
    tables = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    if version != (0, 0) or tables:
        raise ConfigStoreError("not a supported sync-outbox database")
    for statement in _TABLES:
        connection.execute(statement)
    connection.execute(f"PRAGMA application_id = {_APPLICATION}")
    connection.execute("PRAGMA user_version = 1")
    connection.execute("COMMIT")


def _version(connection: Connection) -> tuple[int, int]:
    return (connection.execute("PRAGMA application_id").fetchone()[0],
            connection.execute("PRAGMA user_version").fetchone()[0])
