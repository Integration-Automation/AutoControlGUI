# Retained browser completion and skill verification

The P5/P9 requirement is to verify current independent completion conditions after input authority
has retired, while retaining the original application's context. WebRunner ae1d3ad/0dec5ab now
provides permanent `freeze_readonly()` on the actual existing SDK session. This stage connects that
provider to AutoControl's existing private completion and skill paths; no replacement page can
establish the original browser state.

## Decision and alternatives

Chosen under the existing inline execution/question opt-out: a runtime-owned bounded collection,
keyed by actual effect task ID, owns the original permanently read-only helper after input retirement.
The ordinary target relinquishes that channel; another input task may create its own fresh context.
Private completion admission selects the original effect task's retained entry, never a profile's
latest page, model-supplied context ID, stored observation or new helper. A fresh page loses the state;
keeping a writable helper violates input retirement. Neither alternative satisfies the contract.

## Scope and constraints

- Implement the full browser consumer path: SDK/worker retirement, host lifecycle, actual private
  completion preview/create/finish, skill adoption/publication and existing API/GUI consumers.
- All execution background; tests use real owned IPC/SDK/proxy with fake installed Chromium and
  controlled owned files only. Native/browser/device/24-hour acceptance stays deferred.
- Keep the original forty-item P0–P9 goal; remote device providers and cross-host work remain open.
- No alternate browser engine, production checkout/service/shared environment change, dependency or
  version bump, credential operation, paid feature or Tripo generation.
- File/function/parameters/CC/nesting/line limits 750/75/7/10/4/120. No new import cycle or broad
  suppression. Reuse existing completion/recovery authorization and all shared command surfaces.

## Retirement and ownership

Only a finite completely confirmed source workflow with an independent browser criterion can
retain a helper. Uncertain/prepared/dispatched actions, held input, pending RPC, failed cleanup or
unknown process ownership cannot produce a reader. An absent or older SDK read-only contract closes
normally and leaves completion unavailable; it must not turn an otherwise valid legacy task into
an unsupported-feature cleanup failure.

Evaluate action receipts only after the actual built-in browser/channel/criterion checks. Ordinary
desktop/file/custom cleanup must not depend on browser-retention evidence being readable. Later
report publication may fail visibly, but cannot prevent independently confirmed input retirement.

During broker retirement, the actual worker calls SDK freeze on its owning thread. The worker
permanently refuses perform/configure/probe/transfer/input ACK paths before returning the exact
SDK retirement/context proof. The host independently validates that proof and stops acknowledging
any input. Only confirmed transition and empty journal/ledger permit input lease release. Failure
retains quarantine and cannot be retried into a writable or apparently successful reader.

The runtime keeps at most 16 contexts, each for at most 300 absolute seconds. The deadline starts
at reservation before freeze, so slow detachment never extends the post-freeze lifetime. These are
host bounds, never model options. Capacity exhaustion closes the new source normally rather than
evicting a borrowed context. Expiration, disabled target, source removal/scope/owner change or
loss of the actual original principal invalidate the entry and reap its owned process. Failed reaping remains
tracked and unavailable; it does not free capacity or release the runtime service lock. Maintenance
includes failed detached transfers even before a proof is committed. Once the collection accepts
the process, its cleanup owner cannot also be restored to the source target; later confirmed reaping
must be possible after a transient failure, without inventing a usable reader.
Maintenance and every read check expiration; runtime close drains all entries. Restart cannot restore a live
context or infer one from durable evidence. No new browser/process starts during completion.

## Read-only admission and execution

Private completion bindings already contain source/effect task IDs and fixed verification specs.
Use the effect task ID plus original spec/owner/profile and SDK context proof for retained selection.
Preview and new admission require a currently available matching entry. An exact creation retry
returns the existing child without another read or new grant after context expiry. New admission
rechecks original source/effect snapshots under the insertion transaction and rolls back a stale child.
Ready/observe/verify additionally
check the actual SDK view, current task authority/deadline, origin/root/profile restrictions, both
principals, source snapshots and pre/post context continuity. Cached capabilities are not authority.
Only one read borrower is active for an entry. A completed or failed read scope releases that borrow;
the collection owns process lifetime until expiry/close. Another task's context cannot satisfy it.

The reader exposes ready/observe/pinned verify_browser/cleanup only. Host and worker each reject
tools, native input, transfers and ordinary configure; cleanup never injects releases or clears unknown
input witnesses. Network-retired live DOM is not a new server response. Existing bounded/secret
readback scripts and independent original-action versus fresh-condition evidence remain distinct.

SDK retirement, capabilities, reader binding and cleanup run under a deny-all tool guard and a
no-ACK input observer. Actual observe/verify use the current admitted policy's read-only guard;
the executor intersects nested guards, so deny-all metadata guards must end before legitimate
pinned `AC_browser_read` dispatch. No callback can acquire an ambient tool or native input scope.

Completion renewal uses the root effect context. Successful completion review flows through the
existing private evidence/skill record, accept and review_execution contracts, without widening
task-read access, changing recorded semantic actions or inheriting old success receipts. Existing
API/AC/MCP/REST/CLI/Builder and thin GUI completion/skill Actions keep their request schemas.
Passive capability diagnostics describe support separately from context readiness/native evidence.

An optional post-configuration protocol-1 bootstrap `browser_readonly=1` advertises only the
built-in worker's retirement API; missing, boolean or incompatible markers use legacy cleanup.
Actual SDK proof is still mandatory. The frozen worker accepts only a closed `bind_browser_reader`
operation with a parsed no-action external verification spec. Its exact original criteria, tools,
inputs, budgets and options remain fixed, roots stay within the original ceiling and private DAG/
skill input metadata is absent; only host-admitted origin-policy IDs may change. JSON comparison
preserves value types. The original input spec is never replaced or reactivated.

Already input/network-retired custody is bounded process ownership, not a live read grant. Expired
or revoked original input origins do not alone destroy custody needed by explicit private renewal.
Every DOM read still requires the current completion task's private binding, live reader origins,
original and reviewer principals, snapshots and current root/profile checks. No old origin is revived.

## Verification and delivery

First prove missing worker/SDK transition, retained task binding and real end-to-end completion with
RED tests. Then exercise replacement context, unsupported SDK, failed retirement/reaping, capacity,
expiry, scope/revocation/source changes, concurrent borrowing, lost helper, forged proof, cancelled
reads and two same-profile tasks. Use the real SDK/owned helper with mutable fake DOM for the
source-to-source path; verify no second engine launch and original action receipts unchanged.
Add skill and existing API/GUI surface checks, fixed-source headless/coverage, typing/lint/security/
budgets/import cycles, strict docs, wheel/installed worker evidence, and update all three README
languages/Sphinx/reference/lifecycle/capability/architecture/Progress/update index atomically.
## Maintenance and retirement consistency

Expiry/revocation maintenance captures the real input lease and must recheck its target, owner
and generation under the stop transaction's own SQLite writer. A released or replaced lease
cannot cancel a later token or rewrite stopped source snapshots. Accepted final state and token
cancellation are published before the stop commit becomes visible to settling workers. Current
revocation and original time budgets remain effective. Terminal cleanup still retries confirmed
retirement without changing the task's terminal result.
The revocation reason belongs to the same pending stop writer and survives terminal publication
atomically; no later cosmetic update may change an already published recovery snapshot.

Retirement uses the existing task lock without waiting: only its owner may transfer or reap the
actual target and remove its input lease. A concurrent caller leaves retirement pending instead
of validating an already released lease or detaching twice. Active observation/input cannot be
made to wait for a second retirement owner.

## Dependency ownership

The native proxy reports ownership of its original unretired browser channel; the existing
completion boundary composes policy eligibility using its established receipts/workflow imports.
Runtime supplies its current-operation getter to the private completion adapter. NativeWorker
supplies the actual TaskPolicy constructor after BrowserTarget compares the immutable scope;
the validator is never a model-authored RPC field. BrowserTarget does not import host policy.
The import audit checks added edges inside existing cyclic components as well as new/merged
components. Matching component sizes alone does not prove that no new cycle was introduced.
