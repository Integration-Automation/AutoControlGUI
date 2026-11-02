"""Explicit peer acknowledgement, retirement and full-resync epochs for safe deletion collection."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import RLock
from typing import cast

from je_auto_control.utils.config_sync.contract import ConfigSyncError, _identifier, _revision, _schema_one
from je_auto_control.utils.exception.exceptions import AutoControlException


class FullResyncRequired(AutoControlException, RuntimeError):
    """An unknown, retired or obsolete-epoch peer cannot resume incremental delivery."""


@dataclass(frozen=True)
class SyncPeer:
    """A peer's durable acknowledgement and registration epoch; retirement is never inferred from time."""

    peer_id: str
    acknowledged_revision: int
    epoch: int = 0
    retired: bool = False

    def __post_init__(self) -> None:
        _identifier(self.peer_id, "peer_id")
        _revision(self.acknowledged_revision)
        _revision(self.epoch)
        if not isinstance(self.retired, bool):
            raise ConfigSyncError("peer retirement must be a boolean")


class SyncPeers:
    """Thread-safe peer ledger serialized with sync state; no wall-clock expiry can erase an offline peer."""

    def __init__(self) -> None:
        self._records: dict[str, SyncPeer] = {}
        self._lock = RLock()

    def register(self, peer_id: str, *, full_revision: int, full_resync: bool = False) -> SyncPeer:
        """Register a fully fetched snapshot; retired peers require explicit full_resync and a new epoch."""
        _identifier(peer_id, "peer_id")
        _revision(full_revision)
        if not isinstance(full_resync, bool):
            raise ConfigSyncError("full_resync must be a boolean")
        with self._lock:
            previous = self._records.get(peer_id)
            _check_registration(previous, full_revision, full_resync)
            if previous is not None and not full_resync:
                return previous
            if previous is None and len(self._records) >= 128:
                raise ConfigSyncError("sync peer ledger exceeds 128 devices")
            record = SyncPeer(peer_id, full_revision, previous.epoch + 1 if previous is not None else 0)
            self._records[peer_id] = record
            return record

    def require_active(self, peer_id: str, *, epoch: int | None = None) -> SyncPeer:
        """Reject stale callbacks/outbox records rather than treating a retired device as new."""
        _identifier(peer_id, "peer_id")
        if epoch is not None:
            _revision(epoch)
        with self._lock:
            record = self._records.get(peer_id)
            if record is None or record.retired or epoch is not None and record.epoch != epoch:
                raise FullResyncRequired("peer must fully resynchronize before incremental delivery")
            return record

    def acknowledge(self, peer_id: str, revision: int, *, epoch: int) -> SyncPeer:
        """Advance an active peer only after its snapshot and pending work are durably reconciled."""
        _revision(revision)
        with self._lock:
            previous = self.require_active(peer_id, epoch=epoch)
            if revision < previous.acknowledged_revision:
                raise ConfigSyncError("peer acknowledgement cannot move backwards")
            record = SyncPeer(peer_id, revision, previous.epoch)
            self._records[peer_id] = record
            return record

    def retire(self, peer_id: str) -> SyncPeer:
        """Explicitly retire a known peer, retaining its epoch and acknowledgement for rejoin checks."""
        with self._lock:
            previous = self.require_active(peer_id)
            record = SyncPeer(peer_id, previous.acknowledged_revision, previous.epoch, True)
            self._records[peer_id] = record
            return record

    def can_collect(self, deletion_revision: int) -> bool:
        """Allow collection only after every active peer acknowledged the deletion; no-active-peer is false."""
        _revision(deletion_revision)
        if deletion_revision == 0:
            return False
        with self._lock:
            active = [record for record in self._records.values() if not record.retired]
            return bool(active) and all(record.acknowledged_revision >= deletion_revision for record in active)

    def to_dict(self) -> dict[str, object]:
        """Return independent account-state metadata suitable for persistent CAS storage."""
        with self._lock:
            return {"schema_version": 1, "peers": [asdict(self._records[key]) for key in sorted(self._records)]}

    @classmethod
    def from_dict(cls, body: dict[str, object]) -> SyncPeers:
        """Validate a whole peer snapshot, including duplicate IDs, rather than silently overwriting records."""
        if (not isinstance(body, dict) or set(body) != {"schema_version", "peers"}
                or not _schema_one(body["schema_version"])):
            raise ConfigSyncError("invalid sync peer schema")
        records = body["peers"]
        if not isinstance(records, list) or len(records) > 128:
            raise ConfigSyncError("sync peers must be a list of at most 128 devices")
        result = cls()
        for raw in records:
            record = _peer(raw)
            if record.peer_id in result._records:
                raise ConfigSyncError("duplicate sync peer ID")
            result._records[record.peer_id] = record
        return result


def _peer(raw: object) -> SyncPeer:
    if not isinstance(raw, dict) or set(raw) != {"peer_id", "acknowledged_revision", "epoch", "retired"}:
        raise ConfigSyncError("invalid sync peer record")
    return SyncPeer(cast(str, raw["peer_id"]), cast(int, raw["acknowledged_revision"]),
                    cast(int, raw["epoch"]), cast(bool, raw["retired"]))


def _check_registration(previous: SyncPeer | None, revision: int, full_resync: bool) -> None:
    if previous is None:
        return
    if revision < previous.acknowledged_revision:
        raise ConfigSyncError("a full snapshot cannot precede the peer's confirmed revision")
    if previous.retired and not full_resync:
        raise FullResyncRequired("retired peer requires an explicit full resync")
