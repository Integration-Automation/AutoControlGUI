"""Cross-machine config sync through a small bucket server.

Operators running AutoControl on several machines (work desktop, home
desktop, demo laptop) would otherwise copy hotkey bindings, trigger
definitions, and address-book entries by hand. Each user has one namespaced
bucket on a sync server, and every machine merges its changes into it.

The server side is the signaling server
(:mod:`je_auto_control.utils.remote_desktop.signaling_server`), which serves
``GET`` / ``PUT /config/{user_id}`` with an optional ``X-Signaling-Secret``
header and keeps the buckets in SQLite (:mod:`.store`). A ``PUT`` is a
version-2 envelope naming the revision it was built on and an operation id;
the server refuses it with ``409`` when that revision is no longer current,
and answers a repeated operation id with the revision of the first attempt.

This package is the **headless client** side:

* :mod:`.bucket` -- :class:`ConfigBucket` and the error types.
* :mod:`.merge` -- :func:`merge_buckets` and the per-operation merge.
* :mod:`.client` -- :class:`ConfigSyncClient`
  (``fetch`` / ``push`` / ``sync`` / ``push_operations`` / ``full_resync``);
  it still exports every name of the two modules above.
* :mod:`.versions` -- :class:`SyncEntry` with a version vector, and
  :func:`merge_entries`: the change made knowing the other wins; two changes
  to one key made apart are *both kept* as a conflict. No clock is consulted.
* :mod:`.outbox` -- :class:`SyncOutbox`, the durable queue of changes not
  yet on the server (resent by operation id, bounded back-off, cancellable).
* :mod:`.adapters` -- :class:`SyncAdapter` and the script, locator, hotkey,
  trigger and address-book adapters. Secrets and machine paths leave only as
  references, and applying synced data never enables a hotkey or trigger.
* :mod:`.assets` -- :func:`sync_assets`: files fetched by SHA-256, verified,
  then replaced atomically, through a shared folder
  (:class:`DirectoryAssetTransport`) or the sync server
  (:class:`HttpAssetTransport`).
* :mod:`.blobs` -- :class:`BlobStore`, what the server keeps behind
  ``/blobs``: per account, content-addressed, size-capped, with a quota.
* :mod:`.device` -- :func:`default_device_id`, this machine's stable id.
* :mod:`.session` -- :func:`run_sync`, the whole cycle behind the GUI tab,
  the ``AC_config_sync_*`` commands and the MCP tools.

Each section maps an entry id to an entry. Section names are free-form;
``hotkeys``, ``triggers``, ``address_book`` and ``custom`` are the
conventional ones, and the syncer treats every section the same way.

A removed entry is kept as a tombstone so the deletion reaches every
machine; read live entries with ``ConfigBucket.entries(section)`` or
``values(section)``. A versioned tombstone is dropped only once every
participating device has acknowledged it -- a device retired for staying
away must do an explicit full resync. ``ConfigBucket.upsert`` / ``remove``
version what they write as made by this machine unless told otherwise; flat
entries from before version vectors (or written with ``versioned=False``)
keep the older rule: the later ``last_modified`` wins and the loser is
reported in a ``ConflictRecord``.
"""
from je_auto_control.utils.config_sync.adapters import (
    AddressBookSyncAdapter, ApplyReport, HotkeySyncAdapter, LocatorSyncAdapter,
    ScriptSyncAdapter, SyncAdapter, TriggerSyncAdapter,
)
from je_auto_control.utils.config_sync.assets import (
    AssetManifest, AssetRef, AssetSyncError, AssetSyncResult, AssetTransport,
    DirectoryAssetTransport, HttpAssetTransport, publish_assets, sync_assets,
)
from je_auto_control.utils.config_sync.blobs import BlobStore, BlobStoreError
from je_auto_control.utils.config_sync.client import (
    DEFAULT_SYNC_ATTEMPTS, TOMBSTONE_RETENTION_S, WIRE_VERSION, ConflictRecord, ConfigBucket,
    ConfigSyncClient, ConfigSyncConflict, ConfigSyncError, FullResyncRequired,
    OperationMismatchError, SyncResult,
    batch_operation_id, is_tombstone, merge_buckets, new_operation_id,
)
from je_auto_control.utils.config_sync.outbox import (
    DrainReport, OutboxError, SyncOutbox, default_outbox_path,
)
from je_auto_control.utils.config_sync.session import (
    SyncRunReport, config_sync_full_resync, config_sync_resolve, config_sync_run,
    config_sync_status, default_adapters, default_device_id, resolve_conflict,
    run_full_resync, run_sync, sync_status,
)
from je_auto_control.utils.config_sync.store import (
    ConfigStore, ConfigStoreError, RevisionConflictError, StoreCapacityError,
    default_store_path,
)
from je_auto_control.utils.config_sync.versions import (
    MergeDecision, PeerState, SyncConflict, SyncEntry, SyncOperation, collect_tombstones,
    collectable_revision, compare_vectors, merge_collections, merge_entries,
)

__all__ = [
    "AddressBookSyncAdapter", "ApplyReport", "AssetManifest", "AssetRef", "AssetSyncError",
    "AssetSyncResult", "AssetTransport", "BlobStore", "BlobStoreError",
    "DirectoryAssetTransport", "HotkeySyncAdapter", "HttpAssetTransport",
    "LocatorSyncAdapter", "ScriptSyncAdapter", "SyncAdapter", "SyncRunReport",
    "TriggerSyncAdapter", "config_sync_full_resync", "config_sync_resolve", "config_sync_run",
    "config_sync_status", "default_adapters", "default_device_id", "publish_assets",
    "resolve_conflict", "run_full_resync", "run_sync", "sync_assets", "sync_status",
    "ConfigBucket", "ConfigStore", "ConfigStoreError", "ConflictRecord", "ConfigSyncClient",
    "ConfigSyncConflict", "ConfigSyncError", "DEFAULT_SYNC_ATTEMPTS", "DrainReport",
    "FullResyncRequired", "MergeDecision", "OperationMismatchError", "OutboxError", "PeerState",
    "RevisionConflictError",
    "StoreCapacityError", "SyncConflict", "SyncEntry", "SyncOperation", "SyncOutbox",
    "SyncResult", "TOMBSTONE_RETENTION_S", "WIRE_VERSION", "batch_operation_id",
    "collect_tombstones", "collectable_revision", "compare_vectors", "default_outbox_path",
    "default_store_path", "is_tombstone", "merge_buckets", "merge_collections",
    "merge_entries", "new_operation_id",
]
