"""Deterministic merges for config-sync buckets.

:func:`merge_buckets` merges two whole buckets (what the bucket-level
:meth:`~je_auto_control.utils.config_sync.client.ConfigSyncClient.sync`
does); :func:`apply_operation` and :func:`settle` are the per-operation path
:meth:`~je_auto_control.utils.config_sync.client.ConfigSyncClient.push_operations`
uses. Nothing here touches the network.

Pure standard library; imports no ``PySide6``.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from je_auto_control.utils.config_sync.bucket import (
    TOMBSTONE_RETENTION_S, ConfigBucket, ConfigSyncError, is_tombstone,
)
from je_auto_control.utils.config_sync.versions import (
    PeerState, SyncConflict, SyncEntry, SyncOperation, collect_tombstones, merge_entries,
)


@dataclass
class ConflictRecord:
    """One entry on which the two buckets disagreed.

    For unversioned entries ``dropped`` lost a last-modified race to ``kept``.
    With ``unresolved`` true nothing was dropped: the entries were changed
    concurrently on two devices, ``kept`` holds both as ``siblings`` and
    ``dropped`` is the remote side's copy for reference.
    """
    section: str
    entry_id: str
    dropped: Dict[str, Any]
    kept: Dict[str, Any]
    unresolved: bool = False


def merge_buckets(local: ConfigBucket,
                  remote: ConfigBucket,
                  *, now: Optional[float] = None,
                  tombstone_retention_s: float = TOMBSTONE_RETENTION_S,
                  ) -> Tuple[ConfigBucket, List[ConflictRecord]]:
    """Merge every section of two buckets. Returns merged + conflicts.

    Versioned entries (see :meth:`ConfigBucket.upsert`) merge by causality:
    the one made knowing the other wins, and two made apart are both kept as
    an unresolved conflict -- no clock is consulted. Their tombstones are
    never dropped here.

    Unversioned entries keep the last-write-wins rule: tombstones take part
    like any other entry, so a deletion newer than a remote copy removes it
    and an edit newer than a deletion restores it, and unversioned tombstones
    older than ``tombstone_retention_s`` (measured from ``now``, default the
    current time) are left out of the result. A versioned entry supersedes
    an unversioned copy of the same id, which is reported as dropped.
    """
    if local.user_id != remote.user_id:
        raise ConfigSyncError(
            f"user_id mismatch: local={local.user_id!r} remote={remote.user_id!r}",
        )
    merged = ConfigBucket(user_id=local.user_id, peers=_merged_peers(local, remote))
    conflicts: List[ConflictRecord] = []
    cutoff = (time.time() if now is None else now) - tombstone_retention_s
    for name in set(local.sections) | set(remote.sections):
        merged_section, found = _merge_section(
            name, local.sections.get(name, {}), remote.sections.get(name, {}))
        conflicts.extend(found)
        merged.sections[name] = _without_expired(merged_section, cutoff)
    merged.revision = max(local.revision, remote.revision) + 1
    return merged, conflicts


def _merged_peers(local: ConfigBucket, remote: ConfigBucket) -> Dict[str, Dict[str, Any]]:
    # The server's record of the peers is the shared one; local-only devices
    # are ones this machine has not announced yet.
    return {**{device: dict(body) for device, body in local.peers.items()},
            **{device: dict(body) for device, body in remote.peers.items()}}


def _merge_section(name: str, local_sec: Mapping[str, Dict[str, Any]],
                   remote_sec: Mapping[str, Dict[str, Any]],
                   ) -> Tuple[Dict[str, Dict[str, Any]], List[ConflictRecord]]:
    merged: Dict[str, Dict[str, Any]] = {}
    conflicts: List[ConflictRecord] = []
    for entry_id in set(local_sec) | set(remote_sec):
        local_entry = local_sec.get(entry_id)
        remote_entry = remote_sec.get(entry_id)
        if local_entry is None or remote_entry is None:
            present = local_entry if remote_entry is None else remote_entry
            if present is not None:
                merged[entry_id] = present
            continue
        kept, dropped, unresolved = _winner(entry_id, local_entry, remote_entry)
        merged[entry_id] = kept
        if dropped is not None:
            conflicts.append(ConflictRecord(section=name, entry_id=entry_id, dropped=dropped,
                                            kept=kept, unresolved=unresolved))
    return merged, conflicts


def _winner(entry_id: str, local_entry: Dict[str, Any], remote_entry: Dict[str, Any],
            ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], bool]:
    """``(kept, dropped, unresolved)`` for two copies of one entry."""
    local_versioned = "vector" in local_entry
    remote_versioned = "vector" in remote_entry
    if local_versioned and remote_versioned:
        return _causal_winner(entry_id, local_entry, remote_entry)
    if local_versioned != remote_versioned:
        # The unversioned copy carries no history to compare; the versioned
        # one was written by a client that had seen the bucket.
        if local_versioned:
            return local_entry, remote_entry, False
        return remote_entry, local_entry, False
    kept, dropped = _latest(local_entry, remote_entry)
    return kept, dropped, False


def _causal_winner(entry_id: str, local_entry: Dict[str, Any], remote_entry: Dict[str, Any],
                   ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], bool]:
    decision = merge_entries(SyncEntry.from_dict(entry_id, local_entry),
                             SyncEntry.from_dict(entry_id, remote_entry))
    if decision.conflict is not None:
        return decision.entry.to_dict(), remote_entry, True
    # One side already included the other: nothing was lost, nothing to report.
    return decision.entry.to_dict(), None, False


def _latest(local_entry: Dict[str, Any], remote_entry: Dict[str, Any],
            ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """The unversioned entry that wins and the one it beat (``None`` when equal).

    The later ``last_modified`` wins. At a tie a deletion wins -- ``delete``
    stamps its tombstone no earlier than the entry it removes -- and then the
    larger canonical JSON, so both sides pick the same entry: "local wins"
    had two clients each push their own copy on every sync, never agreeing
    and never reporting the conflict.
    """
    local_ts = float(local_entry.get("last_modified", 0))
    remote_ts = float(remote_entry.get("last_modified", 0))
    if local_ts != remote_ts:
        if remote_ts > local_ts:
            return remote_entry, local_entry
        return local_entry, remote_entry
    if local_entry == remote_entry:
        return local_entry, None
    loser, winner = sorted((local_entry, remote_entry), key=_tie_rank)
    return winner, loser


def _tie_rank(entry: Dict[str, Any]) -> Tuple[bool, str]:
    return is_tombstone(entry), json.dumps(entry, sort_keys=True, default=str)


def _without_expired(section: Dict[str, Dict[str, Any]],
                     cutoff: float) -> Dict[str, Dict[str, Any]]:
    # Only unversioned tombstones expire by age. A versioned one is collected
    # when the peers have acknowledged it, however long that takes.
    return {entry_id: entry for entry_id, entry in section.items()
            if not (is_tombstone(entry) and "vector" not in entry
                    and float(entry.get("last_modified", 0)) < cutoff)}


def batch_operation_id(base_revision: int, operations: Sequence[SyncOperation]) -> str:
    """The id of the push that applies ``operations`` on top of ``base_revision``.

    Derived from the operations themselves, so the same batch retried after
    a lost reply -- or after a restart -- names the same server-side write.
    """
    digest = hashlib.sha256(str(int(base_revision)).encode("ascii"))
    for operation_id in sorted(operation.operation_id for operation in operations):
        digest.update(b"\0" + operation_id.encode("utf-8"))
    return "batch-" + digest.hexdigest()[:48]


def apply_operation(bucket: ConfigBucket, operation: SyncOperation,
                     conflicts: List[SyncConflict]) -> bool:
    """Merge one operation into ``bucket``; whether the bucket changed."""
    entry = operation.entry
    current = bucket.get_entry(operation.section, entry.key)
    if current is None:
        # No entry, or an unversioned one this change supersedes.
        bucket.put_entry(operation.section, entry)
        return True
    decision = merge_entries(current, entry)
    if decision.conflict is not None:
        conflicts.append(SyncConflict(key=entry.key, local=entry, remote=current,
                                      section=operation.section))
    if decision.entry == current:
        return False
    bucket.put_entry(operation.section, decision.entry)
    return True


def awaits_ack(bucket: ConfigBucket, device_id: str) -> bool:
    """Whether ``bucket`` needs a write from ``device_id`` that carries no change.

    A device already listed under ``peers`` owes one while a tombstone waits
    for its acknowledgement. A device not listed yet owes one to *join* --
    so that later deletions wait for it -- but only when the bucket holds
    versioned entries: with none there is nothing whose deletion could be
    forgotten before this device saw it, and the write would be an empty
    revision.
    """
    peer = bucket.peer_states().get(device_id)
    if peer is None:
        return any(bucket.sync_entries(section) for section in bucket.sections)
    return any(entry.deleted and entry.deleted_revision > peer.acked_revision
               for section in bucket.sections
               for entry in bucket.sync_entries(section).values())


def settle(bucket: ConfigBucket, device_id: str, revision: int, now: float,
            max_offline_s: Optional[float]) -> None:
    """Prepare ``bucket`` to be committed as ``revision`` by ``device_id``.

    Stamps new tombstones with the revision that first carries them, records
    that this device has merged up to it, retires peers unseen for longer
    than ``max_offline_s`` (when given), and drops the tombstones every
    remaining peer has acknowledged.
    """
    peers = bucket.peer_states()
    peers[device_id] = PeerState(device_id, acked_revision=revision, last_seen=now)
    if max_offline_s is not None:
        peers = {device: (replace(peer, retired=True)
                          if device != device_id and peer.last_seen < now - max_offline_s else peer)
                 for device, peer in peers.items()}
    bucket.peers = {device: peer.to_dict() for device, peer in peers.items()}
    for section in list(bucket.sections):
        versioned = _stamped(bucket.sync_entries(section), revision)
        kept = collect_tombstones(versioned, peers.values())
        flat = {key: body for key, body in bucket.sections[section].items() if key not in versioned}
        bucket.sections[section] = {**flat, **{key: entry.to_dict() for key, entry in kept.items()}}


def _stamped(entries: Mapping[str, SyncEntry], revision: int) -> Dict[str, SyncEntry]:
    """``entries`` with each new tombstone marked as first carried by ``revision``."""
    return {key: (replace(entry, deleted_revision=revision)
                  if entry.deleted and not entry.deleted_revision else entry)
            for key, entry in entries.items()}


__all__ = [
    "ConflictRecord", "apply_operation", "awaits_ack", "batch_operation_id",
    "merge_buckets", "settle",
]
