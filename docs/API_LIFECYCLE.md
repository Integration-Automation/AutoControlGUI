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
