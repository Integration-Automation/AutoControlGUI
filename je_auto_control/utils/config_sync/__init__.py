"""Phase 7.4: cross-machine config sync via the signaling server.

Operators running AutoControl on several machines (work desktop, home
desktop, demo laptop) currently have to copy hotkey bindings, trigger
definitions, and address-book entries by hand. The sync module gives
each user a small namespaced bucket on the signaling server and a
deterministic merge strategy: every entry carries a ``last_modified``
timestamp; the newer entry wins on conflict.

This module is the **headless client** — it speaks HTTP to a sync
endpoint provided by a server-side companion (see
:mod:`je_auto_control.utils.remote_desktop.signaling_server` for the
matching routes). Both halves use the same JSON schema so a script can
push from one machine and pull from another without ever opening the
GUI.

Sections supported out of the box:

  * ``hotkeys``      — list of HotkeyBinding dicts
  * ``triggers``     — webhook / email / file watcher configurations
  * ``address_book`` — Remote Desktop recent connections
  * ``custom``       — caller-supplied dict; opaque to the syncer

Conflicts always resolve to "later wins"; the loser is preserved in
``ConflictRecord`` so callers can show a "merged 3 entries, dropped 1
older copy" notification.
"""
from je_auto_control.utils.config_sync.client import (
    ConflictRecord, ConfigBucket, ConfigSyncClient, ConfigSyncError,
    merge_buckets,
)

__all__ = [
    "ConfigBucket", "ConflictRecord", "ConfigSyncClient",
    "ConfigSyncError", "merge_buckets",
]
