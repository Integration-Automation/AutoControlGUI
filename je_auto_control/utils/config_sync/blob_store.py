"""Durable account-isolated chunks publish a blob receipt only after every byte, size and full hash verify."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import TYPE_CHECKING, BinaryIO, Optional, cast

from je_auto_control.utils.config_sync.asset_models import MAX_BUNDLE_BYTES
from je_auto_control.utils.config_sync.blob_models import CHUNK_BYTES, SyncAssetBlob, validate_digest
from je_auto_control.utils.config_sync.blob_schema import initialize_blobs
from je_auto_control.utils.config_sync.contract import ConfigStoreError, ConfigStoreFull, ConfigSyncError, _encoded
from je_auto_control.utils.config_sync.contract import _identifier
from je_auto_control.utils.config_sync.database import SyncDatabase

if TYPE_CHECKING:
    from sqlite3 import Connection


class SyncAssetStore:
    """Lazy immutable blob/chunk storage; quota failures and interrupted uploads never publish partial assets."""

    def __init__(self, path: Optional[str | Path] = None, *, max_users: int = 1024,
                   max_bytes: int = MAX_BUNDLE_BYTES, max_chunks: int = 8192, max_blobs: int = 4096) -> None:
        _limit(max_users)
        _limit(max_bytes)
        _limit(max_chunks)
        _limit(max_blobs)
        self._database = SyncDatabase(path, 'AUTOCONTROL_SYNC_ASSET_STORE', 'sync-assets.sqlite3', initialize_blobs)
        self._max_users = max_users
        self._max_bytes = max_bytes
        self._max_chunks = max_chunks
        self._max_blobs = max_blobs

    def put_chunk(self, user_id: str, digest: str, body: bytes) -> bool:
        """Store one verified nonempty bounded chunk once; repeat content consumes no additional quota."""
        _identifier(user_id, 'asset user_id')
        validate_digest(digest)
        _validate_chunk(digest, body, received=True)
        with self._database.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            existing = _chunk(connection, user_id, digest, missing_ok=True)
            if existing is not None:
                connection.execute('COMMIT')
                return False
            _admit(connection, user_id, self._max_users)
            used = connection.execute('SELECT bytes FROM sync_asset_users WHERE user_id=?', (user_id,)).fetchone()[0]
            if used + len(body) > self._max_bytes:
                raise ConfigStoreFull('asset account byte quota exceeded')
            _object_limit(connection, user_id, 'sync_asset_chunks', self._max_chunks)
            connection.execute('INSERT INTO sync_asset_chunks VALUES (?,?,?)', (user_id, digest, body))
            connection.execute('UPDATE sync_asset_users SET bytes=bytes+? WHERE user_id=?', (len(body), user_id))
            connection.execute('COMMIT')
        return True

    def read_chunk(self, user_id: str, digest: str) -> bytes:
        """Return only a bounded chunk whose stored bytes still match their content address."""
        _identifier(user_id, 'asset user_id')
        validate_digest(digest)
        with self._database.connection() as connection:
            body = _chunk(connection, user_id, digest)
        return cast(bytes, body)

    def missing_chunks(self, user_id: str, blob: SyncAssetBlob) -> tuple[str, ...]:
        """Query a bounded unique hash set without allocating complete blob bytes."""
        _validate_blob(user_id, blob)
        with self._database.connection() as connection:
            return tuple(digest for digest in dict.fromkeys(blob.chunks)
                         if _chunk(connection, user_id, digest, missing_ok=True) is None)

    def commit(self, user_id: str, blob: SyncAssetBlob) -> bool:
        """Verify all immutable chunks and atomically publish the canonical blob descriptor, or retain only chunks."""
        _validate_blob(user_id, blob)
        wire = _encoded(blob.to_dict())
        with self._database.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            if _receipt(connection, user_id, blob):
                connection.execute('COMMIT')
                return False
            _admit(connection, user_id, self._max_users)
            _object_limit(connection, user_id, 'sync_asset_blobs', self._max_blobs)
            _verify_blob(connection, user_id, blob)
            connection.execute('INSERT INTO sync_asset_blobs VALUES (?,?,?)', (user_id, blob.sha256, wire))
            connection.execute('COMMIT')
        return True

    def contains(self, user_id: str, blob: SyncAssetBlob) -> bool:
        """Read an exact canonical publication receipt; individual reads still reverify stored chunk bytes."""
        _validate_blob(user_id, blob)
        with self._database.connection() as connection:
            return _receipt(connection, user_id, blob)

    def open(self, user_id: str, blob: SyncAssetBlob) -> BinaryIO:
        """Return a verified seekable stream with bounded RAM; the caller owns and closes the returned stream."""
        if not self.contains(user_id, blob):
            raise ConfigSyncError('missing verified asset blob')
        # pylint: disable-next=consider-using-with  # reason: a successful return transfers stream ownership to the caller; finally closes every failed attempt
        stream = SpooledTemporaryFile(max_size=CHUNK_BYTES, mode='w+b')
        complete = False
        try:
            with self._database.connection() as connection:
                _verify_blob(connection, user_id, blob, output=cast(BinaryIO, stream))
            stream.seek(0)
            complete = True
            return cast(BinaryIO, stream)
        finally:
            if not complete:
                stream.close()

    def status(self, user_id: str) -> dict[str, int]:
        """Read bounded account counts without exposing chunk data or other accounts."""
        _identifier(user_id, 'asset user_id')
        with self._database.connection() as connection:
            row = connection.execute('SELECT bytes FROM sync_asset_users WHERE user_id=?', (user_id,)).fetchone()
            chunks = connection.execute('SELECT count(*) FROM sync_asset_chunks WHERE user_id=?',
                                         (user_id,)).fetchone()[0]
            blobs = connection.execute('SELECT count(*) FROM sync_asset_blobs WHERE user_id=?',
                                        (user_id,)).fetchone()[0]
        return {'bytes': row[0] if row else 0, 'chunks': chunks, 'blobs': blobs}


def _limit(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value < 2**63:
        raise ConfigSyncError('asset quotas must be positive SQLite integers')


def _validate_blob(user_id: str, blob: SyncAssetBlob) -> None:
    _identifier(user_id, 'asset user_id')
    if not isinstance(blob, SyncAssetBlob):
        raise ConfigSyncError('asset operations require a typed blob descriptor')


def _validate_chunk(digest: str, body: bytes, *, received: bool = False) -> None:
    if (not isinstance(body, bytes) or not 1 <= len(body) <= CHUNK_BYTES
            or sha256(body).hexdigest() != digest):
        if received:
            raise ConfigSyncError('asset chunk size or hash does not match')
        raise ConfigStoreError('asset chunk integrity failed')


def _chunk(connection: Connection, user_id: str, digest: str, *, missing_ok: bool = False) -> Optional[bytes]:
    row = connection.execute('SELECT body FROM sync_asset_chunks WHERE user_id=? AND digest=?',
                             (user_id, digest)).fetchone()
    if row is None:
        if missing_ok:
            return None
        raise ConfigSyncError('missing verified asset chunk')
    _validate_chunk(digest, row[0])
    return cast(bytes, row[0])


def _admit(connection: Connection, user_id: str, max_users: int) -> None:
    if connection.execute('SELECT 1 FROM sync_asset_users WHERE user_id=?', (user_id,)).fetchone():
        return
    if connection.execute('SELECT count(*) FROM sync_asset_users').fetchone()[0] >= max_users:
        raise ConfigStoreFull('asset account quota exceeded')
    connection.execute('INSERT INTO sync_asset_users (user_id) VALUES (?)', (user_id,))


def _object_limit(connection: Connection, user_id: str, table: str, maximum: int) -> None:
    if table not in {'sync_asset_chunks', 'sync_asset_blobs'}:
        raise ConfigStoreError('invalid owned asset quota table')
    query = ('SELECT count(*) FROM sync_asset_chunks WHERE user_id=?' if table == 'sync_asset_chunks'
             else 'SELECT count(*) FROM sync_asset_blobs WHERE user_id=?')
    count = connection.execute(query, (user_id,)).fetchone()[0]
    if count >= maximum:
        raise ConfigStoreFull('asset account object quota exceeded')


def _receipt(connection: Connection, user_id: str, blob: SyncAssetBlob) -> bool:
    row = connection.execute('SELECT wire FROM sync_asset_blobs WHERE user_id=? AND digest=?',
                             (user_id, blob.sha256)).fetchone()
    if row is None:
        return False
    try:
        stored = SyncAssetBlob.from_dict(json.loads(row[0]))
    except (TypeError, ValueError, RecursionError, ConfigSyncError) as error:
        raise ConfigStoreError('asset publication receipt integrity failed') from error
    if stored.sha256 != blob.sha256 or _encoded(stored.to_dict()) != row[0]:
        raise ConfigStoreError('asset publication receipt integrity failed')
    if stored != blob:
        raise ConfigSyncError('asset hash identifies different content metadata')
    return True


def _verify_blob(connection: Connection, user_id: str, blob: SyncAssetBlob, *,
                   output: Optional[BinaryIO] = None) -> None:
    digest = sha256()
    size = 0
    for index, chunk_id in enumerate(blob.chunks):
        body = cast(bytes, _chunk(connection, user_id, chunk_id))
        expected = min(CHUNK_BYTES, blob.size - index * CHUNK_BYTES)
        if len(body) != expected:
            raise ConfigSyncError('asset chunk layout does not match declared size')
        digest.update(body)
        size += len(body)
        if output is not None:
            output.write(body)
    if size != blob.size or digest.hexdigest() != blob.sha256:
        raise ConfigSyncError('complete asset size or hash does not match')
