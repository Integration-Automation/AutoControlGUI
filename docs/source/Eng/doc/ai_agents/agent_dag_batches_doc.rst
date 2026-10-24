Managed DAG batches and continuation
====================================

Register before initial execution
----------------------------------------------------------------------

``manage_agent_dag("register", {"definition": graph, "max_parallel": 4})`` freezes an owner-scoped
all-managed graph without submitting a task or acquiring a target. The graph must contain 1..100 closed
task nodes, distinct request keys per host and a valid topology. Action/action-file nodes, unknown fields,
cycles, duplicate dependencies and caller-supplied batch tags are rejected. Local specs bind current
profile/origin ceilings; destination paths on remote nodes are not canonicalized locally. Remote host
configuration is pinned privately without storing its raw credential in the batch record.

The returned ``batch_id`` identifies this exact graph. Explicitly execute::

    batch = manage_agent_dag("register", {"definition": graph, "max_parallel": 4})
    result = run_dag(graph, max_parallel=4, batch_id=batch["batch_id"])

The graph, parallelism and host configuration must still match. Bound batches use only managed dispatch;
custom runners are rejected. Each destination task carries ``options.dag_batch`` with batch ID, graph
digest and node ID. Its key is derived from the batch/node/host/original key, preventing adoption of an
unrelated task that happens to use the original key. The original graph remains unchanged.

Claims and independent completion
----------------------------------------------------------------------

``begin`` changes registered to running once and returns a private attempt identity. ``claim`` commits
before any possible destination delivery, only after dependencies have confirmed receipts. ``record``
accepts bounded coordination identity and independently looks up the exact bound spec/key/task at the
destination. Exact spec-match contract 1, succeeded state, matching independent criteria and confirmed
input retirement are all required before a node becomes confirmed. Raw remote diagnostics are withheld.
``finish`` derives succeeded or waiting_review from the persisted node phases.

An interrupted/lost submit reply leaves claimed/unknown evidence. Neither restart nor a second begin
resets it, even if a later lookup returns no match. Runtime restart fences the old attempt and marks
the batch waiting_review before another caller can claim a node. A confirmed individual task does not authorize another
batch attempt. Original-owner and caller permissions are refreshed; credentials and local origin witnesses
are never forwarded to a remote task host. Matching host transport captures one reviewed configuration.
No batch operation restores login/window state or clears native input quarantine.

Shared surfaces and current limits
----------------------------------------------------------------------

Use ``manage_agent_dag``, ``AC_agent_dag``, MCP ``ac_agent_dag``, ``POST /agent/dag``, Builder or
``agent-task dag register|get|list|begin|claim|record|finish|inspect request.json``. Registration also
accepts optional ``max_parallel`` from 1 to 64. Execution lifecycle requests carry batch_id/attempt;
node requests add node_id and record adds ``receipt={outcome, task_id}``. Normal callers use run_dag
for these transitions. ``get`` returns the immutable graph and node phases/receipts; ``list`` returns up
to 200 visible batches. ``inspect`` queries the stored bound graph without submitting or resuming and
always returns ``resume_permitted=false``.

``run_dag``, ``AC_run_dag`` and MCP ``ac_run_dag`` accept optional batch_id. With no ID, historical
unbound behavior stays unchanged. DAG Actions adds **Register managed batch (no execution)** and
**Read managed batch record**, plus an optional batch-ID input. Registration never runs automatically;
the existing Run action executes the selected batch. Late results are discarded when graph or batch
selection changes. Closing or stopping an existing DAG worker preserves its durable coordinator record;
destination tasks retain their own service lifecycle and pause/review contract.

Explicit whole-graph continuation
----------------------------------------------------------------------

After interruption, use the original graph and batch ID to request a read-only review::

    review = manage_agent_dag("review_continuation", {"batch_id": identifier, "definition": graph})
    request = {"batch_id": identifier, "definition": graph, "snapshot": review["snapshot"],
               "decisions": review["decisions"], "note": "Reviewed all node evidence and scope"}
    result = run_dag(graph, max_parallel=4, batch_id=identifier, recovery=request)

Review requires waiting_review. To fence a live or approved attempt first, explicitly call
``pause_batch`` with batch_id. This stops future coordinator claims; it neither pauses accepted tasks
nor proves input cleanup. Use each destination task's existing pause/cancel/review lifecycle separately.
Do not use fencing as a native handoff signal.

Every node requires exactly one closed decision. ``adopt`` has node_id/action/task_id and accepts only
the bound original's independent completion. ``successor`` has the same fields and follows actual
runtime TaskRecovery provenance to the original; create, review and independently complete that new
task first. An unrelated successful task or caller-authored options cannot establish lineage.
``dispatch`` has node_id/action/spec and requires a never-claimed pending node with no accepted
destination request. ``wait`` has node_id/action and blocks approval. A destination task found before
the coordinator's claim cannot be adopted as batch provenance. Missing lookup evidence never clears
a previous claim or authorizes replay.

After editing decisions, call review_continuation again with the full decisions list. Use its fresh
snapshot and decisions only when can_approve is true. Local dispatch may replace expired origin
references and preserve/narrow original roots; all actions, goals, settings and completion clauses stay
fixed. Remote specs remain unchanged and use destination authority. Historical submission_contract=1
digests bind admitted specifications without granting present authority. Legacy tasks lack that witness
and require live spec-match contract 1; request-key retries never backfill admission evidence. Older
batches without raw input witnesses must use get.input_definition explicitly.

``approve_continuation`` takes batch_id, definition, snapshot, decisions and a nonempty bounded note;
optional timeout_seconds defaults to 30 (maximum 300). It rechecks evidence and atomically stores the
actor-bound plan, adoptions and narrowed dispatch bindings, without dispatching. Identical retries
return the same approval, including its used/cancelled state. ``start_continuation`` takes batch_id,
definition, approval_id and unchanged max_parallel, rechecks evidence and consumes the approval once.
Changing graph, actor, permissions, host configuration or evidence requires a fresh review. run_dag,
AC_run_dag and ac_run_dag accept optional recovery to drive approval/start; custom runners remain refused.
``validate_node`` takes batch_id/attempt/node_id and revalidates adopted completion. Execution repeats
this before adopting a node and before releasing its dependants; missing proof returns it to unknown.

All operations share manage_agent_dag / AC_agent_dag / ac_agent_dag / POST /agent/dag / Builder and
``agent-task dag OPERATION request.json``. ``get`` exposes bounded continuation audit records, including
reviewing user, note, decisions and approval state, without private owner paths or credentials.
DAG Actions adds fence, review and explicit continuation controls with editable request JSON. Fill the
note after reviewing; changed graph/batch selection invalidates stale review results. Read-only inspect
and review keep resume_permitted=false; only explicit approval/start authorizes a new attempt.

Service background coordination
----------------------------------------------------------------------

An explicitly started AgentRuntimeService can own coordination after the caller or view exits::

    accepted = manage_agent_dag("run_background", {
        "batch_id": identifier, "definition": graph, "max_parallel": 4})
    record = manage_agent_dag("get", {"batch_id": identifier})

For a stopped batch, review and approve the complete plan first, then delegate the approved attempt::

    approved = manage_agent_dag("approve_continuation", request)
    accepted = manage_agent_dag("run_background", {
        "batch_id": identifier, "definition": graph, "max_parallel": 4,
        "approval_id": approved["approval_id"]})

The same operation is available through AC/MCP/REST/CLI/Builder. Without approval_id it uses initial
begin; with approval_id it consumes start_continuation. Optional timeout_seconds applies to continuation
evidence checks. Graph, parallelism, actor, owner and host binding rules remain unchanged. Repeated
initial starts or consumed approvals fail; a lost acceptance reply must be inspected, never replayed.
No import, registration or read starts a service. Unavailable/full services reject before consuming
an attempt; a failed queue acceptance fences an already acquired attempt.

The service uses the existing WorkQueue, with four coordinator workers and at most 64 pending/running
deliveries. All nodes retain pre-delivery claims and independent destination completion checks. Both
original owner and actual submitting actor are refreshed during dispatch/polling. Local destinations
use their owning runtime directly, preserving original task ownership without reading a different
global client connection file. Remote endpoints remain pinned and never receive local principals or
origin witnesses. The service's task workers own local execution and physical input retirement.

get/list add ``background=null`` for caller-only runs or a bounded state record using new/in_progress/
success/failed. Failed deliveries require review; these states do not replace independently persisted
batch/node evidence or certify native cleanup. Private delivery authority and attempt capabilities are
withheld. DAG Actions adds **Run managed batch in service background** and **Approve continuation in
service background**. They submit explicitly and return the batch record; closing the view leaves
accepted service work alive. Read the batch record again for current progress.

Service shutdown fences accepted attempts before retiring coordination and local task workers.
Task stop requests and settlement preserve concurrently committed terminal completion evidence.
stop_all also fences visible running/approved batches before cancelling visible local tasks; an
operator cannot stop another owner's batch. Fencing stops future claims. Already accepted/in-flight
destination operations keep their pause, cleanup and unknown-effect contract; remote cleanup is not
inferred. An actual process exit leaves durable claims. Restart marks live batches waiting_review and
old queued/in-progress deliveries failed without reclaiming them. Even an unclaimed old delivery
requires explicit review; an absent destination lookup cannot reset a possible dispatch claim.

Caller service binding
----------------------------------------------------------------------

Caller-driven ``run_dag(..., batch_id=...)`` binds its source before begin or continuation approval.
AgentRuntimeClient.bound() captures an absolute owner-file path and a digest of URL, token and service
generation; bearer credentials remain fresh per request. Valid generation-bearing metadata is required
for bound runs. Ordinary clients remain adaptive, including legacy metadata without a generation.
Local node submit/get/pause reuses the source client through copied execution contexts. Changing global
default discovery cannot move a later local node to another service. Replacing the source URL, token
or generation stops subsequent calls before transport and never silently rebinds an active attempt.

Server-side batch inspection and completion verification read the owning runtime directly. The current
original-owner request-key scope is retained, while the actual caller's authority is refreshed around
queries. Admin inspection therefore uses original-owner keys. Remote hosts retain destination-owned
credentials and never receive local principal/origin data. Existing Python/AC/MCP/Builder and GUI Run
surfaces inherit the same binding; no additional GUI command or credential input is needed.

Replacement detection does not prove retirement of previously accepted work. Its claims remain
durable, and no pause/control request is redirected to a replacement service. Inspect the original
service through a separately verified connection and use explicit batch/task review; restoring a file
does not reset begin, unknown claims or consumed approvals.

Original-owner local admission
----------------------------------------------------------------------

Both caller and service coordination use ``local_task`` after the node claim is durable. Its request is
``{batch_id, attempt, node_id, operation, body}``; normal callers use run_dag rather than constructing
these lifecycle requests. The operation is limited to submit/get/lookup/pause and the node must be
local. Submit/get/lookup require the live attempt and an unsettled claimed node. Submit accepts only
``{spec, idempotency_key}``, exactly matching the bound full node contract. It uses the original owner
for task/key admission, while recording the real caller separately. A caller-authored actor field,
changed contract/key, foreign node or arbitrary method is rejected before input.

The task, request key, submission witness and trusted local admission commit in the same transaction.
The admission binds task/batch/node/attempt/actor and the submitted digest. Matching retries return the
same task. Existing keys without the same trusted binding are refused and never backfilled; options
or caller-provided snapshots cannot create that evidence. Failure before commit starts no task worker.
Get/pause accepts only the admitted task ID; lookup accepts its key and optional exact specification.
Pause permits precise retirement after the attempt is fenced or the original owner loses input
permission, without granting new submission or another task's control. Caller permission is still
checked. Remote tasks retain their destination's ordinary authentication and receive no local actor.

The runtime refreshes original-owner and actor authority at scope entry, checkpoints, immediately
before dispatch, nested command guards and maintenance. The actor must still manage the original
owner's work: an admin downgraded to operator cannot continue another user's admitted task. A fenced
attempt or unknown claim blocks further input. Queued work revalidates before activation. Native
cleanup failures retain existing quarantine; an admission or pause response alone does not prove
input retirement. Task metadata adds bounded ``local_dag_admission`` with contract/batch/node/actor UID,
withholding attempt capabilities and private user-store paths. Existing task JSON views display it.

Current limits
----------------------------------------------------------------------

Cross-owner recovery-child evidence remains in Progress.md. Ordinary TaskRecovery creates a child
owned by its actual creator, while whole-batch evidence reads as the original owner. Use an original-
owner-readable successor or an explicit reviewed evidence handoff; task visibility is never widened
automatically to make a successor adoptable.

Batch retention/cleanup remains in Progress.md. Legacy graphs cannot be retroactively treated as bound
batches. Adoption certifies a historical logical stage; it does not
restore login/window state or assert current application state. Owned fake-target/local/two-host HTTP
and offscreen evidence do not establish real deployment, installed-model or native acceptance.
Browser automation remains on je_web_runner.
