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
