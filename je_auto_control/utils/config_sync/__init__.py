"""Persistent protected config synchronization with causal conflicts and offline retries.

The signaling server provides GET/PUT /config endpoints with committed revisions.
ConfigSyncClient defaults to protected writes and durable account/endpoint outboxes.
Use causal_upsert/causal_remove for edits with device vectors. Concurrent values
remain conflict alternatives; entries() excludes unresolved conflicts and deletions.
The shared device registry governs tombstone collection and retired-device rejoining.
Timestamp upsert/remove/merge_buckets and legacy_writes remain explicit migration APIs.
"""
from je_auto_control.utils.config_sync.client import (
    TOMBSTONE_RETENTION_S, ConflictRecord, ConfigBucket, ConfigSyncClient,
    ConfigSyncError, SyncClientOptions, is_tombstone, merge_buckets,
)
from je_auto_control.utils.config_sync.store import (
    ConfigRevisionConflict, ConfigStore, ConfigStoreCapacityError,
)
from je_auto_control.utils.config_sync.versions import (
    MergeDecision, PeerState, SyncEntry, can_collect_tombstone, merge_entries,
)
from je_auto_control.utils.config_sync.outbox import OutboxReport, SyncOperation, SyncOutbox
from je_auto_control.utils.config_sync.causal_bucket import (
    BucketConflict, bucket_peer_states, causal_remove, causal_upsert,
    collect_acknowledged_tombstones, merge_causal_buckets,
)

from je_auto_control.utils.config_sync.adapters import (
    ApplyReport, SyncAdapter, JsonDefinitionAdapter, ScriptSyncAdapter, LocatorSyncAdapter,
    HotkeySyncAdapter, TriggerSyncAdapter, AddressBookSyncAdapter,
)
from je_auto_control.utils.config_sync.assets import (
    AssetSpec, AssetManifest, AssetTransport, AssetSyncResult, AssetSyncError, sync_assets,
)
from je_auto_control.utils.config_sync.service import (
    config_sync_preview, config_sync_exchange, config_sync_apply, config_sync_retry, config_sync_status,
)
from je_auto_control.utils.config_sync.asset_service import config_sync_assets

__all__ = [
    'ApplyReport', 'SyncAdapter', 'JsonDefinitionAdapter', 'ScriptSyncAdapter', 'LocatorSyncAdapter',
    'HotkeySyncAdapter', 'TriggerSyncAdapter', 'AddressBookSyncAdapter', 'AssetSpec', 'AssetManifest',
    'AssetTransport', 'AssetSyncResult', 'AssetSyncError', 'sync_assets', 'config_sync_preview',
    'config_sync_exchange', 'config_sync_apply', 'config_sync_retry', 'config_sync_status', 'config_sync_assets',

    "ConfigBucket", "ConflictRecord", "ConfigSyncClient",
    "ConfigSyncError", "TOMBSTONE_RETENTION_S", "is_tombstone", "merge_buckets",
    "ConfigRevisionConflict", "ConfigStore", "ConfigStoreCapacityError",
    'SyncClientOptions', 'MergeDecision', 'PeerState', 'SyncEntry', 'can_collect_tombstone', 'merge_entries',
    'OutboxReport', 'SyncOperation', 'SyncOutbox', 'BucketConflict', 'bucket_peer_states', 'causal_remove',
    'causal_upsert', 'collect_acknowledged_tombstones', 'merge_causal_buckets',
]
