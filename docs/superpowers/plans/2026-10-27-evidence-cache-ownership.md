# Database-owned task evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Preserve the existing question opt-out and whole-original-goal final review; no per-stage agents.

**Goal:** Stop cross-database evidence mutation/deletion while preserving old provenance and usable current journals.

**Architecture:** A neutral cache helper derives a namespace from the database's full path and persistent identity. TaskEvidence creates a new history segment for a nonowned stored reference, preserving old references and bytes. Source privacy consumes actual cache roots; existing task/GUI JSON surfaces expose cache state.

**Tech Stack:** Python3.10+, SQLite, pathlib, existing HistoryStore/ActionJournal/FileTarget.

**Spec:** docs/superpowers/specs/2026-10-27-evidence-cache-ownership-design.md

## Global Constraints

Background only; no real browser/device/input, shared-environment installs, version change, paid dependency or fee feature.
Task2 permits only a new owned temporary application installation after the required recorded comparison.
runtime.py remains750; file/function/parameters/CC/nesting/line limits750/75/7/10/4/120, including self.
No added import cycles/duplicates/suppressions, WAL/durability/deadline relaxation or replay.
Original40items and deferred acceptance remain open; final review only at the whole-original-goal end.

## Review Focus

Actual SQLite backup retains task IDs and history paths; only the expired backup may be pruned.
An old/foreign journal is provenance, never permission to overwrite or delete another namespace.
Same-path restart is idempotent; old-layout rebind preserves original run/journal/report bytes.
Failed/concurrent rebind and redirected caches preserve original metadata and user output.
New private roots must not make old/historical journal/image/report paths exportable.

### Task 1: Owned namespace, historical segments and private boundaries

**Files:** new utils/agent_runtime/evidence_cache.py; store.py/evidence.py/transfer_privacy.py; test_agent_evidence_cache_ownership.py and private-source regression tests.
**Interfaces:** EvidenceCache(store:Any).root:Path, .directory(task_id:str)->Path, .file(task_id:str,name:str)->Path, .is_private(path:Path)->bool. TaskEvidence.ensure retains its signature; a nonowned reference creates one new run/segment.

- [x] Add actual completed FileTarget/SQLite backup/prune and restart tests; observe correct RED.
- [x] Add private persistent database identity and namespace/path guards, keeping construction inert.
- [x] Verify independent roots and prune preserve source journal/report/user output and stable restart.

- [x] RED legacy/foreign publication, no-write status, idempotence, concurrent/rolled-back segment and path attacks.
- [x] Atomically rebind only the current link; retain old runs/journals/reports, never move or read old files.
- [x] RED/GREEN source export denies current/old/retained private paths while ordinary filenames stay usable.

Task1 behavior evidence: stage106 broad998JUnit includes all51 acceptance cases (49pass2Win1314skip).
Formal completion still requires the coherent verified commit and actual task-done acceptance command.

Acceptance command (append a fresh owned C `--basetemp`):

```text
python -m pytest -q -ra
 test/unit_test/headless/test_agent_evidence_cache_ownership.py
 test/unit_test/headless/test_agent_evidence_cache_legacy.py
 test/unit_test/headless/test_agent_evidence_cache_transactions.py
 test/unit_test/headless/test_agent_evidence_cache_privacy.py
 test/unit_test/headless/test_agent_evidence_cache_paths.py
 test/unit_test/headless/test_agent_task_evidence.py
 test/unit_test/headless/test_agent_transfer_private_sources.py
```

Expected:49passed2skipped; only literal file symlinks unavailable with Win1314 may skip on this host.
The listed paths are one argv, displayed across lines for readability.

### Task 2: Coherent verification and delivery

**Files:** three READMEs/Sphinx2/architecture/map/lifecycle/capability/Progress/monthly/changelog as applicable.

- [ ] Run task/evidence/history/retention/recovery/transfer/ownership regressions and prescribed static gates.
- [ ] Check exact original58 import edges; preserve existing raw lint debt without new issues/cycles/duplicates.
- [ ] Freeze inputs and run full configured coverage; inspect every skip/error/warning/atexit and hashes.
- [ ] Strict docs, exact fresh wheel/sdist/installed metadata/bytes and real installed-worker proof.
- [ ] Compare/write differences before any isolated installation; mirror only main Agent bytes, monthly ID lock,
  explicit owned-path commit/push and remote SHA/clean proof. Do not mark the original goal complete.
