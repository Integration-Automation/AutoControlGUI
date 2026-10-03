"""Causal entry comparison and acknowledgement-based tombstone collection."""
from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, Mapping, Optional, Sequence, cast

from .models import ConfigSyncError


def _counter(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConfigSyncError('causal counters must be nonnegative integers')
    return value


@dataclass(frozen=True, eq=False)
class SyncEntry:
    """One versioned value or deletion; wall-clock metadata has no ordering authority."""
    value: Mapping[str, object]
    version: Mapping[str, int]
    origin: str
    operation_id: str
    is_deleted: bool = False
    deleted_revision: int = 0

    def __post_init__(self) -> None:
        if not self.origin or not self.operation_id or not isinstance(self.is_deleted, bool):
            raise ConfigSyncError('entry requires origin, operation ID and a boolean deletion flag')
        vector = {}
        for peer, counter in self.version.items():
            if not isinstance(peer, str) or not peer:
                raise ConfigSyncError('version vector peer must be a nonempty string')
            vector[peer] = _counter(counter)
        try:
            value = cast(Dict[str, object], json.loads(json.dumps(dict(self.value), allow_nan=False)))
        except (ValueError, TypeError) as error:
            raise ConfigSyncError('entry value must contain finite JSON data') from error
        object.__setattr__(self, 'version', MappingProxyType(vector))
        object.__setattr__(self, 'value', MappingProxyType(value))
        _counter(self.deleted_revision)

    def to_dict(self) -> Dict[str, object]:
        """Return a wire value preserving all causal identities and deletion evidence."""
        return {'value': dict(self.value), 'version': dict(self.version), 'origin': self.origin,
                'operation_id': self.operation_id, 'is_deleted': self.is_deleted,
                'deleted_revision': self.deleted_revision}

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SyncEntry):
            return NotImplemented
        # JSON boolean true and integer 1 are different edits despite Python equality.
        return json.dumps(self.to_dict(), sort_keys=True) == json.dumps(other.to_dict(), sort_keys=True)


@dataclass(frozen=True)
class MergeDecision:
    """A causal winner or two unchanged concurrent alternatives requiring user choice."""
    local: SyncEntry
    remote: SyncEntry
    merged: Optional[SyncEntry]

    @property
    def conflicted(self) -> bool:
        """Whether causal evidence cannot establish a single winner."""
        return self.merged is None


def _dominates(left: Mapping[str, int], right: Mapping[str, int]) -> bool:
    peers = left.keys() | right.keys()
    return (all(left.get(peer, 0) >= right.get(peer, 0) for peer in peers)
            and any(left.get(peer, 0) > right.get(peer, 0) for peer in peers))


def merge_entries(left: SyncEntry, right: SyncEntry) -> MergeDecision:
    """Compare version vectors; concurrent or inconsistent equal vectors retain both values."""
    if _same_deletion(left, right):
        receipt = left if left.deleted_revision >= right.deleted_revision else right
        return MergeDecision(left, right, receipt)
    if left == right or _dominates(left.version, right.version):
        return MergeDecision(left, right, left)
    if _dominates(right.version, left.version):
        return MergeDecision(left, right, right)
    return MergeDecision(left, right, None)


def _same_deletion(left: SyncEntry, right: SyncEntry) -> bool:
    if not left.is_deleted or not right.is_deleted:
        return False
    first, second = left.to_dict(), right.to_dict()
    first.pop('deleted_revision')
    second.pop('deleted_revision')
    return json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


@dataclass(frozen=True)
class PeerState:
    """A device's acknowledged committed server revision and retirement state."""
    peer_id: str
    acknowledged_revision: int
    retired: bool = False

    def __post_init__(self) -> None:
        if not self.peer_id or not isinstance(self.retired, bool):
            raise ConfigSyncError('invalid peer identity or retirement state')
        _counter(self.acknowledged_revision)


def can_collect_tombstone(entry: SyncEntry, peers: Sequence[PeerState]) -> bool:
    """Collect only acknowledged deletions; retired devices must fully resync on return."""
    active = [peer for peer in peers if not peer.retired]
    return (entry.is_deleted and entry.deleted_revision > 0 and bool(active)
            and all(peer.acknowledged_revision >= entry.deleted_revision for peer in active))
