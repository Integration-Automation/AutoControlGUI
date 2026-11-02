"""Sealed causal account snapshots, conflict views and acknowledged deletion compaction."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field, replace
from hashlib import sha256
from typing import cast

from je_auto_control.utils.config_sync.causal_merge import frontier
from je_auto_control.utils.config_sync.causal_models import CausalConflict, CausalNode, DeletionFence, SyncActor
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded, _identifier, _revision, _schema_one
from je_auto_control.utils.config_sync.peers import SyncPeers
from je_auto_control.utils.config_sync.versions import SyncEntry

__all__ = ["CausalBucket", "SyncActor"]


@dataclass(frozen=True)
class CausalBucket:
    """One account's complete frontier; acknowledgements and commit revisions remain server-owned on commit."""

    user_id: str
    revision: int = 0
    entries: tuple[SyncEntry, ...] = ()
    peer_state: dict[str, object] = field(default_factory=lambda: SyncPeers().to_dict())
    committed: dict[str, int] = field(default_factory=dict)
    fences: tuple[DeletionFence, ...] = ()
    _seal: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        _identifier(self.user_id, "user_id")
        _revision(self.revision)
        entries = tuple(SyncEntry.from_dict(entry.to_dict()) for entry in self.entries)
        fences = tuple(DeletionFence.from_dict(fence.to_dict()) for fence in self.fences)
        nodes = entries + fences
        if len(frontier(nodes)) != len(nodes):
            raise ConfigSyncError("causal snapshot must contain only distinct nondominated alternatives")
        object.__setattr__(self, "entries", entries)
        object.__setattr__(self, "fences", fences)
        object.__setattr__(self, "peer_state", SyncPeers.from_dict(self.peer_state).to_dict())
        _committed(self.committed, nodes, self.revision)
        object.__setattr__(self, "committed", dict(self.committed))
        object.__setattr__(self, "_seal", sha256(_encoded(self._wire()).encode("ascii")).hexdigest())

    @property
    def peers(self) -> SyncPeers:
        """Return an independent ledger; changing it requires with_peers and a conditional server commit."""
        self.to_dict()
        return SyncPeers.from_dict(self.peer_state)

    @property
    def nodes(self) -> tuple[CausalNode, ...]:
        """Return all retained values and compact deletions as one validated frontier."""
        self.to_dict()
        return (*self.entries, *self.fences)

    @property
    def conflicts(self) -> tuple[CausalConflict, ...]:
        """Expose every multi-value frontier without applying a timestamp or origin winner."""
        self.to_dict()
        grouped: dict[tuple[str, str], list[CausalNode]] = defaultdict(list)
        for node in self.nodes:
            grouped[node.key].append(node)
        return tuple(CausalConflict(key, tuple(grouped[key])) for key in sorted(grouped) if len(grouped[key]) > 1)

    @property
    def live_entries(self) -> tuple[SyncEntry, ...]:
        """Return only unambiguous live values suitable for a later explicit adapter."""
        conflicts = {conflict.key for conflict in self.conflicts}
        return tuple(entry for entry in self.entries if not entry.is_deleted and entry.key not in conflicts)

    def with_peers(self, peers: SyncPeers) -> CausalBucket:
        """Build a proposed membership change; the store validates its actor and exact allowed transition."""
        self.to_dict()
        return replace(self, peer_state=peers.to_dict())

    def with_entries(self, entries: tuple[SyncEntry, ...]) -> CausalBucket:
        """Merge pending changes while retaining concurrent alternatives and compacted causal floors."""
        self.to_dict()
        nodes = frontier((*self.entries, *self.fences, *entries))
        identities = {node.change_id for node in nodes}
        return replace(self, entries=tuple(node for node in nodes if isinstance(node, SyncEntry)),
                       fences=tuple(node for node in nodes if isinstance(node, DeletionFence)),
                       committed={key: value for key, value in self.committed.items() if key in identities})

    def collect(self) -> CausalBucket:
        """Replace eligible unambiguous tombstone payloads with permanent minimal deletion evidence."""
        peers = self.peers
        conflicts = {conflict.key for conflict in self.conflicts}
        entries, fences = list(self.entries), list(self.fences)
        for entry in self.entries:
            revision = self.committed.get(entry.change_id, 0)
            if entry.is_deleted and entry.key not in conflicts and peers.can_collect(revision):
                entries.remove(entry)
                fences.append(DeletionFence.from_entry(entry, revision))
        return replace(self, entries=tuple(entries), fences=tuple(fences))

    def _wire(self) -> dict[str, object]:
        return {"schema_version": 1, "kind": "autocontrol.causal", "user_id": self.user_id,
                "revision": self.revision, "entries": [entry.to_dict() for entry in self.entries],
                "peers": self.peer_state, "committed": self.committed,
                "fences": [fence.to_dict() for fence in self.fences]}

    def to_dict(self) -> dict[str, object]:
        """Return a bounded finite JSON snapshot, rejecting mutation after construction."""
        encoded = _encoded(self._wire())
        if sha256(encoded.encode("ascii")).hexdigest() != self._seal:
            raise ConfigSyncError("causal bucket changed after construction")
        return cast(dict[str, object], json.loads(encoded))

    @classmethod
    def from_dict(cls, body: dict[str, object]) -> CausalBucket:
        """Validate exact protocol data before accepting peer claims or deletion fences."""
        fields = {"schema_version", "kind", "user_id", "revision", "entries", "peers", "committed", "fences"}
        if (not isinstance(body, dict) or set(body) != fields or not _schema_one(body["schema_version"])
                or body["kind"] != "autocontrol.causal"):
            raise ConfigSyncError("invalid causal bucket schema")
        if not isinstance(body["entries"], list) or not isinstance(body["fences"], list):
            raise ConfigSyncError("causal entries and fences must be lists")
        return cls(cast(str, body["user_id"]), cast(int, body["revision"]),
                   tuple(SyncEntry.from_dict(raw) for raw in body["entries"]),
                   cast(dict[str, object], body["peers"]), cast(dict[str, int], body["committed"]),
                   tuple(DeletionFence.from_dict(raw) for raw in body["fences"]))


def _committed(values: dict[str, int], nodes: tuple[CausalNode, ...], revision: int) -> None:
    if not isinstance(values, dict):
        raise ConfigSyncError("causal committed revisions must be an object")
    identities = {node.change_id for node in nodes}
    for key, value in values.items():
        _revision(value)
        if key not in identities or not 0 < value <= revision:
            raise ConfigSyncError("invalid causal committed revision")
    for node in nodes:
        if isinstance(node, DeletionFence) and values.get(node.change_id) != node.deletion_revision:
            raise ConfigSyncError("deletion fence must retain its committed revision")
