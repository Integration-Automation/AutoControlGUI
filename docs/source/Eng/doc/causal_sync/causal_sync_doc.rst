Causal review and durable local outboxes
================================================================================

These experimental primitives provide causal entry decisions, a serializable
peer ledger and a durable local retry queue. The current HTTP client still uses
its legacy timestamp merge. The explicit CausalSyncClient now integrates durable
outbox HTTP delivery, durable peer control and atomic local generation adoption. The authoritative store and
dedicated HTTP protocol below validate peer acknowledgements and deletion collection.
Local commands do not contact a server or apply configuration.

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
preserve ledger state and reject duplicate IDs. CausalConfigStore validates these
transitions against the committed ledger; a supplied peer-state transform alone
cannot change authoritative acknowledgement or membership.

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
The generic callback primitive does not itself implement HTTP/CAS rebasing; CausalSyncClient.flush supplies the dedicated v3 sender.
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

Authoritative causal store and protocol
----------------------------------------------------------------

``CausalConfigStore(path)`` shares the lazy SQLite database, account capacity,
atomic CAS and durable historical receipts with ``ConfigStore``. ``get(user_id)``
returns a sealed ``CausalBucket``; an unknown account is an empty revision-zero
snapshot. Recognized plain buckets convert without expiring old tombstones.
Opaque root fields require explicit migration rather than silent loss.

Register a complete snapshot explicitly before editing::

    from je_auto_control import CausalConfigStore, SyncActor

    store = CausalConfigStore("config-sync.sqlite3")
    state = store.get("alice")
    peers = state.peers
    peer = peers.register("desktop", full_revision=state.revision)
    revision = store.commit(
        "alice", state.with_peers(peers), base_revision=state.revision,
        operation_id="register-desktop",
        actor=SyncActor("desktop", peer.epoch, "full_sync", revision=state.revision))

``SyncActor`` modes are edit, full_sync, ack, retire and collect. Full sync must
retain all current data and acknowledge the exact base snapshot; an existing peer
explicitly rejoins at its next epoch. Other modes require an active matching epoch.
Only the actor may acknowledge its own revision (never a future revision), and
retirement names one explicit target. Metadata operations cannot edit values.
The server validates the entire proposed ledger against that one transition.

``with_entries`` retains all nondominated alternatives. ``conflicts`` lists every
alternative, including compact deletion fences; ``live_entries`` excludes ambiguous
and deleted keys. New changes require the actor origin, an advancing own counter
and no invented observations of other origins. Commits cannot forget alternatives,
reuse a change with different payload, or forge committed change revisions.

``collect()`` proposes payload compaction only for unambiguous tombstones whose
positive server commit revision every active peer has acknowledged. Commit with
``SyncActor(origin, epoch, "collect")`` rechecks against authoritative state.
``DeletionFence`` keeps key, version vector, origin, operation ID and deletion
revision permanently, without the old value. Old snapshots remain dominated after
restart; a concurrent edit becomes a visible conflict. Explicit restoration must
observe the deletion floor and any conflicting alternatives. There is no clock
expiry or inferred peer retirement.

Authenticated ``GET /config/{user_id}/causal`` returns ``{version: 3, bucket: ...}``
even for a new account. ``PUT`` accepts exactly version, base_revision,
operation_id and bucket. Add ``_actor: actor.to_dict()`` inside the submitted bucket;
it is validated and never persisted as account data. Snapshot/fence schemas remain
version one, compatible with existing entry/outbox wire formats.

The reply contains version 3, the operation's receipt revision and the latest
committed bucket. An identical historical retry can return its older receipt with
a newer bucket revision. Stale/reused requests return 409; obsolete peers return
409 with code full_resync_required. Malformed data returns 400. Shared-secret and
pre-body size guards apply before storage; account names remain namespaces under
service-wide authentication. This endpoint does not introduce per-account logins.

Once upgraded, old typed/HTTP reads and plain conditional/blind writes refuse the
account rather than dropping causal metadata. Identical old committed receipts may
still return their original revision without mutation. There is no automatic downgrade.
The dedicated route ensures unsupported older servers cannot accept opaque causal data.

Existing private ``AC_config_store_get`` and ``AC_config_store_commit`` (and matching
MCP/Builder Data commands) use version 3 for causal snapshots; a commit's bucket
contains the explicit transient _actor. Path confinement, DRIVE and pre-start
cancellation remain in force. Starting a new causal account requires a CausalBucket
snapshot, as shown above. These commands store data without running scripts or
enabling triggers. The explicit client below supplies HTTP delivery and bounded
rebasing. Durable peer control and atomic local full-resync adoption are described below.

Explicit causal HTTP delivery
----------------------------------------------------------------

``CausalSyncClient(server_url, user_id=..., secret=None, timeout_s=5)`` uses the
dedicated v3 route and the existing HTTP egress/redirect protections. It is an
explicit API; ConfigSyncClient keeps its existing timestamp merge. HTTP timeouts
must be finite, positive and at most 300 seconds. Unsupported older routes or
malformed protocol data fail without falling back to legacy writes.

``fetch()`` returns a complete CausalBucket. ``push(bucket, actor=..., operation_id=...,
base_revision=None)`` commits an exact request and returns CausalReceipt, containing
the original receipt revision and latest complete snapshot. Keep the same ID and
body for uncertain control-commit results. Base defaults to the bucket revision;
they must match. Explicit full-sync/ack/retire/collect actors use the server rules
above. Raw push commits do not adopt local epochs; use the durable control workflow below.

After explicit peer registration, enqueue versioned edits before network I/O::

    from je_auto_control import CausalSyncClient, SyncOperation, SyncOutbox

    client = CausalSyncClient("https://sync.example", user_id="alice")
    queue = SyncOutbox("config-outbox.sqlite3")
    # resolved.origin/epoch must match the stable registered queue identity.
    operation = SyncOperation("delivery-1", "https://sync.example", "alice",
                              resolved.origin, (resolved,))
    queue.enqueue(operation)
    report = client.flush(queue, max_rebases=3)
    confirmed = queue.snapshot(endpoint=operation.endpoint, user_id="alice")

``flush`` first retries any exact persisted prepared request, before refetching.
An uncertain accepted send therefore retains its original delivery identity/base
across restart. Only a typed stale_revision 409 clears that exact prepared base and
allows a bounded fetch/merge/reprepare. Operation-ID conflicts never rebase;
unknown/retired epochs stay blocked. Rebases allow 0–10 retries per attempt, in
addition to the existing bounded attempt/batch/backoff policy. Exhausted stale-base
budgets keep edits offline/due for a later drain. Concurrent values stay conflicts;
delivery does not choose or apply one. Cancellation is checked between requests,
while a received successful commit is confirmed rather than relabelled cancelled.
Wrapped hard/cancellation signals propagate and leave work durable.

``CausalReceipt`` requires every snapshot change to have a positive committed
revision. Its snapshot revision may exceed its operation receipt after an old retry.
The outbox confirms delivery, receipt and latest complete snapshot in one SQLite
transaction guarded by the current lease owner. Snapshot storage failure rolls
back delivery; replaced lease owners cannot publish. Older snapshots do not regress the
cache and different data at the same revision is refused. Generic int-returning
sinks remain compatible and simply do not update the snapshot cache. Credential
headers are never serialized; known resolved credential values in replies are
refused before persistence. ``snapshot`` returns None until a causal delivery has
been durably confirmed. It is a server snapshot, not a local settings application.

Private ``AC_config_causal_fetch``, ``AC_config_causal_commit`` and
``AC_sync_outbox_flush`` have matching MCP and explicit Builder Data commands.
Fetch/commit take endpoint, user_id and optional options; commit also takes bucket,
actor and operation_id. Flush takes path, endpoint, user_id and optional options.
Options accept secret_env (a live environment variable name) and timeout_s. Flush
also accepts max_rebases and policy fields max_attempts, max_batch, backoff,
max_delay and lease_seconds. Unknown fields fail. Credentials are read only for the
live client and never returned or queued. Every command requires DRIVE, including
remote reads; flush intersects current path roots and honors pre-start cancellation.
Action-file CLI execution can invoke these same commands. They store/deliver data
without executing synced scripts, enabling triggers or applying settings.

Durable peer control and local full resync
----------------------------------------------------------------

``CausalSyncClient.control(queue, kind, peer_id=None, discard_pending=False,
policy=None, cancelled=None)`` durably registers, acknowledges, collects, retires
or fully resynchronizes a peer. Kinds are register, ack, collect, retire and
full_resync. Only retire takes a target peer_id. Nothing runs on a timer:
applications explicitly choose when to acknowledge, collect or retire peers.

::

    from je_auto_control import CausalSyncClient, SyncControlRequest, SyncOutbox

    queue = SyncOutbox("config-outbox.sqlite3")
    queue.identity("https://sync.example", "alice", origin="desktop")
    client = CausalSyncClient("https://sync.example", user_id="alice")
    client.control(queue, SyncControlRequest("register", operation_id="join-desktop"))
    client.flush(queue)  # queued edits survive initial registration
    client.control(queue, "ack")
    client.control(queue, "collect")

Use a stable ``SyncControlRequest.operation_id`` for an RPC that may be retried
after completion or restart. A completed same-ID/same-intent retry returns its
original revision without HTTP or replaying effects, even after later controls.
Changed intent with that ID fails. Without an explicit ID, an unfinished matching
intent resumes, while a completed call starts a new logical operation.

One outstanding control is stored per endpoint/account. Exact uncertain prepared
requests retry before GET; only typed stale_revision rejection allows bounded
rebasing (at most three per attempt). Conflicts stay frozen; generation failures
stay blocked until explicit recovery. A live lease excludes a second sender.
Cancellation/hard signals release owned leases without treating them as ordinary
offline failures. Received successful receipts are still confirmed.

``full_resync`` requires explicit ``discard_pending=True`` if old edits remain.
It blocks new local edits during transition; identical enqueue retries remain
idempotent. Only a confirmed receipt atomically updates identity, authoritative
cache and revision, records the control receipt, and marks old pending edits
retired. Their wire payload remains archived; it is never replayed into the new
epoch. A failed local transaction leaves all old state intact and retries the
same prepared request. Unknown or reset server generations use a fresh stable
origin and may adopt a lower root revision. This adopts sync state only; C3
settings/assets adapters and synchronization UI remain separate work.

``queue.request_control(...)`` persists without HTTP. ``control_status`` reviews
state and ``control_receipt(endpoint, user_id, operation_id)`` returns a confirmed
original revision or None. ``client.flush`` drains outstanding control before
incremental edits and counts both kinds in its report; raw queue status/pending
counts contain edits only. Owned outbox SQLite schema 1 migrates atomically to 2
after validating the old tables; edit/control wire schemas stay at 1. Compact
control history stores logical intent and revision without full prepared snapshots.

Private ``AC_sync_peer_control`` / ``ac_sync_peer_control`` and its Builder Data
form take path, endpoint, user_id, operation (default status) and options. Options
accept operation_id, peer_id, discard_pending, secret_env, timeout_s and policy.
All modes require DRIVE and current path roots. Status is local only, performs
no HTTP and does not resolve secret_env. The live credential is never persisted.
``python -m examples.causal_peer_control`` exercises registration, deletion
collection, retirement, explicit full resync and historical receipt retry with
temporary files and loopback HTTP only; it makes no device or external API calls.
