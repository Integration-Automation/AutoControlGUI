"""Causal versions for synced entries: who changed what, on top of what.

The first merge compared ``last_modified`` wall-clock stamps, so a machine
whose clock ran ahead won every disagreement, and two machines editing the
same entry while apart silently lost one edit. A :class:`SyncEntry` instead
carries a *version vector* -- per device, how many changes of that device the
entry includes. Comparing two vectors says whether one entry was made
knowing the other (it supersedes it) or neither knew the other (a real
conflict). Clocks take no part: ``modified_at`` is carried for display only.

Concurrent changes to one key are not resolved here. :func:`merge_entries`
returns both in a :class:`SyncConflict`, and the merged entry holds them as
``siblings`` until someone picks a value with :meth:`SyncEntry.resolved`.
Every machine computes the same conflicted entry, so the state still
converges.

A deletion is a tombstone (``deleted`` true) with a vector of its own, so it
competes like any other change. :func:`collect_tombstones` drops one only
when every peer that is still part of the group has acknowledged a revision
that includes it; a peer that stayed away too long is *retired* and must do
an explicit full resync, so it cannot bring deleted entries back.

Pure standard library; imports no ``PySide6``.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from je_auto_control.utils.config_sync.bucket import ConfigSyncError

#: Relations :func:`compare_vectors` reports.
EQUAL = "equal"
BEFORE = "before"
AFTER = "after"
CONCURRENT = "concurrent"

#: Outcomes of :func:`merge_entries`.
KEPT_LEFT = "left"
KEPT_RIGHT = "right"
CONFLICT = "conflict"


def compare_vectors(left: Mapping[str, int], right: Mapping[str, int]) -> str:
    """How ``left`` relates to ``right``: equal, before, after or concurrent."""
    devices = set(left) | set(right)
    behind = any(left.get(device, 0) < right.get(device, 0) for device in devices)
    ahead = any(left.get(device, 0) > right.get(device, 0) for device in devices)
    if behind and ahead:
        return CONCURRENT
    if behind:
        return BEFORE
    return AFTER if ahead else EQUAL


def join_vectors(*vectors: Mapping[str, int]) -> Dict[str, int]:
    """The smallest vector that includes every change in ``vectors``."""
    joined: Dict[str, int] = {}
    for vector in vectors:
        for device, count in vector.items():
            joined[device] = max(joined.get(device, 0), int(count))
    return joined


def _checked_origin(origin: str) -> str:
    if not isinstance(origin, str) or not origin:
        raise ConfigSyncError("a change needs the id of the device that made it")
    return origin


@dataclass(frozen=True)
class SyncEntry:
    """One synced value (or its deletion) with its causal history.

    ``vector`` maps device id to the number of that device's changes this
    entry includes; ``origin`` and ``operation_id`` name the change that
    produced it. ``siblings`` is non-empty while the entry is an unresolved
    conflict -- then ``value`` is ``None`` and the candidates are there.
    """
    key: str
    value: Optional[Mapping[str, Any]] = None
    vector: Mapping[str, int] = field(default_factory=dict)
    origin: str = ""
    operation_id: str = ""
    deleted: bool = False
    modified_at: float = 0.0
    deleted_revision: int = 0
    siblings: Tuple["SyncEntry", ...] = ()

    @property
    def is_deleted(self) -> bool:
        """Whether this entry records a deletion."""
        return self.deleted

    @property
    def in_conflict(self) -> bool:
        """Whether concurrent changes are still waiting for a choice."""
        return bool(self.siblings)

    @classmethod
    def create(cls, key: str, value: Mapping[str, Any], origin: str, *,
               modified_at: float = 0.0) -> "SyncEntry":
        """A brand-new entry: the first change ``origin`` makes to ``key``."""
        return cls(key=key, value=dict(value), vector={_checked_origin(origin): 1},
                   origin=origin, operation_id=uuid.uuid4().hex, modified_at=modified_at)

    def _successor(self, origin: str, **changes: Any) -> "SyncEntry":
        vector = dict(self.vector)
        vector[_checked_origin(origin)] = vector.get(origin, 0) + 1
        return SyncEntry(key=self.key, vector=vector, origin=origin,
                         operation_id=uuid.uuid4().hex, **changes)

    def edited(self, value: Mapping[str, Any], origin: str, *,
               modified_at: float = 0.0) -> "SyncEntry":
        """This entry with a new value, made by ``origin`` knowing this one."""
        return self._successor(origin, value=dict(value), modified_at=modified_at)

    def removed(self, origin: str, *, modified_at: float = 0.0) -> "SyncEntry":
        """The tombstone that deletes this entry."""
        return self._successor(origin, deleted=True, modified_at=modified_at)

    def resolved(self, value: Optional[Mapping[str, Any]], origin: str, *,
                 modified_at: float = 0.0) -> "SyncEntry":
        """Settle a conflict: ``value`` (``None`` = delete) supersedes every sibling."""
        if value is None:
            return self.removed(origin, modified_at=modified_at)
        return self.edited(value, origin, modified_at=modified_at)

    def to_dict(self) -> Dict[str, Any]:
        """The JSON shape stored in a bucket section.

        ``deleted`` and ``last_modified`` keep the names the unversioned
        format used, so code that only asks "is this a tombstone" still works.
        """
        body: Dict[str, Any] = {
            "value": None if self.value is None else dict(self.value),
            "vector": dict(self.vector), "origin": self.origin,
            "operation_id": self.operation_id, "deleted": self.deleted,
            "last_modified": float(self.modified_at),
        }
        if self.deleted_revision:
            body["deleted_revision"] = int(self.deleted_revision)
        if self.siblings:
            body["siblings"] = [sibling.to_dict() for sibling in self.siblings]
        return body

    @classmethod
    def from_dict(cls, key: str, body: Mapping[str, Any], *, _depth: int = 0) -> "SyncEntry":
        """Parse the :meth:`to_dict` shape; :class:`ConfigSyncError` if it is not one."""
        if not is_versioned(body):
            raise ConfigSyncError(f"entry {key!r} carries no version vector")
        value = body.get("value")
        siblings = body.get("siblings") or ()
        if value is not None and not isinstance(value, Mapping):
            raise ConfigSyncError(f"entry {key!r}: value must be an object or null")
        if not isinstance(siblings, (list, tuple)) or (siblings and _depth):
            raise ConfigSyncError(f"entry {key!r}: malformed siblings")
        return cls(
            key=str(key), value=None if value is None else dict(value),
            vector=_checked_vector(key, body["vector"]),
            origin=str(body.get("origin", "")), operation_id=str(body.get("operation_id", "")),
            deleted=body.get("deleted") is True,
            modified_at=_number(key, body.get("last_modified", 0.0)),
            deleted_revision=int(_number(key, body.get("deleted_revision", 0))),
            siblings=tuple(cls.from_dict(key, sibling, _depth=1) for sibling in siblings),
        )


def _number(key: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or math.isnan(value):
        raise ConfigSyncError(f"entry {key!r}: expected a number, got {value!r}")
    return float(value)


def _checked_vector(key: str, vector: Any) -> Dict[str, int]:
    if not isinstance(vector, Mapping):
        raise ConfigSyncError(f"entry {key!r}: vector must be an object")
    checked: Dict[str, int] = {}
    for device, count in vector.items():
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ConfigSyncError(f"entry {key!r}: vector counts must be integers >= 0")
        checked[str(device)] = count
    return checked


def is_versioned(body: Any) -> bool:
    """Whether a stored entry is in the versioned (:class:`SyncEntry`) shape."""
    return isinstance(body, Mapping) and isinstance(body.get("vector"), Mapping)


@dataclass(frozen=True)
class SyncConflict:
    """Two changes to one key, neither made knowing the other."""
    key: str
    local: SyncEntry
    remote: SyncEntry
    section: str = ""


@dataclass(frozen=True)
class SyncOperation:
    """One local change waiting to reach the server: an entry in a section.

    Its identity is the entry's ``operation_id``, so queueing or sending the
    same change twice is the same operation.
    """
    section: str
    entry: SyncEntry

    @property
    def operation_id(self) -> str:
        """The id of the change this operation carries."""
        return self.entry.operation_id

    def to_dict(self) -> Dict[str, Any]:
        """The JSON shape the outbox stores."""
        return {"section": self.section, "key": self.entry.key, "entry": self.entry.to_dict()}

    @classmethod
    def from_dict(cls, body: Mapping[str, Any]) -> "SyncOperation":
        """Parse the :meth:`to_dict` shape."""
        if not isinstance(body, Mapping) or not isinstance(body.get("entry"), Mapping):
            raise ConfigSyncError("a sync operation must be an object with an entry")
        return cls(section=str(body.get("section", "")),
                   entry=SyncEntry.from_dict(str(body.get("key", "")), body["entry"]))


@dataclass(frozen=True)
class MergeDecision:
    """What merging two versions of one key produced.

    ``entry`` is what both sides should now hold. ``outcome`` says which
    side it came from; on ``"conflict"`` it is a new entry whose ``siblings``
    are the candidates and ``conflict`` names the two inputs.
    """
    entry: SyncEntry
    outcome: str
    conflict: Optional[SyncConflict] = None


def _candidates(entry: SyncEntry) -> Tuple[SyncEntry, ...]:
    return entry.siblings if entry.siblings else (entry,)


def _same_change(left: SyncEntry, right: SyncEntry) -> bool:
    return (left.operation_id == right.operation_id and left.value == right.value
            and left.deleted == right.deleted and left.siblings == right.siblings)


def _conflicted(key: str, left: SyncEntry, right: SyncEntry) -> SyncEntry:
    """The entry holding every candidate neither side has superseded."""
    unique: Dict[str, SyncEntry] = {}
    for candidate in (*_candidates(left), *_candidates(right)):
        unique.setdefault(_identity(candidate), candidate)
    pool = list(unique.values())
    survivors = [candidate for candidate in pool
                 if not any(compare_vectors(candidate.vector, other.vector) == BEFORE
                            for other in pool)]
    survivors.sort(key=_identity)
    vector = join_vectors(left.vector, right.vector)
    only = survivors[0]
    if all(other.value == only.value and other.deleted == only.deleted for other in survivors):
        # One candidate left -- or several that say the same thing, as when
        # two machines each already had the same entry before first syncing.
        # There is nothing to choose between, so it is not a conflict.
        return SyncEntry(key=key, value=only.value, vector=vector, origin=only.origin,
                         operation_id=only.operation_id, deleted=only.deleted,
                         modified_at=only.modified_at, deleted_revision=only.deleted_revision)
    return SyncEntry(
        key=key, vector=vector, siblings=tuple(survivors),
        operation_id="conflict:" + "+".join(_identity(candidate) for candidate in survivors))


def _identity(entry: SyncEntry) -> str:
    # Two devices configured with one id would produce equal vectors for
    # different changes; the operation id still tells those apart.
    return f"{entry.origin}/{entry.operation_id}"


def merge_entries(left: SyncEntry, right: SyncEntry) -> MergeDecision:
    """Merge two versions of one key by causality alone.

    The version made knowing the other wins. When neither knew the other the
    result is a conflict that keeps both: no timestamp, device name or value
    is used to pick one, so the decision is the same whatever the clocks say
    and the same on every machine. An edit made concurrently with a delete is
    a conflict too -- the deletion does not silently win.
    """
    if left.key != right.key:
        raise ConfigSyncError(f"cannot merge {left.key!r} with {right.key!r}")
    relation = compare_vectors(left.vector, right.vector)
    if relation == AFTER or (relation == EQUAL and _same_change(left, right)):
        return MergeDecision(entry=left, outcome=KEPT_LEFT)
    if relation == BEFORE:
        return MergeDecision(entry=right, outcome=KEPT_RIGHT)
    merged = _conflicted(left.key, left, right)
    if not merged.in_conflict:
        outcome = KEPT_LEFT if _same_change(merged, left) else KEPT_RIGHT
        return MergeDecision(entry=merged, outcome=outcome)
    return MergeDecision(entry=merged, outcome=CONFLICT,
                         conflict=SyncConflict(key=left.key, local=left, remote=right))


def merge_collections(local: Mapping[str, SyncEntry], remote: Mapping[str, SyncEntry],
                      ) -> Tuple[Dict[str, SyncEntry], List[SyncConflict]]:
    """Merge two maps of key -> entry; returns the merged map and its conflicts.

    Changes to different keys never conflict. A key only one side has is
    taken as it is -- which is why a deletion must stay as a tombstone until
    :func:`collect_tombstones` says every peer has seen it.
    """
    merged: Dict[str, SyncEntry] = {}
    conflicts: List[SyncConflict] = []
    for key in sorted(set(local) | set(remote)):
        mine, theirs = local.get(key), remote.get(key)
        if mine is None or theirs is None:
            merged[key] = mine if theirs is None else theirs  # type: ignore[assignment]
            continue
        decision = merge_entries(mine, theirs)
        merged[key] = decision.entry
        if decision.conflict is not None:
            conflicts.append(decision.conflict)
    return merged, conflicts


@dataclass(frozen=True)
class PeerState:
    """What the group knows about one device.

    ``acked_revision`` is the newest server revision the device has merged
    into its own state. A ``retired`` device no longer holds back tombstone
    collection and must do a full resync before it may push again.
    """
    device_id: str
    acked_revision: int = 0
    last_seen: float = 0.0
    retired: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """The JSON shape stored under ``peers`` in a bucket."""
        return {"acked_revision": int(self.acked_revision), "last_seen": float(self.last_seen),
                "retired": bool(self.retired)}

    @classmethod
    def from_dict(cls, device_id: str, body: Any) -> "PeerState":
        """Parse the :meth:`to_dict` shape."""
        if not isinstance(body, Mapping):
            raise ConfigSyncError(f"peer {device_id!r} must be an object")
        return cls(device_id=str(device_id),
                   acked_revision=int(_number(device_id, body.get("acked_revision", 0))),
                   last_seen=_number(device_id, body.get("last_seen", 0.0)),
                   retired=body.get("retired") is True)


def collectable_revision(peers: Iterable[PeerState]) -> int:
    """The newest revision every active (non-retired) peer has acknowledged.

    ``0`` when no active peer is known: with nobody to confirm, nothing may
    be collected.
    """
    acked = [peer.acked_revision for peer in peers if not peer.retired]
    return min(acked) if acked else 0


def collect_tombstones(entries: Mapping[str, SyncEntry], peers: Iterable[PeerState],
                       ) -> Dict[str, SyncEntry]:
    """``entries`` without the tombstones every active peer has acknowledged.

    A tombstone is dropped only when its ``deleted_revision`` -- the server
    revision that first carried it -- is at or below what each active peer
    has merged. Age is never a reason: a tombstone dropped while a machine
    that still holds the entry is merely offline lets that machine bring the
    entry back. A tombstone not yet stamped with a revision is always kept.
    """
    horizon = collectable_revision(peers)
    return {key: entry for key, entry in entries.items()
            if not (entry.deleted and not entry.siblings
                    and 0 < entry.deleted_revision <= horizon)}


__all__ = [
    "AFTER", "BEFORE", "CONCURRENT", "CONFLICT", "EQUAL", "KEPT_LEFT", "KEPT_RIGHT",
    "MergeDecision", "PeerState", "SyncConflict", "SyncEntry", "SyncOperation",
    "collect_tombstones", "collectable_revision", "compare_vectors", "is_versioned",
    "join_vectors", "merge_collections", "merge_entries",
]
