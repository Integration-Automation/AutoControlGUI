"""Atomic causal account commits share the persistent CAS store and historical request receipts."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from je_auto_control.utils.config_sync.causal_legacy import read_state
from je_auto_control.utils.config_sync.causal_models import SyncActor
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.causal_validation import validate_transition
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded
from je_auto_control.utils.config_sync.store import ConfigStore


class CausalConfigStore:
    """Read and conditionally upgrade accounts; an existing ConfigStore can share the same lazy transaction owner."""

    def __init__(self, path: Optional[str | Path | ConfigStore] = None, *, max_users: int = 1024) -> None:
        self._store = path if isinstance(path, ConfigStore) else ConfigStore(path, max_users=max_users)

    def get(self, user_id: str) -> CausalBucket:
        """Return an independent complete snapshot; an unknown account has revision zero without being created."""
        return read_state(user_id, self._store.get_document(user_id))

    def commit(self, user_id: str, bucket: CausalBucket, *, base_revision: int, operation_id: str,
               actor: SyncActor) -> int:
        """Atomically validate membership, preserve the frontier and retain an exact idempotent request receipt."""
        if bucket.user_id != user_id:
            raise ConfigSyncError("bucket user_id mismatch")
        submitted = bucket.to_dict()
        submitted["_actor"] = actor.to_dict()
        frozen_bucket, frozen_actor = _parse_causal_request(submitted)

        def transform(previous: Optional[dict[str, object]], next_revision: int) -> str:
            current = read_state(user_id, previous)
            return _encoded(validate_transition(current, frozen_bucket, frozen_actor, next_revision).to_dict())

        # pylint: disable-next=protected-access  # reason: both stores share one internal atomic receipt/CAS protocol
        return self._store._commit_document(user_id, _encoded(submitted), base_revision, operation_id, transform)


def _parse_causal_request(bucket: dict[str, object]) -> tuple[CausalBucket, SyncActor]:
    body = dict(bucket)
    actor = body.pop("_actor", None)
    if not isinstance(actor, dict):
        raise ConfigSyncError("causal commit requires an explicit actor")
    return CausalBucket.from_dict(body), SyncActor.from_dict(actor)
