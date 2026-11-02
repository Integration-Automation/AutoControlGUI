# Retained browser completion implementation plan

> Execute inline using superpowers:executing-plans and test-driven-development. The existing user
> question opt-out persists; no per-task agents/reviewers. One review remains at the full P0–P9 end.

**Goal:** Verify original browser effects with fresh permanent read-only context and adopt that
evidence through existing completion/skill/API/GUI workflows after input authority retires.
**Architecture:** Actual SDK freeze in the original worker, runtime-owned effect-task context
collection and closed borrowers. Keep source evidence, current conditions and authorization distinct.
**Tech Stack:** Existing Python/owned IPC/SQLite/RBAC/je_web_runner; no new dependency or engine.
**Spec:** `docs/superpowers/specs/2026-10-25-retained-browser-completion-design.md` and original
`docs/superpowers/plans/2026-10-23-agent-runtime.md` P5/P9.
**BASE:** AutoControl635325d18e05470078516365327476fd9b7b3dd1, WebRunnerae1d3adfdaa45f01d47bf65fca7966a55fc4d884.

## Global constraints

- Entirely background, no desktop/native/device/real-browser/24-hour acceptance startup.
- No production/shared venv/dependency/version/credential/billing/Tripo changes or merge/deploy.
- Browser paths use je_web_runner exclusively. Context IDs and model/JSON flags grant no authority.
- File/function/parameters/CC/nesting/line <=750/75/7/10/4/120; no new cycles or blanket suppressions.
- Preserve existing desktop/file read-only, recovery/renewal/handoff and unknown-input quarantine.
- Keep all forty tracked gaps until actual corresponding scope is delivered, including remote sources.

## Review focus

1. Two tasks on one profile must never borrow the other's retained DOM or authorization.
2. Freeze failure/forged ACK cannot release input ownership or later revive a writable worker.
3. Expiry/revocation/source mutation during a read must refuse publication and preserve failed cleanup.
4. Service restart/lost helper cannot open a blank page or certify old observations as current.
5. Read-only completion adoption must retain original skill actions and exact independent criteria.

## Files and interfaces

- Modify `browser_target.py`: actual SDK freeze/view, closed mode, same identity, bounded SDK proof.
- Modify `native_worker.py`: monotonic browser retirement and closed read-only RPC operations.
- Modify `native_target.py`: detach a confirmed frozen owned channel while retiring ledger/journal;
  no replacement launch, no native input ACK, no fake readiness flag.
- Create `retained_browser.py`: bounded actual effect-task entry collection and lifecycle checks.
- Create `retained_browser_target.py`: closed borrow adapter for existing completion runtime calls.
- Create neutral `browser_retirement.py` / `browser_readonly_scope.py` helpers. Inject current
  operation from runtime through the existing completion boundary. Actual channel ownership stays
  in native_target; eligibility uses completion_recovery's existing policy dependencies. NativeWorker
  supplies the actual TaskPolicy validator to BrowserTarget after immutable-scope comparison, so
  neither new leaf cycles nor new edges inside an existing cyclic component are introduced.
- Modify `runtime.py`: create collection, retirement collaborator, close/maintenance/prune lifetime.
- Modify `completion_recovery.py` / `readonly_target.py` / `target_profiles.py`: actual private effect
  selection and availability, desktop/file behavior unchanged, passive capability truthful.
- Add dedicated headless protocol/lifecycle/recovery/skill/source-SDK tests; reuse existing helpers.
- Docs: README3, Sphinx2, API_LIFECYCLE/CAPABILITY_MATRIX, architecture + detailed map, example,
  Progress/update index. Existing completion and skill request schemas/Actions remain the seam.

## Task 1: Actual worker retirement and closed SDK mode

- [x] Write `test_agent_retained_browser_worker.py`: real NativeWorker/BrowserTarget with controlled
  SDK session; freeze returns actual contract1/context proof, preserves identity, closes network,
  and refuses old perform/configure/probe/transfer/input paths. Missing/bool/incompatible SDK
  marker returns unavailable with normal cleanup; failed transition cannot issue or revive a reader.
- [x] Run new cases first with owned absent basetemp. Expected RED: missing retirement RPC/method,
  not dependency/setup errors. Implement only behaviors whose failure has been observed.
- [x] Add `BrowserTarget.freeze_readonly() -> dict` and worker `retire_browser` closed transition;
  read-only worker methods reuse original pinned criteria and never configure a replacement task.
- [x] Run the new file plus unchanged browser target/native worker/readonly helper regressions.
  Expected pass; no real engine/input. Source-to-source proof later uses actual SDK, not fake flags.

## Task 2: Effect-task collection, retirement and ownership

- [x] RED tests for `RetainedBrowsers` and closed adapter: 16 entries/300 absolute seconds, task/spec/
  owner/profile/context mismatch, one borrower, no replacement after close/expiry, confirmed reaping,
  failed reaping retained unavailable and still counted. Expiry never extends on borrow.
- [x] Add neutral six-field entry and collection in `retained_browser.py`; close SDK/process only
  through the exact owned channel, outside collection/runtime locks. Never evict a borrowed context.
- [x] RED runtime tests: eligible confirmed source detaches only after actual freeze ACK and before
  broker release; uncertain/pending/held-input/unsupported sources close normally or stay quarantined
  as appropriate. Add a retirement collaborator to keep runtime function/file budgets.
- [x] Wire runtime collection/retirement/maintain/close and strict native detach. Failed retirement
  preserves the input witness; failed later read-only reaping preserves tracked process ownership.
  Expected new and existing ownership/cancellation/recovery tests pass without changing deadlines.
  Start the fixed 300-second deadline at reservation before detachment, without extension at commit.

## Task 3: Real completion/skill/shared-surface integration

- [x] RED actual SDK/owned-helper test: finite confirmed fill, unmet final criterion, input retirement,
  mutate controlled fake DOM, preview/create completion then finish succeeds with one engine launch.
  Original action rows stay unchanged; helper/thread/context/policy remain the actual original.
- [x] Bind collection selection using private root effect task ID and fixed verification spec in
  `completion_target`/preview/create. Reader ready does no configure/launch; observe and pinned
  verify use fresh SDK view and current scope pre/post checks. Runtime cleanup releases the borrow.
- [x] Add two same-profile sources, lost/replaced helper/context, stale snapshot, cancelled read,
  expiry/revocation/disable/source mutation mid-call and forged capability/ACK cases. No fallback.
- [x] Extend skill record/accept/review_execution and existing API/GUI Actions tests with the actual
  new completion evidence. Keep original workflow actions, trial IDs and rights; no raw session handle.
- [x] Update passive diagnostics and docs3/Sphinx2/lifecycle/capability/map/architecture/example.
  Expected existing desktop/file/renewal/handoff/shared-surface tests remain green.
- Preserve explicit private origin renewal through a closed reader-scope bind without reconfiguring
  original input. Separate bounded retired-context custody from every live DOM read grant. Probe
  optional configured-worker retirement support before transition and require actual SDK proof.
  Preserve exact creation retries and roll back source changes during new admission probes.

## Task 4: Fixed-source verification and stage delivery

- [ ] Capture committed baseline before product edits; compare whole quality/type/cycle diagnostics,
  run focused then fixed-source full headless and actual coverage. Existing intermittent HTTP409,
  helper bootstrap deadline and shared pytest-current cleanup errors remain unresolved if not fixed.
- [x] Verify strict docs, package/installed real worker/source-SDK contracts and source-byte parity;
  no shared installation or browser startup. Explicitly record any baseline failures/limitations.
- [x] Publish consistent README/reference/architecture/Progress/update index, stage only owned files,
  commit/push feature branch and verify remote/clean status. Main Agent Progress mirror changes only
  its Agent section; preserve all unrelated raw bytes. Keep original goal active and remote/native
  provider/acceptance work open. One whole-original-plan review remains at its actual end.

### Full-suite correction: idle queue contention

The first completed coverage run had 15,346 passes/78 skips and five DAG failures. Owned caller/
server timing and thread dumps locate SQLite commit/read contention with idle queue claim writers.
The bounded original two-second calls remain unchanged. Add a read-only, queue-specific empty hint
before normal WorkQueue.get_next claims; actual work is still rechecked in BEGIN IMMEDIATE, with
unchanged generations/retries and stale-work recovery. Deterministic reserved-writer tests fail
twice before the correction; the existing five DAG failures plus queue/fencing regressions then pass.
Run the whole corrected source and preserve the earlier failed run as evidence, not a successful gate.

Self-review: actual missing-helper/provider behavior is the deliverable; a plan, capability flag,
historical recording, SDK-only test or fresh page cannot substitute. Each Review Focus has owning
tests above; authorization and lifecycle changes must use current private effect bindings.
### Full-suite correction: stale maintenance and concurrent retirement

Controlled event barriers first reproduce expiry and revocation rewriting an already retired
source. Two publication-window cases also reject stale watchers after release or a new lease;
a settling-worker case requires the accepted final state before stop publication. Preserve the
RED evidence, then guard the stop with the actual target/owner/generation under the same SQLite
writer and publish the accepted token/final state before commit. Current expiry/revocation still
stop input. A separate RED case reproduces a second retirement validating an already released
lease; serialize retirement with the existing nonblocking task lock. Keep all original deadlines,
cleanup evidence and recovery snapshot checks intact. Complete focused and fixed-source whole
verification after these changes; previous full-run evidence is historical.
Publish the revocation reason in the pending stop writer and preserve it under the terminal
transition's writer. An independent RED case observes terminal publication before the previous
post-cancel reason update; the fixed path leaves that published recovery snapshot unchanged.

### Fixed-source checkpoint, 2026-10-26

Canonical full: 15,361 passed / 78 skipped / 3 failed in 3004.00s; actual coverage87.64% meets
the81% floor. All3118 selected inputs and1348 package/config inputs are unchanged through reports.
The failed admin-inspection case cannot reach its succeeded background precondition; retention
uncertain/phase variants fail their two-second DAG precondition before retention assertions.
Owned read-only database evidence preserves unknown/waiting-review and stopped task states;
captured response writes include WinError10053. Prior durable-flush measurements do not establish
the exact cause of these three occurrences. No deadline, assertion, durability or retry was relaxed.
Task4's full-suite gate remains OPEN; the repository's explicit consistent-part checkpoint rule
permits publishing the focused/SDK/artifact/quality-verified implementation and recording every
remaining failure in Progress. This is a partial checkpoint, not full stage or original-goal completion.
