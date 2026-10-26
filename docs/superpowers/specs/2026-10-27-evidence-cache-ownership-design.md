# Database-owned task evidence and historical journal segments

The original P5/Progress Agent item36 requires isolated evidence ownership and safe retention.
Published base968665138c6e3830469ee0d8a4b1af47336f869e reproduces actual public prune deleting
an unexpired source's journal/report after SQLite backup from runtime.sqlite to runtime.db.
The basename-only root and unconditional reuse of a stored journal path are separate defects.

Each database has a persistent private random identity, added within existing lazy schema creation.
Its current cache namespace binds that identity and the complete resolved database path beneath a
dedicated .agent-evidence-cache directory; it cannot alias any older *.evidence root. Copied IDs
do not merge different paths. Same-path restarts retain the same identity. Cache directories/files
reject redirection, unexpected types and multiply linked journal files before effects.

A historical or foreign stored journal reference never supplies filesystem write/delete ownership.
On a new publication/action, create a new owned history/journal segment and atomically rebind only
agent_evidence. Keep the prior run/journal/report references unchanged. Do not inspect, copy, move,
chmod or overwrite old cache files. Concurrent exact ensures create one segment; failed transactions
do not consume the original provenance. Status reads do not create a segment or enumerate foreign
cache files. Report the current cache state through existing task metadata/JSON inspection.

Pruning deletes only recognized artifacts in the current database namespace and its own expired
SQLite task/history rows. Historical/unowned physical files remain, like existing external journals;
they are not silently adopted or garbage-collected. Private source export protection includes current
and legacy cache roots and actual retained historical cache roots without reserving ordinary output
basenames. Neither segmentation nor a cached report grants completion or input authority.

Use real FileTarget tasks, SQLite backup, actual public prune, restart, legacy-layout fixtures,
transaction failure/competition, redirection and private-export tests. No native input, real browser,
dependency/version changes, paid functionality, WAL changes, relaxed deadlines or per-stage agents.
Keep runtime.py750 lines and limits750/75/7/10/4/120; no added cycles, duplicates or suppressions.
All original40items, original handoff audit and deferred native/device/browser/24-hour work remain.
