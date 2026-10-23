# Managed agent tasks

The experimental managed-task core gives external clients, deterministic skills and a configured
local Ollama model the same observe/act/finish lifecycle. A task's own scope never grants operating
system permissions. Native target acceptance remains unverified; see `Progress.md`.

## Start and stop

```powershell
je_auto_control agent-task start
je_auto_control agent-task status
je_auto_control agent-task list
je_auto_control agent-task stop
```

Importing the package does not start a service or operate a target. Explicit startup launches a
hidden local process and publishes its ephemeral loopback address and bearer credential to the
per-user `agent_runtime.json`. Status never returns that credential. Stop requests cancel owned
input first; active dispatch or cleanup prevents premature service retirement.

## Task contract

Submit a JSON file with `je_auto_control agent-task submit task.json`, or call
`submit_agent_task(spec)` from Python. `AgentTaskSpec.from_dict` validates and freezes caller data.
Required fields are `goal`, nonempty `allowed_tools` and nonempty `success_criteria`.
Optional fields are `target`, `mode`, `roots`, `apps`, `inputs`, `actions`, `options` and `budget`.

- `mode`: `external` (default), `skill` or `ollama`. Internal modes are delivered through WorkQueue.
- `target`: a host-configured adapter identity; the default is `local-desktop`.
- `apps`: explicit application names, checked against the foreground process's accessibility nodes.
- `roots`: canonical allowed data roots; file operations and file completion evidence require them.
- `actions`: skill proposals with `tool` and optional `arguments`; every proposal still goes through observation.
- `budget`: max_steps=25, wall_seconds=300, retries=2, action_seconds=30 and model_seconds=120.

Criteria are `result_equals` (key/value in the last confirmed result), `file_exists` (path/min_bytes),
`file_sha256` (path/value), `file_text` (path/value), and `screen` (nonempty existing postcondition spec).
Unknown evidence never proves success. Empty postconditions and unknown criterion kinds are refused.

The reviewed default desktop tool set is intentionally limited. A custom adapter is a trusted Python
extension, not a model-supplied plugin. Native desktop calls run in a hidden, owned helper with bounded JSON IPC and action deadlines.
Cancellation retires the owned process tree; a host ledger releases only announced keys/buttons before
control transfers. Independent databases share a per-session input lock. Window/control scope is checked
again at input dispatch; pointer geometry and redacted window vision currently require Windows.
Additional platform activity adapters remain in Progress.

## External agent lifecycle

1. `submit_agent_task(spec)` returns task_id without taking input control.
2. `observe_agent_task(task_id)` acquires the target and returns a fresh observation_id.
3. `act_agent_task(task_id, {"tool": name, "arguments": args, "observation_id": id})` applies one proposal.
4. Observe again before another action. Old, expired or changed observations are rejected.
5. `finish_agent_task(task_id)` checks completion independently; model text is not proof.

Pause/resume/cancel and get/list functions use the same service. Pause retires input before releasing
control; resume requires new observation. An uncertain action requires explicit owner review before resume; it is never blindly replayed after restart.
New control generations reject old workers. A model cannot set task state or private executor fields.

The executor exposes `AC_agent_task_*` plus `AC_agent_runtime_start/status/stop`.
MCP exposes their lowercase names. The visual Builder derives fields from the same catalogue.
REST provides authenticated GET `/agent/tasks`, GET `/agent/task?task_id=...` and POST
`/agent/submit|observe|act|finish|pause|resume|cancel|shutdown`. Submit body is `{"spec": ...}`;
task operations use `{"task_id": ...}` and act also takes `action`. Shutdown needs host management.

Original principal metadata is authenticated across the local service bridge and store-backed users
are refreshed. MCP clients without RBAC use their live session identity for task ownership.
Task data reads require drive_input, even though get/list have a read-only hint. MCP path roots
are checked on submission and action parameters; further origin-policy lifecycle work is tracked
in Progress. Captured scope cannot widen an enclosing task's command guard.

## Local inference

Choose an already installed tool-capable Ollama model with `options.model`; optional `options.vision`
requires a vision-capable model. Endpoint defaults to `http://127.0.0.1:11434` and must be loopback.
The adapter checks `/api/show`, supplies only offered tools to `/api/chat`, disables redirects,
bounds HTTP concurrency and discards cancelled replies before execution. It never pulls a model
or chooses an external inference service. Configure Ollama with `OLLAMA_NO_CLOUD=1`.

## GUI and persistence

Open Agent Tasks from the workspace. Review the goal, target, execution mode, scope and completion
conditions before submitting. Start, stop, submit, refresh, observe, verify, pause, resume and cancel
are Actions-menu operations. Network work runs through TaskController. Closing the view detaches it;
the service owns submitted tasks.

The dedicated SQLite store records specs, owner references (never bearer tokens), task states,
action receipts and control generations. Prepared/dispatched/confirmed/uncertain receipts distinguish
dispatch from evidence. WorkQueue claim numbers fence stale delivery settlements; busy targets may
defer delivery without spending application retries. History links, action journals, structured reports
and owned cache retention share the task lifecycle; images stay ephemeral unless explicitly opted in.

## Review and run workflows

`draft_agent_workflow(workflow, config)` compiles `download_archive`, `batch_form`, `transfer` or
`workspace` into an immutable task specification without submitting it or operating an application.
CSV/XLSX preview reads only an explicitly rooted input file. Review the returned apps, roots, actions,
expected read-back values and budgets before `submit_agent_task(draft)`. Example configurations live
in `examples/agent_workflow_*.json`; replace their paths and semantic selectors for your applications.

```powershell
je_auto_control agent-task draft download_archive examples/agent_workflow_download_archive.json
```

The Agent Tasks view has a workflow selector and an Actions → Preview workflow command. Put a workflow
configuration in the JSON editor, preview it, then submit the resulting task. `AC_agent_task_draft`,
`ac_agent_task_draft` and authenticated POST `/agent/draft` expose the same compiler.

- **Download/archive:** the `local-files` target runs approved-origin HTTP(S) downloads in its owned
  helper, without desktop input. Redirects are refused. Downloads are limited to 16 MiB, checked for
  complete length and optional SHA256, then linked to a portable archive name without overwriting.
  A manifest records each filename, size and digest. Existing files require the expected digest.
- **Batch form:** validate CSV/XLSX columns first, fill each mapped semantic field, read it back,
  invoke the configured submit button, and read the configured confirmation value. Every row has
  its own durable action receipts. A mismatch stops before proceeding to another submission.
- **Transfer:** focus the source, capture explicit fields from confirmed receipts, apply one of
  identity/strip/upper/lower/collapse_whitespace, fill the destination, read it back and verify save.
- **Workspace:** open explicitly approved existing documents, focus uniquely matched windows,
  optionally snap them, and check the configured control state. Document suffixes are allowlisted;
  this profile does not accept executable paths or command-line arguments.

`actions_complete` completion independently compares every pinned action, resolved argument and
expected result with confirmed receipts. Control selectors require an explicit application and
accessible name; ambiguous, disabled or password controls are refused. Uncertain side effects stop
without replay. These workflows have fake-application and local-file/HTTP acceptance; real
application layouts and platform behavior still need the deferred native acceptance.

## Human takeover and persistent budgets

The default Windows shared-desktop helper installs owned, presence-only keyboard/mouse hooks before
acquiring input. It requires the Default input desktop, no held physical key and at least 60 seconds
of inactivity. Physical hook notifications contain only presence; no key values or pointer positions
are recorded. Native injected-event flags distinguish automation from human presence. A physical
notice crosses the private IPC independently of an active native call, requests host pause, kills
the owned blocked helper if necessary, and cleans recorded input before transfer. Resume is explicit.
An unavailable listener or noninteractive session refuses the next action. Queued workers defer busy
acquisition without spending retries. Other shared-desktop platforms currently require a trusted
activity adapter; their default acquisition reports unavailable rather than claiming idle detection.
Windows native-hook acceptance is still deferred; tests use fake listeners and synthetic IPC notices.

`stop_all_agent_tasks()`, `AC_agent_task_stop_all`, MCP, POST `/agent/stop_all`, CLI `agent-task stop-all`
and the Agent Tasks Actions menu cancel visible tasks. Operators affect their own tasks; host admins
can stop all owners. Active dispatch/cleanup can leave a task temporarily cancelling.

Wall budgets persist monotonic anchors and elapsed high-water marks in SQLite. Wall-clock rollback
and service restart cannot replenish them. A regressed monotonic clock expires an existing budget
conservatively. Paused time counts; queued waiting before first acquisition does not. Native action
and model deadlines remain independently bounded.

The service checks active lease budgets and refreshed owner authority between requests, so an abandoned
external client cannot retain input indefinitely. Tracked Unicode packets and modifiers participate
in the same input ledger; cleanup never claims a modifier that was not part of the original press.

## Receipts, reconciliation and artifacts

`get_agent_task_receipts(task_id, offset=0, limit=100)` returns owner-scoped action attempts, review
witnesses and success/failed/pending/not_started workflow row outcomes. Limit is at most 200.
Prepared receipts precede input, dispatched effects can become uncertain, and committed outcomes
cannot be silently rewritten. A restart marks dispatched attempts uncertain and prepared non-effects
failed, preserving consumed steps. Failed/proven non-effects do not advance a pinned skill sequence.

After independently checking an uncertain attempt, use `reconcile_agent_task(task_id, review)`:

```json
{"action_id": "receipt-id", "decision": "not_applied", "note": "Verified that no record was created"}
```

An `applied` decision also requires the reviewed `result`. This is explicit owner testimony, not
new native verification evidence. The original outcome, note, timestamp and reviewing principal
remain in an immutable review record. Reconciliation does not resume or force success. Resume
reauthorizes and requires a new observation; finish still evaluates the configured completion criteria.
Managed task profiles cannot call task-management commands or reconcile their own proposals.

Task `metadata` links the existing HistoryStore schema, an append-only ActionJournal and private
artifacts. History linkage and task metadata commit together in the runtime SQLite database.
Reports contain verification, per-row status and bounded receipt summaries/digests; raw receipts
remain available through the owner-scoped API. User output files remain in the explicitly authorized
roots and are not treated as disposable task cache.

Images are memory-only by default. `options.persist_images=true` requires a target image marked by
the strict redaction pipeline, a verified JPEG at most 1280 pixels per side and 1 MiB, and at most 100
images per task. Known vault values are scrubbed before durable publication. The generated cache
uses private directories/files and never accepts artifact destinations supplied by model output.

The service sweeps terminal tasks older than 30 days hourly. `prune_agent_tasks(keep_days=30)` and
CLI `agent-task prune --keep-days 30` expose the same owner-scoped operation. Cleanup removes only
recognized files in a validated generated task directory, its metadata/receipts, matching private
history rows and completed delivery records. User outputs and externally linked journals are preserved;
unrecognized cache files and symlink escapes refuse cleanup for review.

AC/MCP expose receipts/reconcile/prune; REST adds POST `/agent/receipts|reconcile|prune`. The task view
Actions menu exposes receipts, owner review and expired-cache cleanup. Put the review object in the
JSON editor for the selected task; the operation records it without automatically resuming.

## Preauthorized schedules and events

`manage_agent_trigger(operation, request)` supports register/list/get/enable/disable/fire/remove;
`list_agent_triggers()` is read-only. A binding captures a validated task specification, original
principal provenance and a fixed interval, cron, file-version or externally delivered event source.
The service starts its watcher only on explicit startup and restores saved bindings after restart.
Internal skills/local models use the same durable WorkQueue; external-mode tasks wait for their client.
Shared desktop acquisition still requires the idle/activity gate.

```powershell
je_auto_control agent-task trigger register examples/agent_trigger_interval.json
je_auto_control agent-task trigger list
```

The four `examples/agent_trigger_*.json` configurations use rooted file workflows; replace their
paths before registration. Intervals are at least one second; cron uses the existing five-field parser
and an explicit timezone (UTC works without optional timezone data). File notifications require a
stable rooted path/size/mtime/inode version for the configured interval. Stability is an event signal;
the workflow must still validate file completion. Existing stable files produce an initial event.

Deliver an external notification with `fire` and
`{"trigger_id": "id", "event_key": "source-event-id", "payload": {"record": 42}}`.
Keys are hashed; payloads are bounded to 64 KiB. The event becomes `inputs.event.key` and
`inputs.event.payload`, never a new tool/application/root authorization. `${event.key}` can name a
versioned output under an approved root; completion file paths use the same scoped interpolation.
Task creation, request-key deduplication and the event record commit in one transaction before delivery.
Duplicate events return the original task ID; changed data under the same event key is refused.

A binding defaults to one unfinished task (`max_pending`, at most 100). Additional events return deferred
without being acknowledged as accepted. Missed interval/cron windows coalesce; file watches retain the
latest stable version. Up to 200 bindings may be configured. Each fire refreshes its registrant's current
role; revocation, invalid scope or invalid source state disables the binding with a review reason.
Disabling/removing a binding stops future fires. Accepted service tasks keep their own lifecycle.
Deduplication tombstones survive task retention while the binding exists, preventing old notifications
from replaying an already expired task.

`submit_agent_task(spec, idempotency_key=...)` also deduplicates direct submissions per principal and
source authority store. Reusing a key with a changed specification fails. Direct keys expire with their
task metadata. AC/MCP/Builder share this argument; CLI submit accepts `--idempotency-key` and the task
view provides an optional submission key. Trigger controls are available through `AC_agent_trigger`,
`ac_agent_trigger`, authenticated POST `/agent/trigger`, CLI and the task view's Actions menu.

Roots are canonicalized before durable acceptance. Replacing a stored canonical root with a symlink
requires scope review; input checkpoints and lease maintenance refuse the changed scope. Managed
operations also block ambient `${secrets.*}` vault resolution, including parallel/DAG workers; access
to a desktop does not implicitly authorize the host vault. Existing unscoped script behavior is preserved.
Task ownership compares both user ID and source authority store. Emergency stop reaches all visible
tasks beyond the display page limit and requests cancellation before serial cleanup. View-only request
cancellation detaches the GUI; explicit Pause/Cancel remain usable during a pending request.

Bulk stop publishes stopped task states before producing a large report batch. The service persists
that publication queue and exposes `metadata.report_pending` until the report/history update is ready.
Cancelled/timed-out/failed unknown attempts can still receive an audit review without reopening their
terminal task. Local-model initialization under temporary HTTP capacity pressure stays queued.
