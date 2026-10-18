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
