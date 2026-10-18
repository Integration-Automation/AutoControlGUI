# Public API lifecycle

The supported entry point for new integrations is `je_auto_control.api`.
Everything reachable only through `je_auto_control.utils` is internal unless a
document explicitly says otherwise. The historical top-level package remains
a broad convenience facade and also exports new headless features under the
project's facade rule. Membership in its `__all__` does not promote a feature
into the versioned stable API.

Structured action-journal storage, capture/read helpers and history provenance
links are experimental while B1 interface integration remains in progress.
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
experimental snapshots; manual-run history ownership remains pending.

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
