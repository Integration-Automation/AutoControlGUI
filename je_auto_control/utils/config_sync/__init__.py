"""Phase 7.4: cross-machine config sync through a small bucket server.

Operators running AutoControl on several machines (work desktop, home
desktop, demo laptop) currently have to copy hotkey bindings, trigger
definitions, and address-book entries by hand. The sync module gives
each user a small namespaced bucket on a sync server and a
deterministic merge strategy: every entry carries a ``last_modified``
timestamp; the newer entry wins on conflict.

This module is the **headless client**. It speaks HTTP to a sync endpoint,
``GET`` / ``PUT /config/{user_id}`` with an optional ``X-Signaling-Secret``
header, that stores the bucket as an opaque JSON document; this package does
not ship that endpoint yet -- the signaling server has no ``/config`` routes.

Each section maps an entry id to a dict carrying ``last_modified``. Section
names are free-form; ``hotkeys``, ``triggers``, ``address_book`` and
``custom`` are the conventional ones, and the syncer treats every section the
same way.

Conflicts always resolve to "later wins"; the loser is preserved in
``ConflictRecord`` so callers can show a "merged 3 entries, dropped 1
older copy" notification. A removed entry is kept as a tombstone so the
deletion reaches every machine; read live entries with
``ConfigBucket.entries(section)``.
"""
from je_auto_control.utils.config_sync.client import (
    TOMBSTONE_RETENTION_S, ConflictRecord, ConfigBucket, ConfigSyncClient,
    ConfigSyncError, is_tombstone, merge_buckets,
)

__all__ = [
    "ConfigBucket", "ConflictRecord", "ConfigSyncClient",
    "ConfigSyncError", "TOMBSTONE_RETENTION_S", "is_tombstone", "merge_buckets",
]
