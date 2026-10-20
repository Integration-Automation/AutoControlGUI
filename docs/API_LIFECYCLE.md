# Public API lifecycle

The supported entry point for new integrations is `je_auto_control.api`.
Everything reachable only through `je_auto_control.utils` is internal unless a
document explicitly says otherwise. The historical top-level package remains
a broad convenience facade and also exports new headless features under the
project's facade rule. Membership in its `__all__` does not promote a feature
into the versioned stable API.

Structured action-journal storage, capture/read helpers and history provenance
links remain experimental, including their explicit manual-run integration.
The documented names are available through `je_auto_control` and
`je_auto_control.utils.action_journal`; `JournalLink` is also exported from
`je_auto_control.utils.run_history`. CLI journal capture/inspection uses the same
experimental schema-v1 snapshots. `inspect_journal` is the sanitized bounded
reader shared by CLI and `AC_journal_read`; `AC_journal_capture` retains the
calling executor's scope, while `execute_action_with_journal` starts a fresh
variable scope. These additions do not change the lifecycle
of existing executor or history APIs.
Explicit capture scopes reject identifiers and destinations containing values
known to the enclosing run's resolved-secret mask before linking history or
running actions.
`JournalRunOptions` and `execute_journal_run` add typed run controls without
expanding the existing seven-parameter convenience signature. Nested scopes
inherit observers and intersect policies; callbacks may run on joined worker
threads. `MCPToolResult` is an experimental JSON-compatible object result with
separate controlled-failure metadata. The MCP journal tools remain experimental
alongside the other B1 journal APIs. Run History inspection uses these same
experimental snapshots. `manual_history_scope` and its `HistoryBinding` value,
`AC_history_capture`, CLI history flags and manual GUI controls are also
experimental. The scope records an explicit owner without replacing variables
or result values; the command returns a separate history/result summary.

Self-healing retains its existing signatures and outcome format. Cancellation
propagates before recovery; audit storage and reads mask secret values known to
the current run without mutating the returned outcome or rewriting legacy files.

Fixed-frame evaluation models, strategy protocol/adapters, `evaluate_locators`,
`evaluate_healing_manifest` and `write_healing_report` are experimental facade
APIs with schema-v1 reports. The corresponding AC, MCP and GUI operations share
that schema. They do not promote the existing live self-healing APIs to stable.

Live self-healing now emits additive schema-v2 audit fields while retaining the
historical outcome and call signatures. Old audit rows default to schema 1.
Unbound VLM calls use in-memory logical capture/actual geometry; a self-healing attempt supplies
one shared logical frame and actual origin. VLM backends may override the additive
`resolve_model` seam; custom backends may leave their effective model unknown.
Operation dispatch and verification are distinct. Legacy analytics candidate
aliases remain compatible; explicit operation ratios expose their populations.

`SelfHealRequest`, `VerificationRequest`, `SelfHealRunResult`, `self_heal_run`
and their typed request/verification errors are experimental facade additions.
The default operation is locate. Verification requires an explicit click and
one Python bool callback or a configured VLM description. VLM verification uses
fresh pixels after dispatch and may incur cost. A false verdict is structured
API data; AC/CLI raises `SelfHealVerificationError` with its result, while MCP
returns structured data with `isError`. Unknown remains null. Callback exceptions,
framework assertions and cancellation propagate; clicks are never retried.
Legacy signatures and eight-field outcomes are retained. `verify_description`
now rejects non-bool backend replies instead of returning them as a verdict.

`inspect_heal_source`, `AC_self_heal_source` and `ac_self_heal_source` are
experimental original-step readers. Additive `HealEvent.journal_path` metadata
is optional and absent for legacy/unbound attempts. A run scope without an actual
action-step binding does not invent a link. `inspect_journal` adds an optional
`step_id` keyword; run/step filters precede the existing limit while the whole
file is validated. Current roots are rechecked around progress and at completion.
The shared GUI reader now accepts a step ID. These are read-only inspection paths,
with no promotion to the stable API and no automatic replay.

Template-candidate functions and their immutable state/preview/verification/
transition models are experimental facade additions. The five
`AC_template_candidate_*` / `ac_template_candidate_*` operations use schema-v1
bundles; only explicit creation persists image bytes. Static PNG/JPEG/BMP targets
are supported, with supplied PNG candidate pixels encoded in the target format.
A reviewed bundle revision is required for acceptance/revert. Acceptance always
reverifies current local labelled samples; rollback preserves later edits.
State names describe current file bytes, not a verified native operation or an
operator-history record. Thresholds belong to the bundle's verification config;
activating an image does not rewrite scripts. Existing RepairStore/manual
coordinate APIs are unchanged and are not called by this workflow.

Journal-candidate APIs (`generate_candidate_from_log`, `CandidateScript`,
`CandidateGenerationError`, `write_candidate_archive`) are experimental. The
`AC_generate_candidate_from_log` / `ac_generate_candidate_from_log` adapters return
code, proposed actions, schema-v1 provenance and explicit exclusions; optional
output exports a single review ZIP. All candidates remain observed-path-only.
Static command/signature/AST and non-dispatching dry-run checks leave dynamic
inputs and native outcomes unverified. Review content is sealed against later
mutation. Source/current roots and cancellation apply throughout. CLI --from-log
requires an explicit run ID and defaults to actions style/JSON output; legacy
file codegen retains its calls-style/source-output behavior. No replay is implicit.

Persistent configuration (`ConfigStore`, its errors, and the top-level
`ConfigBucket`/`ConfigSyncClient` convenience exports) remains experimental.
Version-two commits and the schema-v1 SQLite store provide CAS and durable retry
receipts, with bounded finite JSON. `AC_config_store_get`/`AC_config_store_commit`
and matching MCP/Builder surfaces are private DRIVE operations. Legacy blind
writes require explicit compatibility on both sides; default clients never
silently downgrade. These names do not join the versioned stable API.

Causal primitives (`SyncEntry`, `SyncConflict`, `MergeDecision`, `merge_entries`,
`SyncPeer`, `SyncPeers`, `FullResyncRequired`, `SyncOperation`, `SyncRetryPolicy`,
`SyncDrainResult`, `SyncLocalIdentity`, `SyncOutbox`) are experimental. Entry,
peer and queue wire schemas start at version one. Pure supplied-data operations
are observable; private outbox commands require DRIVE and path confinement.
CausalBucket, CausalConfigStore, SyncActor, CausalConflict and DeletionFence are
also experimental. Account snapshot/fence wire schemas are version one; dedicated
HTTP /causal envelopes are version three. Actor metadata is transient _actor data
inside submitted buckets. Server transactions validate membership, acknowledgements,
retirement/full-sync epochs and deletion collection. Existing store AC/MCP/Builder
commands also accept causal snapshots. Upgraded accounts refuse plain reads/writes;
historical identical receipts still return their original revision. Durable peer control
and atomic local full-resync adoption are also experimental. CausalSyncClient and
CausalReceipt are experimental: explicit fetch/push and bounded outbox HTTP
delivery use v3, retain uncertain prepared requests and atomically confirm complete
snapshots. The plain ConfigSyncClient API and v2 response shapes remain compatible.
Causal 409 details carry typed stale_revision/operation_id_conflict/full_resync_required
reasons; only the first permits rebase. New private HTTP commands use live
options.secret_env credentials and current path/egress authority.

MCP OperationCancelledError and run-history interruption classifiers keep their
existing import aliases and carrier identity through the dependency-free shared
control-signals module. Cancellation retains its deliberate RuntimeError-only
ancestry and remains outside ordinary framework-error containment.

- Stable API removal requires a deprecation warning and two minor releases.
- Beta API removal requires one release note and one minor release.
- Experimental API may change in any release and must be labelled as such.
- Deprecations state the version introduced, planned removal version, and
  replacement. Use `je_auto_control.utils.deprecation.deprecated`.
- Breaking changes and migrations are recorded in `CHANGELOG.md`.

The project remains pre-1.0. A 1.0 release requires passing stable capability
tests on every claimed platform, documented recovery/diagnostic behavior, and
no unresolved critical security advisories.

`AuthorizationContext(user_id, role)` remains compatible. Its optional
`store_path` is filled by `resolve_token` so deferred registrations can refresh
the user's current permissions without retaining credentials. Explicit Python
contexts without this path remain role snapshots. Background registration
methods keep their signatures; the worker or daemon starter no longer supplies
the authority of registered jobs. Observer/watchdog callback variable scopes
are independent of the process scope (see `CHANGELOG.md`).

SyncControlRequest, SyncControlOperation and SyncControlResult are experimental.
CausalSyncClient.control and AC_sync_peer_control/ac_sync_peer_control persist manual
register/ack/collect/retire/full_resync intents. Stable explicit operation IDs replay
compact historical receipts without new effects. Full resync requires explicit pending
retirement consent and adopts identity/cache/retirement atomically after confirmation.
Owned outbox SQLite schemas 1/2 migrate to 3 without changing existing edit wire version 1;
control wire is version 1. Status remains private, local-only and credential-free.
Source coordination is described below; referenced assets are described below; Sync UI and native working-copy loading are described below.

AssetFile, AssetManifest, AssetSyncResult, AssetTransport, DirectoryAssetTransport,
build_asset_manifest and sync_assets are experimental. Asset manifest wire is version 1.
Private AC/MCP/Builder manifest/stage commands publish a complete verified local cache
generation, never an active workspace replacement. Explicit files retain their bytes;
referenced-asset workspace integration is described below. Current roots/cancellation
are rechecked. Corrupt caches fail without overwrite; identical verified caches are reused.

SyncReference, SyncBindings, ApplyReport, SyncAdapter, SyncAdapterState,
ScriptSyncAdapter, LocatorSyncAdapter, HotkeySyncAdapter, TriggerSyncAdapter,
AddressBookSyncAdapter, SettingsSyncAdapter, adapter_from_profile and
materialize_sync_profile are experimental. Private adapter descriptor schema is 1;
owned ledger schema is 2 (migrated from 1). Four private AC/MCP/Builder
snapshot/apply/resolve/materialize commands
require DRIVE. Apply persists a causal inbox; it never replaces live definitions.
Materialization publishes an inert complete generation with native hotkey/trigger flags
disabled. Secret references remain vault placeholders without vault lookup; native
machine fields accept local references; native script/image file fields also accept typed assets. Workspace
preferences require literal values. The separate workspace adapter bridges saved native
GUI preferences; live GUI application remains explicit. Full-resync adapter baselines
and referenced assets are coordinated below; Sync UI and native working-copy loading are described below.

Native sync definition numeric bounds are checked before floating-point finite
conversion. Out-of-range arbitrary-precision JSON integers raise ConfigSyncError
before profile I/O, preserving the documented framework exception boundary.

Private local absolute paths may contain high-entropy directory names. The adapter
exempts only this heuristic for those paths; recognized credential patterns, sensitive
binding names and active resolved-secret masks still refuse plaintext credentials.
Portable entries and the shared secret scanner keep their existing policies.

WorkspaceSettingsSyncAdapter is experimental and adds the workspace kind to private
schema-1 descriptors and versioned profiles; materialization now accepts 1-7 distinct
kinds. Its four portable preference fields use exact incoming types/bounds. Source INI
fallbacks match the GUI. No QSettings or other Qt module is imported by headless capture.
workspace.ini is inert generated data; explicit GUI use first creates a separate mutable
working file. No existing active workspace is overwritten or reloaded on receipt.

SyncWorkspace, SyncWorkspaceError and WorkspaceSyncResult are experimental. The private
workspace descriptor is schema 1. AC_sync_workspace/ac_sync_workspace/Builder Data share
local capture/status/review/resolve/preferences/materialize and explicit network sync/peer controls.
All server modes require DRIVE. A short workspace lease, atomic reset intent/source
fingerprints and idempotent adapter-generation adoption preserve uncertain retries and
prevent retired source replay. Missing legacy reset baselines require a new coordinated
full reset. Source/state/outbox path roles cannot overlap; existing kind/state bindings
remain stable. Credentials refresh per RPC and received data never activates a source.

SyncAssetBlob, SyncAssetReference, SyncAssetStore and SyncAssetHTTPClient are experimental.
Reserved asset marker/descriptor and chunk HTTP protocols are version 1; the separate
owned asset SQLite schema is 1. Private bindings.assets and optional asset_cache_path
are additive schema-1 descriptor fields. Non-asset adapter binding/reset hashes stay
compatible. Source files freeze to content-addressed chunks before causal capture; new
requests upload assets before prepare, while uncertain prepared definitions retry first.
Received metadata and assets publish as one inert generation. Native paths are relative
to its root. Existing AC/MCP/Builder fields preserve DRIVE/current roots/cancellation.
Signaling adds optional create_app asset_store_path and --asset-store, with the same
authentication/pre-body size guard. Server/client stores have explicit byte/object/user
quotas; immutable content has no automatic garbage collection. Older asset-unaware
participants require upgrade before processing new typed references.

The experimental preferences operation requires an explicit bounded observed change-ID list
(empty is a valid reviewed empty profile). It compares the exact current workspace heads,
refuses concurrent alternatives and returns four canonical values using safe defaults for
missing/deleted keys. No source/network/credential reads or Qt imports are added. The lazy
Workspace Sync GUI exposes explicit reviewed application on its main window, separate from
receipt/publication. Captured authority refreshes during work and before queued delivery;
cancellation prevents late preference application while completed durable writes remain committed.

TCP AUTH_FAIL is terminal for client admission: a rejected handler is marked stopped before
the reply is sent, allowing an immediate replacement connection while cleanup finishes.
Wire payloads, max_clients for active/pending clients and the independent pending-handshake
budget remain unchanged. No public names or command schemas change.

load_sync_profile and LoadedSyncProfile are experimental. The published files directory
requires an exact lowercase SHA-256 expected_digest and a separate working-copy container.
Each successful load returns a fresh mutable directory with a schema-1 .sync-profile.json
source-manifest receipt; source cache and existing native/global runtime ownership stay separate.
Native canonical formats and sealed heads must agree; all hotkeys/trigger nodes load disabled.
Only explicit asset markers and native hotkey/trigger paths are rebound; secret placeholders
and literal script strings keep their meaning. Repository/book handles access working files;
script_actions/settings/preferences/definitions describe the loaded snapshot.
The private AC_sync_profile_load/ac_sync_profile_load/Builder Data command shares current
roots/cancellation and requires DRIVE. The GUI exposes load, selected-kind inspection,
explicit script-snapshot import and preference-snapshot application. Later GUI actions check
both the current caller and the captured load owner; completed copies survive late cancellation.

Builder renders imported command names and positional values as literal text, preserving
HTML-like data without rich-text interpretation. Script data remains data until explicit Run.

FolderSyncEngine retains its existing import path and start/stop/is_running/wait_until_ready
surface. Content SHA-256 values replace increasing mtime as the change criterion. Only the
first successful baseline ignores existing files; subsequent runs retain failed/offline edits.
stop signals cancellation, skips self-join and retains a blocked worker until it really ends;
start is a no-op while that worker lives, and readiness clears on stop/exit.
record_received(path) explicitly marks a complete regular file inside the selected watch as
received, returning False for missing/outside/excluded/changing paths. Callers publish first;
receipt updates win over older send/scan completions. This does not change any wire schema.
Native receive receipts are integrated below; remote publication acknowledgement/retry remains in Progress.md.

FileTransferSender.send, WebRTCDesktopViewer.send_file and WebRTCDesktopHost.push_file
accept an optional keyword-only cancelled predicate. Writes now synchronously confirm
the original bridge callback, cap buffered data at 1 MiB and fail after a bounded wait.
Callback errors reach FileTransferError; cancellation/hard signals keep their original
identity. Chunk sizes must be integers from 1 byte through 1 MiB (bool is refused), and
source truncation/growth relative to the announced size aborts the transfer. Success means
the channel accepted every frame, not that the peer committed the file. The wire is unchanged.
Concurrent producers on one channel fail explicitly; a pending abort retains ownership.
FolderSyncEngine accepts an optional cancelled predicate and provides nonjoining
request_stop plus stop_requested. GUI folder jobs capture authority and peer identity;
loss of ownership stops scans and queued writes. Viewer connection_identity is opaque.
Native inbox pulls use a per-channel queue of at most 32 jobs on the original loop,
perform blocking sends in a worker and cancel owned jobs on host shutdown. Failure replies
remain bound to their original control channel. Remote publication acknowledgement/retry and clipboard
coverage remain C3 follow-ups in Progress.md.

FileTransferReceiver.close is idempotent and terminal: it refuses subsequent frames and
discards unfinished bytes while preserving any earlier published target. abort discards
only the active partial transfer, allowing a later allowed transfer on the same channel.
Writes, publication and cleanup share a lock; callbacks run outside it. Cleanup attempts
both close and unlink, logs ordinary filesystem failures and preserves original interruption
objects. Native host/viewer receives bind to a fresh receiver and their concrete authenticated
peer/channel. Stop, files/control close, terminal connection state and file permission loss
clean partial bytes without waiting for another frame. Stale channels and state callbacks
cannot retire a replacement transfer. Terminal cleanup precedes state callbacks, including
callbacks that reconnect immediately. File/audit/state callback interruption carriers propagate
unchanged; ordinary native callback failures retain their existing logging/containment behavior.
The Remote Desktop GUI uses the same endpoints. No wire, facade, command or MCP schema changes.
Remote folder publication acknowledgement/retry and clipboard loop/disconnect coverage remain in Progress.md.

FileReceiveReceipt (utils.remote_desktop.file_receipts) is frozen local metadata with an
absolute path, lowercase SHA-256 and nonnegative byte size; malformed metadata raises the
flat-family FileReceiptError. FileTransferReceiver.handle_message accepts keyword-only
on_receipt, emitting once after complete atomic publication and before the legacy path callback.
The digest is built from successfully written chunks, without rereading a changing target;
short writes, aborts and publication failures emit no receipt. Host/viewer
set_file_receipt_callback accepts a listener or None, retaining existing path/audit callbacks
and original interruption objects. Relative inbox/watch paths bind at construction; path
notifications now use absolute paths for relative inbox configurations.
FolderSyncEngine.record_receipt registers original received bytes and returns False for
unselected/missing targets or detached/revoked owners. It does not hash the target, so delayed
processing cannot consume a later local edit. Legacy record_received(path) still explicitly
hashes current content. Receipt state wins older scans/sender completions; owner checks precede
filesystem access and repeat before state mutation with consistent lifecycle/content lock order.
The GUI folder toggle binds receipts to its captured viewer and engine; live role/auth/peer
checks retain the original authority. Local receipt metadata does not acknowledge remote
publication or verify a sender-provided checksum. Wire changes and reliable reconnect retry
remain separate C3 work in Progress.md, along with clipboard regressions.
