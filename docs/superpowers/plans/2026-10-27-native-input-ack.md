# Native input acknowledgement revalidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Preserve the existing question opt-out; no per-stage agents. Final independent review is at the whole original goal's end.

**Goal:** Refuse new native input if activity or target validity changes while awaiting its owner ACK.

**Architecture:** NativeWorker uses one private validation method at the pre-event, prepared-pointer
and post-ACK boundaries. Its cleanup mode permits release events only and retains the existing
owned-input ledger/ACK/retirement contract.

**Tech Stack:** Existing Python, native worker, input observers and pytest fake backends.

**Spec:** docs/superpowers/specs/2026-10-27-native-input-ack-design.md

## Global Constraints

Background only, no native input/hooks/browser/device/24hour acceptance; original40items remain.
No version/dependency/shared-environment/production changes, model downloads or paid features.
Limits750file/75function/7parameters including self/CC10/nesting4/120columns; runtime.py remains750.
Preserve original15second bootstrap/3second cleanup/action deadlines and all historical failures.
No new cycles, duplicates, suppressions, retry/replay or weakening of ownership checks.

## Review Focus

- Activity changes during owner ACK must prevent the wrapper backend press.
- Target changes during owner ACK must be rejected even without an activity monitor.
- Mouse preparation may itself expose changed activity; reject before the outer press ACK.
- Malformed/missing owner ACK never reaches a backend or the post-ACK permission boundary.
- Takeover must still permit owned release cleanup, without enabling any new press/move/text/scroll.

### Task 1: Worker checks and headless behavior evidence

**Files:** Modify je_auto_control/utils/agent_runtime/native_worker.py and
test/unit_test/headless/test_agent_native_input_scope.py; create
test/unit_test/headless/test_agent_native_ack_boundary.py.

**Interfaces:** NativeWorker._validate_input(self,event:dict)->None consumes existing _cleanup,
_activity/_check_activity and _target.validate_input; _input's signature/wire protocol stay unchanged.

- [x] Add RED tests: actual wrapper/backend absent after activity or target changes during ACK;
  target-only mode, healthy exact order, bad/missing ACK, mouse preparation takeover, and release-only cleanup.
- [x] Run the new test file in a fresh owned C basetemp; retain expected behavior failures, no setup errors.
- [x] Implement the validation boundaries and cleanup event-kind guard. Extend the pointer-order
  regression with the new final check, retaining every existing pre-ACK assertion.
- [x] Run all test_agent_native*.py plus test_agent_activity.py, native wrapper and input-ledger regressions.
  Expected: all supported cases pass, no warnings, no real native input.

**Delivery checks for Task1:**

**Files:** Progress.md Agent item10; docs/updates current month/index; measured architecture_explore.md;
this plan/spec as needed.

**Interfaces:** No public or persisted interface changes. Existing docs retain persistent-source and
native acceptance gaps. New record binds actual RED/GREEN, static results and source commit.

- [x] Run Ruff, three-platform typing, whole Pylint paired with existing baseline, Bandit/Radon and
  original58 import-edge comparison; no new findings/cycles, existing debt retained.
- [x] Verify file/function/parameter/nesting limits and documentation/structure checks. Use targeted
  real-owned-helper IPC tests for retirement and takeover; no full-suite success claim for changed source.
- [x] Record under actual monthly ID lock, mirror only main Agent preserving all other bytes/40items,
  commit/push explicit paths and verify remote SHA/clean state. Run actual task-done acceptances.

Next original work remains the actual Windows persistent-source driver, bounded transport and
cross-helper lifetime. A later full-source coverage/artifact proof must cover this source and those
changes before final delivery; these are not prerequisites for claiming only this finite safety fix.

Behavior evidence: stage109 initial RED12failed7passed2.88s, strict numeric ACK RED2failed4passed3.06s;
GREEN33passed3.31s. Expanded13modules192passed61.69s, no skipped/error/warning cases;3313input hashes
unchanged. Actual coherent commit and task-done commands still required before formal task completion.

Ruling: fold verification/records into Task1's single coherent safety fix. They are acceptance for the
same behavior, not a separate feature. Original task-start BASE5d07b27 and initial brief are retained;
the actual task-done gate must include the delivery checks as well. No second task has started.

Ruling: this is an independently testable safety correction within original item10. Its focused
acceptance does not replace the later full Windows feature, final full coverage or deferred native evidence.

Delivery evidence: stage109 whole-source gates and original58 lint/import audits pass their
no-new-findings contracts; raw Pylint30 remains existing debt.41doc/structure cases pass14.88s
after measuring7stale architecture counts. Changed code nesting<=2, unchanged published
_release_owned has5levels explicitly retained in source-budgets01.json. One coherent9path
feature publication and actual task-done1 postcommit verifier finalize this finite fix.
No current full-source coverage/artifact/native completion claim; original40items active.
