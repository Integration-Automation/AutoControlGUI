Task recovery and reauthorization
================================================

Reviewed successor tasks
------------------------

A retired desktop/browser context cannot safely continue from historical field receipts.
``manage_agent_recovery("preview", {"task_id": source_id})`` reads a stopped finite skill without
observing or operating its target. It returns source receipt summaries, per-row outcomes, attempted
and verified step counts, remaining actions and a ``snapshot`` binding the exact source task,
receipts and review witnesses. Issues such as unknown effects, failed read-back, old coordinates or
missing capture producers withhold the draft. Unknown counts are not reported as completed steps.

Review the application state and reconstruct any necessary preparation with semantic actions and
fresh captures, within the source scope. Explicitly call ``manage_agent_recovery("create", request)``
with ``task_id``, ``snapshot``, ``spec`` and a nonempty operator ``note``. Only goal/actions may change;
target, tools, roots, apps, inputs, budgets, options and independent completion conditions remain fixed.
Private skill publication pins are removed. Missing captures, copied observation indexes and coordinate
steps are rejected. Unreconciled source effects must first use the existing receipt review operation.
A changed source requires another preview and approval; an active input lease prevents replacement.

Creation and the unique source link commit in one SQLite transaction. Repeated identical approval
returns the same successor, including after restart or a lost reply; different approval conflicts.
The source retains its state, receipts, reviews and row outcomes. The child starts with no receipts and
must satisfy fresh completion evidence; success does not complete its parent. The delegated source cannot resume. Task/list metadata exposes
``recovery`` provenance. Retention keeps source evidence while a child exists; removal leaves a tombstone
until the source is pruned, so replaying an old approval cannot resurrect a retired child.

The shared surfaces are ``AC_agent_task_recovery``, MCP ``ac_agent_task_recovery``,
``POST /agent/recovery`` with ``{operation, request}``, Builder, and
``agent-task recovery preview|create request.json``. Both operations require operator ``drive_input``.
Agent tasks Actions provides **Review remaining work / replan** and **Create reviewed successor task**.
A successful preview prepares a separate Recovery JSON editor with an empty review note. It never fills
or submits the ordinary task form. Change the plan/note, then explicitly create. Changing the selected
task clears the draft and late replies are ignored. Creation uses normal durable background dispatch;
closing the view only detaches requests. Login/window restoration, arbitrary pointer regrounding and
real application/native acceptance remain separate work; no browser engine or paid dependency is added.

External-agent and local-model replanning
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Recovery also supports stopped ``external`` and ``ollama`` tasks. These modes do not define an
executable finite prefix, so preview reports ``completed_steps=null``, no remaining action array or
row progress, ``draft=null`` and ``new_plan_required``. A separate ``review_template`` preserves source
scope, mode, model/endpoint, budgets and completion criteria while leaving goal/actions empty. Even a
dormant action array in the old specification is never treated as executed or remaining work.

The operator must explicitly supply a nonempty goal and review note. The original wording may be
retained after review; no completed progress is thereby inherited. Dynamic successors cannot carry
dormant actions or switch execution modes/model settings. Unknown effects
still require reconciliation and another source snapshot. No completed receipt, old observation or
model history is copied, and a model stop without fresh completion evidence remains unknown.

Use the same API/AC/MCP/REST/CLI/Builder surfaces. GUI Actions **Review remaining work / replan**
prepares the separate Recovery editor with blank goal/note; it does not submit anything. External
children wait for client-driven observe/act. Explicitly approved Ollama children use normal background
dispatch, fresh observations and a new backend with the original pinned local model/endpoint. Preview
makes no model HTTP call. A test-owned Ollama-compatible loopback endpoint verifies show/chat ordering,
model identity, the new goal and empty first history. This fixture is not installed-model acceptance;
actual model/native evidence remains in Progress.md; authorization renewal is described below.

Explicit successor authorization
--------------------------------

Origin witnesses can expire when a client session retires. Ordinary ``preview``/``create`` still require
the original live authority. Explicit renewal uses two additional operations on the same recovery API:

1. ``manage_agent_recovery("review_authorization", {"task_id": source_id})`` returns the source
   ``snapshot``, ``authorization_review`` digest, clipped authorization context and a draft or editable
   ``review_template``. Review does not start a target or contact a model.
2. Review the remaining work and supply ``task_id``, ``snapshot``, ``spec``, nonempty ``note`` and
   ``authorization_review`` to ``manage_agent_recovery("create_authorized", request)``.

The original normalized roots remain the upper bound. Every still-live source policy is retained;
current caller policies are added and intersected with that bound. Unavailable old witnesses may be
replaced only for this successor; their files and the stopped source are never rewritten or resumed.
Current unavailable authority is rejected. Trusted host calls without a session policy still require
explicit approval within the original roots and host profile. Review metadata clips unrelated roots.
Operators may keep or narrow the proposed roots; tools, apps, inputs, mode/model/endpoint, budgets,
completion conditions and other options cannot expand or change. Retained policies cannot be removed.

The digest binds the source snapshot and effective authorization context. Changed roots or sessions
require another review; changed source receipts also require another snapshot. Completion criteria
outside the new scope withhold a runnable template. Incompatible remaining actions require editing
and full validation; criteria are never silently dropped. Dynamic templates still require an explicit
goal. Unknown effects need reconciliation, and unsettled input ownership continues to block creation.
Renewal neither clears quarantine nor certifies login, window state or native readiness.

The task, unique recovery link and authorization evidence commit atomically. ``recovery.reauthorization``
records the review digest, bounded context, approved roots and actor. Audit survives child retention
until the source is pruned. ``existing_successor`` reports the previous child even after retirement;
replaying approval cannot create another child or switch approval modes.

All four operations require owner/operator ``drive_input``. API/AC/MCP/REST/Builder share the protocol;
CLI uses ``agent-task recovery review_authorization|create_authorized request.json``. Agent tasks Actions
adds **Review successor authorization** and **Create reauthorized successor**. Review fills the dedicated
Recovery editor, with an empty note; creation always requires the separate explicit action.
Deterministic targets, authenticated loopback HTTP and offscreen Qt validate these contracts. Published
skill/trigger renewal, application-state restoration and actual model/native acceptance remain open.
