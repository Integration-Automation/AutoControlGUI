# Public API lifecycle

The supported entry point for new integrations is `je_auto_control.api`.
Everything reachable only through `je_auto_control.utils` is internal unless a
document explicitly says otherwise. The historical top-level package remains
available for compatibility but is not expanded with new integrations.

- Stable API removal requires a deprecation warning and two minor releases.
- Beta API removal requires one release note and one minor release.
- Experimental API may change in any release and must be labelled as such.
- Deprecations state the version introduced, planned removal version, and
  replacement. Use `je_auto_control.utils.deprecation.deprecated`.
- Breaking changes and migrations are recorded in `CHANGELOG.md`.

The project remains pre-1.0. A 1.0 release requires passing stable capability
tests on every claimed platform, documented recovery/diagnostic behavior, and
no unresolved critical security advisories.

Remote RBAC uses a reviewed capability catalog, independent of provider hints.
Unknown commands require host administration. Filesystem metadata is checked at
every scoped executor dispatch, including nested scripts and flow blocks.
Internal `RequestBinding` preserves authorization, roots and variable snapshots
for deferred work; it adds no public command or facade API.

`je_auto_control.api.journal` is Beta (schema version 1). It exports
`ActionEvent`, `ActionJournal`, `JournalError`, `read_events`,
`execute_journaled`, `read_action_journal` and `list_journal_runs`.
The legacy facade re-exports these for JSON/GUI integration compatibility;
the stable `core.py` namespace is unchanged. Journal readers validate schema
and ordering and do not execute records.

`je_auto_control.api.healing` is Beta. It exports fixed-frame evaluation models,
`evaluate_locators`, `healing_context`, `TemplateRevisionStore` and six JSON
comparison/revision adapters. HealEvent writes schema 2 and reads schema 1.
Compared location correctness and original-operation verification are separate.
Existing `self_heal_locate`/`self_heal_click` imports and commands remain available.

`je_auto_control.api.codegen` is Beta. It exports `CandidateScript`,
`CandidateError`, `generate_candidate_from_log` and `generate_journal_candidate`.
Manifest schema 1 identifies the exact source snapshot and observed-only replay.
Existing list-based codegen and CLI flags remain supported. Generation validates
but never executes the candidate; masked/incomplete/failed steps are omitted
from replay inputs and retained as provenance and warnings.

Candidate replay excludes ordinary runtime variable references without recorded resolved binding evidence. Block fields are validated without dispatch. Journal privacy includes signature-bound positional values and sensitive getter results; unhandled contained errors propagate to terminal container status while handled errors remain distinguishable.

`je_auto_control.api.config_sync` is Beta. It exports ConfigStore, ConfigBucket, ConfigSyncError, ConfigRevisionConflict and ConfigStoreCapacityError. SQLite commit/get/close are lazy and Qt-free. Version-2 server writes require CAS and stable operation IDs; bare PUT requires explicit migration configuration. Historical facade re-exports match these names for integration compatibility.

Beta config_sync now also exports ConfigSyncClient/SyncClientOptions, SyncEntry/MergeDecision/merge_entries, PeerState/can_collect_tombstone, SyncOutbox/SyncOperation/OutboxReport and causal bucket helpers. Default client writes are protected; legacy timestamp merge and opt-in blind transport remain compatibility APIs. Causal wire metadata preserves operation/origin/vector/deletion revisions and unresolved alternatives.

Beta config_sync adds SyncAdapter/ApplyReport, five definition adapters, asset manifest/transport/result models and six shared sync operations. Python services accept cooperative cancellation; AC/MCP wire adapters expose JSON-only arguments. GUI and Script Builder use the same services. Historical facade exports are compatibility mirrors.

Beta remote_sessions exports immutable identities/status/events, typed errors and get/disconnect/events functions. AC/MCP add JSON lifecycle adapters and all transport commands accept keyword-only optional session_id; historical facade mirrors remain compatible. Omitted IDs use transport/role script defaults. GUI identities are independent. SessionStatus aliases RemoteSession; active is local allocation, not WebRTC peer authentication.

Beta config recovery now separates never-dispatched intent, exact uncertain writes and confirmed stale writes. Explicit Retry renews exhausted exact attempts and causally rebases stale envelopes atomically. Adapter acknowledgements advance only after resolved explicit Apply; status exposes applied_revision/recovery and Exchange distinguishes recovery_required. Existing commands and script transport defaults remain compatible.

`je_auto_control.api.capabilities` is Beta. `BackendContext`, `CapabilityStatus`,
`CapabilitySnapshot` and `probe_capabilities` expose passive status evidence,
not a claim of platform acceptance. The legacy facade re-exports these names;
the stable core namespace remains unchanged. `AC_diagnose(include_active=False)`
and GUI diagnostics skip actual capture/cursor reads. The stable Python
`run_diagnostics()` retains active checks by default and accepts
`include_active=False`. Native Wayland grant failures never choose another
input device automatically; CLI selection is explicit.

Existing image search, BGR screenshot and fixed-frame healing entry points keep
their signatures and lazily select NumPy/Pillow when OpenCV is absent. The
fallback supports bounded normalized gray template matching, not arbitrary
OpenCV processing or video. Strict OpenCV/je_open_cv dependency accessors now
raise ImageDependencyRequired, which preserves RuntimeError compatibility and
adds AutoControlException, needs_dependency and capability metadata.

`je_auto_control.api.wayland_input` is Beta and re-exports the D3
`linux_wayland.input_events` and `linux_wayland.global_shortcuts` models. PhysicalRecorder returns
bounded raw kernel events, not a replay timeline. StopShortcutSession owns one
asynchronous portal registration and its cancellation; failed authorization is
retained until explicit close/start. Constructing either helper does not open
devices or request consent. WaylandInputSession, five script operations and the historical facade mirror
share JSON AC/MCP/Script Builder adapters. Diagnostics owns an independent panel
session. Raw results are masked in action journals; remote operations require
host administration. Stop sets a cooperative stop_event and stops native input
control, not arbitrary Python execution. Native acceptance remains in Progress.md;
the stable namespace and legacy replay recording contract are unchanged.

Native default authorization uses a separate connection-attempt lock, with
active/pending owners detached under a short cache lock. Stop/reset cancel
pending IPC and stale completion cannot publish its grant; permission polling
also leaves the cache lock free. Tests include controlled workers without
performing desktop input.
