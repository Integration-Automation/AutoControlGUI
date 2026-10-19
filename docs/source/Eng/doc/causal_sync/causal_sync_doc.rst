Causal review and durable local outboxes
================================================================================

These experimental primitives provide causal entry decisions, a serializable
peer ledger and a durable local retry queue. The current HTTP client still uses
its legacy timestamp merge; automatic causal client/server integration,
acknowledgement-based collection and the full-resync workflow remain separate
C2 work. The commands below never contact a server or apply configuration.

Entries and explicit conflicts
----------------------------------------------------------------

::

    from je_auto_control import SyncEntry, merge_entries

    left = SyncEntry("settings", "theme", {"value": "dark"},
                     {"desktop": 1}, "edit-desktop", "desktop")
    right = SyncEntry("settings", "theme", {"value": "light"},
                      {"laptop": 1}, "edit-laptop", "laptop")
    decision = merge_entries(left, right)
    assert decision.conflict.local == left
    assert decision.conflict.remote == right
    resolved = left.evolve({"value": "chosen"}, origin="desktop",
                           operation_id="resolution", observed=(right,))
    assert merge_entries(right, resolved).entry == resolved

``MergeDecision`` contains a relation, either a selected ``entry`` or a
``SyncConflict``. Strict vector dominance selects a causal successor; concurrent
vectors and equal-version forks retain both alternatives. Origin/operation reuse
with changed data is rejected. JSON booleans and numbers remain distinct.
Values may contain timestamp metadata, but wall clock never chooses a winner.
Different section/entry keys cannot be merged. ``is_deleted=True`` is a
versioned tombstone, not a request to delete local files or execute an action.

Each entry copies finite JSON and seals its causal evidence. Later mutation is
refused during merge/serialization. Version vectors contain at most 128 devices;
keys are printable nonempty text up to 512 characters. Origin/operation IDs and
positive bounded counters use the shared config contract. Explicit ``evolve``
can observe all selected alternatives to resolve them causally.

Peer acknowledgements and epochs
----------------------------------------------------------------

``SyncPeers`` registers ``SyncPeer`` records, acknowledges revisions and explicitly
retires devices. A retired/unknown/obsolete-epoch device raises
``FullResyncRequired`` for incremental use. ``register(..., full_resync=True)``
advances its epoch after a full snapshot; a snapshot cannot precede the last
confirmed revision. The ledger never infers retirement from elapsed time.

``can_collect(deletion_revision)`` only tests eligibility. A positive committed
deletion revision must be acknowledged by every active peer; no active peers and
revision zero both return false. It does not remove data. ``to_dict/from_dict``
preserve ledger state and reject duplicate IDs; binding this state to authoritative
server revisions and deletion collection is still pending.

Durable operations and retry
----------------------------------------------------------------

::

    from je_auto_control import SyncOperation, SyncOutbox, SyncRetryPolicy

    operation = SyncOperation("delivery-1", "https://sync.example", "alice",
                              "desktop", (resolved,))
    queue = SyncOutbox("config-outbox.sqlite3")
    queue.enqueue(operation)
    print(queue.status(endpoint=operation.endpoint, user_id=operation.user_id))

``SyncOutbox.enqueue`` returns ``None``. Equal namespace/ID retries are idempotent;
changed data with the same ID is refused. Endpoint and account isolate records.
Canonical HTTP endpoints reject credentials, queries and fragments. A stable
origin/epoch is bound when the namespace is first created; a conflicting existing
epoch requires the separate full-resync workflow. Default storage resolves
``AUTOCONTROL_SYNC_OUTBOX`` or ``~/.autocontrol/config-outbox.sqlite3`` on first
use. Optional SQLite loads only on use and each operation closes its connection.
Foreign databases are rejected before adding queue tables.

``prepare(operation, base_revision=..., bucket=...)`` stores an exact independent
request before delivery. Account identity must match. It cannot change until
``reject_prepared(..., rejected_base=...)`` is explicitly called after a definite
stale-base rejection. Unknown/changed logical operations cannot clear a request.
This separation preserves uncertain-result retries across restart.

``flush(sender, endpoint=..., user_id=..., policy=..., cancelled=...)`` invokes a
caller-provided synchronous sink. The sink receives the same operation/prepared
request and returns a positive revision. Use ``operation.delivery_id`` as the
stable server receipt identity. The sink must honor at-least-once delivery;
HTTP/CAS rebasing is not automatically supplied by this local primitive.
Successful committed sends stay successful when cancellation follows them.
Cancellation/hard exits, including explicit interruption causes, propagate without
being stored as ordinary offline failures.

``SyncRetryPolicy`` bounds each drain to 1–10 attempts per operation and 1–1000
operations. Backoff is persisted and capped at 30 seconds without sleeping.
An active lease excludes another attempt until expiry; a callback may finish
after expiry, and its old owner cannot publish another owner's queue result.
The sink supplies its own transport timeout and idempotency behavior. Failures remain pending/offline; conflicts and
full-resync requirements remain visible and are not silently retried. Status
includes counts, lease/offline states, confirmed delivery revision and at most ten
sanitized error previews.

Pending views return a bounded enqueue-order prefix (1–1000 records and at most
16 MiB of serialized data); aggregate pending counts remain complete. Entry data
per logical operation is capped at 1 MiB. No client credentials or HTTP headers
are serialized; known resolved-secret values are refused. Payloads should carry
secret references, with config/asset adapters still tracked under C3.

Commands and Builder
----------------------------------------------------------------

* ``AC_sync_entry_merge`` / ``ac_sync_entry_merge`` review supplied entry JSON.
* ``AC_sync_peer_state`` / ``ac_sync_peer_state`` transform supplied ledger JSON:
  register, acknowledge, retire, require_active or can_collect. The returned JSON
  is not a remote peer change.
* ``AC_sync_outbox_enqueue`` / ``ac_sync_outbox_enqueue`` persist one local edit.
* ``AC_sync_outbox_status`` / ``ac_sync_outbox_status`` inspect counts and optional
  bounded pending snapshots using ``include_pending`` and ``limit``.

The pure transforms are observable without drive permission. Private outbox
operations require DRIVE and honor current MCP roots and pre-start cancellation;
inspection may initialize an absent database. Script Builder offers all four as
explicit Data commands. Generation/review/enqueue never runs a synced script,
enables a trigger or calls a device/model. Existing action-file CLI execution can
drive these AC commands.

``python -m examples.causal_sync`` uses temporary files and controlled callbacks
to show conflict retention, explicit resolution, peer epochs and identical queued
request retry with zero HTTP/device calls. This is local evidence, not remote
convergence or native acceptance.
