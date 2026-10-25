# Public API lifecycle

manage_agent_skill adds review_execution(candidate_id, task_id, execution_task_id,
optional completion_task_id), returning an execution_review token, bounded evidence, expected_version
and approval_required. accept with execution_task_id requires that token plus the existing explicit
version/note. The real original validation trial/spec hash/skill pin stays unchanged. A new injected
recovery-review seam validates at most sixteen private executable links, exact complete original
semantic effects (including JSON types), fixed scope, current principals and final independent
completion/retirement. A separately reviewed read-only proof may verify only the final effect and is
nested under execution_review. No target probe, capture restoration, source success rewrite, fabricated
trial or input grant occurs. One BEGIN IMMEDIATE writer checks proof, candidate and authority before
and after version/publication SQL. New agent_skill_executions stores historical proof alongside the
unchanged five-column publication; get/list expose execution_review only when actually adopted.
Transient task retention cannot authorize new adoption; published audit survives without live rights.
Existing ordinary accept/completion/recording remains compatible. Shared API/AC/CLI/authenticated
MCP/REST/Builder inherit the operation; two inert GUI Actions and four locales prepare requests.

manage_agent_skill record adds optional completion_task_id while task_id remains the original
workflow. Confirmed semantic source actions become a draft only after private independently completed
read-only evidence is checked. recording_template derives data after trusted proof validation;
recorded_spec keeps its succeeded-source signature and gate. One writer owns source/proof checks,
shared candidate insertion and post-write authority checks; _save retains ordinary record/repair and
origin-reauthorization deduplication. No nested writer, source rewrite, replay or fabricated trial.
Candidate provenance.completion_review contains historical IDs/hashes, not live authority. Added
criteria require the new candidate's own validation. Authority loss rolls back and returns managed
HTTP409. Existing API/AC/MCP/REST/CLI/Builder share the field; one inert Actions example and four
locale labels prepare the record request. Publication semantics stay compatible.

manage_agent_skill accept adds optional completion_task_id while task_id retains the original real
validation trial. Shared completion_contract validation has no service/DAG transport dependency;
managed_tasks.validate_recorded_completion keeps its existing signature and completion rules. Runtime
injects its existing authority/scope checks; AgentSkills supplies its existing snapshot digest. The
evidence module has no reverse service/model dependency, and ordinary AgentSkills construction remains valid.
Unrelated candidates, spec/pin mismatch, direct replacement of validation trials by executable children, missing private
admission/real ancestry, changed scope, unresolved effects, unretired readers and authority loss refuse.
The fixed derived completion_spec is shared by admission and consumers. Add agent_skill_completions,
an optional proof row atomically linked to the original five-column publication. Existing publication
task_id semantics remain; get/list add completion_review only for actual adopted publication. Caller,
owner/reviewer checks and candidate integrity are revalidated under BEGIN IMMEDIATE before version CAS;
post-write authority/proof failure rolls back all publication/adoption writes. Library authority loss
is a typed managed review refusal and HTTP returns 409. Historical proof remains after transient reader
retention; it grants no current task/input/read authority. Existing shared operations inherit the field;
one thin GUI Actions example and four locale labels prepare a request without executing it.

Existing HTTP pause/cancel/stop_all/shutdown routes use an independent per-IP token bucket with the
same default 120 requests/minute and burst 30 as ordinary requests. Authentication and failed-token
lockout, live RBAC/delegation, owner scope, audit/metrics and retirement remain mandatory. Normal
request limits are unchanged. The shared client recognizes exact DAG pause_batch/local_task-pause
bodies, reserves existing control transport slots and adds X-AutoControl-Agent-Control: 1 to /agent/dag.
The server validates the closed body before dispatch; marked execution/unknown bodies return 400.
Control exhaustion remains 429. Custom gates are called under their existing signature/policy instead
of silently bypassed. No new public command or GUI action is needed: existing controls inherit it.

manage_agent_recovery adds preview_completion/create_completion to its existing API/AC/MCP/REST/CLI/Builder
operation enum and thin GUI Actions. Preview returns source_task/effect_task/snapshot/verification_spec
without target access. Create accepts only task_id/snapshot/note, plus the existing optional source_owner
policy and ownership_review token; verification_spec is server-derived and is not a caller input.
An additive private agent_readonly_completions binding is committed with the ordinary successor link.
The new external-mode task has no actions, never starts a model, refuses act and ordinary executable
recovery, and selects only a permanent read-only helper from the original host configuration. All finite
skill actions must be confirmed; dynamic sources must have no dormant plan or unresolved effects. At
least one independent criterion is mandatory. Original pinned receipts can satisfy action/result clauses,
but current independent criteria and input retirement must succeed anew. Both owners and the actual
reviewer remain live around reads and after cleanup; cancellation/restart and generation fences remain.
Task metadata adds bounded completion_review provenance. Explicit retries retain original effect-owner
authority and actual recovery lineage, enabling existing DAG successor adoption without changing the
stopped original. Remote readers, production deployment and native acceptance remain open.
Repeated observe/finish operations send the same configuration to the existing read-only helper; only
an exact canonical spec/owner/profile match can rerun current readiness. Different configuration still
refuses, and no ready/observation result is cached across operations.

NativeDesktopTarget.completion_reader(spec) adds an internal host seam for a fresh standard desktop/file
observation context. A separate permanently read-only helper must report exact contract=1 and
input_supported=false before any configuration. Both sides refuse executable tools/input ACKs; the
host also refuses local workflow launch/recover and preserves unexpected-input quarantine. Closed
views cannot restart a helper, and retired reports only successful reader cleanup. Live owner, roots,
parent checkpoint and operation identity are checked around reads; browser criteria must be pinned.
Target summaries add readonly_completion={contract:1,status:"not_probed"} for declared standard proxies
or {status:"not_supported"}. Existing API/AC/MCP/REST/CLI/Builder/GUI target views share this passive
metadata. No custom property/native probe runs during summaries. Browser fresh-start and legacy/custom
helper fallback remain refused. The host seam alone does not restore UI state or publish success;
the reviewed task operations above perform independent verification and cleanup before publication.

Android command compilation now extracts display/window/activity focus once per guard and exactly
matches all six field orders. Nonempty labels preserve duplicate empty values through shell command
substitution. Serial/boot sentinels, same-connection pre/post checks, input-security digests, encoded
byte limits and action deadlines remain unchanged. Compiled proposals stay host-only and exact
recompilation still rejects differing bodies; no old input is rebound or replayed. Owned POSIX fixture
reads preserve raw bytes with a Bash builtin path and portable cat fallback. Their bounded diagnostic
records expose phase/elapsed/status only, withholding timeout commands, arguments and output. This
improves checked-path latency without adding device-control authority, a provider or managed readiness.

Caller-driven bound DAG runs use AgentRuntimeClient.bound() to capture an absolute owner-file path
and a hash of endpoint/token/generation. Every operation re-reads valid loopback metadata and refuses
identity changes before transport. Local node submit/get/pause uses the same bound client; server-side
inspection/completion evidence reads the owning runtime directly under current original-owner scope,
while independently refreshing the actual caller. Ordinary clients remain adaptive and legacy metadata
without a generation is still usable there; bound DAG runs require valid generation metadata. No
credential cache or automatic rebind/replay is introduced. Existing Python/AC/MCP/Builder/GUI Run
surfaces inherit this behavior.

local_task extends the existing DAG protocol with batch_id/attempt/node_id/operation/body. It accepts
only local submit/get/lookup/pause; submit/get/lookup require the exact active claimed node. Submit
validates the full bound spec/key, admits under the original owner and atomically stores actual actor,
source node/attempt and submission digest with the task/key/witness. Existing keys without matching
trusted admission are never adopted or backfilled. Get/pause accept only the exact admitted task ID;
pause permits precise retirement after the batch is fenced or original owner loses input permission.
Caller and service modes use this same bridge. Per-scope, pre-dispatch and maintenance checks refresh
original owner, actual actor, cross-owner management authority and live claim/attempt. Metadata adds
local_dag_admission contract/batch/node/actor UID, withholding attempt capabilities and user-store paths.
Ordinary submit stays caller-owned.

Recovery preview/review_authorization optionally accept owner_policy="source_owner" and return bounded
ownership contract/policy/review/owner UID/actor UID. Explicit create/create_authorized then require the
same owner_policy plus ownership_review, in addition to the existing snapshot/spec/note and optional
authorization_review. No arbitrary owner or actor field is accepted. The token binds the source snapshot,
both user-store namespaces and their current roles; changes require another review. Creation uses the
fresh source owner while separately recording the actual reviewer in agent_recovery_owners, atomically
with the task/lineage and any independent origin authorization renewal. Matching retries keep the exact
accepted ownership; ordinary children are never backfilled into a different policy. Default recovery
ownership remains the actual caller. API/AC/MCP/REST/CLI/Builder share the existing recovery operation.
GUI owner selection prepares these fields and rejects a changed selection before dispatching creation.
Task recovery metadata adds bounded ownership audit data; private store paths remain service-side.
Runtime scope/checkpoints/nested guard/pre-input and maintenance refresh original-owner Drive and the
reviewer's live ability to manage that owner. Input retirement/quarantine remain unchanged. The audit
survives child task retention with the recovery tombstone until source retention cascades it. DAG
continuation can read and adopt a source-owned child with normal original-owner visibility, genuine
recovery provenance and independent completion; other task visibility is never widened.

manage_agent_dag adds register/get/list/begin/claim/record/finish/inspect on POST /agent/dag and
AC_agent_dag / MCP ac_agent_dag / CLI agent-task dag / Builder. Register accepts an all-managed graph
and optional max_parallel (1..64), pins its canonical digest and registered host configuration, and
creates pending node records atomically. run_dag and AC_run_dag/MCP ac_run_dag accept optional batch_id;
bound runs reject custom runners and changed graphs/parallelism/hosts. Begin issues one attempt; claim
commits before destination contact. Destination specs carry batch/graph/node tags and derived unique
keys. Record verifies the exact destination request match, task ID, completion clauses and input
retirement independently before confirming a node. Unknown effects or missing replies never reset a
claim. Restart invalidates the old attempt and marks live batches waiting_review. Finish derives batch outcome from durable node phases. get/list omit owner/host credentials;
inspect stays read-only with resume_permitted=false. Original owner and current caller are refreshed.
Legacy unbound DAGs are unchanged. Add pause_batch/review_continuation/approve_continuation/
start_continuation/validate_node on the same surfaces. Review binds all explicit decisions, current
authority, destination identity and the real approving actor to a fresh snapshot. Approval performs no
dispatch; start consumes it once and refreshes evidence. run_dag/AC_run_dag/ac_run_dag add optional
recovery alongside batch_id to drive approval/start. Adopt only independently completed originals or
actual TaskRecovery successors; dispatch only never-claimed pending nodes without accepted requests.
Revalidate adopted dependencies before claims. Local origin renewal may only preserve/narrow the
original scope; remote authority remains destination-owned. Submission witnesses preserve historical
identity, never authority; legacy tasks require live spec matching and are never backfilled on retry.
pause_batch fences new coordinator dispatch, without pausing accepted destination tasks or claiming
input cleanup. run_background takes batch_id/definition/max_parallel and optional approval_id/
timeout_seconds. An explicitly started service consumes initial begin or the reviewed continuation
approval, persists a WorkQueue delivery and coordinates independently of the client/view. Queue failure
fences the attempt. Four workers and 64 pending deliveries bound service work. get/list add background
state without authority, attempt capabilities or credentials. Local destination calls bind the owning
runtime and retain original task ownership; the actual submitting actor is also refreshed on dispatch
and polling. Remote hosts retain their own authority. Shutdown and stop_all fence visible coordinators;
accepted destination work keeps its separate retirement contract. Restart fails old queued/running
deliveries without reclaim/replay. See the managed DAG guide.

Existing prune_agent_tasks(keep_days=30), AC/MCP/REST/CLI/Builder/GUI prune and hourly maintenance now
also collect expired unused registered batches and settled succeeded batches. Replies retain deleted /
keep_days and add deleted_batches / deleted_dag_deliveries. Each sweep bounds batch and orphan-delivery
collection at 1,000; task collection keeps its existing 1,000 bound. Scope remains owner/admin-visible.
Batch deletion rechecks state/age under the same lock as begin/claim/continuation/admission and one
database transaction. Nonterminal related tasks, in-flight dispatch, durable input ownership, uncertain
actions, nonfinal phases and pending/in-progress/fresh deliveries prevent collection. Retained batches
protect tagged tasks, precise admissions, receipt/adoption sources and their recovery descendants;
waiting_review/running/approved batches do not expire automatically. Cascades remove only settled
local batch metadata; task artifacts retain their separate recognition/ownership checks. Only host
management removes expired terminal orphan agent_dag deliveries; other queue namespaces stay untouched.
Remote destinations do not receive a retention lease: cross-host evidence handoff remains in Progress.md.
Task pause/cancel uses an atomic nonterminal stop request and conditional settlement, preserving
concurrently committed terminal results instead of failing service shutdown or overwriting completion.

Trigger review_authorization takes trigger_id. Explicit create_authorized additionally requires
snapshot/authorization_review/spec/nonempty note. Preserve template goal/actions/settings/criteria and
kind/config/max_pending, allowing only reviewed origin replacement and equal/narrower roots. Creation
atomically enables one future-event registration, disables/retires its source and stores bounded actor/
context/root proof. Repeated matching approval returns the same binding, including a removed-child
tombstone; a retired source cannot be reenabled. Ordinary enable now revalidates original live scope.
Lineage event history retains accepted keys/payload hashes/original task IDs and counts outstanding
tasks across generations. Inherited duplicates never redispatch queued old work; duplicates accepted
by the current binding retain normal queued dispatch. Schedule backlogs do not replay, file checkpoints
persist, and a new event's task/local receipt/lineage receipt commit together. Removing ancestors keeps
deduplication; explicit removal of the entire lineage clears its proof/history. Shared API/AC/MCP/REST/
CLI/Builder and separate GUI trigger review/creation use the same contract; no native cleanup is implied.

Managed skills now expose review_authorization/create_authorized. Review takes candidate_id; explicit
creation takes candidate_id/snapshot/authorization_review/spec/note. Only the current published version
can be renewed; retain actions, goal, parameter schema, scope/settings and criteria, except unavailable
origin references and equal/narrower roots inside the original/current/live-source intersection.
Create saves an audited draft in the same lineage, without executing, validating or publishing it.
Fresh exact-candidate validation and explicit compare-and-set publication remain mandatory. Atomic
deduplication handles concurrent callers/lost replies/restart; publication/context changes invalidate
review. All shared skill surfaces and the GUI Skills operation selector expose both explicit operations.
Neither old versions nor their in-flight pins mutate. Trigger renewal uses the separate protocol above.

Recovery also supports explicit `review_authorization` and `create_authorized`. Review requires
`task_id`; creation adds `authorization_review` to the usual snapshot/spec/note request. Only this
explicit path may replace unavailable old origin references and narrow roots. Live old restrictions
remain, current policies intersect the original root ceiling, and all other permissions/settings and
completion criteria stay fixed. An invalid current policy fails closed. Context changes require review
again. Task/link/actor/context/approved-root evidence commit together; the audit outlives child pruning
until source retention. Quarantine and old witness files remain unchanged. All four operations use
owner/operator drive_input; only create/create_authorized dispatch work. CLI, Builder and separate
GUI authorization Actions share the existing API/AC/MCP/REST route. Skills and triggers use the separate protocols above;
application-state restoration remains open. See the Sphinx recovery guide for the full protocol.

`manage_agent_recovery(operation, request)` adds owner/operator-scoped `preview` and `create` for stopped
skill, external-agent and local-model tasks. Finite preview reports remaining semantic actions, row outcomes and a digest of the exact source
task, receipts and reviews. It never observes a target or starts work. Create requires explicit snapshot,
spec and review note; a changed source, unsettled input lease or unreconciled effect prevents creation.
Only goal/actions may change: target, tools, roots, apps, inputs, budget, options and completion conditions
remain fixed; private skill publication pins are removed. Historical captures/indexes/coordinates cannot
be reused. Operators may insert fresh semantic preparation/read-back within the existing scope.
Task creation and its unique source link commit atomically. A repeat returns the same child; different
approval conflicts. A retired child leaves a tombstone until source retention, preventing resurrection.
The source keeps its receipts, reviews, rows and status. Child metadata/list results expose provenance;
new completion never completes the parent, and the delegated source cannot resume. Retention preserves source evidence while a child remains.
Explicit create uses normal durable background dispatch; closing the view does not cancel the child.
External/local-model preview never infers a remaining action array or completed-step count. It returns
`source_mode`, `new_plan_required` and a `review_template` with empty goal/actions; `draft` stays null.
Operators must explicitly supply a nonempty goal and note. They may retain the original goal wording
after review; this never inherits source progress. Dormant action arrays and changes to execution
mode or model/endpoint are rejected. Source scope and
completion checks stay fixed. External successors wait for explicit observe/act; local-model successors
use normal background dispatch, a new backend and fresh child-only model history. Preview makes no
model request. A test-owned loopback model confirms the pinned show/chat requests without downloading
or starting a real model. Actual installed-model/native acceptance remains separate.
Surfaces: `AC_agent_task_recovery`, MCP `ac_agent_task_recovery`, `POST /agent/recovery`, CLI
`agent-task recovery preview|create request.json`, Builder and the Agent tasks Recovery page/Actions.
Both operations require drive_input, including direct runtime use; this does not restore login/window
state automatically or replace independently verified native acceptance.

Browser host profiles can select a reviewed installed Python environment through optional
`settings.helper_python` (an absolute local interpreter path). Explicit helpers run with `-I`, using
installed packages rather than the caller's `PYTHONPATH` or working directory. Virtualenv executable
symlinks retain their environment identity. Task options cannot select the interpreter.
Host managers can call `manage_agent_target("probe", {"name":"reviewed-browser"})` or use
`AC_agent_target`, MCP/REST, `agent-task target probe request.json` and the GUI Host targets operation.
The probe uses a separate bounded owned helper, imports browser dependencies through `je_web_runner`,
then retires it without acquiring input ownership or starting a browser. Its result can say
`python_dependencies_ready`; `browser_launch=not_probed` and `native_evidence=not_recorded` stay explicit.
`last_probe` is an in-memory timestamped diagnostic snapshot; passive readiness and task permissions
are unchanged by probing. Disabled targets stay disabled. Desktop/device native probes remain open.
The prepared isolated environment installs wheels from both feature worktrees. Shared environments
and production checkouts remain untouched; production service configuration and real-browser acceptance
remain separate work. Browser automation still belongs entirely to WebRunner (`je_web_runner`).

Desktop finite skills now use the same context-continuity fence as browser skills. Retiring a
desktop scope or its owned helper requires review before an old prefix can continue; paused form/window
state is not established by historical receipts. Live uninterrupted contexts continue normally. File
adapters retain their persistent-artifact recovery. Target checks run before helper replacement, and
existing resume/status/receipt interfaces expose the human-review result. Draft/authentication/window
state restoration remains open; reviewed successor creation is available above. Native acceptance stays paused.

A finite browser skill's verified prefix now requires its original live browser/helper context.
After pause, cleanup, helper loss or runtime restart, retained action history cannot prove that the
form still contains its previous values. Continuation enters human review before launching a replacement
helper or sending the next action. Review the remaining steps and create a new task explicitly.
Pausing before any retained attempt and attempts reviewed as failed/not-applied permit a fresh start.
External owners can reobserve a new context and plan fresh scoped actions; ordinary uninterrupted skills
continue on their existing session. Restoring authenticated/draft browser state remains open work.

Local runtime principal and live-root forwarding now requires an explicit local-service call.
Generic authenticated HTTP requests carry the supplied bearer token; local user/store/witness metadata
is attached only by the runtime client after validating the loopback service destination and route.
The versioned `je_auto_control.api` namespace exposes every advertised `api.core` name, including
managed browser commands, target recovery and skills. Executor typing stubs include all shipped commands;
unresolved postponed project types use the generator's existing `Any` fallback instead of invalid names.
Concurrent budget readers sample clocks inside the exclusive database transaction, preventing false
task timeouts when readers acquire locks in a different order. Actual clock rollback remains fail-closed.
GUI/MCP/REST/CLI share these repaired client and API contracts. Production checkouts and existing
native/browser/device/24-hour acceptance pauses remain unchanged.

Managed browser file commands `browser_link`, `browser_download` and `browser_upload` (with matching
`AC_browser_*` commands) delegate to WebRunner transfer contract version 1. Download and upload grants
require explicit host/task roots. Downloads preserve scoped browser cookies inside the owned SDK/helper,
check complete length and optional SHA256, and publish without overwriting an existing file; reuse
requires its matching SHA256. Uploads read one regular file up to 4 MiB into a checked immutable snapshot,
verify optional SHA256 and SDK metadata, and never submit a form. Network operations remain in `je_web_runner`.
The browser `download_archive` preview accepts a query `url`, explicit `allowed_origins`, rooted `directory`
and `files` with a plain `name` and either `url` or link `selector`/optional `frame`; `page_url` can override
the query page per file. It captures fresh links, downloads at most 16 MiB per file and writes a manifest
whose names/sizes/hashes are independently verified. GUI Actions draft file target/workflow/upload examples
without starting resources. MCP/REST/CLI/Builder/model tools share these commands; link reads still require
drive-input authority. Deployment and real-browser acceptance remain open; existing acceptance pauses hold.

Browser tasks accept pinned completion clauses such as
`{"kind":"browser","operation":"value","selector":"#field","value":"expected"}`.
Operations are exact `text`, `value`, `visible` (boolean), or `url` (no locator). They require an explicit
`AC_browser_read` grant and task origins; completion cannot add permissions. At finish, the same owned
helper checks a current allowed HTTP(S) page and independently reads the full SDK value through guarded
read commands. Receipts, bounded previews and model stop messages do not substitute for those reads.
Blank/unavailable/out-of-scope pages, refused readbacks and invalid verifier replies remain unknown;
failed comparisons remain failed. Cancellation, authority revocation and human-review errors propagate.
GUI Actions can draft an inert browser completion example; API/MCP/REST/CLI finish share the verifier.
SPA URL fragments remain intact while origin checks exclude only the fragment. Browser/native
application acceptance and reviewed transfers remain open.

Managed browser startup now requires the exact WebRunner `ManagedBrowserSession.contract_version == 1`
contract before constructing its policy or opening a proxy/browser. Missing, boolean, string, older or
unknown markers fail with an actionable readiness reason. SDK source `575e5d2` provides complete text/value
readback: at most 8,000 UTF-16 code units, with over-limit/invalid Unicode refusal instead of truncation.
AutoControl applies matching Unicode bounds to browser arguments and workflow preview data before effects.
The consumer/SDK source contract is tested through the real owned helper with fake Chromium; deployment
and real-browser/native acceptance remain separate from that evidence.


`draft_agent_workflow("batch_form", config)` and `transfer` accept `backend: browser` with
explicit `allowed_origins` and a reviewed browser target. CSV/XLSX sources stay rooted; browser drafts
emit only `AC_browser_*` actions and never fall back to desktop input. Forms take `url`, CSS `fields`,
optional frame selectors/new-record control, and submit plus confirmation selectors. Each fill has an
independent exact value readback. Optional `confirmation_column` supplies a per-row expected marker.
Transfers take `source_url`/`destination_url`, capture text/value fields, apply an allowlisted transform,
fill and read back destination fields, then verify saving. A stale confirmation is refused before submit.
`AC_browser_wait` / `browser_wait` polls text/value reads only, including a newly visible element;
`wait_seconds` defaults to 5, is capped by the action budget, and late matching replies are refused.
It never repeats a fill or click. Python/core, catalog/model schemas, MCP, CLI/REST task operations,
Builder and GUI workflow preview use the shared compiler. Browser readback can serve as independent
skill evidence. Actual application acceptance and production upload/download configuration remain open.
Managed browser startup requires WebRunner contract version 1 with complete bounded readback.

Managed browser profiles (`kind: browser`) now delegate to the owned `je_web_runner` SDK from
WebRunner (`D:\Codes\WebRunner`; integration source on its isolated managed-session branch).
Profiles require exact `settings.allowed_origins`, browser-only tools and no desktop apps; every task
also declares a narrower nonempty `options.allowed_origins`. Profile/task grants are checked again on
activation. Registration stays inert. Install the reviewed managed-session SDK and its Chromium runtime
in the helper environment explicitly; absent dependencies fail readiness and nothing is installed automatically.
`AC_browser_navigate`, `AC_browser_click`, `AC_browser_fill`, `AC_browser_select`, `AC_browser_check`
and `AC_browser_read` share Python/core, executor, MCP and Builder schemas. They operate inside the
managed helper; drive them through the existing task submit/observe/act lifecycle, not an ambient browser.
The read operation is `text`, `value` or `visible`; secret form controls are refused by WebRunner.
Observation-local DOM indexes resolve selectors and frames after the runtime's freshness check.
Failed effects remain uncertain and require reconciliation; pause/cancel retire owned resources.
GUI Actions can draft a browser target example for review, and DOM selection only edits the action request.
The dedicated helper preserves one fresh session across readiness checks. Ordinary cleanup acknowledges
browser cleanup and reaps its owned process tree; eligible completion sources instead transfer their
actual frozen context to the bounded runtime collection. Browser tasks acquire no desktop input ownership.
Controlled cross-source tests use the real SDK with fake Chromium and owned IPC/loopback. Browser/native
acceptance, production transfer configuration and additional browser workflow kinds remain tracked in `Progress.md`.

MCP asynchronous calls preserve the accepting caller's role, session, exact root policy and
disclosure view; retired sessions and path policies reject late dispatch. Stateless async calls keep
their fixed profile. HTTP tool-list changes reach all live session streams for plugin updates, while
session enable/disable targets one owner and avoids duplicate delivery. Stream registration and HTTP
headers share one lock so an early notification cannot precede the response headers.
The metadata-only `benchmarks/mcp_discovery.py --repeats 20` benchmark records count, JSON bytes,
warm in-process handshake, search and enable latency. The captured Windows/Python 3.14.4 run has
732 permitted tools / 358,029 initial response bytes in full mode and 5 / 2,029 in progressive mode
(99.43% fewer response bytes). Handshake is 58.263 / 47.439 ms; search median is 16.243 / 19.718 ms.
Progressive enable median is 42.486 ms. These local timings exclude cold imports and native work.
See the dated JSON report under `docs/benchmarks/`; argument-policy coverage limits remain in `Progress.md`.

Retired PathPolicy.validate calls now raise PathNotAllowedError. Public signatures and tool names remain unchanged.

MCP supports opt-in session disclosure: `je_auto_control_mcp --tool-mode progressive` starts
with five discovery controls; `ac_mcp_tools_enable` / `ac_mcp_tools_disable` change only that session.
`--tool-mode static --tool-profile ac_screen_size,ac_list_windows` supplies a fixed profile for clients
that do not refresh tool lists. The default `full` mode retains its unpaginated permitted list.
Progressive/static pages use opaque, single-use cursors bound to a snapshot and caller; changed tools,
roles, view configuration or expired cursors require restarting `tools/list`. Enable/disable notify
the owning connection. Session closure retires outstanding metadata callbacks and clears cursors.
Use `MCPServer.configure_tool_disclosure(...)` for HTTP/embedded servers, or host environment
`JE_AUTOCONTROL_MCP_DISCLOSURE` and comma-separated `JE_AUTOCONTROL_MCP_TOOL_PROFILE`.
`plan_mcp_tool_profile(...)` and Diagnostics Actions preview startup arguments without starting a server.
Stateless requests use a fixed, unpaginated initial profile; they do not retain session enablement.
Read-only ceilings cover later plugin registrations. Unauthenticated/shared-token peers see operator
tools, matching their existing invocation ceiling; host-management tools require authenticated authority.

ToolView/ToolPage and plan_mcp_tool_profile are additive experimental APIs. The legacy server.start_mcp_stdio_server import remains an alias to the lazy stdio entry point.

MCP tool discovery is available through `search_mcp_tools(query, limit=10)` and
`get_mcp_tool_schema(name)`, corresponding AC/MCP commands, and Diagnostics → Actions.
Search returns bounded summaries with category and required capability; full schemas require a
single-tool lookup. Both queries refresh role authority and respect the registry's read-only filter.
MCP queries use that server's live registry, including plugin changes. CLI inspection:
`je_auto_control_mcp --search-tools document --limit 5` or `--tool-schema ac_mcp_tool_search`.
Full mode remains the default; opt-in session disclosure is described alongside this metadata API.

The additive metadata API is experimental and Qt-free. Discovery never executes a tool or widens roots, environment references or role grants.

The experimental managed-task API adds AgentTaskSpec/Budget/Handle/Result, AgentObservation,
AgentActionRequest/Result, AgentRuntime, AgentTaskError/ControlBusy, submit/get/list/observe/act/
finish/pause/resume/cancel_agent_task and explicit start/stop/status service functions. Import has no
service/native side effects. The shared AC/MCP/Builder catalogue preserves existing command names.
The default desktop adapter now isolates native calls in an owned helper, enforces action deadlines
and retains a host input ledger for cleanup before transfer. Cancelled clients request host pause.
See AGENT_TASKS.md for contracts, completion certainty, ownership and remaining native limitations.
WorkQueue.defer(item_id, claim=...) is additive; it returns a currently owned delivery to new without
consuming an application retry and refuses stale claims.

`Executor.execute_one(name, arguments=None)` is additive and returns the raw command result.
`run_tool_call` now uses it: configured identities must possess the command capability,
private top-level arguments are refused, runtime variables interpolate, cancellation propagates,
and an enclosing action journal captures the call. Calls without an RBAC scope retain local trust.
Nested dispatch intersects context-local command guards after argument interpolation.

Selected dev pushes run `.github/workflows/ei-lifecycle.yml` in an isolated
libei/libeis container, retaining versions and both native logs for 14 days in
`ei-lifecycle-<run>-<attempt>` artifacts. Half-open and live cleanup children
have 10/60-second deadlines and faulthandler. Unrelated child failures fail CI;
successful cleanup requires begin/end markers. The half-open probe also requires
equal integer descriptor counts; live cleanup releases owned device refs first.
Run 39507190704 on libei/libeis 1.3.901-1 passes 9/9 and 20/20 checks, including
native out-of-region refusal without CLI fallback. Half-open `ei_unref` still
segfaults, so runtime protection remains and helper isolation is pending.
Device pause and sequence readback remain unverified. These controlled socket
peers do not establish compositor consent, physical or multi-monitor acceptance.

A native Wayland pointer coordinate outside every granted EIS region, after
raw-coordinate and layout-origin mapping, raises `LibeiUnavailable` with
`state="failed"` and disables automatic CLI fallback. A rejected move emits
no motion/frame or subsequent click. Valid coordinates, devices without
regions, later valid requests on the same sender and explicit CLI selection
retain their existing behavior.

This correction adds no public names or signatures and retains the existing
exception family. It does not revoke an otherwise valid sender or its grant.

The additive public capability API is BackendContext, CapabilityStatus,
CapabilitySnapshot and probe_capabilities(context), exported from the root
and versioned je_auto_control.api/core namespaces. Contexts are detached and
immutable; statuses contain name/state/backend/reason/recovery/desktop_wide.
Snapshots serialize platform/display_server/passive/input/capture. Eight
states distinguish unverified prerequisites from available last-local native
observations, permission/dependency gaps, unsupported, paused, revoked and
failed states. Cached libei availability requires a completed handshake plus
active keyboard/absolute-pointer/button/scroll families; partial grants remain
unverified, paused families report paused, and missing required devices revoke
that readiness claim. A result grants no authority, does not poll native events,
and cannot prove external freshness or full monitor coverage. The input
item covers key/pointer events, separately from wtype text.

AC_probe_capabilities and read-only ac_probe_capabilities share a no-argument
adapter and reject caller-supplied context/authority metadata. Their Builder
and Diagnostics surfaces use the same contract; viewer queries need
read_screen. Rendering/language changes do not probe. Existing active
diagnostics and input/capture operations retain their signatures, authority
checks and failure families. Native restore/restart/context integration
and native session retry/cancel/stop controls remain open in Progress.md.

The GUI task infrastructure provides `gui.task_controller.TaskController`:
`submit(work, owner=widget)` returns a caller-owned `TaskHandle` with
typed `TaskOutcome` and `TaskProgress` observations. Work receives a
Qt-free `CancellationToken` with checkpoints, bounded interruptible waits
and progress reporting. Submission captures context; dispatch refreshes
store-backed identity. Work must receive plain data, avoid widget references
and authorize its own operation. Existing
`DeferredAuthorization.scope()` still requires input privilege, while
`context_scope()` only refreshes/binds identity for independently authorized work.

Owner/handle/controller destruction requests cooperative stop and drops
late delivery. Each task has a separate ID/token; callbacks run on the GUI
thread. Cancellation does not forcibly interrupt an uncooperative call
or relabel a successful committed return. Errors/progress use the captured
secret scope; terminal errors retain no exception traceback. Failed thread
starts roll back both registries and preserve the original failure.
Diagnostics now adopts this controller. Remaining panel/backend migrations
and native session operations stay in `Progress.md`.

Active **Diagnostics → Actions → Run diagnostics** uses the shared task
controller off the GUI thread. **Stop diagnostics** requests cooperative stop;
the view distinguishes running, stopping, canceled and failed states in four
languages. Progress counts completed checks. Duplicate runs are ignored, close
abandons late progress/results, and a deliberate retry starts a new owned run.
GUI cancellation is a typed outcome without retained exception tracebacks;
headless core/SDK/CLI and the MCP handler preserve original direct/wrapped controls.
Ordinary probe failures still become report rows and allow remaining checks.

`CancellationToken`, `TaskProgress` and `cancellation_scope` are exported by both
SDK namespaces. Bind `with cancellation_scope(token): report = run_diagnostics()`;
the owning caller can call `token.cancel()` from another thread. The existing
no-argument diagnostics signature remains. Scope binding grants no authority;
`cancellation_scope(None)` only suspends cancellation for bounded owned cleanup.
`AC_diagnose` and the new read-only `ac_diagnose` share the report. The MCP tool
accepts no arguments, uses request cancellation/progress and requires
`read_screen`, as does the explicit GUI action. Caller-supplied tokens or
authority metadata are rejected. These are active checks: capture may request
consent. `ac_probe_capabilities` remains the separate passive alternative.

Scoped Wayland D-Bus connect/read/partial-write waits poll at intervals capped
at 0.1s within the original total deadline. Cancellation attempts Request.Close
on the originating bus with its separate 0.25s budget, then releases that
connection; a canceled returned image is discarded. Scoped CLI captures stop
and reap their newly owned helper/process group with bounded cleanup, preserving
the original control even if pipe close fails; reaped numeric PIDs are never
signaled. liboeffis acquisition observes scoped stop and releases its own context.
Uncooperative/native calls are not forcibly preempted; the GUI remains responsive
while cleanup completes. Restore/restart, native session controls, capture-owner
metadata and remaining panel/backend migrations stay in `Progress.md`.

`python -m examples.cancellable_diagnostics` runs a controlled cancellation demo
without providers. `--active --cancel-after 2` explicitly runs diagnostics and
requests stop after two seconds; native/device/API acceptance remains separate.

Diagnostics construction and retranslation are passive UI operations. Its
Actions command submits run_diagnostics to an owned worker; Stop requests cleanup.
Headless/AC signatures remain unchanged; active ac_diagnose is additive. The passive capability
surface below is additive and separate from active checks.

Screenshot portal signatures and the ordinary AutoControlScreenException family
remain compatible. Abandoned requests attempt Request.Close on their originating
bus with a separate 0.25-second I/O budget; completed Response interactions are
already over. Original controls survive D-Bus wrappers and cleanup. SessionBus
retains its signatures while bounding writes and the remaining reply wait and
closing partial connect/authentication/Hello state before failed __enter__ exits.
No facade, AC, MCP, Builder or wire surface is added. Live portal cancellation,
restore and compositor-restart acceptance remain open in Progress.md.

Wayland native input preserves the existing exception families and signatures.
LibeiUnavailable/OeffisUnavailable carry internal inert state distinguishing
optional absence from permission, pause, revocation and protocol failures.
Auto mode only falls back for optional absence/unclassified legacy adapters;
explicit libei selection and classified refusals propagate. Cached refusals
require explicit reset before a fresh permission request; native chord cleanup
uses its original backend and preserves cancellation. This safety behavior
adds no facade, AC or MCP command. Public capability probes and independent
input/capture diagnosis remain open in Progress.md.

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

Journal-candidate APIs (`generate_candidate_from_log`, `CandidateScript`,
`CandidateGenerationError`, `write_candidate_archive`) are experimental. The
`AC_generate_candidate_from_log` / `ac_generate_candidate_from_log` adapters return
code, proposed actions, schema-v1 provenance and explicit exclusions; optional
output exports a single review ZIP. All candidates remain observed-path-only.
Static command/signature/AST and non-dispatching dry-run checks leave dynamic
inputs and native outcomes unverified. Review content is sealed against later
mutation. Source/current roots and cancellation apply throughout. CLI --from-log
requires an explicit run ID and defaults to actions style/JSON output; legacy
file codegen retains its calls-style/source-output behavior. No replay is implicit.

Persistent configuration (`ConfigStore`, its errors, and the top-level
`ConfigBucket`/`ConfigSyncClient` convenience exports) remains experimental.
Version-two commits and the schema-v1 SQLite store provide CAS and durable retry
receipts, with bounded finite JSON. `AC_config_store_get`/`AC_config_store_commit`
and matching MCP/Builder surfaces are private DRIVE operations. Legacy blind
writes require explicit compatibility on both sides; default clients never
silently downgrade. These names do not join the versioned stable API.

Causal primitives (`SyncEntry`, `SyncConflict`, `MergeDecision`, `merge_entries`,
`SyncPeer`, `SyncPeers`, `FullResyncRequired`, `SyncOperation`, `SyncRetryPolicy`,
`SyncDrainResult`, `SyncLocalIdentity`, `SyncOutbox`) are experimental. Entry,
peer and queue wire schemas start at version one. Pure supplied-data operations
are observable; private outbox commands require DRIVE and path confinement.
CausalBucket, CausalConfigStore, SyncActor, CausalConflict and DeletionFence are
also experimental. Account snapshot/fence wire schemas are version one; dedicated
HTTP /causal envelopes are version three. Actor metadata is transient _actor data
inside submitted buckets. Server transactions validate membership, acknowledgements,
retirement/full-sync epochs and deletion collection. Existing store AC/MCP/Builder
commands also accept causal snapshots. Upgraded accounts refuse plain reads/writes;
historical identical receipts still return their original revision. Durable peer control
and atomic local full-resync adoption are also experimental. CausalSyncClient and
CausalReceipt are experimental: explicit fetch/push and bounded outbox HTTP
delivery use v3, retain uncertain prepared requests and atomically confirm complete
snapshots. The plain ConfigSyncClient API and v2 response shapes remain compatible.
Causal 409 details carry typed stale_revision/operation_id_conflict/full_resync_required
reasons; only the first permits rebase. New private HTTP commands use live
options.secret_env credentials and current path/egress authority.

MCP OperationCancelledError and run-history interruption classifiers keep their
existing import aliases and carrier identity through the dependency-free shared
control-signals module. Cancellation retains its deliberate RuntimeError-only
ancestry and remains outside ordinary framework-error containment.

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

SyncControlRequest, SyncControlOperation and SyncControlResult are experimental.
CausalSyncClient.control and AC_sync_peer_control/ac_sync_peer_control persist manual
register/ack/collect/retire/full_resync intents. Stable explicit operation IDs replay
compact historical receipts without new effects. Full resync requires explicit pending
retirement consent and adopts identity/cache/retirement atomically after confirmation.
Owned outbox SQLite schemas 1/2 migrate to 3 without changing existing edit wire version 1;
control wire is version 1. Status remains private, local-only and credential-free.
Source coordination is described below; referenced assets are described below; Sync UI and native working-copy loading are described below.

AssetFile, AssetManifest, AssetSyncResult, AssetTransport, DirectoryAssetTransport,
build_asset_manifest and sync_assets are experimental. Asset manifest wire is version 1.
Private AC/MCP/Builder manifest/stage commands publish a complete verified local cache
generation, never an active workspace replacement. Explicit files retain their bytes;
referenced-asset workspace integration is described below. Current roots/cancellation
are rechecked. Corrupt caches fail without overwrite; identical verified caches are reused.

SyncReference, SyncBindings, ApplyReport, SyncAdapter, SyncAdapterState,
ScriptSyncAdapter, LocatorSyncAdapter, HotkeySyncAdapter, TriggerSyncAdapter,
AddressBookSyncAdapter, SettingsSyncAdapter, adapter_from_profile and
materialize_sync_profile are experimental. Private adapter descriptor schema is 1;
owned ledger schema is 2 (migrated from 1). Four private AC/MCP/Builder
snapshot/apply/resolve/materialize commands
require DRIVE. Apply persists a causal inbox; it never replaces live definitions.
Materialization publishes an inert complete generation with native hotkey/trigger flags
disabled. Secret references remain vault placeholders without vault lookup; native
machine fields accept local references; native script/image file fields also accept typed assets. Workspace
preferences require literal values. The separate workspace adapter bridges saved native
GUI preferences; live GUI application remains explicit. Full-resync adapter baselines
and referenced assets are coordinated below; Sync UI and native working-copy loading are described below.

Native sync definition numeric bounds are checked before floating-point finite
conversion. Out-of-range arbitrary-precision JSON integers raise ConfigSyncError
before profile I/O, preserving the documented framework exception boundary.

Private local absolute paths may contain high-entropy directory names. The adapter
exempts only this heuristic for those paths; recognized credential patterns, sensitive
binding names and active resolved-secret masks still refuse plaintext credentials.
Portable entries and the shared secret scanner keep their existing policies.

WorkspaceSettingsSyncAdapter is experimental and adds the workspace kind to private
schema-1 descriptors and versioned profiles; materialization now accepts 1-7 distinct
kinds. Its four portable preference fields use exact incoming types/bounds. Source INI
fallbacks match the GUI. No QSettings or other Qt module is imported by headless capture.
workspace.ini is inert generated data; explicit GUI use first creates a separate mutable
working file. No existing active workspace is overwritten or reloaded on receipt.

SyncWorkspace, SyncWorkspaceError and WorkspaceSyncResult are experimental. The private
workspace descriptor is schema 1. AC_sync_workspace/ac_sync_workspace/Builder Data share
local capture/status/review/resolve/preferences/materialize and explicit network sync/peer controls.
All server modes require DRIVE. A short workspace lease, atomic reset intent/source
fingerprints and idempotent adapter-generation adoption preserve uncertain retries and
prevent retired source replay. Missing legacy reset baselines require a new coordinated
full reset. Source/state/outbox path roles cannot overlap; existing kind/state bindings
remain stable. Credentials refresh per RPC and received data never activates a source.

SyncAssetBlob, SyncAssetReference, SyncAssetStore and SyncAssetHTTPClient are experimental.
Reserved asset marker/descriptor and chunk HTTP protocols are version 1; the separate
owned asset SQLite schema is 1. Private bindings.assets and optional asset_cache_path
are additive schema-1 descriptor fields. Non-asset adapter binding/reset hashes stay
compatible. Source files freeze to content-addressed chunks before causal capture; new
requests upload assets before prepare, while uncertain prepared definitions retry first.
Received metadata and assets publish as one inert generation. Native paths are relative
to its root. Existing AC/MCP/Builder fields preserve DRIVE/current roots/cancellation.
Signaling adds optional create_app asset_store_path and --asset-store, with the same
authentication/pre-body size guard. Server/client stores have explicit byte/object/user
quotas; immutable content has no automatic garbage collection. Older asset-unaware
participants require upgrade before processing new typed references.

The experimental preferences operation requires an explicit bounded observed change-ID list
(empty is a valid reviewed empty profile). It compares the exact current workspace heads,
refuses concurrent alternatives and returns four canonical values using safe defaults for
missing/deleted keys. No source/network/credential reads or Qt imports are added. The lazy
Workspace Sync GUI exposes explicit reviewed application on its main window, separate from
receipt/publication. Captured authority refreshes during work and before queued delivery;
cancellation prevents late preference application while completed durable writes remain committed.

TCP AUTH_FAIL is terminal for client admission: a rejected handler is marked stopped before
the reply is sent, allowing an immediate replacement connection while cleanup finishes.
Wire payloads, max_clients for active/pending clients and the independent pending-handshake
budget remain unchanged. No public names or command schemas change.

load_sync_profile and LoadedSyncProfile are experimental. The published files directory
requires an exact lowercase SHA-256 expected_digest and a separate working-copy container.
Each successful load returns a fresh mutable directory with a schema-1 .sync-profile.json
source-manifest receipt; source cache and existing native/global runtime ownership stay separate.
Native canonical formats and sealed heads must agree; all hotkeys/trigger nodes load disabled.
Only explicit asset markers and native hotkey/trigger paths are rebound; secret placeholders
and literal script strings keep their meaning. Repository/book handles access working files;
script_actions/settings/preferences/definitions describe the loaded snapshot.
The private AC_sync_profile_load/ac_sync_profile_load/Builder Data command shares current
roots/cancellation and requires DRIVE. The GUI exposes load, selected-kind inspection,
explicit script-snapshot import and preference-snapshot application. Later GUI actions check
both the current caller and the captured load owner; completed copies survive late cancellation.

Builder renders imported command names and positional values as literal text, preserving
HTML-like data without rich-text interpretation. Script data remains data until explicit Run.

FolderSyncEngine retains its existing import path and start/stop/is_running/wait_until_ready
surface. Content SHA-256 values replace increasing mtime as the change criterion. Only the
first successful baseline ignores existing files; subsequent runs retain failed/offline edits.
stop signals cancellation, skips self-join and retains a blocked worker until it really ends;
start is a no-op while that worker lives, and readiness clears on stop/exit.
record_received(path) explicitly marks a complete regular file inside the selected watch as
received, returning False for missing/outside/excluded/changing paths. Callers publish first;
receipt updates win over older send/scan completions. This does not change any wire schema.
Native receive receipts and explicit GUI reconnect/resume are integrated below.

FileTransferSender.send, WebRTCDesktopViewer.send_file and WebRTCDesktopHost.push_file
accept an optional keyword-only cancelled predicate. Writes now synchronously confirm
the original bridge callback, cap buffered data at 1 MiB and fail after a bounded wait.
Callback errors reach FileTransferError; cancellation/hard signals keep their original
identity. Chunk sizes must be integers from 1 byte through 1 MiB (bool is refused), and
source truncation/growth relative to the announced size aborts the transfer. Default manual-mode success means
the channel accepted every frame, not that the peer committed the file. Legacy manual wire remains available; confirmed native mode is described below.
Concurrent producers on one channel fail explicitly; a pending abort retains ownership.
FolderSyncEngine accepts an optional cancelled predicate and provides nonjoining
request_stop plus stop_requested. GUI folder jobs capture authority and peer identity;
loss of ownership stops scans and queued writes. Viewer connection_identity is opaque.
Native inbox pulls use a per-channel queue of at most 32 jobs on the original loop,
perform blocking sends in a worker and cancel owned jobs on host shutdown. Failure replies
remain bound to their original control channel. Explicit GUI reconnect/resume and clipboard lifecycle coverage are described below.

FileTransferReceiver.close is idempotent and terminal: it refuses subsequent frames and
discards unfinished bytes while preserving any earlier published target. abort discards
only the active partial transfer, allowing a later allowed transfer on the same channel.
Writes, publication and cleanup share a lock; callbacks run outside it. Cleanup attempts
both close and unlink, logs ordinary filesystem failures and preserves original interruption
objects. Native host/viewer receives bind to a fresh receiver and their concrete authenticated
peer/channel. Stop, files/control close, terminal connection state and file permission loss
clean partial bytes without waiting for another frame. Stale channels and state callbacks
cannot retire a replacement transfer. Terminal cleanup precedes state callbacks, including
callbacks that reconnect immediately. File/audit/state callback interruption carriers propagate
unchanged; ordinary native callback failures retain their existing logging/containment behavior.
The Remote Desktop GUI uses the same endpoints. No wire, facade, command or MCP schema changes.
Explicit GUI reconnect/resume and clipboard lifecycle coverage are described below.

FileReceiveReceipt (utils.remote_desktop.file_receipts) is frozen local metadata with an
absolute path, lowercase SHA-256 and nonnegative byte size; malformed metadata raises the
flat-family FileReceiptError. FileTransferReceiver.handle_message accepts keyword-only
on_receipt, emitting once after complete atomic publication and before the legacy path callback.
The digest is built from successfully written chunks, without rereading a changing target;
short writes, aborts and publication failures emit no receipt. Host/viewer
set_file_receipt_callback accepts a listener or None, retaining existing path/audit callbacks
and original interruption objects. Relative inbox/watch paths bind at construction; path
notifications now use absolute paths for relative inbox configurations.
FolderSyncEngine.record_receipt registers original received bytes and returns False for
unselected/missing targets or detached/revoked owners. It does not hash the target, so delayed
processing cannot consume a later local edit. Legacy record_received(path) still explicitly
hashes current content. Receipt state wins older scans/sender completions; owner checks precede
filesystem access and repeat before state mutation with consistent lifecycle/content lock order.
The GUI folder toggle binds receipts to its captured viewer and engine; live role/auth/peer
checks retain the original authority. Local receipt metadata does not acknowledge remote
publication or verify a sender-provided checksum in legacy mode. GUI explicit reconnect/resume is described below; explicit clipboard lifecycle coverage is described below.

Publication-confirmed native sends use keyword-only require_commit=True on the existing
FileTransferSender.send, WebRTCDesktopViewer.send_file and WebRTCDesktopHost.push_file.
The default remains False for legacy manual callers; the GUI folder sender always opts in.
Confirmed mode requires a native file listener on the original authenticated channel/loop
and runs outside the bridge thread. A fresh version-2 nonce probe precedes each file's source
metadata/content reads, including after permission changes. Source paths bind to their call cwd.
The strict begin includes commit=2 and a transfer ID; strict end includes SHA-256 and a new
unpredictable nonce. The receiver validates ID, integer size, nonce and checksum before atomic
replacement, then sends file_commit with that ID/nonce/digest/size before user callbacks.
Only a matching response completes delivery. Unsupported, timed-out, cancelled, replaced or
revoked operations retain failure; a completed receipt wins cancellation arriving later.
Each queued write keeps its existing bound; capability replies wait at most two seconds and
publication replies five seconds. They are distinct from write/backpressure waits.
Protocol requests are bounded, weakly indexed and retired on channel/session/permission end;
captured generations prevent revoke/regrant from reviving a pending request. Envelope parsing
is bounded to 4 KiB before decoding. FileCommitError stays in the flat framework family and
native sender boundaries expose FileTransferError with original interruption identities.
Legacy manual envelopes and path/receipt listeners remain available. GUI folder delivery now
requires compatible support on both peers. Same-engine uncertain sends retry without advancing
the confirmed digest. Explicit GUI reconnect/resume and clipboard lifecycle coverage are described below.

FolderSyncEngine.checkpoint() exports a frozen FolderSyncCheckpoint only after request_stop/stop
and actual worker retirement; a live blocked sender raises flat-family FolderSyncStateError.
The metadata contains the absolute watch, recursion flag, baseline status and immutable name/digest
pairs. Export and constructor restoration perform no filesystem reads. Invalid/mutable/duplicate
entries and mismatched watch/recursion options fail explicitly. A replacement copies metadata and
receives a fresh sender/cancelled predicate; it never adopts the old transport or authority.
The baseline includes initially ignored files and frozen local receipts, not just delivered files.

GUI folder start/stop now lives in folder_sync_controls.py; the existing panel toggle delegates to it.
One FolderSyncHistory retains a stopped engine across viewer stop/reconnect. The user reconnects
and explicitly presses Start sync. Handoff requires a matching authenticated host fingerprint,
absolute watch path and local principal (including user-store provenance). Missing/changed host
identity, root or principal establishes a fresh baseline. Unknown fingerprints are scoped to one
concrete viewer/connection, never a replacement. Host metadata uses the existing authentication
trust model and adds no cryptographic identity guarantee. Store-backed permission is refreshed
before a new engine can read the watch or send; old callback/worker bindings remain invalid.
A still-running old worker refuses handoff, including a change of peer/root; retry after it exits.
Failed starts leave the retained baseline intact. Explicitly disabling folder sync forgets the
baseline, but still owns a retiring worker. Viewer Stop/reconnect retains it until resume; panel
destruction/application exit clears it. This state is memory-only and never auto-enables sync.

TCP/WebSocket clipboard APIs and legacy text/image JSON envelopes remain compatible. Transfers
are explicit: received values do not automatically forward/broadcast, and identical deliberate
sends are not deduplicated. Viewer send_clipboard_text/image capture the original channel before
encoding, recheck ownership before writing and propagate connection replacement as ConnectionError.
Buffered receive dispatch rejects stopped/replaced channels; decoded clipboard data rechecks the
same channel before invoking callbacks. Host receive checks shutdown/authentication after reads
and again after decoding; input/clipboard/file control routes require PERMISSION_FULL.
Ordinary clipboard callback/provider failures keep their logging/containment behavior. Explicit
wrapped cancellation/hard signals preserve the original object at SDK/native GUI boundaries.

The Qt-free clipboard_delivery module shares lazy native application and captured ClipboardDelivery
metadata. ClipboardReceiver binds the original peer weakly once before it starts,
preventing a callback from keeping its own viewer and Qt panel alive until cyclic GC.
Only actual queued deliveries retain the peer strongly until consumed or discarded.
GUI callbacks carry the concrete viewer and DeferredAuthorization captured at connect;
the queued slot checks its current owned viewer and live connection, refreshes the original user
and rechecks ownership before applying data. Explicit GUI push refreshes before native clipboard
read and again before network send. Ambient callback-thread users never supply authority.
No clipboard OS watcher, automatic forwarder or implicit reconnection replay is introduced.
Existing SDK methods and the GUI Push clipboard button share these contracts without new root,
AC, MCP, Builder or wire fields. Native providers remain lazy; controlled tests replace them.

Workflow additions: draft_agent_workflow compiles inspectable task specs; workflow_download,
workflow_manifest, workflow_control and workflow_open require a managed operation scope.
AC/MCP/Builder share their schemas; REST adds POST /agent/draft and CLI adds agent-task draft.

stop_all_agent_tasks is additive across Python/AC/MCP/REST/CLI/GUI and respects task visibility.
Shared-desktop acquisition now requires a supported physical activity adapter; Windows uses an owned
presence-only hook. Budgets persist monotonic elapsed high-water marks without resetting on resume.

Task results add metadata provenance. get_agent_task_receipts, reconcile_agent_task and prune_agent_tasks
are additive across Python/AC/MCP/REST/CLI/GUI. Committed receipts are immutable; uncertain outcomes
need explicit owner review. Native task images persist only with strict-redaction opt-in and bounds.

submit_agent_task accepts an optional owner-scoped idempotency_key. manage_agent_trigger and
list_agent_triggers add durable preauthorized interval/cron/file/event bindings across all task surfaces.
Private vault guards are installed by managed operation context; unscoped script interpolation is unchanged.

Input ownership writes a private, fsynced per-resource crash witness before native dispatch and input ACK. An unfinished witness blocks new owners across databases. Explicit host-only recovery requires a review note and a trusted no-held-input probe, never replays persisted input or signals persisted PIDs, and does not reconcile/resume the old task. POSIX input helpers monitor their actual parent and retire only their own live session group. Approved document handoff runs outside the input helper tree, so user applications survive normal task cleanup; bounded, preapproved focus steps wait for scoped windows. Observations also expire against a host monotonic clock. Native desktop/device acceptance remains unverified.

Managed skill candidates store sealed task scopes, typed explicit data slots and source-task provenance in the runtime SQLite database. Recording requires confirmed receipts and independently verified success. Validation creates a distinct pinned task; publication requires that exact trial's successful completion, an explicit review note and a compare-and-set version. Semantic selector repairs create new candidates. In-flight tasks retain their original version/digest; arbitrary pointer receipts are not guessed into semantic skills. Legacy mutable SkillLibrary behavior is preserved.

Accepted tasks, trigger templates and skill trials retain live origin policy references. A private witness contains only current root ceilings; missing/revoked/corrupt witnesses fail closed. Authenticated local HTTP forwards the current caller's additional restrictive ceiling without granting identity or capability. Every operation checkpoint and lease maintenance rechecks roots. MCP client roots and asynchronous roots refresh are session-local; stale replies cannot renew retired authorities. Static host policies persist until replacement, while retiring client-supplied root authority revokes its references. HTTP client roots do not overwrite the shared resource provider's configured workspace. Workers/maintenance run in fresh contexts, shutdown tracks actual in-flight deliveries before lease acquisition, and unstarted queued work remains durable.

Legacy MCP wrappers and parallel/local DAG workers preserve the origin intersection. Metadata is resolved lazily for task-aware dispatch and worker handoff, and a failed policy publication invalidates its previous witness.

Managed action references resolve observation-local element centers or rendered image pixels into native coordinates only after identity/freshness/fingerprint checks. Explicit coordinates cannot conflict with a reference; invalid/disabled/out-of-frame targets fail before preparing an action. SQLite atomically links grounding metadata to each prepared receipt, including requested arguments, frame ID/hash and non-image geometry; reports expose the same provenance. Local-model schemas carry an observed_target extension while legacy executor signatures stay unchanged. AgentObservationStale round-trips over local HTTP, and bounded pre-dispatch replanning requires an adapter's explicit can_reobserve guarantee. Native adapters deny it while any owned input or unsettled operation remains. Native acceptance stays unverified.

Native helper protocol 1 includes a read-only bootstrap handshake bounded to fifteen seconds. Configure/observe/perform retain their configured action deadlines; cleanup retains its own bound and ownership cannot transfer before retirement. Image-point grounding verifies actual bounded JPEG pixels against the advertised rendered dimensions.

Managed mouse presses normalize button ownership and confirm the actual cursor before input. Windows pointer checks reject foreign overlays. Vision renders the exact scoped window into cleared private GDI storage, rejects geometry changes and releases resources even on rendering/read failure. There is no desktop-crop fallback. Fake-native tests cover these paths; native acceptance remains unverified.

The Agent tasks view groups task scope, workflow settings, triggers, skills and recovery into separate pages. Its observation page lists read-only elements and shows a validated, strictly masked JPEG at one rendered pixel per logical widget pixel. Selecting a row or image point only edits a frame-bound action request; Actions -> Perform observed action sends it through the shared task API. Switching tasks clears the preview, and late replies cannot replace the selected task. A new frame requires reselection before an old reference can be sent. Closing the view only detaches its requests.

Managed workflow waits (workflow_wait / AC_workflow_wait) poll only exact scoped control values or states, with cancellation and a deadline capped by the action budget (default five seconds, maximum sixty). They never replay a write or submit. Fixed skills require all previous receipts to match the pinned sequence before continuing, including after resume; autonomous model loops retain stuck detection. New form/transfer drafts refuse an already-matching confirmation before submit and wait for a fresh transition afterward. Batch configurations may provide new_record_selector to reset each record; confirmations prove the configured UI transition, and transaction-specific receipt values should be used when available. Archive drafts also re-read the exact reviewed manifest and current file digests at finish (one-megabyte manifest and sixty-four-megabyte total evidence limit).

AgentHumanReview identifies an unsaved-content or unknown-dialog gate. It persists waiting_user and retires input ownership, including for external observe requests; explicit resume still rechecks the gate. Windows detection uses native dialog/disabled-owner evidence and known English/Chinese/Japanese unsaved labels. Workspace tasks also pause for leading/trailing asterisks in document titles; a window entry may supply unsaved_selector and unsaved_value for an application-specific indicator before layout changes. These checks do not infer every application's dirty state. Recognized standard file pickers use a context-local driver on the existing AC_handle_file_dialog executor: exact unique title, same PID, confirmed foreground and canonical rooted absolute paths. UIA control patterns must belong to the actual owned root window, even when another window shares its PID. All behavior has fake-native/loopback coverage; actual platform acceptance remains unverified.

Host-reviewed targets use AgentTargetProfile and manage_agent_target (AC_agent_target; register/get/disable/enable). Names and configuration are immutable; desktop/file adapters are currently supported, and unimplemented kinds or executable settings are rejected. Tasks pin the host profile digest and cannot expand its tools, applications, roots or network origins. Availability persists across restart and is checked at dispatch; disabling requests pause/cleanup, while enabling requires explicit task resume. list_agent_targets / AC_agent_target_list / CLI agent-task targets expose passive metadata with readiness=not_probed and native_evidence=not_recorded. Full configuration requires manage_hosts; CLI agent-task target and the GUI Host targets page use the same service. Live anonymous MCP tool sessions have operator authority across direct and legacy wrapper calls; MCP host management requires an authenticated administrator. Trusted direct Python callers remain unchanged. Browser automation belongs to WebRunner (je_web_runner), with D:/Codes/WebRunner as the development source; the managed browser adapter is not part of these target registrations.

Existing browser automation, including open_path(URL) and AC_open_path, delegates to WebRunner (Python package je_web_runner). URL plans now report backend=je_web_runner; callers inspecting the previous webbrowser descriptor should use the new value. Signatures and local-file opening stay compatible. URL execution requires the configured WebRunner project and propagates WebRunnerBridgeError when unavailable, without opening an OS browser as a fallback. The development source is D:/Codes/WebRunner. Planning and injected-opener tests remain usable without that package; browser protocol support is determined by WebRunner and its selected browser. Existing dedicated browser GUI/MCP/AC paths and recorded WR_* actions share the same bridge.

## Local DAG evidence-only recovery operations

Existing recovery children held by another caller can provide completion evidence to their
original local DAG through an explicit revocable handoff. In `manage_agent_recovery`, use
`review_handoff` with the final `task_id`, `batch_id` and `node_id`; an authorized manager then calls
`create_handoff` with the same IDs, returned `handoff_review` as `review`, and a nonempty `note`.
The service derives the recipient from the real original admission. In a `review_continuation`
successor decision, explicitly include `handoff_id` alongside `node_id`, `action` and `task_id`, then
review and approve the whole continuation. At most sixteen real recovery links are supported,
including a privately admitted permanent read-only final verifier. Ordinary task ownership remains.

`get_handoff` and `revoke_handoff` take `handoff_id`; `list_handoffs` takes `batch_id` and `node_id`.
Issuance and consumption refresh actual owners, admitting reviewers, issuing-session root witnesses,
current consumer ceilings, fixed scope, effect snapshots, independent completion and retirement.
Approval, start and late dependency validation recheck consent; revocation or evidence loss blocks
adoption. Grants expire no later than the earliest retained terminal witness's existing thirty-day
deadline. Returned data contains bounded IDs, hashes and status, without private task arguments,
captures or principal-store paths. No ordinary task-read/input access, ownership transfer or replay is
granted. Cross-host and non-DAG handoff contracts remain outstanding in `Progress.md`.

The Agent Tasks Handoffs page has an operation selector and JSON editor; Actions prepare review,
create and revoke requests without dispatching them. Five editable `agent_handoff_*.json` examples
cover review/create/get/list/revoke. Python, AC, CLI, authenticated MCP, REST and Builder use the
same recovery operations. These checks establish contract and owned-file behavior; deferred native
desktop, browser, device and 24-hour acceptance still require their own evidence.

## Read-only completion renewal and current evidence validity

When original origin references are expired or unavailable, explicitly call
`manage_agent_recovery("review_completion_authorization", {"task_id": "<source-id>"})`.
Review the server-derived `verification_spec` and retained/replaced/current origin context, then call
`create_authorized_completion` with the same `task_id`, returned `snapshot`, `authorization_review`
and a nonempty `note`. Optional `owner_policy="source_owner"` requires the returned `ownership_review`
at creation. Callers cannot supply a replacement verification spec. Existing live constraints stay;
new roots intersect the original ceiling, prior reader ceiling and current session. Ordinary
completion review does not replace this explicit consent for an already renewed reader.

The child is permanently read-only. It independently checks current conditions against the actual
confirmed original effects, without input, replay, restoring captures or modifying old witnesses.
Source/effect snapshots, real owners/reviewers and original DAG admission are rechecked. Task admission
and final completion each revalidate inside their own SQLite writer after SQL; changes roll back.
At most sixteen actual recovery links are supported. A retired successful reader may be explicitly
renewed again, retaining its previous narrower ceiling and all still-valid inherited restrictions.
Changed source/effect evidence remains refused and must not be silently repaired by scope renewal.

Historical `get` preserves succeeded state; loss of renewed authority makes its current
`completion_contract` zero and `completion_authorization` unavailable. DAG adoption and late dependency
validation then refuse that evidence. Malformed/missing renewed read-only markers fail before helper
startup. Recording with `completion_task_id` uses the approved restricted scope and original semantic
actions, but the draft still needs its own fresh validation trial. Renewal does not publish an expired
candidate or renew a published skill grant. Existing skill reauthorization remains separate.

Python, AC, CLI, authenticated MCP, REST and Builder share both operations. The Recovery page exposes
two explicit Actions using its selected task, owner policy and request editor. Editable examples are
`agent_completion_authorization_review.json` and `agent_completion_authorization_create.json`.
Remote read-only providers, cross-host handoffs, actual application
state restoration and deferred native/device/browser/24-hour acceptance remain in `Progress.md`.

## Explicit renewed-reader completion handoffs

Existing `review_handoff` / `create_handoff` can explicitly transfer completion evidence from
a privately renewed, permanently read-only reader to its real original local DAG. Select that reader's
task ID and the actual original batch/node. The service derives the proof; callers cannot supply a
policy, ownership override or authorization bundle. Ordinary handoffs keep their existing rules.

The preview's `evidence.completion_authorization` contains the completion task/review, a bound review
digest, approved-root count and replaced/retained/current origin IDs. It omits private principal paths,
action arguments and captures. Set creation's `review` to the returned top-level `handoff_review`, then
provide a nonempty `note`. Every actual task keeps its reviewed ceiling; all live historical restrictions stay, unavailable
references are explicitly reviewed, and the issuing session's additional constraints remain live.
The grant uses the exact already-verified reader roots. A different intersection requires another
real completion review and verification. The consuming session/profile still applies its own limits.

At most sixteen actual recovery links may mix previously reviewed executable successors and private
readers. A succeeded intermediate reader needs actual private historical scope and retirement proof;
an ordinary succeeded source does not gain that exemption. No helper is launched or input replayed
while granting or adopting evidence. Old source state, witnesses, receipts and all task owners stay.
The original owner receives only the bounded completion projection, without ordinary access to the
other caller's task. Revocation or lost authority blocks adoption and late dependency validation.

Original accepted-request hashes, raw submission witnesses, private admission, graph, owners/reviewers,
all real source/child snapshots and the leaf renewal remain bound. Reads and post-write checks use
the same SQLite writer, including uncommitted changes; mutation rolls back admission/grant creation.
An inherited `dag_batch` option is not admission: a bounded real recovery chain must resolve the actual
original request and admitting identity without creating a replacement admission row. Earlier ordinary
completion binding hashes remain compatible. Each historical task retains its own policy review;
combining history cannot bypass the normal sixteen-live-origin limit or any original root ceiling.

Exact active retries retain their note and ID; revoked IDs never reactivate. Restart and adoption
preserve the earliest retained terminal witness's thirty-day deadline. Historical get/list/revoke stay
available after an origin expires, while that history supplies no usable completion or input grant.
Python, AC, CLI, authenticated MCP, REST and Builder share the five existing operations. Existing
Handoffs Actions and its JSON editor/result view show the explicit renewed review without dispatching
consent automatically. Cross-host handoff, remote readers, actual application/device
providers and deferred native/browser/device/24-hour acceptance remain in `Progress.md`.

## Explicit task-source completion evidence handoffs

The five existing handoff operations also accept a real non-DAG source task:

- `review_handoff`: supply `source_task` and the actual final evidence `task_id`.
- `create_handoff`: add the returned top-level `handoff_review` as `review`, plus a nonempty `note`.
- `list_handoffs`: supply `source_task`; `get_handoff` and `revoke_handoff` still use `handoff_id`.

Task-source fields and DAG batch/node fields are mutually exclusive. The service resolves persisted
grant IDs to their actual storage family. Original DAG ancestry must use its real batch/node route,
even if a later read-only reader dropped its `dag_batch` option. No synthetic DAG node or admission
is created. Ordinary standalone tasks need no invented submission witness or idempotency key;
any actual accepted request is bound and rechecked on the same SQLite writer.

Select `handoff_id` explicitly in existing skill operations. `record` uses a separate verified reader
through `completion_task_id` and creates a draft which still needs its own new validation trial.
`accept` with `completion_task_id` keeps the actual original candidate's validation task.
`review_execution` and its matching `accept` may select an actual `execution_task_id`; add
`completion_task_id` when the final granted evidence is a separate reader. The service verifies
the exact complete original semantic action plan, real execution IDs and independent final criteria.
A reader never becomes an execution task or a substitute validation trial.

The grant yields only a private bounded evidence view. Original task owners, source state and
receipts remain; ordinary get/list/observe/act/resume access never expands. Granting or adopting
launches no helper and replays no input. Real source/child snapshots, original optional requests,
actual owners/reviewers, retired input and every live historical origin remain checked. New recorded
drafts retain both issuing and consuming session ceilings. Unavailable restrictions require actual
private completion renewal; matching hashes or caller-authored scope flags cannot replace it.
Read-only evidence adoption does not renew a published skill's original input authorization.

At most sixteen real recovery links include source ancestry and the forward granted chain. Earliest
retained terminal evidence expires after thirty days; anchoring at a later reader cannot extend an
older ancestor. Same-writer post-insert and exact-retry checks honor revocation tombstones for both
DAG and task grants. Source/request/role/origin/revocation changes roll back grant creation, draft
recording or publication. Revoked IDs never reactivate. Historical get/list/revoke after an origin
expires expose bounded IDs and hashes, not continued completion or input authority.

The Handoffs page explicitly selects original local DAG or original task when preparing JSON.
Three skill Actions prepare recording, publication or execution review with a handoff placeholder;
they do not issue consent or publish automatically. Python, AC, CLI, authenticated REST/MCP and
Builder share the same operations and actual caller identities. Editable requests are
`agent_task_handoff_review.json`, `agent_task_handoff_create.json`, `agent_skill_recording_handoff.json`,
`agent_skill_completion_handoff.json`, `agent_skill_execution_handoff_review.json` and
`agent_skill_execution_handoff_accept.json` under `examples/`.

Cross-host handoffs, remote readers, actual application/device providers, deferred native
and twenty-four-hour acceptance, and unresolved HTTP409/bootstrap issues remain in `Progress.md`.

## Retained original browser completion

Stopped browser tasks with confirmed effects can now use the existing completion review and
skill workflow with their actual original WebRunner context. The owned worker permanently freezes
SDK input/network before its input journal and lease release; the runtime retains at most 16
contexts for at most 300 absolute seconds, starting before detachment. Preview/new admission probe that exact effect task's live SDK view.
The verifier borrows it for fresh bounded DOM/value reads, without configure, input ACKs, transfers
or another browser/helper. Retirement, capability probes and cleanup deny nested tools and native input.
Same-profile tasks keep separate contexts. A saved context ID grants nothing.
Private completion authorization can explicitly renew the verification scope within the original
ceiling while the original input specification stays immutable. Expired input origins grant no reads;
bounded private custody alone is not authority. Removed owners, disabled targets, changed sources,
expiry and failed reads invalidate contexts. Confirmed process reaping is required to free ownership;
failed cleanup stays tracked. Restart cannot restore a page. Network-retired DOM is not new server data.
Existing Python/AC/MCP/REST/CLI/Builder and GUI Actions share the same review requests. Skill recording
keeps original actions; publication requires its own actual validation trial and selected completion.
See `examples/agent_browser_retained_completion.py`. Cold browser-prefix reconstruction, remote
readers, production deployment and deferred native/browser/device/24-hour acceptance remain open.

## Idle work queue polling

Idle background workers check empty work queues without reserving a database writer, reducing
contention with task status and completion transactions. A nonempty hint still requires the original
transaction to recheck and claim the work. Claim generations, stale-work recovery and retry limits
remain enforced; task and transport deadlines are unchanged.

Lease maintenance binds expiry/revocation stops to the actual input owner and generation in the
same stop transaction. A delayed watcher cannot rewrite retired recovery evidence or cancel a newer
lease. The accepted final state and cancellation token are set before the stop becomes visible;
current revocation and the original deadlines remain enforced.
