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
Owned outbox SQLite schema 1 migrates to 2 without changing existing edit wire version 1;
control wire is version 1. Status remains private, local-only and credential-free.
Settings/assets application and sync UI remain C3 work.

AssetFile, AssetManifest, AssetSyncResult, AssetTransport, DirectoryAssetTransport,
build_asset_manifest and sync_assets are experimental. Asset manifest wire is version 1.
Private AC/MCP/Builder manifest/stage commands publish a complete verified local cache
generation, never an active workspace replacement. Explicit files retain their bytes;
settings redaction/adapters and causal integration remain C3. Current roots/cancellation
are rechecked. Corrupt caches fail without overwrite; identical verified caches are reused.
