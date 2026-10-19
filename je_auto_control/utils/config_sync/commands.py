"""Bounded local configuration-store commands shared by executor, MCP and Script Builder."""
from pathlib import Path
from typing import Optional

from je_auto_control.utils.config_sync.store import ConfigStore, _parse_bucket
from je_auto_control.utils.path_guard.path_guard import validate_path
from je_auto_control.utils.path_guard.policy import PathPolicy


def _store(path: str, policy: Optional[PathPolicy]) -> ConfigStore:
    candidate: Path = validate_path(path)
    if policy is not None:
        candidate = policy.validate(candidate, operation="config store")
    return ConfigStore(candidate)


def _get_config_store(path: str, user_id: str, *,
                       path_policy: Optional[PathPolicy] = None) -> dict[str, object]:
    bucket = _store(path, path_policy).get(user_id)
    return {"version": 2, "cas": True, "bucket": bucket.to_dict() if bucket is not None else None}


def _commit_config_store(path: str, user_id: str, bucket: dict[str, object], base_revision: int, operation_id: str, *,
                          path_policy: Optional[PathPolicy] = None) -> dict[str, object]:
    value = _parse_bucket(bucket)
    revision = _store(path, path_policy).commit(user_id, value, base_revision=base_revision, operation_id=operation_id)
    return {"version": 2, "revision": revision, "cas": True}
