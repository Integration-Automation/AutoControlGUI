Managed DAG batch identity
==========================

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

This stage supplies initial-execution evidence for later recovery. Explicit whole-batch continuation
approval, adopting a reviewed replacement task, dependency revalidation, independent background batch
coordination and retention/cleanup remain in Progress.md. Legacy graphs cannot be retroactively treated
as bound batches. Owned fake-target/local/two-host HTTP and offscreen evidence do not establish real
deployment, installed-model or native acceptance. Browser automation remains on je_web_runner.
