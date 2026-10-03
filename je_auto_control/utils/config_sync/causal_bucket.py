"""Merge versioned buckets without clock-based winners or lost conflict alternatives."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .models import ConfigBucket, ConfigSyncError
from .versions import PeerState, SyncEntry, can_collect_tombstone, merge_entries


@dataclass(frozen=True)
class BucketConflict:
    """An unresolved entry retaining both sides and every surviving alternative."""
    section: str
    entry_id: str
    local: Mapping[str, object]
    remote: Mapping[str, object]


def _canonical(entry: Mapping[str, object]) -> str:
    return json.dumps(dict(entry), sort_keys=True, separators=(',', ':'), allow_nan=False)


def _decode(entry: Mapping[str, Any]) -> SyncEntry:
    metadata = entry.get('_sync')
    value = {key: item for key, item in entry.items() if key not in ('_sync', 'deleted')}
    if metadata is None:
        legacy_operation = hashlib.sha256(_canonical(entry).encode('utf-8')).hexdigest()
        return SyncEntry(value, {}, 'legacy', legacy_operation, entry.get('deleted', False))
    if not isinstance(metadata, Mapping):
        raise ConfigSyncError('entry causal metadata must be a mapping')
    version, origin, operation = metadata.get('version'), metadata.get('origin'), metadata.get('operation_id')
    if not isinstance(version, Mapping) or not isinstance(origin, str) or not isinstance(operation, str):
        raise ConfigSyncError('entry causal identity is invalid')
    return SyncEntry(value, version, origin, operation, entry.get('deleted', False),
                     metadata.get('deleted_revision', 0))


def _encode(entry: SyncEntry) -> Dict[str, Any]:
    result = dict(entry.value)
    result['_sync'] = {'version': dict(entry.version), 'origin': entry.origin,
                       'operation_id': entry.operation_id, 'deleted_revision': entry.deleted_revision}
    if entry.is_deleted:
        result['deleted'] = True
    return result


def _alternatives(entry: Mapping[str, Any]) -> List[Dict[str, Any]]:
    alternatives = entry.get('sync_conflict')
    if alternatives is None:
        return [dict(entry)]
    if not isinstance(alternatives, list) or not alternatives or not all(isinstance(x, dict) for x in alternatives):
        raise ConfigSyncError('conflict alternatives must be nonempty entry objects')
    return alternatives


def _heads(left: Mapping[str, Any], right: Mapping[str, Any]) -> List[Dict[str, Any]]:
    unique = {_canonical(item): item for item in _alternatives(left) + _alternatives(right)}
    values = [(key, item, _decode(item)) for key, item in sorted(unique.items())]
    heads = []
    for key, item, entry in values:
        superseded = any(other_key != key and merge_entries(entry, other).merged == other
                         for other_key, _item, other in values)
        if not superseded:
            heads.append(item)
    return heads


def _merge_section(section: str, left: Mapping[str, Dict[str, Any]], right: Mapping[str, Dict[str, Any]]
                   ) -> Tuple[Dict[str, Dict[str, Any]], List[BucketConflict]]:
    result = {}
    conflicts = []
    for entry_id in sorted(left.keys() | right.keys()):
        if entry_id not in left:
            result[entry_id] = dict(right[entry_id])
            continue
        if entry_id not in right:
            result[entry_id] = dict(left[entry_id])
            continue
        heads = _heads(left[entry_id], right[entry_id])
        if len(heads) == 1:
            result[entry_id] = heads[0]
        else:
            result[entry_id] = {'sync_conflict': heads}
            conflicts.append(BucketConflict(section, entry_id, dict(left[entry_id]), dict(right[entry_id])))
    return result, conflicts


def merge_causal_buckets(local: ConfigBucket, remote: ConfigBucket) -> Tuple[ConfigBucket, List[BucketConflict]]:
    """Preserve concurrent edits, including conflicts received from another device."""
    if local.user_id != remote.user_id:
        raise ConfigSyncError('user_id mismatch')
    result = ConfigBucket(local.user_id, revision=max(local.revision, remote.revision))
    conflicts = []
    for section in sorted(local.sections.keys() | remote.sections.keys()):
        entries, section_conflicts = _merge_section(section, local.sections.get(section, {}),
                                                   remote.sections.get(section, {}))
        result.sections[section] = entries
        conflicts.extend(section_conflicts)
    # Snapshot the result so subsequent caller edits cannot mutate either source bucket.
    return ConfigBucket.from_dict(json.loads(json.dumps(result.to_dict(), allow_nan=False))), conflicts


def causal_upsert(bucket: ConfigBucket, section: str, entry_id: str, value: Mapping[str, object], *,
                  device_id: str, operation_id: Optional[str] = None) -> None:
    """Explicitly edit or resolve an entry by advancing this device after every known variant."""
    old = bucket.sections.get(section, {}).get(entry_id)
    vector: Dict[str, int] = {}
    if old is not None:
        for alternative in _alternatives(old):
            for peer, counter in _decode(alternative).version.items():
                vector[peer] = max(counter, vector.get(peer, 0))
    vector[device_id] = vector.get(device_id, 0) + 1
    deleted = value.get('deleted', False)
    if not isinstance(deleted, bool):
        raise ConfigSyncError('deleted must be a boolean')
    entry = SyncEntry({key: item for key, item in value.items() if key != 'deleted'}, vector, device_id,
                      operation_id or uuid.uuid4().hex, deleted, 0)
    bucket.sections.setdefault(section, {})[entry_id] = _encode(entry)


def causal_remove(bucket: ConfigBucket, section: str, entry_id: str, *, device_id: str) -> bool:
    """Record a causally later deletion without inferring order from the machine clock."""
    old = bucket.sections.get(section, {}).get(entry_id)
    if old is None or old.get('deleted') is True:
        return False
    causal_upsert(bucket, section, entry_id, {'deleted': True}, device_id=device_id)
    return True


def collect_acknowledged_tombstones(bucket: ConfigBucket, peers: Sequence[PeerState]) -> ConfigBucket:
    """Collect only deletions acknowledged by the complete known active-device set.

    Callers supply the persisted account device registry, never a guessed subset.
    Retired peers must obtain a full snapshot before contributing incremental edits.
    """
    result = ConfigBucket.from_dict(bucket.to_dict())
    for entries in result.sections.values():
        for entry_id, entry in list(entries.items()):
            if 'sync_conflict' not in entry and can_collect_tombstone(_decode(entry), peers):
                del entries[entry_id]
    return result


_PEERS_SECTION = '__sync_devices__'


def bucket_peer_states(bucket: ConfigBucket) -> Tuple[PeerState, ...]:
    """Read the shared account device registry; unresolved registry conflicts prohibit collection."""
    peers = []
    for peer_id, entry in bucket.sections.get(_PEERS_SECTION, {}).items():
        if 'sync_conflict' in entry:
            # Conservative unresolved peers prevent GC until their state is resolved.
            peers.append(PeerState(peer_id, 0))
        else:
            peers.append(PeerState(peer_id, entry.get('acknowledged_revision', 0), entry.get('retired', False)))
    return tuple(peers)


def device_requires_full_sync(bucket: Optional[ConfigBucket], device_id: str) -> bool:
    """Reject retired or unresolved device-registration state until an explicit full snapshot."""
    if bucket is None:
        return False
    entry = bucket.sections.get(_PEERS_SECTION, {}).get(device_id)
    return entry is not None and ('sync_conflict' in entry or entry.get('retired') is True)


def update_peer_state(bucket: ConfigBucket, peer: PeerState, *, device_id: str) -> None:
    """Version an explicit acknowledgement/retirement update in the shared bucket."""
    causal_upsert(bucket, _PEERS_SECTION, peer.peer_id,
                  {'acknowledged_revision': peer.acknowledged_revision, 'retired': peer.retired}, device_id=device_id)


def prepare_tombstone_revisions(bucket: ConfigBucket, base_revision: int) -> ConfigBucket:
    """Assign new deletions the exact upcoming CAS revision in a copied envelope."""
    result = ConfigBucket.from_dict(json.loads(json.dumps(bucket.to_dict(), allow_nan=False)))
    for entries in result.sections.values():
        for entry in entries.values():
            metadata = entry.get('_sync')
            if entry.get('deleted') is True and isinstance(metadata, dict) and metadata.get('deleted_revision') == 0:
                metadata['deleted_revision'] = base_revision + 1
    return result
