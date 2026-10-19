"""Lazy owned SQLite adapter profiles keep causal heads and private source baselines across restarts."""
from __future__ import annotations

from dataclasses import asdict
from itertools import islice
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable, Mapping, Optional
from uuid import uuid4

from je_auto_control.utils.config_sync.adapter_ledger import (
    MAX_HEAD_BYTES, capture_sources, fingerprint, merge_head, read_heads,
)
from je_auto_control.utils.config_sync.adapter_references import validate_portable
from je_auto_control.utils.config_sync.adapter_schema import AdapterKind, KINDS, validate_record
from je_auto_control.utils.config_sync.contract import ConfigStoreError, ConfigSyncError, _encoded, _identifier
from je_auto_control.utils.config_sync.control_models import _identity
from je_auto_control.utils.config_sync.database import SyncDatabase
from je_auto_control.utils.config_sync.outbox_models import SyncLocalIdentity
from je_auto_control.utils.config_sync.versions import SyncEntry

if TYPE_CHECKING:
    from sqlite3 import Connection

_APPLICATION = 0x41436164
_TABLES = (
    'CREATE TABLE adapter_heads (scope TEXT NOT NULL,entry_id TEXT NOT NULL,change_id TEXT NOT NULL,'
    'wire TEXT NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(scope,change_id))',
    'CREATE TABLE adapter_seen (scope TEXT NOT NULL,entry_id TEXT NOT NULL,origin TEXT NOT NULL,'
    'operation_id TEXT NOT NULL,change_id TEXT NOT NULL,digest TEXT NOT NULL,'
    'compacted INTEGER NOT NULL DEFAULT 0,'
    'PRIMARY KEY(scope,entry_id,origin,operation_id))',
    'CREATE TABLE adapter_sources (scope TEXT NOT NULL,entry_id TEXT NOT NULL,fingerprint TEXT NOT NULL,'
    'version TEXT NOT NULL,counter INTEGER NOT NULL,PRIMARY KEY(scope,entry_id))',
)
_ADOPTIONS = 'CREATE TABLE adapter_adoptions (scope TEXT PRIMARY KEY,operation_id TEXT NOT NULL)'


def _initialize(connection: Connection) -> None:
    version = _version(connection)
    if version == (_APPLICATION, 2):
        return
    connection.execute('BEGIN IMMEDIATE')
    version = _version(connection)
    if version == (_APPLICATION, 2):
        connection.execute('COMMIT')
        return
    if version == (_APPLICATION, 1):
        _validate_version_one(connection)
        connection.execute('ALTER TABLE adapter_seen ADD COLUMN compacted INTEGER NOT NULL DEFAULT 0')
        connection.execute(_ADOPTIONS)
        connection.execute('PRAGMA user_version=2')
        connection.execute('COMMIT')
        return
    tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    if version != (0, 0) or tables:
        raise ConfigStoreError('not a supported adapter-profile database')
    for statement in _TABLES:
        connection.execute(statement)
    connection.execute(_ADOPTIONS)
    connection.execute(f'PRAGMA application_id={_APPLICATION}')
    connection.execute('PRAGMA user_version=2')
    connection.execute('COMMIT')


def _version(connection: Connection) -> tuple[int, int]:
    return (connection.execute('PRAGMA application_id').fetchone()[0],
            connection.execute('PRAGMA user_version').fetchone()[0])


def _validate_version_one(connection: Connection) -> None:
    expected = {'adapter_heads': {'scope', 'entry_id', 'change_id', 'wire', 'digest'},
                'adapter_seen': {'scope', 'entry_id', 'origin', 'operation_id', 'change_id', 'digest'},
                'adapter_sources': {'scope', 'entry_id', 'fingerprint', 'version', 'counter'}}
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if tables != set(expected):
        raise ConfigStoreError('invalid owned adapter-profile schema')
    for name, columns in expected.items():
        # Fixed owned schema names above, never caller-supplied SQL identifiers.
        if {row[1] for row in connection.execute(f'PRAGMA table_info({name})')} != columns:
            raise ConfigStoreError('invalid owned adapter-profile columns')


class SyncAdapterState:
    """Persist one named profile's identity-scoped heads and source baselines; construction opens no database."""

    def __init__(self, path: Optional[str | Path], identity: SyncLocalIdentity, *, profile: str = 'main',
                   checkpoint: Optional[Callable[[], None]] = None) -> None:
        _identity(identity)
        _identifier(profile, 'adapter profile')
        self.identity = identity
        self.profile = profile
        self._checkpoint = checkpoint
        self._database = SyncDatabase(path, 'AUTOCONTROL_SYNC_ADAPTER_STATE', 'sync-adapters.sqlite3', _initialize)

    def _scope(self, kind: AdapterKind) -> str:
        if kind not in KINDS:
            raise ConfigSyncError('unsupported adapter kind')
        body = asdict(self.identity)
        body.pop('confirmed_revision')
        return fingerprint({'identity': body, 'profile': self.profile, 'kind': kind})

    def checkpoint(self) -> None:
        """Recheck the caller's live authority/cancellation seam without serializing it into profile state."""
        if self._checkpoint is not None:
            self._checkpoint()

    def heads(self, kind: AdapterKind) -> dict[str, SyncEntry]:
        """Review all portable alternatives without reading or activating the live source."""
        self.checkpoint()
        scope = self._scope(kind)
        with self._database.connection() as connection:
            heads = _profile_heads(connection, scope, kind)
            self.checkpoint()
            return heads

    def adopted_control(self, kind: AdapterKind) -> Optional[str]:
        """Read the generation's completed adoption marker without observing live source files."""
        self.checkpoint()
        with self._database.connection() as connection:
            row = connection.execute('SELECT operation_id FROM adapter_adoptions WHERE scope=?',
                                     (self._scope(kind),)).fetchone()
        return row[0] if row else None

    def update(self, kind: AdapterKind, sources: Optional[Mapping[str, dict[str, object]]],
                 incoming: Mapping[str, SyncEntry], *, compacted: frozenset[str] = frozenset()
                 ) -> tuple[dict[str, SyncEntry], tuple[str, ...]]:
        """Atomically observe source changes and merge a validated bounded portable batch."""
        self.checkpoint()
        scope = self._scope(kind)
        if sources is not None:
            _validate_sources(kind, sources)
        _validate_incoming(kind, incoming)
        _validate_compacted(incoming, compacted)
        stored: set[str] = set()
        with self._database.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            _profile_heads(connection, scope, kind)
            if sources is not None:
                capture_sources(connection, scope, kind, self.identity.origin, sources, checkpoint=self.checkpoint)
            for entry in incoming.values():
                self.checkpoint()
                if merge_head(connection, scope, entry, self.identity.origin, compacted=entry.change_id in compacted):
                    stored.add(entry.entry_id)
            heads = _profile_heads(connection, scope, kind)
            self.checkpoint()
            connection.execute('COMMIT')
        return heads, tuple(sorted(stored))

    def adopt(self, kind: AdapterKind, incoming: Mapping[str, SyncEntry], baseline: Mapping[str, str], *,
              operation_id: str, compacted: frozenset[str] = frozenset()) -> None:
        """Initialize an empty new generation once using the source fingerprints captured before full resync."""
        self.checkpoint()
        _identifier(operation_id, 'adapter adoption operation')
        _validate_incoming(kind, incoming)
        _validate_compacted(incoming, compacted)
        _validate_baseline(kind, baseline)
        scope = self._scope(kind)
        with self._database.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT operation_id FROM adapter_adoptions WHERE scope=?', (scope,)).fetchone()
            if row is not None:
                if row[0] != operation_id:
                    raise ConfigSyncError('adapter generation already adopted a different control')
                _profile_heads(connection, scope, kind)
                connection.execute('COMMIT')
                return
            if connection.execute('SELECT 1 FROM adapter_sources WHERE scope=? LIMIT 1', (scope,)).fetchone():
                raise ConfigSyncError('new adapter generation already contains unadopted local work')
            for entry in incoming.values():
                self.checkpoint()
                merge_head(connection, scope, entry, self.identity.origin, compacted=entry.change_id in compacted)
            for entry_id, marker in baseline.items():
                self.checkpoint()
                connection.execute('INSERT INTO adapter_sources VALUES (?,?,?,?,?) '
                                   'ON CONFLICT(scope,entry_id) DO UPDATE '
                                   'SET fingerprint=excluded.fingerprint,version=?',
                                   (scope, entry_id, marker, '{}', 0, '{}'))
            _profile_heads(connection, scope, kind)
            connection.execute('INSERT INTO adapter_adoptions VALUES (?,?)', (scope, operation_id))
            self.checkpoint()
            connection.execute('COMMIT')

    def resolve(self, kind: AdapterKind, entry_id: str, value: dict[str, object], *,
                  observed: Iterable[str], is_deleted: bool = False) -> SyncEntry:
        """Resolve exactly the currently reviewed heads; changed evidence refuses the resolution."""
        self.checkpoint()
        scope = self._scope(kind)
        if not isinstance(is_deleted, bool):
            raise ConfigSyncError('resolution deletion flag must be a JSON boolean')
        validate_record(kind, entry_id, value, deleted=is_deleted)
        validate_portable(value, root_key=entry_id if kind == 'settings' else '')
        expected = resolution_ids(observed)
        with self._database.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            current = [item for item in _profile_heads(connection, scope, kind).values() if item.entry_id == entry_id]
            if sorted(expected) != sorted(item.change_id for item in current):
                raise ConfigSyncError('adapter conflict heads changed after review')
            entry = current[0].evolve(value, origin=self.identity.origin, operation_id=uuid4().hex,
                                       observed=current, is_deleted=is_deleted)
            merge_head(connection, scope, entry, self.identity.origin)
            self.checkpoint()
            connection.execute('COMMIT')
        return entry


def resolution_ids(observed: Iterable[str]) -> tuple[str, ...]:
    """Bound and validate explicitly reviewed identifiers without opening profile state."""
    if isinstance(observed, (str, bytes)):
        raise ConfigSyncError('resolution requires a head collection, not one string')
    expected = tuple(islice(observed, 129))
    if not expected or len(expected) > 128 or not all(isinstance(item, str) for item in expected):
        raise ConfigSyncError('resolution requires a bounded explicit head set')
    return expected


def _validate_compacted(incoming: Mapping[str, SyncEntry], compacted: frozenset[str]) -> None:
    if (not isinstance(compacted, frozenset) or not compacted <= incoming.keys()
            or any(not incoming[key].is_deleted or incoming[key].value for key in compacted)):
        raise ConfigSyncError('compacted adapter evidence requires empty sealed deletion entries')


def _validate_baseline(kind: AdapterKind, baseline: Mapping[str, str]) -> None:
    if not isinstance(baseline, Mapping) or len(baseline) > 1000:
        raise ConfigSyncError('adapter adoption requires bounded source fingerprints')
    for name, marker in baseline.items():
        validate_record(kind, name, {}, deleted=True)
        if not isinstance(marker, str) or len(marker) != 64 or any(char not in '0123456789abcdef' for char in marker):
            raise ConfigSyncError('invalid adapter source fingerprint')
    _encoded({'baseline': dict(baseline)}, max_bytes=MAX_HEAD_BYTES)


def _validate_sources(kind: AdapterKind, sources: Mapping[str, dict[str, object]]) -> None:
    if not isinstance(sources, Mapping) or len(sources) > 1000:
        raise ConfigSyncError('adapter sources require a bounded mapping')
    size = 0
    for entry_id, value in sources.items():
        validate_record(kind, entry_id, value)
        validate_portable(value, root_key=entry_id if kind == 'settings' else '')
        size += len(_encoded(value))
    if size > MAX_HEAD_BYTES:
        raise ConfigSyncError('adapter source view exceeds sixteen MiB')


def _validate_incoming(kind: AdapterKind, incoming: Mapping[str, SyncEntry]) -> None:
    if not isinstance(incoming, Mapping) or len(incoming) > 1024:
        raise ConfigSyncError('incoming adapter operations require a bounded mapping')
    size = 0
    for change_id, entry in incoming.items():
        if not isinstance(entry, SyncEntry) or entry.section != kind or change_id != entry.change_id:
            raise ConfigSyncError('incoming adapter keys must match their sealed change IDs and section')
        validate_record(kind, entry.entry_id, entry.value, deleted=entry.is_deleted)
        validate_portable(entry.value, root_key=entry.entry_id if kind == 'settings' else '')
        size += len(_encoded(entry.to_dict()))
    if size > MAX_HEAD_BYTES:
        raise ConfigSyncError('incoming adapter batch exceeds sixteen MiB')


def _profile_heads(connection: Connection, scope: str, kind: AdapterKind) -> dict[str, SyncEntry]:
    heads = read_heads(connection, scope)
    try:
        _validate_incoming(kind, heads)
    except ConfigSyncError as error:
        raise ConfigStoreError('stored adapter profile violates its domain or reference schema') from error
    return heads
