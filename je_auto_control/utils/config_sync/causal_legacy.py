"""Lossless explicit conversion of recognized plain buckets into causal account state."""
from __future__ import annotations

from hashlib import sha256
from typing import Optional

from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded
from je_auto_control.utils.config_sync.store import _parse_bucket
from je_auto_control.utils.config_sync.versions import SyncEntry


def read_state(user_id: str, body: Optional[dict[str, object]]) -> CausalBucket:
    """Read causal data or convert recognized legacy values without wall-clock tombstone expiry."""
    if body is None:
        return CausalBucket(user_id)
    if body.get("kind") == "autocontrol.causal":
        result = CausalBucket.from_dict(body)
    else:
        result = _convert(body)
    if result.user_id != user_id:
        raise ConfigSyncError("bucket user_id mismatch")
    return result


def _convert(body: dict[str, object]) -> CausalBucket:
    if not set(body) <= {"user_id", "sections", "revision"}:
        raise ConfigSyncError("opaque legacy fields require explicit migration before causal sync")
    bucket = _parse_bucket(body)
    if bucket.to_dict() != body:
        raise ConfigSyncError("legacy bucket requires explicit normalization before causal sync")
    entries = []
    for section, values in bucket.sections.items():
        for entry_id, raw in values.items():
            value = {key: data for key, data in raw.items() if key not in {"last_modified", "deleted"}}
            identity = sha256(_encoded({"section": section, "entry_id": entry_id, "value": value,
                                        "is_deleted": raw.get("deleted", False)}).encode("ascii")).hexdigest()
            entries.append(SyncEntry(section, entry_id, value, {"legacy-import": 1},
                                     "import-" + identity, "legacy-import", bool(raw.get("deleted", False))))
    return CausalBucket(bucket.user_id, bucket.revision, tuple(entries),
                        committed={entry.change_id: bucket.revision for entry in entries})
