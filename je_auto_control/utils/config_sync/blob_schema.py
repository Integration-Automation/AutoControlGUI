"""Identify an owned immutable asset-chunk database before creating account quotas or verified blob receipts."""
from __future__ import annotations

from typing import TYPE_CHECKING

from je_auto_control.utils.config_sync.contract import ConfigStoreError

if TYPE_CHECKING:
    from sqlite3 import Connection

_APPLICATION = 0x4143626c
_TABLES = (
    'CREATE TABLE sync_asset_users (user_id TEXT PRIMARY KEY,bytes INTEGER NOT NULL DEFAULT 0)',
    'CREATE TABLE sync_asset_chunks (user_id TEXT NOT NULL,digest TEXT NOT NULL,body BLOB NOT NULL,'
    'PRIMARY KEY(user_id,digest))',
    'CREATE TABLE sync_asset_blobs (user_id TEXT NOT NULL,digest TEXT NOT NULL,wire TEXT NOT NULL,'
    'PRIMARY KEY(user_id,digest))',
)


def initialize_blobs(connection: Connection) -> None:
    """Serialize initialization and refuse foreign/future databases without modifying their tables."""
    if _version(connection) == (_APPLICATION, 1):
        return
    connection.execute('BEGIN IMMEDIATE')
    version = _version(connection)
    if version == (_APPLICATION, 1):
        connection.execute('COMMIT')
        return
    tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    if version != (0, 0) or tables:
        raise ConfigStoreError('not a supported asset-chunk database')
    for statement in _TABLES:
        connection.execute(statement)
    connection.execute(f'PRAGMA application_id={_APPLICATION}')
    connection.execute('PRAGMA user_version=1')
    connection.execute('COMMIT')


def _version(connection: Connection) -> tuple[int, int]:
    return (connection.execute('PRAGMA application_id').fetchone()[0],
            connection.execute('PRAGMA user_version').fetchone()[0])
