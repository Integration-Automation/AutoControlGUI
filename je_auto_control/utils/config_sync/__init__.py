"""Persistent cross-machine config buckets and conditional HTTP commits.

ConfigStore persists buckets and operation receipts in lazy SQLite storage.
ConfigSyncClient uses version-two base revisions and operation IDs by default;
legacy blind writes require explicit client/server compatibility settings.
The signaling server serves GET/PUT /config/{user_id} with its existing optional
X-Signaling-Secret gate. Bucket account names are namespaces, not separate logins.

The current merge_buckets helper still uses last_modified ordering and bounded
wall-clock tombstones. Conditional persistence prevents concurrent blind writes;
it does not supply causal merge, peer acknowledgements or a durable client outbox.
Synchronization stores data without executing scripts or enabling triggers.
"""
from je_auto_control.utils.config_sync.client import (
    TOMBSTONE_RETENTION_S, ConflictRecord, ConfigBucket, ConfigSyncClient,
    ConfigSyncError, is_tombstone, merge_buckets,
)
from je_auto_control.utils.config_sync.store import (
    ConfigRevisionConflict, ConfigStore, ConfigStoreError, ConfigStoreFull,
)

__all__ = [
    "ConfigRevisionConflict", "ConfigStore", "ConfigStoreError", "ConfigStoreFull",
    "ConfigBucket", "ConflictRecord", "ConfigSyncClient",
    "ConfigSyncError", "TOMBSTONE_RETENTION_S", "is_tombstone", "merge_buckets",
]
