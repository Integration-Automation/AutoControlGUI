"""Persistent cross-machine config buckets and conditional HTTP commits.

ConfigStore persists buckets and operation receipts in lazy SQLite storage.
ConfigSyncClient uses version-two base revisions and operation IDs by default;
legacy blind writes require explicit client/server compatibility settings.
The signaling server serves GET/PUT /config/{user_id} with its existing optional
X-Signaling-Secret gate. Bucket account names are namespaces, not separate logins.

SyncEntry/merge_entries preserve concurrent alternatives using version vectors;
SyncPeers models explicit acknowledgements and retirement/full-resync epochs.
SyncOutbox persists isolated edits and prepared requests with bounded retry leases.
CausalConfigStore and the dedicated version-three /causal route validate peer
acknowledgements, full-resync epochs and payload collection with permanent fences.
CausalSyncClient explicitly fetches/commits v3 snapshots and drains durable outboxes
with exact retries, bounded CAS rebasing and atomically confirmed snapshot receipts.
Durable explicit controls coordinate registration and atomic full-resync adoption.
The merge_buckets helper retains legacy last_modified and time-bounded tombstones.
Portable asset manifests stage complete verified local generations without
replacing an active workspace; configuration adapters remain separate.
Synchronization stores data without executing scripts or enabling triggers.
"""
from je_auto_control.utils.config_sync.client import (
    TOMBSTONE_RETENTION_S, ConflictRecord, ConfigBucket, ConfigSyncClient,
    ConfigSyncError, is_tombstone, merge_buckets,
)
from je_auto_control.utils.config_sync.store import (
    ConfigRevisionConflict, ConfigStore, ConfigStoreError, ConfigStoreFull,
)
from je_auto_control.utils.config_sync.causal_models import CausalConflict, DeletionFence, SyncActor
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.causal_store import CausalConfigStore
from je_auto_control.utils.config_sync.causal_client import CausalSyncClient
from je_auto_control.utils.config_sync.causal_receipt import CausalReceipt
from je_auto_control.utils.config_sync.control_models import SyncControlOperation, SyncControlRequest, SyncControlResult
from je_auto_control.utils.config_sync.asset_models import AssetFile, AssetManifest, AssetSyncResult
from je_auto_control.utils.config_sync.adapter_references import SyncBindings, SyncReference
from je_auto_control.utils.config_sync.adapter_schema import ApplyReport
from je_auto_control.utils.config_sync.adapter_state import SyncAdapterState
from je_auto_control.utils.config_sync.adapters import (
    AddressBookSyncAdapter, HotkeySyncAdapter, LocatorSyncAdapter, ScriptSyncAdapter, SettingsSyncAdapter,
    SyncAdapter, TriggerSyncAdapter, WorkspaceSettingsSyncAdapter,
)
from je_auto_control.utils.config_sync.adapter_profiles import materialize_sync_profile
from je_auto_control.utils.config_sync.adapter_factory import adapter_from_profile
from je_auto_control.utils.config_sync.workspace_sync import SyncWorkspace
from je_auto_control.utils.config_sync.workspace_models import SyncWorkspaceError, WorkspaceSyncResult
from je_auto_control.utils.config_sync.assets import (
    AssetTransport, DirectoryAssetTransport, build_asset_manifest, sync_assets,
)
from je_auto_control.utils.config_sync.versions import MergeDecision, SyncConflict, SyncEntry, merge_entries
from je_auto_control.utils.config_sync.peers import FullResyncRequired, SyncPeer, SyncPeers
from je_auto_control.utils.config_sync.outbox import (
    SyncDrainResult, SyncLocalIdentity, SyncOperation, SyncOutbox, SyncRetryPolicy,
)

__all__ = [
    "SyncWorkspace", "SyncWorkspaceError", "WorkspaceSyncResult",
    "SyncBindings", "SyncReference", "ApplyReport", "SyncAdapterState", "SyncAdapter", "ScriptSyncAdapter",
    "LocatorSyncAdapter", "HotkeySyncAdapter", "TriggerSyncAdapter", "AddressBookSyncAdapter", "SettingsSyncAdapter",
    "WorkspaceSettingsSyncAdapter",
    "materialize_sync_profile",
    "adapter_from_profile",
    "AssetFile", "AssetManifest", "AssetSyncResult", "AssetTransport", "DirectoryAssetTransport",
    "build_asset_manifest", "sync_assets",
    "SyncControlOperation", "SyncControlRequest", "SyncControlResult",
    "CausalSyncClient", "CausalReceipt",
    "CausalBucket", "CausalConfigStore", "CausalConflict", "DeletionFence", "SyncActor",
    "MergeDecision", "SyncConflict", "SyncEntry", "merge_entries", "FullResyncRequired", "SyncPeer", "SyncPeers",
    "SyncDrainResult", "SyncLocalIdentity", "SyncOperation", "SyncOutbox", "SyncRetryPolicy",
    "ConfigRevisionConflict", "ConfigStore", "ConfigStoreError", "ConfigStoreFull",
    "ConfigBucket", "ConflictRecord", "ConfigSyncClient",
    "ConfigSyncError", "TOMBSTONE_RETENTION_S", "is_tombstone", "merge_buckets",
]
