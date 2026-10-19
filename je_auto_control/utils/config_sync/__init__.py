"""Persistent cross-machine config buckets and conditional HTTP commits.

ConfigStore persists buckets and operation receipts in lazy SQLite storage.
ConfigSyncClient uses version-two base revisions and operation IDs by default;
legacy blind writes require explicit client/server compatibility settings.
The signaling server serves GET/PUT /config/{user_id} with its existing optional
X-Signaling-Secret gate. Bucket account names are namespaces, not separate logins.

SyncEntry/merge_entries preserve concurrent alternatives using version vectors;
SyncPeers models explicit acknowledgements and retirement/full-resync epochs.
SyncOutbox persists isolated edits and prepared requests with bounded retry leases.
These local primitives do not yet replace the HTTP client's timestamp merge or
automatically wire peer acknowledgements/collection into the server. The current
merge_buckets helper retains its legacy last_modified and time-bounded tombstones.
Synchronization stores data without executing scripts or enabling triggers.
"""
from je_auto_control.utils.config_sync.client import (
    TOMBSTONE_RETENTION_S, ConflictRecord, ConfigBucket, ConfigSyncClient,
    ConfigSyncError, is_tombstone, merge_buckets,
)
from je_auto_control.utils.config_sync.store import (
    ConfigRevisionConflict, ConfigStore, ConfigStoreError, ConfigStoreFull,
)
from je_auto_control.utils.config_sync.versions import MergeDecision, SyncConflict, SyncEntry, merge_entries
from je_auto_control.utils.config_sync.peers import FullResyncRequired, SyncPeer, SyncPeers
from je_auto_control.utils.config_sync.outbox import (
    SyncDrainResult, SyncLocalIdentity, SyncOperation, SyncOutbox, SyncRetryPolicy,
)

__all__ = [
    "MergeDecision", "SyncConflict", "SyncEntry", "merge_entries", "FullResyncRequired", "SyncPeer", "SyncPeers",
    "SyncDrainResult", "SyncLocalIdentity", "SyncOperation", "SyncOutbox", "SyncRetryPolicy",
    "ConfigRevisionConflict", "ConfigStore", "ConfigStoreError", "ConfigStoreFull",
    "ConfigBucket", "ConflictRecord", "ConfigSyncClient",
    "ConfigSyncError", "TOMBSTONE_RETENTION_S", "is_tombstone", "merge_buckets",
]
