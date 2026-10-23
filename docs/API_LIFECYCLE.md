# Public API lifecycle

The experimental managed-task API adds AgentTaskSpec/Budget/Handle/Result, AgentObservation,
AgentActionRequest/Result, AgentRuntime, AgentTaskError/ControlBusy, submit/get/list/observe/act/
finish/pause/resume/cancel_agent_task and explicit start/stop/status service functions. Import has no
service/native side effects. The shared AC/MCP/Builder catalogue preserves existing command names.
The default desktop adapter now isolates native calls in an owned helper, enforces action deadlines
and retains a host input ledger for cleanup before transfer. Cancelled clients request host pause.
See AGENT_TASKS.md for contracts, completion certainty, ownership and remaining native limitations.
WorkQueue.defer(item_id, claim=...) is additive; it returns a currently owned delivery to new without
consuming an application retry and refuses stale claims.

`Executor.execute_one(name, arguments=None)` is additive and returns the raw command result.
`run_tool_call` now uses it: configured identities must possess the command capability,
private top-level arguments are refused, runtime variables interpolate, cancellation propagates,
and an enclosing action journal captures the call. Calls without an RBAC scope retain local trust.
Nested dispatch intersects context-local command guards after argument interpolation.

Selected dev pushes run `.github/workflows/ei-lifecycle.yml` in an isolated
libei/libeis container, retaining versions and both native logs for 14 days in
`ei-lifecycle-<run>-<attempt>` artifacts. Half-open and live cleanup children
have 10/60-second deadlines and faulthandler. Unrelated child failures fail CI;
successful cleanup requires begin/end markers. The half-open probe also requires
equal integer descriptor counts; live cleanup releases owned device refs first.
Run 39507190704 on libei/libeis 1.3.901-1 passes 9/9 and 20/20 checks, including
native out-of-region refusal without CLI fallback. Half-open `ei_unref` still
segfaults, so runtime protection remains and helper isolation is pending.
Device pause and sequence readback remain unverified. These controlled socket
peers do not establish compositor consent, physical or multi-monitor acceptance.

A native Wayland pointer coordinate outside every granted EIS region, after
raw-coordinate and layout-origin mapping, raises `LibeiUnavailable` with
`state="failed"` and disables automatic CLI fallback. A rejected move emits
no motion/frame or subsequent click. Valid coordinates, devices without
regions, later valid requests on the same sender and explicit CLI selection
retain their existing behavior.

This correction adds no public names or signatures and retains the existing
exception family. It does not revoke an otherwise valid sender or its grant.

The additive public capability API is BackendContext, CapabilityStatus,
CapabilitySnapshot and probe_capabilities(context), exported from the root
and versioned je_auto_control.api/core namespaces. Contexts are detached and
immutable; statuses contain name/state/backend/reason/recovery/desktop_wide.
Snapshots serialize platform/display_server/passive/input/capture. Eight
states distinguish unverified prerequisites from available last-local native
observations, permission/dependency gaps, unsupported, paused, revoked and
failed states. Cached libei availability requires a completed handshake plus
active keyboard/absolute-pointer/button/scroll families; partial grants remain
unverified, paused families report paused, and missing required devices revoke
that readiness claim. A result grants no authority, does not poll native events,
and cannot prove external freshness or full monitor coverage. The input
item covers key/pointer events, separately from wtype text.

AC_probe_capabilities and read-only ac_probe_capabilities share a no-argument
adapter and reject caller-supplied context/authority metadata. Their Builder
and Diagnostics surfaces use the same contract; viewer queries need
read_screen. Rendering/language changes do not probe. Existing active
diagnostics and input/capture operations retain their signatures, authority
checks and failure families. Native restore/restart/context integration
and native session retry/cancel/stop controls remain open in Progress.md.

The GUI task infrastructure provides `gui.task_controller.TaskController`:
`submit(work, owner=widget)` returns a caller-owned `TaskHandle` with
typed `TaskOutcome` and `TaskProgress` observations. Work receives a
Qt-free `CancellationToken` with checkpoints, bounded interruptible waits
and progress reporting. Submission captures context; dispatch refreshes
store-backed identity. Work must receive plain data, avoid widget references
and authorize its own operation. Existing
`DeferredAuthorization.scope()` still requires input privilege, while
`context_scope()` only refreshes/binds identity for independently authorized work.

Owner/handle/controller destruction requests cooperative stop and drops
late delivery. Each task has a separate ID/token; callbacks run on the GUI
thread. Cancellation does not forcibly interrupt an uncooperative call
or relabel a successful committed return. Errors/progress use the captured
secret scope; terminal errors retain no exception traceback. Failed thread
starts roll back both registries and preserve the original failure.
Diagnostics now adopts this controller. Remaining panel/backend migrations
and native session operations stay in `Progress.md`.

Active **Diagnostics → Actions → Run diagnostics** uses the shared task
controller off the GUI thread. **Stop diagnostics** requests cooperative stop;
the view distinguishes running, stopping, canceled and failed states in four
languages. Progress counts completed checks. Duplicate runs are ignored, close
abandons late progress/results, and a deliberate retry starts a new owned run.
GUI cancellation is a typed outcome without retained exception tracebacks;
headless core/SDK/CLI and the MCP handler preserve original direct/wrapped controls.
Ordinary probe failures still become report rows and allow remaining checks.

`CancellationToken`, `TaskProgress` and `cancellation_scope` are exported by both
SDK namespaces. Bind `with cancellation_scope(token): report = run_diagnostics()`;
the owning caller can call `token.cancel()` from another thread. The existing
no-argument diagnostics signature remains. Scope binding grants no authority;
`cancellation_scope(None)` only suspends cancellation for bounded owned cleanup.
`AC_diagnose` and the new read-only `ac_diagnose` share the report. The MCP tool
accepts no arguments, uses request cancellation/progress and requires
`read_screen`, as does the explicit GUI action. Caller-supplied tokens or
authority metadata are rejected. These are active checks: capture may request
consent. `ac_probe_capabilities` remains the separate passive alternative.

Scoped Wayland D-Bus connect/read/partial-write waits poll at intervals capped
at 0.1s within the original total deadline. Cancellation attempts Request.Close
on the originating bus with its separate 0.25s budget, then releases that
connection; a canceled returned image is discarded. Scoped CLI captures stop
and reap their newly owned helper/process group with bounded cleanup, preserving
the original control even if pipe close fails; reaped numeric PIDs are never
signaled. liboeffis acquisition observes scoped stop and releases its own context.
Uncooperative/native calls are not forcibly preempted; the GUI remains responsive
while cleanup completes. Restore/restart, native session controls, capture-owner
metadata and remaining panel/backend migrations stay in `Progress.md`.

`python -m examples.cancellable_diagnostics` runs a controlled cancellation demo
without providers. `--active --cancel-after 2` explicitly runs diagnostics and
requests stop after two seconds; native/device/API acceptance remains separate.

Diagnostics construction and retranslation are passive UI operations. Its
Actions command submits run_diagnostics to an owned worker; Stop requests cleanup.
Headless/AC signatures remain unchanged; active ac_diagnose is additive. The passive capability
surface below is additive and separate from active checks.

Screenshot portal signatures and the ordinary AutoControlScreenException family
remain compatible. Abandoned requests attempt Request.Close on their originating
bus with a separate 0.25-second I/O budget; completed Response interactions are
already over. Original controls survive D-Bus wrappers and cleanup. SessionBus
retains its signatures while bounding writes and the remaining reply wait and
closing partial connect/authentication/Hello state before failed __enter__ exits.
No facade, AC, MCP, Builder or wire surface is added. Live portal cancellation,
restore and compositor-restart acceptance remain open in Progress.md.

Wayland native input preserves the existing exception families and signatures.
LibeiUnavailable/OeffisUnavailable carry internal inert state distinguishing
optional absence from permission, pause, revocation and protocol failures.
Auto mode only falls back for optional absence/unclassified legacy adapters;
explicit libei selection and classified refusals propagate. Cached refusals
require explicit reset before a fresh permission request; native chord cleanup
uses its original backend and preserves cancellation. This safety behavior
adds no facade, AC or MCP command. Public capability probes and independent
input/capture diagnosis remain open in Progress.md.

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
Native receive receipts and explicit GUI reconnect/resume are integrated below.

FileTransferSender.send, WebRTCDesktopViewer.send_file and WebRTCDesktopHost.push_file
accept an optional keyword-only cancelled predicate. Writes now synchronously confirm
the original bridge callback, cap buffered data at 1 MiB and fail after a bounded wait.
Callback errors reach FileTransferError; cancellation/hard signals keep their original
identity. Chunk sizes must be integers from 1 byte through 1 MiB (bool is refused), and
source truncation/growth relative to the announced size aborts the transfer. Default manual-mode success means
the channel accepted every frame, not that the peer committed the file. Legacy manual wire remains available; confirmed native mode is described below.
Concurrent producers on one channel fail explicitly; a pending abort retains ownership.
FolderSyncEngine accepts an optional cancelled predicate and provides nonjoining
request_stop plus stop_requested. GUI folder jobs capture authority and peer identity;
loss of ownership stops scans and queued writes. Viewer connection_identity is opaque.
Native inbox pulls use a per-channel queue of at most 32 jobs on the original loop,
perform blocking sends in a worker and cancel owned jobs on host shutdown. Failure replies
remain bound to their original control channel. Explicit GUI reconnect/resume and clipboard lifecycle coverage are described below.

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
Explicit GUI reconnect/resume and clipboard lifecycle coverage are described below.

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
publication or verify a sender-provided checksum in legacy mode. GUI explicit reconnect/resume is described below; explicit clipboard lifecycle coverage is described below.

Publication-confirmed native sends use keyword-only require_commit=True on the existing
FileTransferSender.send, WebRTCDesktopViewer.send_file and WebRTCDesktopHost.push_file.
The default remains False for legacy manual callers; the GUI folder sender always opts in.
Confirmed mode requires a native file listener on the original authenticated channel/loop
and runs outside the bridge thread. A fresh version-2 nonce probe precedes each file's source
metadata/content reads, including after permission changes. Source paths bind to their call cwd.
The strict begin includes commit=2 and a transfer ID; strict end includes SHA-256 and a new
unpredictable nonce. The receiver validates ID, integer size, nonce and checksum before atomic
replacement, then sends file_commit with that ID/nonce/digest/size before user callbacks.
Only a matching response completes delivery. Unsupported, timed-out, cancelled, replaced or
revoked operations retain failure; a completed receipt wins cancellation arriving later.
Each queued write keeps its existing bound; capability replies wait at most two seconds and
publication replies five seconds. They are distinct from write/backpressure waits.
Protocol requests are bounded, weakly indexed and retired on channel/session/permission end;
captured generations prevent revoke/regrant from reviving a pending request. Envelope parsing
is bounded to 4 KiB before decoding. FileCommitError stays in the flat framework family and
native sender boundaries expose FileTransferError with original interruption identities.
Legacy manual envelopes and path/receipt listeners remain available. GUI folder delivery now
requires compatible support on both peers. Same-engine uncertain sends retry without advancing
the confirmed digest. Explicit GUI reconnect/resume and clipboard lifecycle coverage are described below.

FolderSyncEngine.checkpoint() exports a frozen FolderSyncCheckpoint only after request_stop/stop
and actual worker retirement; a live blocked sender raises flat-family FolderSyncStateError.
The metadata contains the absolute watch, recursion flag, baseline status and immutable name/digest
pairs. Export and constructor restoration perform no filesystem reads. Invalid/mutable/duplicate
entries and mismatched watch/recursion options fail explicitly. A replacement copies metadata and
receives a fresh sender/cancelled predicate; it never adopts the old transport or authority.
The baseline includes initially ignored files and frozen local receipts, not just delivered files.

GUI folder start/stop now lives in folder_sync_controls.py; the existing panel toggle delegates to it.
One FolderSyncHistory retains a stopped engine across viewer stop/reconnect. The user reconnects
and explicitly presses Start sync. Handoff requires a matching authenticated host fingerprint,
absolute watch path and local principal (including user-store provenance). Missing/changed host
identity, root or principal establishes a fresh baseline. Unknown fingerprints are scoped to one
concrete viewer/connection, never a replacement. Host metadata uses the existing authentication
trust model and adds no cryptographic identity guarantee. Store-backed permission is refreshed
before a new engine can read the watch or send; old callback/worker bindings remain invalid.
A still-running old worker refuses handoff, including a change of peer/root; retry after it exits.
Failed starts leave the retained baseline intact. Explicitly disabling folder sync forgets the
baseline, but still owns a retiring worker. Viewer Stop/reconnect retains it until resume; panel
destruction/application exit clears it. This state is memory-only and never auto-enables sync.

TCP/WebSocket clipboard APIs and legacy text/image JSON envelopes remain compatible. Transfers
are explicit: received values do not automatically forward/broadcast, and identical deliberate
sends are not deduplicated. Viewer send_clipboard_text/image capture the original channel before
encoding, recheck ownership before writing and propagate connection replacement as ConnectionError.
Buffered receive dispatch rejects stopped/replaced channels; decoded clipboard data rechecks the
same channel before invoking callbacks. Host receive checks shutdown/authentication after reads
and again after decoding; input/clipboard/file control routes require PERMISSION_FULL.
Ordinary clipboard callback/provider failures keep their logging/containment behavior. Explicit
wrapped cancellation/hard signals preserve the original object at SDK/native GUI boundaries.

The Qt-free clipboard_delivery module shares lazy native application and captured ClipboardDelivery
metadata. ClipboardReceiver binds the original peer weakly once before it starts,
preventing a callback from keeping its own viewer and Qt panel alive until cyclic GC.
Only actual queued deliveries retain the peer strongly until consumed or discarded.
GUI callbacks carry the concrete viewer and DeferredAuthorization captured at connect;
the queued slot checks its current owned viewer and live connection, refreshes the original user
and rechecks ownership before applying data. Explicit GUI push refreshes before native clipboard
read and again before network send. Ambient callback-thread users never supply authority.
No clipboard OS watcher, automatic forwarder or implicit reconnection replay is introduced.
Existing SDK methods and the GUI Push clipboard button share these contracts without new root,
AC, MCP, Builder or wire fields. Native providers remain lazy; controlled tests replace them.

Workflow additions: draft_agent_workflow compiles inspectable task specs; workflow_download,
workflow_manifest, workflow_control and workflow_open require a managed operation scope.
AC/MCP/Builder share their schemas; REST adds POST /agent/draft and CLI adds agent-task draft.

stop_all_agent_tasks is additive across Python/AC/MCP/REST/CLI/GUI and respects task visibility.
Shared-desktop acquisition now requires a supported physical activity adapter; Windows uses an owned
presence-only hook. Budgets persist monotonic elapsed high-water marks without resetting on resume.

Task results add metadata provenance. get_agent_task_receipts, reconcile_agent_task and prune_agent_tasks
are additive across Python/AC/MCP/REST/CLI/GUI. Committed receipts are immutable; uncertain outcomes
need explicit owner review. Native task images persist only with strict-redaction opt-in and bounds.

submit_agent_task accepts an optional owner-scoped idempotency_key. manage_agent_trigger and
list_agent_triggers add durable preauthorized interval/cron/file/event bindings across all task surfaces.
Private vault guards are installed by managed operation context; unscoped script interpolation is unchanged.

Input ownership writes a private, fsynced per-resource crash witness before native dispatch and input ACK. An unfinished witness blocks new owners across databases. Explicit host-only recovery requires a review note and a trusted no-held-input probe, never replays persisted input or signals persisted PIDs, and does not reconcile/resume the old task. POSIX input helpers monitor their actual parent and retire only their own live session group. Approved document handoff runs outside the input helper tree, so user applications survive normal task cleanup; bounded, preapproved focus steps wait for scoped windows. Observations also expire against a host monotonic clock. Native desktop/device acceptance remains unverified.
