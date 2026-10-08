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

* :mod:`.client` -- :class:`ConfigBucket`, :class:`ConfigSyncClient`
  (``fetch`` / ``push`` / ``sync`` / ``push_operations`` / ``full_resync``).
* :mod:`.versions` -- :class:`SyncEntry` with a version vector, and
  :func:`merge_entries`: the change made knowing the other wins; two changes
  to one key made apart are *both kept* as a conflict. No clock is consulted.
* :mod:`.outbox` -- :class:`SyncOutbox`, the durable queue of changes not
  yet on the server (resent by operation id, bounded back-off, cancellable).

Each section maps an entry id to an entry. Section names are free-form;
``hotkeys``, ``triggers``, ``address_book`` and ``custom`` are the
conventional ones, and the syncer treats every section the same way.

A removed entry is kept as a tombstone so the deletion reaches every
machine; read live entries with ``ConfigBucket.entries(section)`` or
``values(section)``. A versioned tombstone is dropped only once every
participating device has acknowledged it -- a device retired for staying
away must do an explicit full resync. Entries written without a device id
keep the older rule: the later ``last_modified`` wins and the loser is
reported in a ``ConflictRecord``.
"""
from je_auto_control.utils.config_sync.client import (
    DEFAULT_SYNC_ATTEMPTS, TOMBSTONE_RETENTION_S, WIRE_VERSION, ConflictRecord, ConfigBucket,
    ConfigSyncClient, ConfigSyncConflict, ConfigSyncError, FullResyncRequired, SyncResult,
    batch_operation_id, is_tombstone, merge_buckets, new_operation_id,
)
from je_auto_control.utils.config_sync.outbox import (
    DrainReport, OutboxError, SyncOutbox, default_outbox_path,
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
    "ConfigBucket", "ConfigStore", "ConfigStoreError", "ConflictRecord", "ConfigSyncClient",
    "ConfigSyncConflict", "ConfigSyncError", "DEFAULT_SYNC_ATTEMPTS", "DrainReport",
    "FullResyncRequired", "MergeDecision", "OutboxError", "PeerState", "RevisionConflictError",
    "StoreCapacityError", "SyncConflict", "SyncEntry", "SyncOperation", "SyncOutbox",
    "SyncResult", "TOMBSTONE_RETENTION_S", "WIRE_VERSION", "batch_operation_id",
    "collect_tombstones", "collectable_revision", "compare_vectors", "default_outbox_path",
    "default_store_path", "is_tombstone", "merge_buckets", "merge_collections",
    "merge_entries", "new_operation_id",
]
