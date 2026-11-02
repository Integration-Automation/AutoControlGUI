"""Atomic adapter head merging preserves source baselines, parallel branches and compact operation receipts."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import TYPE_CHECKING, Callable, Mapping, Optional, cast
from uuid import uuid4

from je_auto_control.utils.config_sync.contract import ConfigStoreError, ConfigSyncError, _encoded, _revision
from je_auto_control.utils.config_sync.versions import SyncEntry, merge_entries

if TYPE_CHECKING:
    from sqlite3 import Connection

ABSENT = 'absent'
MAX_HEAD_BYTES = 16 * 1024 * 1024


def fingerprint(value: dict[str, object]) -> str:
    """Hash portable definition data, never its resolved secret or machine value."""
    return sha256(_encoded(value).encode('ascii')).hexdigest()


def read_heads(connection: Connection, scope: str, entry_id: Optional[str] = None) -> dict[str, SyncEntry]:
    """Read bounded sealed head records and reject damaged stored evidence."""
    result: dict[str, SyncEntry] = {}
    size = 0
    query = 'SELECT entry_id,change_id,wire,digest FROM adapter_heads WHERE scope=?'
    parameters = (scope,) if entry_id is None else (scope, entry_id)
    query += '' if entry_id is None else ' AND entry_id=?'
    rows = connection.execute(query + ' ORDER BY entry_id,change_id', parameters)
    for logical_id, change_id, wire, digest in rows:
        if not _valid_wire(wire, digest):
            raise ConfigStoreError('adapter head integrity failed')
        size += len(wire)
        if size > MAX_HEAD_BYTES or len(result) >= 1024:
            raise ConfigStoreError('adapter head view exceeds its bounded profile size')
        try:
            entry = SyncEntry.from_dict(json.loads(wire))
        except (ValueError, TypeError, RecursionError, ConfigSyncError) as error:
            raise ConfigStoreError('invalid stored adapter head') from error
        if (entry.entry_id, entry.change_id) != (logical_id, change_id):
            raise ConfigStoreError('adapter head key integrity failed')
        result[entry.change_id] = entry
    return result


def _valid_wire(wire: str, digest: str) -> bool:
    return (isinstance(wire, str) and wire.isascii() and len(wire) <= 1024 * 1024
            and fingerprint_wire(wire) == digest)


def fingerprint_wire(wire: str) -> str:
    """Digest the exact canonical operation, including its portable payload."""
    return sha256(wire.encode('ascii')).hexdigest()


def merge_head(connection: Connection, scope: str, entry: SyncEntry, origin: str, *, compacted: bool = False) -> bool:
    """Remember an operation once and keep every nondominated alternative; no wall-clock selection occurs."""
    wire = _encoded(entry.to_dict())
    digest = fingerprint_wire(wire)
    key = (scope, entry.entry_id, entry.origin, entry.operation_id)
    if _remembered(connection, key, entry, digest, compacted):
        return False
    previous = list(read_heads(connection, scope, entry.entry_id).values())
    pruned, dominated = _merge_plan(previous, entry)
    connection.execute('INSERT INTO adapter_seen VALUES (?,?,?,?,?,?,?)',
                       (*key, entry.change_id, digest, int(compacted)))
    _ensure_source(connection, scope, entry.entry_id)
    connection.execute('UPDATE adapter_sources SET counter=max(counter,?) WHERE scope=? AND entry_id=?',
                       (entry.version.get(origin, 0), scope, entry.entry_id))
    if dominated:
        return False
    if len(previous) - len(pruned) >= 128:
        raise ConfigSyncError('adapter definition has too many unresolved alternatives')
    for change_id in pruned:
        connection.execute('DELETE FROM adapter_heads WHERE scope=? AND change_id=?', (scope, change_id))
    connection.execute('INSERT INTO adapter_heads VALUES (?,?,?,?,?)',
                       (scope, entry.entry_id, entry.change_id, wire, digest))
    return True


def _remembered(connection: Connection, key: tuple[str, str, str, str], entry: SyncEntry,
                  digest: str, compacted: bool) -> bool:
    seen = connection.execute('SELECT change_id,digest,compacted FROM adapter_seen '
                              'WHERE scope=? AND entry_id=? AND origin=? AND operation_id=?', key).fetchone()
    if seen is None:
        return False
    minimal = compacted or bool(seen[2] and entry.is_deleted)
    if seen[0] != entry.change_id or not minimal and seen[1] != digest:
        raise ConfigSyncError('adapter operation ID identifies different causal data')
    if compacted:
        connection.execute('UPDATE adapter_seen SET compacted=1 '
                           'WHERE scope=? AND entry_id=? AND origin=? AND operation_id=?', key)
    return True


def _merge_plan(previous: list[SyncEntry], entry: SyncEntry) -> tuple[list[str], bool]:
    pruned, dominated = [], False
    for old in previous:
        decision = merge_entries(old, entry)
        if decision.relation in {'same', 'left'}:
            dominated = True
        elif decision.relation == 'right':
            pruned.append(old.change_id)
    return pruned, dominated


def _ensure_source(connection: Connection, scope: str, entry_id: str) -> None:
    connection.execute('INSERT OR IGNORE INTO adapter_sources VALUES (?,?,?,?,?)',
                       (scope, entry_id, ABSENT, '{}', 0))


def capture_sources(connection: Connection, scope: str, section: str, origin: str,
                    sources: Mapping[str, dict[str, object]], *, checkpoint: Callable[[], None]) -> None:
    """Only a changed source creates a local branch; applying an inert inbox never rewrites that source."""
    rows = {row[0]: _source_row(row[1:]) for row in connection.execute(
        'SELECT entry_id,fingerprint,version,counter FROM adapter_sources WHERE scope=?', (scope,))}
    heads = read_heads(connection, scope)
    for entry_id in sorted(sources.keys() | rows.keys()):
        checkpoint()
        current = [item for item in heads.values() if item.entry_id == entry_id]
        _capture_one(connection, (scope, section, origin, entry_id), sources.get(entry_id), rows.get(entry_id), current)


def _source_row(row: tuple[object, ...]) -> tuple[str, dict[str, int], int]:
    marker, version, counter = row
    try:
        vector = json.loads(cast(str, version))
        if not isinstance(marker, str) or not isinstance(vector, dict):
            raise ConfigStoreError('invalid adapter source baseline')
        _revision(cast(int, counter))
        for value in vector.values():
            _revision(value)
    except (ValueError, TypeError, RecursionError, ConfigSyncError) as error:
        raise ConfigStoreError('invalid adapter source baseline') from error
    return marker, vector, cast(int, counter)


def _capture_one(connection: Connection, context: tuple[str, str, str, str], value: dict[str, object] | None,
                   row: tuple[str, dict[str, int], int] | None, current: list[SyncEntry]) -> None:
    scope, section, origin, entry_id = context
    marker = fingerprint(value) if value is not None else ABSENT
    _ensure_source(connection, scope, entry_id)
    if len(current) == 1 and _head_marker(current[0]) == marker:
        _baseline(connection, scope, entry_id, marker, current[0].version)
        return
    if row is not None and row[0] == marker:
        return
    if row is None and value is None:
        return
    vector = _next_version(row, origin)
    entry = SyncEntry(section, entry_id, value or {}, vector, uuid4().hex, origin, value is None)
    merge_head(connection, scope, entry, origin)
    _baseline(connection, scope, entry_id, marker, entry.version)


def _next_version(row: tuple[str, dict[str, int], int] | None, origin: str) -> dict[str, int]:
    vector = dict(row[1]) if row is not None else {}
    counter = row[2] if row is not None else 0
    vector[origin] = max(vector.get(origin, 0), counter) + 1
    return vector


def _head_marker(entry: SyncEntry) -> str:
    return ABSENT if entry.is_deleted else fingerprint(entry.value)


def _baseline(connection: Connection, scope: str, entry_id: str, marker: str, version: dict[str, int]) -> None:
    connection.execute('UPDATE adapter_sources SET fingerprint=?,version=? WHERE scope=? AND entry_id=?',
                       (marker, _encoded(cast(dict[str, object], version)), scope, entry_id))
