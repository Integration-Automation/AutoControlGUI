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
secret references. Source adapters and coordination are described below; referenced assets are described below.

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
origin and may adopt a lower root revision. This adopts sync state only; coordinated source baselines are described below.
Referenced-asset integration is described below; synchronization UI remains separate work.

``queue.request_control(...)`` persists without HTTP. ``control_status`` reviews
state and ``control_receipt(endpoint, user_id, operation_id)`` returns a confirmed
original revision or None. ``client.flush`` drains outstanding control before
incremental edits and counts both kinds in its report; raw queue status/pending
counts contain edits only. Owned outbox SQLite schemas 1/2 migrate atomically to 3
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

Verified local asset generations
----------------------------------------------------------------

``AssetFile(path, sha256, size)`` describes one relative portable name, lowercase
SHA-256 and exact byte length. ``AssetManifest(files)`` sorts an immutable tuple
and derives its digest from canonical version-one JSON. Unknown fields, unsafe
names, case/Unicode aliases and file/directory collisions fail before storage.
Parent-directory spelling must be consistent across all entries.
Limits are 1024 assets, 64 MiB per file and 256 MiB per complete generation.

::

    from je_auto_control import DirectoryAssetTransport, build_asset_manifest, sync_assets

    manifest = build_asset_manifest("selected-assets", ["script.json", "templates/button.png"])
    transport = DirectoryAssetTransport("selected-assets", "local-asset-cache")
    result = sync_assets(manifest, transport)
    # result.directory contains both verified files. Nothing is executed or enabled.

The manifest contains relative names, hashes and sizes; machine roots remain on
the live transport. This is an explicit opaque-file selection and preserves file
bytes. The source adapters below replace selected secrets and machine paths with
references; referenced-asset workspace coordination is described below.
It does not automatically capture workspace files or upload them to a server.

``build_asset_manifest(source_root, paths, cancelled=None)`` reads the selected
ordinary files under one root. ``DirectoryAssetTransport`` is lazy and uses no
network. ``AssetTransport`` is a protocol with a target_root and context-managed
binary ``open(asset)``; custom transports supply their own I/O timeouts. Cancellation
is checked before work and between bounded 64 KiB reads; explicit wrapped hard or
cancellation signals propagate. Successful publication stays successful if
cancellation follows it.

``sync_assets(manifest, transport, cancelled=None)`` stages every asset and
verifies exact length/SHA-256 before publishing the entire generation directory
with one rename. A late failed template cannot publish a partial script bundle.
Staging files are flushed before publication. This is one complete immutable
generation, not an in-place replacement of active workspace files. The returned
AssetSyncResult contains directory, manifest_digest, reused, file_count and
byte_count. Repeated/concurrent sends reuse only a fully reverified generation.
Missing, modified or unmanifested cached files and symlinks are refused; damaged
evidence is retained. Failure/cancellation removes the owned temporary staging
directory and leaves existing generations intact. No current workspace pointer
is changed, and scripts/triggers are never executed or enabled.

Private ``AC_sync_asset_manifest`` / ``ac_sync_asset_manifest`` take source_root
and a paths JSON array and return manifest/digest. ``AC_sync_assets`` /
``ac_sync_assets`` take manifest, source_root and target_root and return the JSON
result. Builder Data forms preserve these exact fields. Both commands require
DRIVE even for local reads, intersect current default/MCP roots and recheck live
roots and cancellation while transferring. ``python -m examples.sync_assets``
runs only against temporary local files, with zero network/device/API calls.

Durable source adapters and inert native profiles
----------------------------------------------------------------

``ScriptSyncAdapter``, ``LocatorSyncAdapter``, ``HotkeySyncAdapter``,
``TriggerSyncAdapter``, ``AddressBookSyncAdapter``, ``SettingsSyncAdapter`` and ``WorkspaceSettingsSyncAdapter``
capture explicitly selected real sources without starting backends or callbacks.
Script selection is relative to one root; settings select a JSON object, not GUI
QSettings preferences; use the separate workspace adapter below. Locator repositories use name/role/app_name filters. Hotkey
and trigger adapters capture definitions only, excluding runtime enabled/fired state.
Address-book definitions exclude last-used and local connection/wake metadata.

::

    from je_auto_control import ScriptSyncAdapter, SyncAdapterState, SyncLocalIdentity

    identity = SyncLocalIdentity("https://sync.example", "alice", "desktop", 0, 0)
    state = SyncAdapterState("adapter-state.sqlite3", identity)
    adapter = ScriptSyncAdapter("selected-scripts", state, paths=["login.json"])
    entries = adapter.snapshot()  # change_id -> SyncEntry, including alternatives

State construction is lazy. The default path is
``AUTOCONTROL_SYNC_ADAPTER_STATE`` or ``~/.autocontrol/sync-adapters.sqlite3``.
Owned SQLite schema 2 isolates endpoint/account/origin/epoch/profile/domain. Capture
emits an operation only for a changed portable source fingerprint. ``apply(entries)``
validates the complete incoming batch before persisting heads/receipts/source baselines
in one transaction. It returns stored/unchanged/conflicts/unresolved entry IDs and never
replaces an active source, registers received bindings or starts a trigger poller.
Unactivated local source edits remain concurrent with received alternatives. Old replay
cannot resurrect a deletion, and the same operation ID cannot change its bytes.

``resolve(entry_id, value, observed=head_ids, is_deleted=False)`` requires the exact
reviewed change-ID set and captures source changes before resolution. A stale review
fails. Tombstone resolution uses an empty value and ``is_deleted=True``. Conflicts,
missing references and invalid native local binding types remain durable for review;
``definitions()`` and complete materialization refuse them rather than omit entries.
``materialize_sync_profile(adapters, target_root)`` publishes 1-7 distinct kinds using
the verified asset layer. Native files and ``profile/<kind>.json`` version metadata
share one immutable generation. Hotkey/trigger enabled flags are false, recursively.
No active workspace pointer changes, source files are untouched and scripts stay inert.

Named references
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``SyncReference("secret", "LOGIN")`` and ``SyncReference("local", "downloads")``
serialize as ``{"$autocontrol_ref": {"kind": "local", "name": "downloads"}}``.
``SyncBindings(fields={entry_id: {json_pointer: reference}}, local_values={...})``
replaces explicit fields before persistence. JSON pointers address the portable record,
for example ``/actions/0/1/password`` in a script. Existing ``${secrets.LOGIN}``
placeholders become secret references automatically. Exact string matches against
unambiguous local values also become local references. Local bindings accept immutable
finite JSON scalars; raw vault values are never bindings and vault lookup never occurs.
Secret names follow the vault placeholder grammar. Scripts and JSON settings retain
secret references as placeholders on materialization; locator/hotkey/trigger/address-book
fields support only local references. Workspace preferences require literal values.
Missing local names or type-incompatible values block publication.
Recognized credential fields, private secret-command arguments, absolute machine paths
and device/display selectors require references. These checks do not infer arbitrary
semantic secrets: callers must select portable data and explicitly bind sensitive fields.

Private command descriptors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Four Data commands and matching MCP tools require DRIVE and current default/MCP roots,
even for snapshots: ``AC_sync_adapter_snapshot(profile)``,
``AC_sync_adapter_apply(profile, entries)``,
``AC_sync_adapter_resolve(profile, entry_id, value, observed, is_deleted=False)`` and
``AC_sync_profile_materialize(profiles, target_root)``. Snapshot returns kind/entries;
entries map change IDs to versioned wire objects. Apply returns ApplyReport fields;
resolve returns one wire entry. ``profiles`` is an array of 1-7 private descriptors.
Builder JSON fields preserve these structures. Live source/state authority and
cancellation remain checked through final profile publication; cancellation rolls back
an incomplete merge. Explicit wrapped hard/cancellation signals preserve their meaning.

::

    {
      "schema_version": 1,
      "kind": "scripts",
      "state_path": "adapter-state.sqlite3",
      "identity": {"endpoint": "https://sync.example", "user_id": "alice",
                   "origin": "desktop", "epoch": 0, "confirmed_revision": 0},
      "profile_id": "main",
      "source": {"path": "selected-scripts", "paths": ["login.json"]},
      "bindings": {"fields": {}, "local_values": {}}
    }

``adapter_from_profile`` constructs lazily from this private schema-1 descriptor.
Supported kinds are scripts/locators/hotkeys/triggers/address_book/settings/workspace. Source is
either an explicit path (only scripts accept paths) or an inline records object.
File sources use each domain's native JSON: locator object, address-book entries array,
schema-1 hotkey/trigger arrays or plain settings object. These descriptors contain local
paths and binding values and remain private; only portable entries belong on the wire.
``python -m examples.sync_adapters`` captures all six actual sources and materializes
twelve temporary native/metadata files, with zero execution, registration, vault reads
or network calls. Source/outbox coordination and full-resync baselines are described below.
Live GUI preference application, explicit native loading, Sync UI and
folder/clipboard/disconnection regression remain C3 work in Progress.md.

Journal capture keeps the existing conservative secret-field policy. An inline
definition containing a password field is masked even when its value is a reference,
so candidate generation excludes that action rather than reconstruct an incomplete
apply/resolve operation. Private reference descriptors and publication commands can
remain reproducible. No redacted value is substituted with a working credential.

Native numeric definitions check supported ranges before finite conversion.
Extreme JSON integers fail with ConfigSyncError before adapter storage is opened.

Private absolute local path bindings may contain high-entropy names. Only that
heuristic is exempted for those private paths; recognized credential formats, sensitive
binding names and known resolved-secret values remain refused. Portable data and the
shared secret scanner are unchanged.

Saved native GUI workspace preferences
----------------------------------------------------------------

``WorkspaceSettingsSyncAdapter(source_path, state)`` captures the saved native GUI
INI file, normally ``~/.je_auto_control/gui.ini``. The causal kind is ``workspace``;
records are the four independent keys theme/font_pt/navigation_visible/navigation_width,
each wrapped as ``{"value": ...}``. Other sections, secrets, geometry and device state
are never selected. Missing source files contain no edits; removing a stored preference
emits a causal tombstone. Source fallback normalization is shared with the GUI.
Incoming values require theme dark/light, font_pt in 0/10/12/14/16/20, a JSON boolean
for navigation_visible and an integer 200-1200 for navigation_width. References and
unknown keys are refused for this domain. Source INI is UTF-8 and bounded to one MiB;
malformed input and ambiguous native aliases fail before adapter storage.
Group/key case follows local native QSettings rules; Python's DEFAULT inheritance is
disabled. See `Qt's key syntax documentation <https://doc.qt.io/qt-6/qsettings.html#section-and-key-syntax>`_.

::

    from je_auto_control import WorkspaceSettingsSyncAdapter

    adapter = WorkspaceSettingsSyncAdapter("saved-gui.ini", state)
    entries = adapter.snapshot()
    # An explicitly configured receiver applies these versions to its inert profile.

Existing snapshot/apply/resolve/materialize commands take ``kind: "workspace"`` in
the private descriptor, with ``source: {"path": "saved-gui.ini"}`` or explicit inline
records. The four preferences preserve independent conflicts and exact reviewed
resolution. Up to seven distinct kinds can publish together. A complete generation
contains ``workspace.ini`` plus ``profile/workspace.json``. Absent/deleted preferences
use safe native defaults in that INI, without changing the source or current GUI.

For explicit new-GUI loading, copy the generated workspace.ini to a separate mutable
working file, then pass ``QSettings(working_file, QSettings.Format.IniFormat)`` to
``AutoControlGUIUI(settings=...)``. Do not open the immutable cache itself for GUI
writes: the GUI saves its preferences on close. Capture reads saved preferences;
receiving versions does not reload a running window. The dedicated Sync UI and live
preference application remain separate C3 work. ``python -m examples.sync_workspace``
demonstrates capture, inert publication and the explicit working copy without Qt,
network/device/API calls or an existing workspace change.


Coordinated source workspaces
----------------------------------------------------------------

``SyncWorkspace(configuration, path_policy=None, cancelled=None)`` lazily selects
1-7 distinct private source profiles. Construction authorizes paths without opening
source files, credentials or SQLite. Configuration is schema 1::

    {
      "schema_version": 1,
      "endpoint": "https://sync.example",
      "user_id": "alice",
      "outbox_path": "workspace-outbox.sqlite3",
      "profiles": [{"kind": "workspace", "state_path": "adapter-state.sqlite3",
                    "source": {"path": "saved-gui.ini"}}]
    }

Profiles use the source/profile_id/bindings rules above, without a separate identity
or schema_version. Outbox identity supplies origin/epoch; one kind stays bound to its
state path/profile_id. Different kinds may share an adapter database. Source files,
adapter storage and outbox roles cannot overlap. Private bindings/configuration stay local.

``capture()`` durably queues portable heads once, without network or credential reads.
Batch enqueue is atomic and bounded to 10,000 edits/16 MiB. Restart imports the pending
frontier before observing sources, preserving actor counters. ``synchronize(options=...)``
captures offline work, registers when needed, retries uncertain frozen requests before
GET, delivers edits and reconciles validated server snapshots. All seven domains are
validated before cache/prepare/confirmation, including permanent deletion fences.
Invalid snapshots raise SyncWorkspaceError with a fixed code; transport failures keep
pending work. Generic CausalSyncClient retains optional validation for existing callers.

WorkspaceSyncResult contains captured/delivered/pending/revision/conflicts/unresolved/state.
Delivered counts definition edits; pending includes edits and controls. ``status()`` reads
local metadata without source/credential/network access. A short workspace lease excludes
other mutating coordinators; authority/cancellation and live credential references are
rechecked before RPCs. Resolved credentials never belong in queued definitions; even a
short declared credential is masked before network-operation source capture. Local
capture has no credential lookup. Native INI parse failures omit private source lines.

``review(kind)`` returns current heads without observing sources. ``resolve(kind, entry_id,
value, observed=change_ids, is_deleted=False)`` queues an explicit choice against the exact
reviewed head set. ``materialize(target_root)`` publishes a complete verified inert
generation and refuses pending resets, retired peers, conflicts or unresolved references.
It never executes scripts, enables hotkeys/triggers or changes active preferences.

``control(SyncControlRequest(...), options=...)`` explicitly registers, acknowledges,
collects, retires or performs full_resync. Source fingerprints and the durable reset intent
commit in one outbox transaction. Only confirmed reset adopts identity/cache and retires
old pending edits. Each new adapter generation adopts the authoritative frontier and
prepared source baseline once. Unchanged pre-reset files never replay retired edits;
new source changes made during an uncertain reset survive later capture. Repeated control
IDs return the original receipt without retiring later work. Legacy/external resets or
new source selections without matching baselines fail with missing_baseline; use a fresh
coordinated full reset. Existing adopted generations allow later source selection changes.
Owned outbox schemas 1/2 migrate to 3; adapter schema 1 migrates to 2 while preserving
heads, source fingerprints, edit wire and compact control receipts. Wire schemas stay 1.

Private ``AC_sync_workspace`` / ``ac_sync_workspace`` / Builder Data take configuration,
operation (default status) and optional options. All modes require DRIVE/current roots.
Local status/capture accept no options; review takes kind; resolve takes kind/entry_id/
value/observed/is_deleted; materialize takes target_root. Network operations sync and
register/ack/collect/retire/full_resync accept secret_env/timeout_s/policy/max_rebases.
Controls additionally accept operation_id/peer_id/discard_pending under their usual rules.
``python -m examples.sync_workspace_http`` uses two real temporary source selections and
loopback HTTP to demonstrate offline concurrency, exact resolution, restart, inert
publication and no retired replay. Referenced assets are described below. Live GUI application,
explicit native loading, Sync UI and folder/clipboard/disconnection regression remain
open in Progress.md. No device or paid API acceptance is implied.


Referenced asset synchronization
----------------------------------------------------------------

``SyncAssetBlob(sha256, size, chunks)`` describes at most 64 MiB as an exact tuple
of 256-KiB chunk hashes (the last may be shorter). ``SyncAssetReference(path, blob)``
uses the reserved ``$autocontrol_asset`` marker, with an exact portable path under
``assets/``. Both descriptors are versioned finite JSON, with no source machine path.
Recognized credentials in destination paths or asset references in private/machine
fields are refused. Script arguments and native script/image file fields accept assets;
secret references still stay local and never trigger vault reads.

Select source assets explicitly through private bindings::

    {
      "fields": {"login.json": {"/actions/0/1/image":
        {"$autocontrol_ref": {"kind": "local", "name": "button"}}}},
      "local_values": {"button": "selected/templates/button.png"},
      "assets": {"button": "assets/templates/button.png"}
    }

``assets`` maps a selected local alias to its portable destination; local_values
supplies the source filename. All factory paths are authorized and bound absolutely
at construction, so a later working-directory change cannot redirect a read. Capture
copies only selected referenced files into an immutable chunk cache before recording
their causal fingerprint. It transfers opaque raw bytes and never discovers files or
reads a vault. An asset-only change creates a new definition version even when the
script JSON stays unchanged. Missing/invalid current sources fail capture explicitly;
already frozen chunks remain durable. Source and all storage roles cannot overlap.

Workspace configuration optionally accepts ``asset_cache_path`` (default
``<outbox_path>.assets.sqlite3``). The cache path is pinned per namespace independently
of existing adapter state bindings. Low-level profiles/SyncAdapterState also accept
asset_cache_path, defaulting to ``<state_path>.assets.sqlite3``. Endpoint/account cache
scope survives peer epoch changes. Existing non-asset binding and reset baseline hashes
remain unchanged. Source alias/destination rules participate in reset configuration.

``SyncAssetStore(path=None, max_users=1024, max_bytes=256*1024*1024,
max_chunks=8192, max_blobs=4096)`` opens SQLite lazily. Chunks verify their own hash
before admission; commit verifies layout, size and the complete hash before publishing
a blob receipt. Equal retries consume no extra quota. Missing, corrupt, foreign or
future storage cannot publish usable content. Reads reverify chunk bytes and use a
seekable temporary stream with a 256-KiB spool threshold. Accepted chunks survive late
receipt failures/cancellation. Quota exhaustion is explicit; immutable history is
retained without automatic garbage collection. The owned asset database schema is 1.

``SyncAssetHTTPClient(endpoint, user_id=..., secret_env=None, timeout_s=5,
cancelled=None)`` uploads/downloads between a supplied store/account and the remote
account. Probe identifies missing hashes, accepted uncertain chunks are skipped on
restart, and the final blob receipt is idempotent. Every RPC refreshes the declared
environment credential and reuses bounded HTTP egress with redirects disabled. No
credential or local source path is part of a blob descriptor or receipt.

Signaling ``create_app(..., asset_store_path=None)`` and CLI ``--asset-store`` select a
separate lazy server database, defaulting to AUTOCONTROL_SYNC_ASSET_STORE or
``~/.autocontrol/sync-assets.sqlite3``. Version-one JSON routes are authenticated under
``/config/{user_id}/assets``: POST probe, GET/PUT chunks/{sha256}, PUT blobs/{sha256}.
Uploads use canonical bounded base64 and share the pre-body secret/one-MiB guard;
account isolation and quotas apply to chunks and blob receipts. Config/outbox wire
protocols and existing database versions do not change. Older asset-unaware servers
refuse the dedicated route before a Workspace sends an asset-bearing definition.

``SyncWorkspace.synchronize`` uploads frozen assets before preparing new causal edit
requests. An already prepared uncertain definition retries its exact PUT first, without
an asset probe. A received reference already complete on the server may be resolved
before local bytes arrive; later synchronization downloads them. Interrupted downloads
retain verified chunks and report offline/unresolved, never a script-only generation.
Full-resync baseline adoption suppresses unchanged retired source/asset versions.

Existing AC_sync_workspace/ac_sync_workspace/Builder operations and the four private
adapter/profile commands accept these descriptor fields with DRIVE/current roots and
cancellation. Complete publication streams the exact native metadata and referenced
bytes from one head view into a single verified generation. Missing, conflicting or
corrupt assets refuse the entire output. Native file paths are relative to the generation
root; explicitly loaded working copies must resolve them against that root. Receipt
does not execute scripts, register hotkeys, arm triggers or replace current preferences.
``python -m examples.sync_referenced_assets`` transfers an actual multi-chunk PNG/script
over temporary stdlib loopback HTTP and publishes three inert files. It needs no optional
web framework or external service. Sync UI/live application/native loading and separate
folder/clipboard/disconnection regression remain in Progress.md; native/paid acceptance
remains deferred.
