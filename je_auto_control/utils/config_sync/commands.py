"""Bounded local configuration-store commands shared by executor, MCP and Script Builder."""
from pathlib import Path
from typing import Optional

from je_auto_control.utils.config_sync.client import ConfigBucket
from je_auto_control.utils.config_sync.store import ConfigStore, _parse_bucket
from je_auto_control.utils.config_sync.causal_store import CausalConfigStore, _parse_causal_request
from je_auto_control.utils.path_guard.path_guard import validate_path
from je_auto_control.utils.path_guard.policy import PathPolicy


def _store(path: str, policy: Optional[PathPolicy]) -> ConfigStore:
    candidate: Path = validate_path(path)
    if policy is not None:
        candidate = policy.validate(candidate, operation="config store")
    return ConfigStore(candidate)


def _get_config_store(path: str, user_id: str, *,
                       path_policy: Optional[PathPolicy] = None) -> dict[str, object]:
    bucket = _store(path, path_policy).get_document(user_id)
    version = 3 if bucket is not None and bucket.get("kind") == "autocontrol.causal" else 2
    if version == 2 and bucket is not None:
        bucket = ConfigBucket.from_dict(bucket).to_dict()
    return {"version": version, "cas": True, "bucket": bucket}


def _commit_config_store(path: str, user_id: str, bucket: dict[str, object], base_revision: int, operation_id: str, *,
                          path_policy: Optional[PathPolicy] = None) -> dict[str, object]:
    store = _store(path, path_policy)
    if bucket.get("kind") == "autocontrol.causal":
        value, actor = _parse_causal_request(bucket)
        revision = CausalConfigStore(store).commit(user_id, value, base_revision=base_revision,
                                                  operation_id=operation_id, actor=actor)
        return {"version": 3, "revision": revision, "cas": True}
    revision = store.commit(user_id, _parse_bucket(bucket), base_revision=base_revision, operation_id=operation_id)
    return {"version": 2, "revision": revision, "cas": True}
