# Managed agent tasks

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

The private `.agent-evidence-cache/` namespace binds the complete canonical database path and a
persistent database identity. Restoring a database elsewhere does not adopt its stored journal path.
On the next action/report, the runtime atomically creates one new owned history/journal segment;
old run/journal/report references stay unchanged and historical files are not inspected or moved.
Same-path restart reuses the current segment. Status reads do not create one; task metadata reports
`artifact_cache_state` as `owned` or `historical`, without granting completion or input authority.
Retention prunes only recognized files in the current namespace and this database's expired metadata.
Historical physical files remain; current, legacy and retained historical roots stay private to exports.

Before deployment or rollback, compare exact source and artifact hashes; the unchanged version number alone does
not identify private-cache compatibility. A runtime without this private-root protection must not reuse the
newer database/cache. A reviewed restore must use matching pre-upgrade state at its recorded locations, retire
owned input first, and exclude retained newer private files from every legacy task root. Preserve uncertain
journals and avoid replay. Keep the compatible runtime if these conditions cannot be established.

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

## Host crash and workspace recovery

Input ownership writes a private, fsynced per-resource crash witness before native dispatch and input ACK. An unfinished witness blocks new owners across databases. Explicit host-only recovery requires a review note and a trusted no-held-input probe, never replays persisted input or signals persisted PIDs, and does not reconcile/resume the old task. POSIX input helpers monitor their actual parent and retire only their own live session group. Approved document handoff runs outside the input helper tree, so user applications survive normal task cleanup; bounded, preapproved focus steps wait for scoped windows. Observations also expire against a host monotonic clock. Native desktop/device acceptance remains unverified.

Use `recover_agent_target(target, note)`, `AC_agent_target_recover`, MCP `ac_agent_target_recover`, POST `/agent/recover_target`, or `agent-task recover-target TARGET NOTE`. The Agent Tasks Actions menu uses the target and crash recovery review note fields. These operations require `manage_hosts`. A live resource lock prevents recovery; Windows checks the unlocked desktop and all held keys/buttons. Other shared platforms require a trusted recovery adapter. The local-files target holds no native input. The witness records only transient owned release data, clears it after confirmed cleanup, and retains the review's actor/time/note. A corrupt or redirected witness is refused; no automatic replay or arbitrary PID cleanup occurs.

Bootstrap observations disclose no unrelated foreground controls. Only focus arguments present in the reviewed plan may bootstrap; arbitrary input continues to require an allowed foreground application. Document handoff confirms OS acceptance only; later window readiness and configured workflow read-back provide separate evidence.

## Recorded skills and reviewed repair versions

Managed skill candidates store sealed task scopes, typed explicit data slots and source-task provenance in the runtime SQLite database. Recording requires confirmed receipts and independently verified completion. Validation creates a distinct pinned task; publication requires verified completion evidence for that exact trial, an explicit review note and a compare-and-set version. Semantic selector repairs create new candidates. In-flight tasks retain their original version/digest; arbitrary pointer receipts are not guessed into semantic skills. Legacy mutable SkillLibrary behavior is preserved.

Call `manage_agent_skill(operation, request)` or `AC_agent_skill`; MCP uses `ac_agent_skill`, REST uses POST `/agent/skill`, and CLI uses `agent-task skill OP REQUEST.json`. The Agent Tasks view provides a skill operation selector, JSON request editor and Actions menu. `list_agent_skills` / `AC_agent_skill_list` inspect owner-visible candidates. Even read-only skill inspection requires drive-input authority because snapshots can contain application data. These task management operations are excluded from managed task tool scopes.

1. **record**: supply `task_id`, `name`, and optional `parameters` / `validation_criteria` / `completion_task_id`. A source must have independently verified completion, confirmed receipts, and explicit independent criteria or semantic read-back. Additional criteria augment the original checks. Raw pointer steps require authoring reviewed selectors first.
2. **preview**: supply `candidate_id` and optional literal `parameters`. Each parameter definition has a `type` (`string`, `integer`, `number`, `boolean`) and explicit JSON `paths`. Slots address existing action arguments, read-back `expect_result`, inputs or criterion values; defaults must agree, and overlaps/unknown parameters/interpolation expressions are refused. Tool names, roots, apps, target and budgets are fixed. Parameterize both a form's fill value and read-back expectation where needed.
3. **validate**: use the same candidate/parameters to create a real task. Only approved scope may execute; normal human activity, ownership, budgets and deterministic completion checks apply. Poll its task ID.
4. **accept**: supply `candidate_id`, that candidate's successful validation `task_id`, `expected_version` (zero for the first version), and a review `note`. An unrelated success, altered snapshot, unconfirmed effect, failed read-back or stale version cannot publish. Publication metadata records actor/note/trial.
5. **run**: supply `skill_id`, an explicit positive `version`, and optional `parameters`. Task metadata contains a service-bound `skill_pin` with version and digest. New publications never alter queued/running tasks.
6. **repair**: supply an accepted `candidate_id`, a review `note`, and `changes` containing `path` / `value`. Only existing selector `name`, `role` or `automation_id` values may change. Validate the resulting candidate and explicitly accept it against the current version. No automatic overwrite, tool/root expansion or silent locator application occurs.

For a stopped source, explicitly select `completion_task_id` on `record`, keeping `task_id`
equal to the original workflow. Its actual confirmed semantic actions, not the reader's empty plan,
become the draft. An ordinary external workflow needs no pre-existing validation-trial row. Private
reader admission, exact derived scope, real ancestry, independent completion/retirement and current
caller/source-owner/reviewer authority are required. Source/proof checks and candidate insertion use
one SQLite write transaction, with post-write proof and live authority rechecks; failures leave no
draft. `provenance.completion_review` is historical IDs/hashes and grants no live authority after reader
retention. The new draft still requires its own exact validation trial; added `validation_criteria`
cannot inherit the old reader's result. Source state and receipts stay intact, with no replay or
fabricated trial. GUI Actions prepare the request without recording or publishing.

If a validation trial is stopped after all its actions are confirmed, `accept` also accepts an optional
`completion_task_id` naming a separately reviewed and successfully finished permanent read-only child.
Keep `task_id` equal to the original real validation trial. Its candidate/spec hash/pin must match;
the reader must have exact derived criteria, confirmed retirement and private admission plus a real
recovery chain (at most sixteen read-only links). Caller, source/effect owners and actual reviewer stay
live through the publication transaction. Version/publication/adoption writes are atomic; the original
trial remains stopped. `publication.task_id` keeps its original meaning and optional
`publication.completion_review` records historical reader IDs/hashes. Reader evidence may expire after
publication; an unpublished adoption cannot use expired/missing evidence. The GUI Actions example
prepares the explicit request without publishing.

For a partially executed validation trial, first call `manage_agent_skill("review_execution", request)`
with `candidate_id`, the original `task_id` and a separate final `execution_task_id`. Then explicitly
`accept` those same IDs with the returned `execution_review`, `expected_version` and a nonempty `note`.
At most sixteen actual executable recovery links must confirm the complete original semantic plan;
a successful different remainder is insufficient. Comparison includes JSON types, captured values,
expectations and grounding, without restoring captures or rebuilding historical UI state. Each task
retains its existing limits and separate approval. Current callers, all owners and actual admission
reviewers must remain authorized. Version, publication and historical `publication.execution_review`
commit atomically, with post-write evidence/authority checks. The original stays stopped and retains
`publication.task_id`; no recovery child becomes a fabricated validation trial. An optional
`completion_task_id` must verify the final executable effect and is nested in this execution audit.
Expired evidence cannot approve an unpublished candidate. Two Actions examples prepare review and
accept requests without executing them; `agent_skill_execution_review.json` and
`agent_skill_execution_accept.json` are editable request examples.

Use `je_auto_control agent-task skill review_execution examples/agent_skill_execution_review.json`
to inspect the passive proof. Copy its token into `agent_skill_execution_accept.json`, review the IDs,
version and note, then explicitly run `agent-task skill accept` with that request file. An optional
`completion_task_id` goes in both requests and must belong to the final executable successor.
Review never probes a target or changes task state. It does not authorize input or transfer an old
caller-owned child: ordinary ownership checks still apply to every chain participant.


The eight `examples/agent_skill_*.json` files are editable request examples, not executable tasks. `agent_skill_completion_accept.json` shows explicit read-only publication evidence; `agent_skill_completion_record.json` prepares stopped-source recording. Skill definitions and publication records remain in the library when transient task caches expire; accepting an unpublished candidate still needs its retained verified task evidence. Native application acceptance remains separate from the deterministic fake-target regression evidence.

## Origin path policy lifetime

Accepted tasks, trigger templates and skill trials retain live origin policy references. A private witness contains only current root ceilings; missing/revoked/corrupt witnesses fail closed. Authenticated local HTTP forwards the current caller's additional restrictive ceiling without granting identity or capability. Every operation checkpoint and lease maintenance rechecks roots. MCP client roots and asynchronous roots refresh are session-local; stale replies cannot renew retired authorities. Static host policies persist until replacement, while retiring client-supplied root authority revokes its references. HTTP client roots do not overwrite the shared resource provider's configured workspace. Workers/maintenance run in fresh contexts, shutdown tracks actual in-flight deliveries before lease acquisition, and unstarted queued work remains durable.

`JE_AUTOCONTROL_MCP_PATH_ROOTS` retains configured static ceilings. With `JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT`, each MCP session has its own client root set; unknown roots deny file access, removal takes effect on the next checkpoint, and session/server retirement revokes the client authority. Replacing `MCPServer.argument_policy` retires its previous witnesses. An old asynchronous roots reply cannot recreate the dropped policy. A revoked task keeps its receipts; re-authorize a new task rather than silently editing its original scope. A paused task reports that its scope needs review.

The origin header is an additional ceiling on an authenticated runtime call, never a capability grant. Origin references accumulate by intersection and cannot enlarge accepted roots. They are retained in trigger/skill task snapshots, checked again before execution and across runtime restart. Closing the GUI view still detaches without cancelling service work; explicitly retiring a client-supplied path authority has different authorization consequences. Scope enforcement remains within the managed runtime, not an OS sandbox.

Legacy MCP wrappers and parallel/local DAG workers preserve the origin intersection. Metadata is resolved lazily for task-aware dispatch and worker handoff, and a failed policy publication invalidates its previous witness.

## Observation-local point actions

Managed action references resolve observation-local element centers or rendered image pixels into native coordinates only after identity/freshness/fingerprint checks. Explicit coordinates cannot conflict with a reference; invalid/disabled/out-of-frame targets fail before preparing an action. SQLite atomically links grounding metadata to each prepared receipt, including requested arguments, frame ID/hash and non-image geometry; reports expose the same provenance. Local-model schemas carry an observed_target extension while legacy executor signatures stay unchanged. AgentObservationStale round-trips over local HTTP, and bounded pre-dispatch replanning requires an adapter's explicit can_reobserve guarantee. Native adapters deny it while any owned input or unsettled operation remains. Native acceptance stays unverified.

Use `act_agent_task(task_id, action)` with the latest `observation_id`. Add exactly one `reference`: `{"element_index": 0}` or `{"image_point": [120, 80]}`. Keep real tool arguments such as `mouse_keycode="left"`; omit `x`/`y` when using a reference. Supported point commands are `AC_click_mouse`, `AC_set_mouse_position` and `AC_press_mouse`. Element bounds are native coordinates; image points use the displayed image's pixels and require trusted redacted geometry. The host handles scale/origin conversion; it does not accept caller-supplied transforms or a different image.

The same action object works through Python, AC/MCP/REST, CLI `agent-task act`, and Script Builder's `AC_agent_task_act` action parameter. Two editable request examples are `agent_observed_click.json` and `agent_image_click.json`. Local Ollama tools expose `observed_target`; its values become the same host reference rather than extra executor keyword arguments. The prompt preserves image geometry separately from image bytes, and cloned schemas do not mutate shared legacy tool definitions.

`get_agent_task_receipts` includes `grounding`: original arguments, observation ID/fingerprint, target identity, selected element metadata and image geometry where available. Actual receipt arguments record the resolved native coordinates. Frame bytes remain ephemeral under the existing image persistence rules. Grounding is committed with preparation, survives recovery, and is deleted with its owned action metadata.

A missing/expired/changed observation raises `AgentObservationStale` before dispatch. Local agents may reobserve and replan up to the configured retry budget, never replay a dispatched effect. Adapters must explicitly guarantee `can_reobserve`; held input, unsettled native work, human takeover, ambiguous effects and unknown custom adapters require the existing stop/review path. Explicit legacy coordinates retain their existing interpretation.

Emergency stop batch-reads compact task snapshots. metadata.details_deferred indicates that full artifact/history details remain available through get_agent_task; cancellation is acknowledged without scanning each task cache.

Native helper protocol 1 includes a read-only bootstrap handshake bounded to fifteen seconds. Configure/observe/perform retain their configured action deadlines; cleanup retains its own bound and ownership cannot transfer before retirement. Image-point grounding verifies actual bounded JPEG pixels against the advertised rendered dimensions.

Managed mouse presses normalize button ownership and confirm the actual cursor before input. Windows pointer checks reject foreign overlays. Vision renders the exact scoped window into cleared private GDI storage, rejects geometry changes and releases resources even on rendering/read failure. There is no desktop-crop fallback. Fake-native tests cover these paths; native acceptance remains unverified.

Native implementation references: [PrintWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-printwindow), [GetDIBits](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-getdibits), and [WindowFromPoint](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-windowfrompoint).

The Agent tasks view groups task scope, workflow settings, triggers, skills and recovery into separate pages. Its observation page lists read-only elements and shows a validated, strictly masked JPEG at one rendered pixel per logical widget pixel. Selecting a row or image point only edits a frame-bound action request; Actions -> Perform observed action sends it through the shared task API. Switching tasks clears the preview, and late replies cannot replace the selected task. A new frame requires reselection before an old reference can be sent. Closing the view only detaches its requests.

Managed workflow waits (workflow_wait / AC_workflow_wait) poll only exact scoped control values or states, with cancellation and a deadline capped by the action budget (default five seconds, maximum sixty). They never replay a write or submit. Fixed skills require all previous receipts to match the pinned sequence before continuing, including after resume; autonomous model loops retain stuck detection. New form/transfer drafts refuse an already-matching confirmation before submit and wait for a fresh transition afterward. Batch configurations may provide new_record_selector to reset each record; confirmations prove the configured UI transition, and transaction-specific receipt values should be used when available. Archive drafts also re-read the exact reviewed manifest and current file digests at finish (one-megabyte manifest and sixty-four-megabyte total evidence limit).

AgentHumanReview identifies an unsaved-content or unknown-dialog gate. It persists waiting_user and retires input ownership, including for external observe requests; explicit resume still rechecks the gate. Windows detection uses native dialog/disabled-owner evidence and known English/Chinese/Japanese unsaved labels. Workspace tasks also pause for leading/trailing asterisks in document titles; a window entry may supply unsaved_selector and unsaved_value for an application-specific indicator before layout changes. These checks do not infer every application's dirty state. Recognized standard file pickers use a context-local driver on the existing AC_handle_file_dialog executor: exact unique title, same PID, confirmed foreground and canonical rooted absolute paths. UIA control patterns must belong to the actual owned root window, even when another window shares its PID. All behavior has fake-native/loopback coverage; actual platform acceptance remains unverified.

Host-reviewed targets use AgentTargetProfile and manage_agent_target (AC_agent_target; register/get/disable/enable). Names and configuration are immutable; desktop/file adapters are currently supported, and unimplemented kinds or executable settings are rejected. Tasks pin the host profile digest and cannot expand its tools, applications, roots or network origins. Availability persists across restart and is checked at dispatch; disabling requests pause/cleanup, while enabling requires explicit task resume. list_agent_targets / AC_agent_target_list / CLI agent-task targets expose passive metadata with readiness=not_probed and native_evidence=not_recorded. Full configuration requires manage_hosts; CLI agent-task target and the GUI Host targets page use the same service. Live anonymous MCP tool sessions have operator authority across direct and legacy wrapper calls; MCP host management requires an authenticated administrator. Trusted direct Python callers remain unchanged. Browser automation belongs to WebRunner (je_web_runner), with D:/Codes/WebRunner as the development source; the managed browser adapter is not part of these target registrations.

Existing browser automation, including open_path(URL) and AC_open_path, delegates to WebRunner (Python package je_web_runner). URL plans now report backend=je_web_runner; callers inspecting the previous webbrowser descriptor should use the new value. Signatures and local-file opening stay compatible. URL execution requires the configured WebRunner project and propagates WebRunnerBridgeError when unavailable, without opening an OS browser as a fallback. The development source is D:/Codes/WebRunner. Planning and injected-opener tests remain usable without that package; browser protocol support is determined by WebRunner and its selected browser. Existing dedicated browser GUI/MCP/AC paths and recorded WR_* actions share the same bridge.

## Explicit local DAG evidence handoffs

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

## Renew read-only completion authorization explicitly

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
Browser/remote read-only providers, cross-host handoffs, actual application
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
consent automatically. Cross-host handoff, browser/remote readers, actual application/device
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

Cross-host handoffs, browser/remote readers, actual application/device providers, deferred native
and twenty-four-hour acceptance, and unresolved HTTP409/bootstrap issues remain in `Progress.md`.


Windows persistent presence uses a lazy runtime-owned source reference and one fixed host capability
per input-helper lifetime. The supported-session guard queries the current active physical console,
WTS local protocol/remote/connection state and remote/shadow indicators before observation and each
fresh sample. Reader checks and its independent0.25second watchdog permanently fence source loss.
Actual input locks, journals and release-only ACK cleanup remain separate; cleanup failure retains
ownership for explicit retry. Takeover callbacks are pinned to the actual channel/control lease and
perform negative-only pause without depending on ambient caller authority. Passive target summaries
expose coarse presence/cleanup classes with native_evidence=not_recorded, no probes or capability IDs.
File/browser/custom reviewed workers stay inert. Native/browser/device/24hour acceptance stays deferred;
see Progress.md and the persistent-windows-presence spec/plan. Bounded JSON/budget primitives reside in
wire_data.py and keep their models reexports, separating owned transports from runtime/model cycles.

Installed wheel and source distributions include the REST Dashboard and Swagger HTML, CSS and
JavaScript resources. The same localhost REST routes and authentication rules apply to an
installed package; serving static pages grants no task or desktop input authority.
