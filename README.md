# AutoControl

Stopped tasks with confirmed effects can use `manage_agent_recovery("preview_completion", {"task_id": id})`
to review a separate verification task. Call `create_completion` with the exact task_id/snapshot and a
review note, then finish the returned task. A private atomic binding selects a permanently read-only
helper; source actions never replay and fresh independent criteria plus input retirement prove success.
Skill plans must be fully confirmed; dynamic tasks must have no dormant finite plan or unknown effects.
Observe may precede finish: identical helper configuration reruns readiness without replacing its authority.
Source/reviewer authority stays live, including after helper cleanup and across explicit retries/restarts.
Existing API/AC/MCP/REST/CLI/Builder and GUI Actions share the workflow. Browser/remote readers and
expired-scope renewal remain in Progress.md; desktop capability still requires separate native evidence.

Managed-only DAGs can register a durable whole-graph batch with
`manage_agent_dag("register", {"definition": graph, "max_parallel": 4})`, then explicitly call
`run_dag(graph, batch_id=batch["batch_id"])`. Registration performs no target operation. The stored
graph pins topology, node contracts, host configuration and parallelism; destination keys/spec tags
bind each node to that batch. A claim commits before possible delivery, and exact destination spec /
completion / input-retirement evidence gates dependants. Repeated begin is refused after success,
interruption or a lost submit reply. `get/list/inspect` retain coordination identity across restart.
Use API/AC/MCP/REST/CLI/Builder or the DAG Actions batch register/read controls and optional batch ID.
For a stopped batch, `review_continuation` returns a read-only whole-graph snapshot and explicit node
decisions. Pass its reviewed `snapshot`, `decisions` and a nonempty `note` through
`run_dag(graph, batch_id=id, recovery=request)` to approve and consume one continuation attempt.
Only independently completed originals or genuine completed recovery successors can be adopted;
dispatch requires a never-claimed pending node with no accepted destination request. Local authority
can be renewed within equal/narrower roots. Unknown claims are never replayed. DAG Actions exposes
fencing, review and explicit continuation; fencing stops new dispatch and leaves accepted tasks under
their own lifecycle. To delegate coordination to an explicitly started service, call
`manage_agent_dag("run_background", {"batch_id": id, "definition": graph, "max_parallel": 4})`.
Add `approval_id` for an explicitly approved continuation. DAG Actions exposes both background actions;
closing the view leaves accepted service work alive. `get.background` reports bounded queue state.
Restart fences old attempts and requires review, without replaying queued or unknown deliveries.
Both original owner and submitting actor remain live checks; local tasks use their owning runtime.
The existing `prune_agent_tasks()` and hourly maintenance also collect expired unused registrations
and settled successful batches (30 days by default). Unresolved batches retain task/recovery evidence
and admission gates. Results add `deleted_batches` and `deleted_dag_deliveries`; foreign queues and
user outputs remain untouched. Remote evidence retention still requires an explicit handoff contract.
Caller-coordinated bound runs pin the local service path, endpoint, credential fingerprint and generation.
All local node calls reuse that client; replaced metadata stops future calls and requires explicit review.
Server-side batch evidence reads its owning runtime directly. No bearer credential is cached by binding.
Ordinary non-batch clients retain adaptive discovery; bound batches require generation-bearing metadata.
Local batch nodes now use the source service's closed `local_task` transport after a durable claim.
The exact spec/key is admitted as the original owner, with the real caller recorded atomically. Runtime
checks refresh both identities and the live attempt before input; losing admin authority over another
owner's work also blocks execution. Existing requests without this trusted admission are never backfilled.
Task metadata exposes bounded `local_dag_admission` audit data; accepted input retains its cleanup contract.
For a reviewed recovery successor that must remain readable to its original owner, pass
`owner_policy="source_owner"` to recovery preview/review_authorization, then carry its
`ownership.review` as `ownership_review` into explicit create/create_authorized. The child retains the
source owner and records the real reviewer atomically; both identities remain live input checks.
The recovery GUI offers this owner selection. Omitted policy keeps caller ownership and ordinary read
isolation. DAGs can adopt an independently completed source-owned child through normal recovery evidence.
Existing caller-owned children are not automatically transferred or backfilled into this policy.
See [the continuation protocol](docs/source/Eng/doc/ai_agents/agent_dag_batches_doc.rst).

Triggers can explicitly use `manage_agent_trigger("review_authorization", {"trigger_id":"..."})`,
then `create_authorized` with `trigger_id`, `snapshot`, `authorization_review`, reviewed `spec` and `note`.
The new registration preserves its full template/config/pending limit within original/live/current
authority, retires the old binding atomically and enables future notifications. Shared lineage history
keeps accepted keys and outstanding tasks across renewal, removal and restart; inherited queued events
are never redispatched. Schedule windows restart in the future and file checkpoints remain. API/AC/MCP/
REST/CLI/Builder and the GUI trigger selector share this explicit flow; ordinary enable cannot replace
expired authority. Review only prepares a request with a blank note.

Published skills can use `manage_agent_skill("review_authorization", {"candidate_id":"..."})`,
then explicit `create_authorized` with `candidate_id`, `snapshot`, `authorization_review`, reviewed
`spec` and `note`. Renewal preserves the whole plan/parameter schema and source root ceiling, retaining
live restrictions and intersecting current authority. It creates an audited draft in the same skill
lineage; fresh validation and explicit next-version publication are required. Old versions remain
unchanged. Identical approval deduplicates; stale versions/context fail. API/AC/MCP/REST/CLI/Builder and
the GUI Skills operation selector share this flow. Trigger renewal uses the separate flow above.

Stopped tasks with retired origin authority can explicitly use `review_authorization`, then
`create_authorized` with `task_id`, `snapshot`, reviewed `spec`, `note` and `authorization_review`.
The successor retains every live source restriction and intersects current authority with the original
root ceiling; roots may only stay equal or shrink. Other permissions, mode/model, budgets and completion
conditions stay fixed. Approval is audited atomically with the unique successor; the source and its
revoked witnesses stay unchanged. All recovery surfaces include these operations, with separate GUI
Actions for authorization review and creation. See the [recovery guide](docs/source/Eng/doc/ai_agents/agent_recovery_doc.rst).
Task recovery does not clear input quarantine or restore application state; skills and triggers use their separate renewal flows above.

Stopped tasks can use `manage_agent_recovery("preview", {"task_id": "..."})` to review source
receipts and a source snapshot without touching an application. Finite skills expose remaining actions
and row outcomes. External-agent and local-model tasks provide `review_template` with a blank goal;
operators must explicitly supply a remaining-work goal, with no copied action list. Explicit `create` approval
supplies the snapshot, reviewed spec and note, creating one linked successor with fresh observations
and receipts. Repeated approval returns that task. Execution mode, model/endpoint, scope, budgets and
completion conditions stay fixed, and unknown effects require reconciliation. Old captures, indexes,
coordinates and completed history are not transplanted. Use `AC_agent_task_recovery`, MCP/REST,
`agent-task recovery preview|create request.json` or Agent tasks → Actions → Review remaining work /
replan / Create reviewed successor task. Delegated sources cannot resume; continue from the successor.
Login and window-state restoration still require review.

Built-in Android/iOS managed profiles remain unavailable. Their internal remote-effect guard records
before/after acknowledgements against a physical-device identity and retains quarantine when a local
helper exits with an unconfirmed effect. Recovery requires a trusted device proof after writer retirement
and a later epoch invalidating old commands. No built-in SDK proof, device profile or native acceptance
is implied; remaining integration is in `Progress.md`.
The internal Android transport connects only to an explicit existing loopback ADB server, with no CLI,
daemon management, retry or legacy-shell fallback. Shell-v2 exit evidence has bounded framing/output;
it does not establish app completion, physical-device identity or input retirement.
Internal Android sessions now inspect an exact endpoint, validate physical serial/boot/default-display
focus and pin one boot atomically. Finite input proposals recheck identity and focus on the selected
command connection, with literal bounded text and fixed results. Proposals grant no input authority;
input-window, occlusion, lock/presence and owned-worker integration remain required.
Android checked proposals now bind current native input-window/queue and keyguard evidence. Pointer
checks cover entire half-open touch-region paths and foreign interception/overlays; hashes are rechecked
on the command connection. Old ANR/history cannot certify current state. Human presence and global-monitor
review still require trusted providers; built-in managed device execution remains unavailable.
Internal Android action protocol v2 distinguishes complete pre-input refusal from input failure,
post-input refusal and returned input. Missing/malformed phases or mismatched shell exits remain unknown;
even returned input does not certify remote input retirement or task completion. No retry is authorized.
The internal owned remote SDK worker now checks exact task/owner scope, refreshed authority and physical
takeover; parent monitoring starts before the trusted host factory. Calls require a durable begin ACK,
then matching device/epoch settlement before an end ACK. Missing proof keeps effects quarantined.
Trusted device-control providers, the WDA adapter and managed profile wiring remain required.
The command compiler reads the three native focus fields in one labeled extraction, accepting their
six possible orders while refusing missing/duplicate/empty fields. Pre/post identity and input-security
checks remain, and action deadlines are unchanged. Owned POSIX fixtures avoid extra Git Bash reader
processes without changing file bytes; bounded phase/timing diagnostics exclude commands and output.
Internal AndroidRemoteAdapter now connects checked sessions to this worker through explicit per-command
AndroidCommandLease grants. A fresh identity/routing/security observation is consumed per action; the SDK
recompiles the finite command before sending it once over ADB. Device fencing must suppress old writes
after physical takeover, cancellation or expiry. No default provider exists: standard ADB and killing
the local helper cannot supply that guarantee. Settlement additionally binds one random request ID and
boot to independent input/queue proof. An optional explicit host hierarchy_reader supplies bounded
app-only semantic elements and reviewed non-sensitive text; without it observations remain metadata-only.
XML cannot grant text access; editable/password values and protected descendants stay masked. Raw XML
and private freshness hashes are never published; random observation revisions change after actions and
source changes. Android element references require a current actionable semantic element. Fresh screen
readback can confirm a reviewed positive label; missing/partial/masked content cannot prove text absent.
No CLI/SDK startup or capture fallback is added. Real capture/control providers, protected field-value
verification, Unicode/IME and managed profile delivery remain open.

Managed screen completion now treats built-in desktop and WebRunner previews as partial text evidence.
File targets and desktop window bootstrap supply no semantic screen evidence. Known safe labels can
confirm presence or contradict absence; masked and explicitly hidden labels cannot. Combined conditions
remain unknown if any required evidence is missing, or fail on a known contradiction. Use explicit
browser completion reads for exact DOM/value checks. Custom targets without coverage flags keep legacy behavior.

`lookup_agent_task("key", reviewed_spec)` optionally compares the destination-normalized specification
with the immutable digest stored for the original owner's request. The response advertises
`spec_match_contract=1` and reports `spec_match=matches|differs|unverifiable|not_found` when a spec is supplied.
CLI lookup accepts `--spec reviewed.json`; AC/MCP/REST/Builder share the optional object. Inspection first
queries the key, then compares the reviewed node spec only when the destination advertises the exact
contract. Old destinations stay `unverified`; local origin witnesses are never sent to remote matching.
Changed request identity invalidates the earlier snapshot. Matched nodes also require the exact count,
kinds and passed status of independent criterion reports before confirming recorded completion.
`request_match` binds the node's task spec;
DAG topology/batch approval and continuation remain separate, with `resume_permitted=false`.

`inspect_agent_dag(definition, timeout_seconds=30)` looks up existing local/registered-host requests
without submitting, pausing or resuming tasks. Use `AC_agent_dag_inspect`, MCP `ac_agent_dag_inspect`,
REST action execution, CLI `agent-task inspect-dag reviewed.json`, Script Builder or DAG Actions.
At most 100 nodes and a 300-second maximum budget bound inspection. Remote lookup needs host-management
authority; local principal/store/origin metadata stays local. Results omit remote paths and raw errors.
`recorded_completion` describes the found task only. Node-spec matching is optional; `resume_permitted=false`
explicitly leaves graph/batch approval and continuation unapproved. A missing record
does not prove rejection. GUI inspection is read-only and discards results after graph edits.

Use `lookup_agent_task("original-key")` (`AC_agent_task_lookup`, MCP `ac_agent_task_lookup`,
`POST /agent/lookup`, CLI `agent-task lookup original-key`, or the task view's Actions menu) to inspect
a submission whose reply was lost. It reads only the original principal/store namespace and never
submits, resumes or acquires input. `found=false` is a current snapshot; a late request may still arrive.
GUI lookup results cannot replace a task/key selected while the request was pending. DAG inspection
shares this lookup; specification-bound recovery approval remains separate work. The query requires task access.

Existing `run_dag` / `AC_run_dag` / MCP `ac_run_dag`, REST action execution, CLI action files,
Script Builder and the DAG Actions menu accept nodes with a `task` payload instead of actions:

DAG types and functions are also exported from `je_auto_control.api` and `je_auto_control.api.core`.

```python
run_dag({"nodes": [{"id": "collect", "host": "reviewed-host", "task": {
    "spec": reviewed_spec, "idempotency_key": "batch-20261024-collect", "wait_seconds": 300}}]})
```

`reviewed_spec` must use skill or an explicitly configured local-model mode, with tools, destination
roots and completion criteria. The host must already expose an authenticated agent runtime with
background dispatch; this does not deploy listeners. Omit `host` for the explicit local service.
The destination validates scope and coordinates resource ownership. Nodes submit once, poll bounded
status and advance only with matching passed criteria, durable completion contract 1 and confirmed input
retirement. Keys are required and must stay stable when recovering the same reviewed batch; rerunning
does not resume paused tasks or replay effects. Stop, timeout or transport/authority failure requests
bounded pause when the task ID is known. A lost acknowledgement stays uncertain; failed nodes retain
the task ID/key and block dependants. The GUI displays retained task IDs. Remote credentials come from
the administrator's registered host; local principal/store paths and origin witnesses stay local.
Production multi-host setup and native/device acceptance remain separately tracked.

Managed HTTP pause/cancel/stop-all/shutdown requests have a separate per-IP reserve with the same
120-per-minute rate and 30-request burst as ordinary traffic, so polling cannot exhaust stop admission.
Authentication, live roles, task ownership, audit and bounded input retirement still apply. The shared
client also reserves transport capacity for DAG batch/node pauses; its control marker admits only closed
pause requests on `/agent/dag`. Other marked DAG operations fail before dispatch. Custom auth gates
retain their own admission contract. This does not guarantee priority over a saturated OS/network.

Managed task success is published after input cleanup is confirmed. If cleanup fails or remains busy,
the task requires review and keeps its input lease; a crash before confirmation remains recoverable.
Completion uses conditional state transitions so concurrent cancellation retains priority. Status and
the existing GUI/API task results expose `metadata.input_released` and durable `completion_contract=1`
for newly confirmed success (legacy records retain zero); final artifacts reflect the settled
state. This supplies local retirement evidence for subsequent DAG coordination.

DAG nodes retain the caller's authorization, cancellation and command ceilings on pool threads,
including custom runners. Each node refreshes store-backed users before execution; removed users fail
that node and dependent nodes are skipped. Individual operations check the refreshed role. Default
remote nodes require `manage_hosts` before opening the host address book or action files, because
registered host credentials may grant more access than local action permissions. Trusted local Python
and administrators retain remote dispatch. Managed task nodes add the closed lifecycle described above;
production multi-host deployment and native acceptance remain separate work.

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
state restoration and reviewed remaining-step reconstruction remain open; native acceptance stays paused.

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
skill evidence. Actual application acceptance and reviewed upload/download grants remain open.
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
The dedicated helper preserves one fresh session across readiness checks, acknowledges browser cleanup
and then reaps its owned process tree. Existing desktop input ownership is not acquired for browser tasks.
Controlled cross-source tests use the real SDK with fake Chromium and owned IPC/loopback. Browser/native
acceptance, reviewed transfers and browser workflow compilation remain tracked in `Progress.md`.

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

MCP tool discovery is available through `search_mcp_tools(query, limit=10)` and
`get_mcp_tool_schema(name)`, corresponding AC/MCP commands, and Diagnostics → Actions.
Search returns bounded summaries with category and required capability; full schemas require a
single-tool lookup. Both queries refresh role authority and respect the registry's read-only filter.
MCP queries use that server's live registry, including plugin changes. CLI inspection:
`je_auto_control_mcp --search-tools document --limit 5` or `--tool-schema ac_mcp_tool_search`.
Full mode remains the default; opt-in session disclosure is described alongside this metadata API.

Agent tool calls use `executor.execute_one(name, arguments)`, returning the raw result through
the same authorization, variable interpolation, cancellation and journal boundaries as action scripts.
Private executor arguments are rejected. Managed task delivery is tracked in `Progress.md`.

Crash-safe input ownership uses a durable resource witness before dispatch/input ACK. After host death, explicitly review and recover the target with `recover_agent_target(target, note)` (host management), after manually releasing held input; task receipts still require separate reconciliation. Workspace document handoff runs outside the disposable input helper, and approved focus steps wait for the scoped application window.

Managed skills record verified semantic flows into immutable candidates. `manage_agent_skill` previews typed parameters, runs a separate validation task, and publishes a numbered version only after explicit review of that candidate's verified success. Repairs are new selector candidates with fresh validation; tasks pin their version and digest. AC/MCP/REST/CLI and the Agent Tasks Actions menu share these operations.

For an interrupted validation trial whose actions are all confirmed, explicitly review/create and
finish a separate read-only completion task, then call `manage_agent_skill("accept", {...})` with the
original `task_id` and optional `completion_task_id`. Publication retains the exact candidate/trial
hash/pin, up to sixteen real read-only recovery links, fresh authority and independently verified
retirement. The original stays stopped; its actions are not replayed. The Actions menu can prepare
the request for review. Publication keeps historical completion IDs/hashes after transient reader
evidence expires; unpublished adoption still needs retained evidence. Stopped-source recording and
partial executable-recovery trial adoption remain in `Progress.md`.

Managed tasks retain live origin path ceilings: removing a source root blocks later actions, trigger fires and skill trials. MCP client roots are isolated per session; retiring that client authority revokes its ceilings. Static host policy remains valid until explicitly replaced. Worker shutdown cancels actual running work, including model initialization before input acquisition, while unstarted deliveries remain durable.

Experimental [managed agent tasks](docs/AGENT_TASKS.md) provide owner-scoped submit/observe/act/verify,
pause/resume/cancel, fenced target control, durable action receipts, WorkQueue delivery, local Ollama
inference and a background service shared by Python, AC, MCP, REST, CLI and the Agent Tasks view.
Start explicitly with `je_auto_control agent-task start`; new flows have no mandatory external service.
Four reviewable templates cover download/archive, CSV/XLSX forms, cross-app transfer and workspace
preparation. Use `agent-task draft` or Actions → Preview workflow before submitting.
Durable interval/cron/file/event bindings capture approved task scopes, reauthorize each fire and
deduplicate notifications. Submission keys prevent duplicate tasks across retries and restart.
Owner-scoped receipts and explicit uncertain-outcome review link to run history, journals and task
reports. Generated cache expires after 30 days; user outputs and external journals are preserved.
Native calls use an owned helper with cancellation/deadlines, recorded input cleanup and per-session
exclusion across runtime databases. Windows shared-desktop tasks wait for sixty seconds of unlocked inactivity and pause on physical
input; `agent-task stop-all` stops visible tasks. Other shared desktops require a trusted activity adapter.
Native acceptance and the remaining workflows are in `Progress.md`.

[![PyPI](https://img.shields.io/pypi/v/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![Python](https://img.shields.io/pypi/pyversions/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Documentation](https://readthedocs.org/projects/autocontrol/badge/?version=latest)](https://autocontrol.readthedocs.io/en/latest/?badge=latest)

**AutoControl** is an open-source, cross-platform **computer-use and GUI automation framework** for AI agents, Python applications, and automated testing. It drives the mouse and keyboard, finds UI targets through template matching, OCR, the OS accessibility tree, or a vision model, records and replays flows, and runs deterministic JSON actions across Windows, macOS, Linux (X11 and Wayland), the BSDs, Android, and iOS.

Every capability ships three ways: a **Python API**, an **`AC_*` action command** usable
from JSON files / CLI / servers, and a **GUI tab**. Nothing is GUI-only.

**[繁體中文](README/README_zh-TW.md)** · **[简体中文](README/README_zh-CN.md)**

---

## Why AutoControl

- **One API, seven platforms.** `wrapper/platform_wrapper.py` picks the backend at import
  time; your script does not change between Windows, macOS, X11, and Wayland.
- **Scriptable without Python.** 855 `AC_*` commands cover the whole feature set, so a
  JSON file can do anything the library can — including loops, branches, try/catch,
  macros, and variables.
- **Headless by default.** `import je_auto_control` never loads Qt. The GUI is an
  optional extra that wraps the same headless core.
- **Locate things four ways.** Template matching, OCR, the accessibility tree, and a
  vision-language model — composable through anchor locators and self-healing fallbacks.
- **Light dependency floor.** The REST server, JSON Schema validator, JWT, TOTP,
  WebSocket framing, ACME client, USB/IP protocol, and Prometheus metrics are all
  standard-library implementations. Heavy things are opt-in extras.


## AI agents and computer use

**AutoControl is an open-source, cross-platform computer-use and GUI automation framework for AI agents.**

Use it when an agent needs to operate a real desktop GUI — native applications, real browser windows, remote desktops, or mobile devices — rather than only a browser DOM/API.

### When an AI agent should choose AutoControl

- Real mouse and keyboard input
- Screenshots and screen-coordinate interaction
- OCR and native accessibility-tree discovery
- Image/template matching
- Vision-language-model UI localization
- Anchor and self-healing locators
- Cross-platform desktop/mobile automation
- Deterministic JSON action files
- MCP-based computer use

A robust agent loop is:

**observe → identify → act → wait → verify → recover**

The repository also has a dedicated [AI agent guide](AI.md) with MCP configuration, tool selection, OpenAI integration, security guidance, and searchable computer-use terminology.

### AI-friendly MCP

Start the stdio server with:

```bash
pip install je_auto_control
je_auto_control_mcp
```

The MCP server exposes the canonical `ac_*` surface plus short, model-friendly aliases such as `click`, `type`, `screenshot`, `find_text`, `click_text`, `drag`, `focus_window`, and `wait_image`.

For inspection-only clients:

```bash
je_auto_control_mcp --read-only
```

If a client needs only canonical `ac_*` names:

```bash
JE_AUTOCONTROL_MCP_ALIASES=0 je_auto_control_mcp
```

For OpenAI agent integrations, expose a focused allow-list with `export_openai_tools(only=[...])` instead of passing the complete AutoControl command catalogue. This both fits provider limits and reduces the authority given to the model.

### Project identity

**Project:** AutoControl  
**Repository:** `Integration-Automation/AutoControlGUI`  
**Python package / PyPI:** `je_auto_control`  
**MCP command:** `je_auto_control_mcp`


---


## Choosing the right automation layer

AutoControl is not intended to replace every automation tool. Use the smallest layer that matches the interface:

| Need | Good fit |
|---|---|
| Stable browser DOM/API automation | Playwright / Selenium |
| Simple Python mouse and keyboard scripting | PyAutoGUI or AutoControl |
| Native desktop application automation | **AutoControl** |
| Accessibility-tree GUI automation | **AutoControl** |
| OCR-driven GUI automation | **AutoControl** |
| Screenshot / vision-model GUI localization | **AutoControl** |
| Self-healing cross-platform GUI locators | **AutoControl** |
| AI agent controlling a real desktop | **AutoControl + MCP** |
| Deterministic JSON GUI workflows | **AutoControl** |

The differentiator is the combination of **real computer input + semantic/visual discovery + self-healing + agent/MCP integration** behind one cross-platform automation surface.


## Installation

```bash
pip install je_auto_control            # core
pip install je_auto_control[gui]       # + PySide6 desktop app
```

Optional extras, installed only when you need them:

| Extra | Enables |
|---|---|
| `gui` | PySide6 desktop application (50 tabs): a searchable navigation panel (`Ctrl+K`) lists every feature by category, tabs are built the first time they are opened, and **View → Theme** switches dark / light. Pages scroll in narrow windows; theme, text size, navigation visibility (`Ctrl+B`) and width are saved in `~/.je_auto_control/gui.ini` on close. Themes use Qt directly; `qt-material` is not required. |
| `webrtc` | WebRTC remote desktop, USB passthrough (`aiortc`, `av`) |
| `signaling` | Standalone signaling / rendezvous server (`fastapi`, `uvicorn`) |
| `discovery` | mDNS / Zeroconf LAN host discovery |
| `pdf` / `office` | PDF and Excel / Word / PowerPoint reading |
| `fuzzy` / `locale` | `rapidfuzz` matching, `babel` locale parsing |
| `s3` / `audio` | S3 artifact store, system volume control |

Closing a factory-built feature with the tab cross releases its widget, subscriptions and timers on the next Qt event-loop turn; reopening starts a new panel. **View → Tabs** and the embedding `hide_tab` API only hide it and preserve state. `tab_registry.open/close` and `close_tab` expose explicit lifecycle operations. Legacy owner-built forms and Remote Desktop remain reusable on close while their lifecycle migration is pending.

**Windows on arm64** installs and runs, minus what upstream cannot ship
there: neither `opencv-python` nor `cryptography` publishes a `win_arm64`
wheel. So `find_image*`, `screenshot()` (the OpenCV/BGR one — the Pillow
capture still works), the secret vault, action-file encryption, ACME/TLS
and encrypted recording each raise a message naming the missing wheel
instead of failing obscurely. Mouse, keyboard, screen size, window
management, the accessibility tree, the action executor, the MCP/REST/TCP
servers and the GUI all work — measured, not assumed. Every other platform
is unaffected.

**Requirements:** Python ≥ 3.10 (≥ 3.11 on Windows arm64, which is where
CPython's official builds for it start). On Linux, install build
prerequisites first:

```bash
sudo apt-get install cmake libssl-dev
```

OCR, VLM, and LLM backends (`pytesseract`, `easyocr`, `paddleocr`, `anthropic`,
`openai`) are loaded on demand — install whichever you actually use. For Tesseract,
`find_tesseract_cmd()` locates the executable (`$TESSERACT_CMD`, then `PATH`, then the
installers' default folders), `set_tessdata_dir()` points it at a language-data folder,
and `ocr_status()` / `ocr_languages()` say what is missing before the first OCR call.

**Log file:** the library logs to `~/.je_auto_control/logs/AutoControlGUI.log`,
created on the first record (importing alone writes nothing) and shared by every
process on the account (appended to, one process id per line, moved to `.1`
past 10 MB). Set `JE_AUTOCONTROL_LOG_FILE` to write elsewhere, or to
`os.devnull` to turn the file off.

---

## 60-second quick start

**1. As a Python library**

```python
import je_auto_control as ac

ac.set_mouse_position(500, 300)
ac.click_mouse("mouse_left")
ac.write("Hello World")
ac.hotkey(["ctrl_l", "s"])

x, y = ac.locate_image_center("save_button.png", detect_threshold=0.9)
ac.click_text("Submit")                       # OCR
ac.click_accessibility_element(name="OK")     # accessibility tree
ac.click_by_description("the green Submit button")   # vision model
ac.screenshot("shot.png", screen_region=[0, 0, 800, 600])
```

**2. As a JSON action file** — `flow.json`

```json
[
    ["AC_set_var", {"name": "user", "value": "alice"}],
    ["AC_locate_and_click", {"image": "login.png", "mouse_keycode": "mouse_left"}],
    ["AC_write", {"write_string": "${user}"}],
    ["AC_retry", {"max_attempts": 3, "body": [
        ["AC_wait_text", {"target": "Welcome", "timeout": 10}]
    ]}],
    ["AC_assert_text", {"text": "Welcome"}],
    ["AC_generate_html_report", {"html_name": "report"}]
]
```

```bash
je_auto_control run flow.json --var user=bob
je_auto_control run flow.json --dry-run     # list the steps without touching the mouse
```

**3. As a desktop app**

```bash
pip install je_auto_control[gui]
python -c "import je_auto_control; je_auto_control.start_autocontrol_gui()"
```

Record a flow, edit it in the visual Script Builder, and save it as the same JSON
format the CLI runs. (`python -m je_auto_control` is the legacy action-file runner — `-e`, `-d`,
`-c`, `--execute_str` — not the GUI.)

---

## Capability overview

Every row works headlessly. "GUI tab" is where the same feature surfaces in the
desktop app; tab commands live in the window's **Actions** menu.

| Capability | Python API | `AC_*` command | GUI tab |
|---|---|---|---|
| Mouse | `click_mouse` (`clicks=2` double-clicks), `set_mouse_position`, `mouse_scroll`, `tween_drag` / `drag_path` (paced by `step_delay_s`, `settle_s`) | `AC_click_mouse`, `AC_tween_drag`, `AC_drag_path` | Auto Click |
| Keyboard | `write`, `write_secret`, `hotkey`, `type_keyboard`, `keyboard_key_name` (code → canonical name; Windows also takes aliases such as `ctrl`, `esc`, `enter`) | `AC_write`, `AC_write_secret`, `AC_hotkey` | Auto Click |
| Screen & pixels | `screenshot`, `screen_size`, `get_pixel` | `AC_screenshot` | Screenshot |
| Image matching | `locate_image_center`, `locate_and_click` | `AC_locate_and_click` | Image Detect |
| OCR text | `click_text`, `wait_for_text`, `read_text_in_region`, `ocr_status` | `AC_click_text`, `AC_wait_text`, `AC_ocr_status` | OCR Reader |
| Accessibility tree | `find_accessibility_element`, `click_accessibility_element` | `AC_a11y_find`, `AC_a11y_click` | Accessibility |
| Vision-model locator | `locate_by_description`, `click_by_description` | `AC_vlm_locate`, `AC_vlm_click` | VLM |
| Anchor locator | — | `AC_anchor_click`, `AC_anchor_locate` | — |
| Self-healing locators | `self_heal_run`, `self_heal_locate`, `self_heal_click` | `AC_self_heal_click` | Self-Healing |
| Natural-language planner | `plan_actions`, `run_from_description` | `AC_llm_plan` | LLM Planner |
| Computer-use agent | `AgentLoop`, `run_agent` | `AC_run_agent` | Computer Use |
| Record & replay | `record`, `stop_record` | `AC_record`, `AC_stop_record` | Record |
| JSON scripting | `execute_action`, `execute_files` | all 855 commands | Script, Script Builder |
| Variables & flow control | `execute_action_with_vars` | `AC_set_var`, `AC_loop`, `AC_for_each`, `AC_try`, `AC_retry` | Variables |
| Data-driven runs | — | `AC_for_each_row` (CSV / JSON / SQLite / Excel) | Data Sources |
| Assertions | `assert_text`, `assert_image` | `AC_assert_text` + 20 more | Assertions |
| Test suites | `run_suite` | `AC_run_suite` | Test Suites |
| Scheduler (interval + cron) | `default_scheduler` | — | Scheduler |
| Global hotkeys | `default_hotkey_daemon` | — | Hotkeys |
| Event triggers | `default_trigger_engine` | `AC_email_trigger_add` | Triggers, Webhooks, Email |
| Window management *(Windows, macOS, X11)* | `list_windows`, `focus_window` | `AC_focus_window`, `AC_snap_window` | Window Manager |
| Clipboard (text + image) | `get_clipboard`, `set_clipboard`, `get_clipboard_image`, `set_clipboard_image` | `AC_clipboard_get`, `AC_clipboard_set`, `AC_clipboard_get_image`, `AC_clipboard_set_image` | — |
| Remote desktop | `RemoteDesktopHost`, `RemoteDesktopViewer` | `AC_start_remote_host`, `AC_remote_connect` | Remote Desktop |
| USB enumeration & passthrough | `list_usb_devices`, `enable_usb_passthrough` | `AC_usb_*` (16 commands) | USB Devices, USB Share |
| Secrets vault | `default_secret_manager` | `AC_secret_set` + `${secrets.NAME}` | Secrets |
| Reports (HTML / JSON / XML) | `generate_html_report` | `AC_generate_html_report` | Report |
| Run history | `HistoryStore`, `manual_history_scope` | `AC_history_list`, `AC_history_capture` | Run History, Script Executor, Script Builder |
| Action journals | `execute_journal_run`, `inspect_journal` | `AC_journal_capture`, `AC_journal_read` | Run History, Script Builder |
| Metrics & tracing | `default_metric_registry`, `render_metrics_text` | — | — |
| Diagnostics | `run_diagnostics` | `AC_diagnose` | Diagnostics |
| Test-code generation | `generate_code` | — | — |

Self-healing propagates cancellation before fallback or clicking. Its audit log masks secrets already resolved in the current run before writing or returning records; returned locator outcomes retain their original values. Legacy log files are not rewritten.

Live image/VLM self-healing now shares one lazy logical capture, including its actual clipped origin. `screen_region` is `[left, top, right, bottom]` for both strategies. Schema-v2 audit records add run/step identity, content/configuration version, frame hash, strategy/capture timing and resolved backend/model; old records still load. Click dispatch without a verifier is recorded as issued or failed, with verification left unknown. The GUI exposes region input and selected-record evidence; Script Builder keeps region JSON structured. Historical `healed`/`heal_rate` count located candidates; separate operation metrics require explicit verification.

Experimental `self_heal_run(SelfHealRequest(...))` defaults to locating. Choose `operation="click"` and `VerificationRequest(verifier=...)` (a Python bool callback) or `VerificationRequest(description=...)` (a configured VLM) to check the post-condition after input dispatch. VLM verification obtains a fresh logical frame and may incur API cost. `verified` is true, false or unknown; `found` and `issued` alone do not verify the operation. Exceptions and cancellation propagate without retrying the click. `AC_self_heal_run` and MCP `ac_self_heal_run` accept a nested `request`; explicit false verification fails the command/CLI or returns MCP `isError` with the structured result. GUI **Self-Healing** offers an optional post-condition field, and Script Builder edits the JSON request. Standalone VLM capture now uses the same logical origin/Retina normalization in memory. Framework assertions stop lookup recovery.

Captured self-healing rows now include an optional `journal_path` alongside run/step IDs. Experimental `inspect_heal_source(path, run_id, step_id)`, `AC_self_heal_source` and MCP `ac_self_heal_source` read only the original step’s sanitized lifecycle snapshots. In **Self-Healing**, select a row and choose **Actions → Inspect original step** to open the background reader. Switching targets waits for the older reader to stop and retains the requester’s context; closing cancels pending work. Run History’s reader also accepts an optional step ID. Run/step filtering precedes the output limit, the whole file is validated, current path roots are rechecked around progress callbacks, and cancellation returns no partial result. Legacy or uncaptured rows have no original-source link; inspection never replays a command.

Experimental causal synchronization provides `CausalBucket`, `CausalConfigStore`, `SyncActor`, conflict-preserving entry versions and a durable local `SyncOutbox`. The dedicated authenticated `GET/PUT /config/{user_id}/causal` protocol (version 3) validates peer registration, acknowledgements, retirement/full-sync epochs and collection in the same CAS transaction as retry receipts. Collected deletions retain permanent minimal fences; legacy writers cannot overwrite upgraded accounts. Private `AC_config_store_get` / `AC_config_store_commit` and matching MCP/Builder commands read and commit causal JSON with an explicit `_actor`. Pure merge/peer commands and private outbox commands remain available. The explicit `CausalSyncClient` and `AC_config_causal_fetch`, `AC_config_causal_commit`, `AC_sync_outbox_flush` (matching MCP/Builder commands) now deliver v3 HTTP requests: uncertain sends reuse the frozen request; only definite stale-base errors rebase within a bounded budget. `CausalReceipt` confirms the original receipt and latest complete snapshot atomically in the outbox. Command credentials use a live `options.secret_env` reference. `CausalSyncClient.control` and private `AC_sync_peer_control` / `ac_sync_peer_control` / Builder Data commands durably register, acknowledge, collect, retire and perform full resync. `SyncControlRequest(operation_id=...)` makes completed RPC retries idempotent; full resync requires explicit `discard_pending=True` before atomically adopting a new generation and archiving pending old edits. Local `status` reads no credential or network. Run `python -m examples.causal_peer_control` for the temporary loopback workflow; explicit local asset generations are available through `AssetManifest`, `DirectoryAssetTransport`, `build_asset_manifest`, `sync_assets` and private `AC_sync_asset_manifest` / `AC_sync_assets` (MCP/Builder). All assets stage and pass SHA-256/size checks before one directory publication; damaged caches are refused and scripts stay inert. `python -m examples.sync_assets` uses temporary directories only. Seven experimental adapters now capture selected scripts, locators, hotkeys, triggers, address-book entries, JSON settings and saved native GUI preferences into durable causal profiles. `SyncBindings` replaces explicit secrets and machine values with named references; `materialize_sync_profile` publishes a complete inert native-format generation. Private `AC_sync_adapter_snapshot`, `AC_sync_adapter_apply`, `AC_sync_adapter_resolve`, `AC_sync_profile_materialize` and matching MCP/Builder commands share the workflow. `python -m examples.sync_adapters` uses temporary files only. Private absolute path bindings accept high-entropy directory names while recognized credential formats remain refused. Native numeric definitions reject out-of-range values, including extreme JSON integers, with typed errors before storage. `WorkspaceSettingsSyncAdapter` captures only theme, font size, navigation visibility/width from native GUI INI files and publishes an inert `workspace.ini`; explicitly copy it to a separate working file before opening a new GUI. `python -m examples.sync_workspace` stays Qt-free. `SyncWorkspace` now coordinates selected sources, durable offline capture, causal HTTP, exact conflict review and full-resync source baselines. Private `AC_sync_workspace` / `ac_sync_workspace` / Builder Data share status/capture/sync/review/resolve/preferences/materialize and explicit peer controls; all require DRIVE. Runtime network credentials use `options.secret_env`. `python -m examples.sync_workspace_http` demonstrates two temporary sources over loopback, conflict resolution, restart and no replay of retired edits. Received definitions remain inert. Referenced asset transport is described below; explicit native working-copy loading is described below; `ConfigSyncClient` retains its timestamp merge. See the [causal/outbox guide](docs/source/Eng/doc/causal_sync/causal_sync_doc.rst) and `python -m examples.causal_sync`.

The lazy **Workspace Sync** tab exposes local status/capture, network synchronization and peer controls, exact causal review/resolution, and complete inert publication through **Actions**. Paste an explicit private workspace descriptor; credentials are environment variable names. Sync never applies received preferences automatically. Select `workspace`, review its current heads, then choose **Apply reviewed GUI preferences** to update theme, font and navigation in the running window. `SyncWorkspace.preferences(observed=change_ids)` and the existing AC/MCP/Builder `preferences` operation return four canonical values only when the exact reviewed heads remain conflict-free; missing/deleted values use safe defaults. Workers preserve caller context, refresh DRIVE authority, support cancellation and discard stale results on close. The view shows revision/pending/conflict/reference counts and the last successful sync revision; no connection starts when opened.

Explicit native loading uses `load_sync_profile(directory, target_root, expected_digest=...)` and `LoadedSyncProfile`, with private `AC_sync_profile_load` / `ac_sync_profile_load` / Builder Data equivalents. The published `files` directory and exact reviewed manifest digest create a fresh editable workspace. Full verified bytes, canonical native files and sealed heads must agree before atomic publication. Loaded hotkeys and every trigger node are disabled native objects; locator and address-book handles use the working files. Typed asset references and native hotkey/trigger paths resolve against that working root, while literal script strings keep their meaning and secrets stay placeholders. In **Workspace Sync**, materialization fills the directory/digest fields; choose a working-copy container and **Load reviewed native profile**. Separate Actions inspect the selected native kind, open a loaded script snapshot in Builder, or apply its preference snapshot. These actions recheck both the current caller and captured owner; opening a script keeps Run explicit. Builder renders imported command names and positional data as literal text. `python -m examples.sync_profile_load` uses seven temporary domains and a real PNG with no network or device calls.

Folder mirroring now compares SHA-256 content instead of increasing modification times: metadata-only touches do not resend, while same-time/older-time edits do. FolderSyncEngine retains pending/offline edits across restarts, checks stop between files, and owns a blocked sender until it exits. Transport owners can explicitly call record_received(path) after publication to prevent echoing received bytes. Native GUI frozen-receipt handling is described below.

File sends now wait for each DataChannel callback, bound buffered data to 1 MiB and propagate channel failures to the caller. Optional `cancelled` predicates stop queued writes; announced byte counts detect source truncation/growth. Native folder jobs capture their authorization, engine, viewer and peer connection, and stop when ownership changes. Inbox downloads run outside the event loop through a per-channel queue capped at 32 requests. Default manual-mode channel acceptance is not publication acknowledgement; confirmed mode is described below. GUI reconnect handoff is described below.

Native file receivers now discard unfinished bytes on shutdown, files/control channel close, terminal connection state, replacement channel or revoked file permission. Closed receivers reject late frames; current peer/channel and authentication checks protect replacement transfers, including viewer receives before authentication. State cleanup precedes user callbacks so callback-driven reconnection survives an old failure. File/audit/state callbacks preserve original cancellation and hard-interruption objects. Filesystem cleanup failures are logged after both close and unlink are attempted. Existing Remote Desktop controls use this lifecycle automatically; completed targets and the legacy wire format remain available.

Local `FileReceiveReceipt(path, sha256, size)` metadata now freezes the original received bytes after atomic publication. `FileTransferReceiver.handle_message(on_receipt=...)` and native host/viewer `set_file_receipt_callback()` expose it without rereading the published file. `FolderSyncEngine.record_receipt()` prevents echo while retaining later local edits; legacy `record_received(path)` explicitly snapshots current content. The GUI folder toggle captures its engine and viewer for receipt delivery and refreshes its original authorization before touching the watch. Relative inbox/watch paths bind to their creation working directory; existing path notices use absolute paths. These local receipts feed the confirmed native mode below; GUI reconnect handoff is described below.

Native `FileTransferSender.send`, viewer `send_file` and host `push_file` now accept keyword-only `require_commit=True`. Confirmed mode probes an authenticated native peer before source metadata/content reads, sends version-2 begin/end metadata and verifies the matching transfer ID, unpredictable end nonce, SHA-256 and byte size after atomic publication. Relative source paths bind before the exchange. Each file rechecks peer support/permission; waits are bounded and cancellation, channel/loop replacement or permission loss retain failure. GUI folder sends always require this mode, so accepted-but-dropped bytes do not advance delivery state and uncertain sends retry on the same engine. Legacy manual mode remains the default and sends its original envelopes. Both peers need confirmed-transfer support for GUI folder delivery; unsupported peers fail before file content is sent. Explicit GUI reconnect/resume is described below.

GUI reconnect retains one in-memory folder baseline per panel. After reconnecting, press Start sync again: the same authenticated host fingerprint, absolute watch path and local principal resume failed/offline edits through a new authorised sender. A missing/changed host fingerprint, different root or principal starts a fresh baseline; a still-running old worker blocks handoff until it exits. Explicitly disabling folder sync resets the baseline, while stopping/reconnecting the viewer retains it. Closing the application clears it. The fingerprint follows the existing authenticated host-metadata trust model, not a new cryptographic identity guarantee. SDK callers can stop a FolderSyncEngine, export checkpoint() after actual worker retirement and pass that immutable FolderSyncCheckpoint to a replacement engine with the same path/recursion mode and an explicitly authorised sender. The baseline includes initially ignored files and received bytes; it is not a list of remote acknowledgements.

TCP/WebSocket clipboard transfers use the existing explicit SDK methods and GUI Push clipboard button. Received text/images do not automatically send or broadcast onward; deliberate repeated sends of identical content remain valid. Buffered viewer/host reads recheck the original connection, authentication and full-control permission before applying clipboard data. Viewer sends pin the original channel before encoding and refuse replacement. Queued GUI deliveries retain their concrete viewer and connecting user; permissions and ownership are refreshed before native clipboard writes, before explicit clipboard reads and again before sending. Stale/revoked work is discarded or reports its permission error. Ordinary provider/callback errors stay contained; original cancellation and hard-control objects propagate. Text/image JSON envelopes and existing APIs remain unchanged. Callback registration binds the original viewer weakly once, so a disconnected viewer does not keep itself and its Qt panel alive until cyclic GC. Actual queued deliveries still retain the original peer and authority until consumed or discarded. Controlled local protocol, loopback and offscreen tests replace native clipboard providers; real-device and paid-API acceptance remain deferred.

Experimental referenced assets use `SyncAssetBlob`, `SyncAssetReference`, `SyncAssetStore` and `SyncAssetHTTPClient`. Explicit `SyncBindings.assets` aliases freeze selected files into immutable SHA-256 references; asset-only changes create new causal versions. `SyncWorkspace` uploads verified chunks before preparing new definition requests, resumes interrupted transfers and downloads referenced bytes before complete inert publication. Existing private AC/MCP/Builder workspace/profile commands share these fields. `asset_cache_path` selects the client cache; signaling `--asset-store` / `AUTOCONTROL_SYNC_ASSET_STORE` select the separate server database. Authenticated version-one asset routes use 256-KiB chunks, a 64-MiB per-file bound and default per-account limits of 256 MiB, 8,192 chunks and 4,096 blob receipts. Quota exhaustion fails explicitly; immutable history has no automatic garbage collection. Paths in native output are relative to the generation root. `python -m examples.sync_referenced_assets` sends a real PNG and script through temporary loopback HTTP with no execution or active workspace change.

Experimental persistent configuration uses `ConfigStore.commit(..., base_revision=..., operation_id=...)` and a version-two signaling PUT envelope. SQLite transactions preserve buckets and retry receipts across restart; stale revisions or changed operation identities conflict. `ConfigSyncClient` defaults to conditional writes; blind legacy writes require explicit client/server opt-in. `--config-store` selects the lazy database. Private `AC_config_store_get` / `AC_config_store_commit` and matching MCP tools share explicit Script Builder Data commands. This stores data without running scripts or enabling triggers; causal merge and offline outbox remain separate. See the [persistent config guide](docs/source/Eng/doc/config_store/config_store_doc.rst) and `python -m examples.config_store`.

Experimental journal-to-code candidates use `generate_candidate_from_log(path, run_id=...)`, `AC_generate_candidate_from_log`, and MCP `ac_generate_candidate_from_log`. They reconcile lifecycle snapshots, retain recorded control sources and retry evidence, and mark partial reconstructions as observed paths. Failed/incomplete invocations and unknown or redacted inputs remain explicit exclusions; parallel order is never invented. Generated Python/pytest/Robot source passes static, command and non-dispatching dry-run checks. `codegen --from-log run.jsonl --run-id selected` prints a JSON review bundle; `-o review.zip` or `write_candidate_archive` atomically exports code, actions and provenance together. **Actions → Review journal candidate** in Recording Editor or Script Builder opens source/diff/manifest/warnings; Builder import is separate and refuses intervening editor changes. Neither generation nor import runs the candidate. See the [journal candidate guide](docs/source/Eng/doc/journal_candidates/journal_candidates_doc.rst) and `python -m examples.journal_candidates`.

Experimental template-candidate revisions use `create_template_candidate`, `preview_template_candidate`, `verify_template_candidate`, `accept_template_candidate` and `revert_template_candidate`, with matching `AC_template_candidate_*` / `ac_template_candidate_*` operations. A new immutable JSON bundle retains original bytes and the candidate encoded in the target’s PNG/JPEG/BMP format. Preview returns bounded thumbnails. Verification compares both frozen versions on a local sample manifest; acceptance requires a labelled hit, an expected miss and every labelled case correct, plus the reviewed bundle SHA-256. Acceptance rechecks the dataset and atomically replaces only matching original bytes; revert restores exact original bytes and refuses later edits. Unknowns and native-operation success remain separate. The recorded threshold applies to verification; activating image bytes does not edit script thresholds. **Self-Healing → Template candidates** offers all five Actions, background work, cancellation and JSON evidence. Run `python -m examples.template_candidates` for a temporary-file-only example.

Experimental fixed-frame comparisons use `evaluate_locators` or `evaluate_healing_manifest`, `AC_self_heal_evaluate`, MCP `ac_self_heal_evaluate`, and **Self-Healing → Version comparison**. Reports separate labelled accuracy, wrong predictions, unknowns and verified recovery, include p50/p95 and provenance, and export JSON/HTML through `write_healing_report` or GUI Actions. The local manifest operation never captures, clicks or selects a network backend. See the [dataset, populations and limits](benchmarks/self_healing/README.md).

Beyond this table, `utils/` holds 311 headless packages covering assertions, resilience,
data quality, i18n auditing, redaction, governance, observability, and more. The full
per-module map is in **[architecture_explore.md](architecture_explore.md)**.

---

Experimental structured journal capture is exported from `je_auto_control` (also available in `utils.action_journal`): `journal_scope` captures existing executor calls, and `execute_action_with_journal` isolates one run. Local loop/parallel/DAG steps retain parent IDs; failures, cancellation and dry-runs are distinct. Existing history owners automatically link explicit captures, including captures opened by local parallel/DAG workers; `HistoryStore.journals_for_run` returns the non-owning links. Clearing/pruning history leaves journal files intact. The CLI supports `run script.json --journal run.jsonl [--journal-run-id ID]` and `journal run.jsonl [--run-id ID] [--limit 100]`. Journal reads show sanitized lifecycle snapshots in append order; output defaults to 100 snapshots (maximum 10,000). `AC_journal_capture` accepts named parameters and runs a nested `body` on the owning executor without replacing its variables; `AC_journal_read` shares sanitized, bounded inspection with the CLI and public `inspect_journal`. Both commands are editable in Script Builder. Capture rejects identifiers or destinations containing secrets known to the run before history linking, file creation or action effects. MCP `ac_journal_capture` and `ac_journal_read` provide structured results, progress and cooperative cancellation. Captured journal roots and observers survive nested captures and local workers; reads can cancel between validated records. `JournalRunOptions` and `execute_journal_run` expose the same controls in Python.

Manual runs can opt into history with `manual_history_scope`, `AC_history_capture`, CLI `run --history [--history-db PATH]`, or **Record in Run History** in Script Executor / Script Builder. An optional GUI journal path also works independently of history. GUI/CLI result JSON and existing variable scopes are preserved; the command returns `history_id`, `record` and `failed_actions`. Existing and nested captures link to the new manual row. CLI previews use the `cli.preview` source label; ordinary runs use `cli.run`.

Run History includes a read-only journal browser. Use **Actions → Use Journals from Selected Run** to select a provenance link, or **Choose Journal** for an external file. Set a run ID and snapshot limit, then **Read Journal**; start/completion snapshots stay separate and their full sanitized data appears on selection. **Cancel Journal Read** and closing the view request cancellation between records. File parsing runs in a background worker; selecting a link opens no file.

Values resolved from `${secrets.NAME}` are masked in application diagnostics during executor runs, including nested actions and local parallel/DAG workers. CLI/REST/MCP requests and scheduled, trigger, hotkey and email runs retain the mask through error handling and audit/history writes; report records capture redacted snapshots. DAG calls retain the owner mask through complete node diagnostics, including standalone calls and custom local runners. Watchdog, observer and callback-executor calls also retain it through final diagnostics; independent rules have separate masks. CLI stderr is masked, while API outcomes, raised exceptions and CLI result payloads retain their original values. Masks are discarded when the owning request or run exits. Interrupted history runs are recorded as `error`, while journal steps remain `cancelled`; no error screenshot is taken. Cancellation propagates through non-strict execution, recovery/retry, callbacks and local workers. Hard exits retain their original signal even if history completion fails.

## Command-line interface

Each `je_auto_control run` invocation, including `--dry-run` and runs without `--var`, gets a fresh variable scope. Top-level `run_from_description` and `StateMachine.run()` also isolate variables while sharing them across their own actions and states; nested calls reuse an existing execution scope. A caller-owned `Executor()` keeps its own variables.

```bash
je_auto_control run script.json [--var name=value] [--dry-run] [--allow-package NAME]
je_auto_control validate script.json          # alias: lint
je_auto_control fmt script.json [--check]
je_auto_control list-commands [--filter mouse] [--json]
je_auto_control record out.json [--duration 5]
je_auto_control codegen script.json --target pytest -o test_flow.py
je_auto_control failure-bundle failure.zip --error "login timed out"
je_auto_control list-jobs
je_auto_control start-server --port 9938      # TCP socket server
je_auto_control start-rest   --port 9939      # REST API
je_auto_control version
```

`--var name=value` is parsed as JSON when possible (`count=10` becomes an int),
otherwise kept as a string. `run` exits 1 when any action failed (the run
still goes on to the end), so a CI step fails with it. The legacy
`python -m je_auto_control -e file.json` entry point still works, and its
`-e`, `-d` and `--execute_str` flags exit 1 the same way. Under
[TestPioneer](https://github.com/Integration-Automation/TestPioneer), which
sets `TEST_PIONEER_ARTIFACT_DIR`, the HTML, JSON and XML reports asked for
under a relative name are written below that directory.

---

## Servers and integrations

| Surface | Start it with | Notes |
|---|---|---|
| **MCP server** | `je_auto_control_mcp` (stdio) or `AC_start_mcp_http_server` | 759 tools for Claude Desktop / Claude Code / custom tool loops: the full `ac_*` surface plus short model-friendly aliases for common GUI actions. Speaks the stateless MCP 2026-07-28 beside the `initialize`-based revisions. Bearer auth, TLS, audit log, rate limit, plugin hot-reload, CI fake backend. |
| **REST API** | `je_auto_control start-rest` | Bearer token, per-IP rate limit + lockout, SQLite audit hook, `/metrics`, `/openapi.json`, `/docs` Swagger UI, `/dashboard`. |
| **TCP socket server** | `je_auto_control start-server` | Newline-framed JSON action lists. Binds `127.0.0.1` by default. |
| **pytest plugin** | installed automatically | Fixtures plus a Gherkin step library for pytest-bdd / behave. |
| **Language server** | `python -m autocontrol_lsp.server` | Completion and diagnostics for `AC_*` action JSON, generated from the live command table. |
| **Remote desktop** | `RemoteDesktopHost` / GUI | TCP, WebSocket, or WebRTC; TOTP, trust list, TURN config, file/clipboard/audio sync. |

All servers bind to `127.0.0.1` unless you opt in explicitly.

The MCP window-state tools `ac_window_minimize`, `ac_window_maximize` and `ac_window_restore` return the window handle on accepted requests and `isError: true` on backend refusal (including a stale handle or rejected activation). Raw Win32 `ShowWindow` previous visibility is normalized by the backend.

**Package gate.** `AC_add_package_to_executor` and `AC_add_package_to_callback_executor` import a Python package and register its members as commands, so an action list arriving over any of these surfaces could load `os` or `subprocess`. No package loads unless it has been allowed: a package that is not on the allowlist is refused before it is imported, and that action fails with `AutoControlExecuteActionException`. Allow packages (submodules included) from Python with `executor.allow_packages("name", …)`, for every entry point — both CLIs, the socket / REST / MCP servers and the scheduler — with the `JE_AUTOCONTROL_ALLOWED_PACKAGES` environment variable (comma-separated names, read when the process starts), or for one CLI run with `je_auto_control run script.json --allow-package NAME` (repeatable). `executor.set_allow_arbitrary_packages(True)` opens the gate for every package, which is what earlier releases did by default (with a `DeprecationWarning`). None of these is an `AC_*` command, so an action list cannot open its own gate.

**Opt-in hardening.** Each of these is off until configured, and a server without them behaves as before. `JE_AUTOCONTROL_RBAC_USERS=<user store file>` makes the REST API and the MCP HTTP transport resolve the bearer token to a user and authorise each route, tool and privileged `AC_*` command by role (viewer / operator / admin); the shared token is then refused. `JE_AUTOCONTROL_MCP_PATH_ROOTS` (directories separated by the OS path separator) confines every MCP tool argument that is a file path to those directories, `JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT=1` adds the client's `roots/list`, and `JE_AUTOCONTROL_MCP_ENV_REF_ALLOW` limits which `env://` names `ac_resolve_ref` may read. `JE_AUTOCONTROL_ACTION_SIGNING_PUBLIC_KEY` makes an endpoint verify Ed25519-signed action files without being able to sign them (`create_signing_keypair`; the private key stays on the signing machine). A remote-desktop viewer writes files pushed by a host only below `~/Downloads/AutoControl` (`JE_AUTOCONTROL_REMOTE_DOWNLOAD_DIR`); that one is on by default.

The REST GUI shows RBAC mode and disables the shared-token field while a user store is active. `rest_api_registry.status()` includes `rbac_enabled` and returns `token: null` in that mode; use an individual user token. Custom REST gates that only implement `check()` remain supported in shared-token mode; RBAC requires an authenticated user context and refuses an identityless success.

RBAC viewers do not receive the named sensitive-read tools, even when their MCP `readOnlyHint` is true: clipboard/history, local document/data/SQL and dotenv reads, reference resolution, credential generation, persistent store readers, outbound checks, microphone capture and external VLM requests require operator/admin. Assertion containers also require operator because their specs can read those resources. Screen observation and pure input parsing keep their existing classification. `ac_realize_item`, `ac_idempotency_begin` and `ac_rate_limit` change state and are excluded from `--read-only` mode.

Delayed interval/cron jobs, triggers, hotkeys, watchdog rules, webhooks, e-mail triggers and observer callbacks retain their registrant’s identity. Store-backed users and roles are checked again on dispatch; deleted users, unavailable stores and viewers cannot execute deferred work. Starting a daemon does not transfer its registrations to the starter. Ownership metadata retains no RBAC bearer token; explicit Python `AuthorizationContext` values without `store_path` keep their captured role, and work registered outside RBAC clears worker identity. Observer/watchdog callbacks get fresh variable scopes, and failed watchdog actions do not count as dismissed popups. Nested callbacks retain the caller’s failure count; a webhook with a revoked owner returns HTTP 403 and `fired: false`.

### How the remote-desktop wire protocol works

TCP hosts release a rejected authentication attempt’s client slot before sending `AUTH_FAIL`. A viewer can retry immediately, including after a bad token, wrong handshake message or denied approval, while socket cleanup/logging finishes. Pending handshakes retain their independent resource bound.

Worth knowing before you expose a host, and described nowhere else in the
docs. The default transport is length-prefixed framing over raw TCP — no extra
dependencies — and it opens with an **HMAC-SHA256 challenge/response
handshake**: a viewer that fails auth is dropped before it is sent a single
frame. JPEG frames are encoded at the configured FPS and quality and handed to
authenticated viewers through a shared *latest-frame slot*, so a slow viewer
drops frames instead of stalling the rest. Viewer input arrives as JSON and is
**validated against an allow-list** of actions before being applied through the
ordinary input wrappers, so a viewer cannot invent new operations.

```python
# Be remoted — start a host and hand the token + port to whoever views you
from je_auto_control import RemoteDesktopHost
host = RemoteDesktopHost(token="hunter2", bind="127.0.0.1",
                         port=0, fps=10, quality=70)
host.start()
print("listening on", host.port, "viewers:", host.connected_clients)
```

```python
# Control another machine — connect a viewer and send input
from je_auto_control import RemoteDesktopViewer
viewer = RemoteDesktopViewer(host="10.0.0.5", port=51234, token="hunter2",
                             on_frame=lambda jpeg: ...)
viewer.connect()
viewer.send_input({"action": "mouse_move", "x": 100, "y": 200})
viewer.disconnect()
```

Narrow who may connect at all with an IP allow-list (CIDR ranges or exact
addresses); peers outside it are rejected during the handshake:

```python
RemoteDesktopHost(token="tok", ip_allowlist=["10.0.0.0/8", "192.168.1.100"])
```

---

## Platform support

| Platform | Backend | Input | Screen capture | Recording | Window management |
|---|---|:---:|:---:|:---:|:---:|
| Windows 10 / 11 | Win32 ctypes (+ optional Interception driver) | ✅ | ✅ | ✅ | ✅ |
| macOS 10.15+ | pyobjc / Quartz | ✅ | ✅ | ✅¹ | ✅ |
| Linux X11 | python-Xlib (+ optional `uinput`) | ✅ | ✅ | ✅ | ✅ |
| Linux Wayland | libei via the desktop portal, or ydotool / wtype + a capture tool | ✅ | ✅ | ❌ | ❌ |
| FreeBSD / OpenBSD / NetBSD | python-Xlib, the same X11 backend as Linux | ✅² | ⚠️² | ✅² | ✅² |
| Android | adb + uiautomator2 | ✅ | ✅ | — | — |
| iOS | WebDriverAgent / facebook-wda | ✅ | ✅ | — | — |

¹ macOS recording captures through a Quartz event tap and needs
**Accessibility** permission (System Settings → Privacy & Security →
Accessibility). Without it recording raises and names the permission
rather than returning an empty session.

² The BSDs run the X11 backend unchanged — the same X server, the same
`python-Xlib`, which is the only dependency input, recording and window
management have. A `freebsd` CI job drives real input on a real FreeBSD 14 and
reads it back off the X server; OpenBSD and NetBSD take the same code path but
have no CI runner. Screen capture is the exception, and the reason is
packaging rather than the platform: it goes through Pillow/mss and OpenCV, and
`opencv-python`, `pillow` and `cryptography` publish no FreeBSD wheels. Build
those from ports and capture, image matching, OCR and action encryption work
too — `import je_auto_control` no longer requires any of them.

Wayland key/button/pointer input in `auto` mode uses CLI when the optional native
backend is absent. Once a portal request starts, refusal, timeout, handshake
failure, device pause or revocation stops input; it never silently switches
providers. Repeated refused calls retain inert failure state without reopening
consent. `JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=libei` requires native input;
`=cli` explicitly selects CLI. After resolving permission, an explicit
`je_auto_control.linux_wayland.libei.reset_default_backend()` allows a fresh
request. Interrupted native chords attempt all owned key releases on the same
backend and preserve the original cancellation. This does not change the
explicit wtype text path or screen-capture selection.

The `ydotool` fallback needs **ydotool 1.0 or newer**. Every argument
AutoControl builds arrived in that release; 0.1.x — which is what Debian
bookworm and every current Ubuntu still ship under that name, and Debian
trixie ships not at all — answers the same arguments with exit code 0 and no
events. AutoControl detects it and refuses rather than reporting success for
input it never sent. Arch, Fedora and Debian unstable package 1.0.

That fallback also positions the pointer accurately **only where the
compositor's pointer acceleration is off**. `ydotool mousemove --absolute`
sends no absolute event: it drives the cursor into the corner the compositor
clamps to and then moves relative to it, so the compositor accelerates the
move — measured against a real wlroots session, libinput's default profile
travels exactly twice the distance asked for. ydotool's own `--help` says the
same; AutoControl logs it once per process rather than mispositioning in
silence. Turn acceleration off for the ydotoold device (sway: `input
type:pointer accel_profile flat` and `pointer_accel 0`), or install
`liboeffis` so the libei path — absolute at the protocol level — is used.

The factor is the compositor's own setting and no client can read it back, so
only you know whether it is off. `JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL=flat`
says it is, and moves silently; `=strict` refuses the move rather than let a
click land somewhere else; leaving it unset keeps the warn-and-move default.

Wayland screen capture needs the tool your compositor supports, because no
single one covers them all: `grim` on wlroots compositors (sway, Hyprland,
river), `gnome-screenshot` on GNOME, `spectacle` on KDE. Install one and every
capture path — screenshots, image and anchor locators, OCR, screen recording,
remote desktop — goes through it. With none installed, a session bus is
enough: the built-in D-Bus client tries `xdg-desktop-portal` last, though it may ask for consent the
first time. Failing that, capture fails loudly with an install hint rather than
returning the blank XWayland root. The `screen_capture` check in
`je_auto_control.api.run_diagnostics()` (and the GUI Diagnostics tab) reports
which tier is in use.

A native Wayland pointer coordinate outside every granted EIS region, after
raw-coordinate and layout-origin mapping, raises `LibeiUnavailable` with
`state="failed"` and disables automatic CLI fallback. A rejected move emits
no motion/frame or subsequent click. Valid coordinates, devices without
regions, later valid requests on the same sender and explicit CLI selection
retain their existing behavior.

Passive **input/capture capabilities** use `BackendContext`, `CapabilityStatus`,
`CapabilitySnapshot` and `probe_capabilities` from `je_auto_control.api` (also
exported at the package root). Call
`probe_capabilities(BackendContext.current()).to_dict()`, use no-argument
`AC_probe_capabilities` / read-only `ac_probe_capabilities`, or choose
**Diagnostics → Actions → Inspect input and capture capabilities**. Builder
provides the same no-argument command. `python -m examples.capabilities` prints
live prerequisites and a deterministic XWayland scope example without desktop operations.

Input describes key/pointer events; the existing wtype text path is separate.
The probe reads environment/PATH and nonblocking cached native state; it never
loads optional native libraries, connects, polls events, captures or requests
permission. Installed tools or a bus address mean `unverified`, not readiness.
Cached libei readiness requires a completed handshake and active keyboard,
absolute pointer, button and scroll families. A partial grant remains
unverified; paused families and removed required devices report paused/revoked.
The eight states are `available`, `unverified`, `needs_permission`,
`needs_dependency`, `unsupported`, `paused`, `revoked` and `failed`.
`available` is only the last local observation and may be stale; every real
operation rechecks authority. XWayland always has `desktop_wide=False` and cannot
cover native Wayland windows. Other scope flags remain subject to granted
regions/permissions and do not verify every monitor.

Contexts detach environment/executable facts and may carry an owner's inert
input/capture observations. They grant no authority. Default live results omit
environment values, command arguments, executable paths and native error text;
AC/MCP accept no supplied observations. Explicit CLI configuration remains
distinct from automatic fallback after observed optional native absence;
permission/pause/revocation/failure metadata cannot imply CLI fallback.
Capture helper and portal selection are diagnosed independently. Rendering and
language changes reuse the snapshot without probing. Native portal restore,
compositor restart, capture-result/context integration and native session
controls remain in `Progress.md`.

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

Opening Diagnostics displays a localized not-run state and performs no checks.
Choose **Actions → Run diagnostics** to start the existing active checks, which
can capture the screen or require portal consent. Changing the display language
does not start checks. The explicit `run_diagnostics`, `AC_diagnose` and MCP
diagnostic calls retain their active behavior. Passive capability inspection is a separate action below.

Abandoned screenshot portal requests attempt `Request.Close` on the originating
bus before disconnect, using a separate 0.25-second D-Bus I/O budget. A returned
alternate handle is followed; after an uncertain method reply, the predicted
handle is used. Completed responses are not closed again. Ordinary cleanup
errors do not replace the primary capture failure; original cancellation and
hard-control objects survive wrappers and cleanup. D-Bus writes and reply waits
share the call budget, connection setup has an explicit timeout, and interrupted
connect/authentication/Hello releases its owned descriptor even when `__enter__`
fails. Actual compositor/dialog cancellation remains platform acceptance work.

One Wayland-only difference to plan around: **a capture may contain the mouse
cursor.** Nothing here asks for it, but wlroots composites a *software* cursor
into the output buffer whenever the backend has no cursor plane — which
includes any session run with `WLR_NO_HARDWARE_CURSORS=1` — and that buffer is
what screen capture hands back. Windows and X11 never include the pointer, so a
locator, a template match or an OCR read can find a pointer-shaped hole in the
middle of its target here and nowhere else. Wayland does not let a client read
the cursor position, so there is nothing to reliably mask or move around it:
park the pointer away from what you are about to capture. The `screen_capture`
check reports this as `cursor_may_be_captured`.

For a setup none of that fits, name your own command — it wins over every
detected tool, and `{output}` is replaced with a temporary PNG path:

```bash
export JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND="mycapture --png {output}"
```

Wayland forbids global input recording for unprivileged clients — set
`JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11` to record on an X11 session. Window
management works on Windows, macOS (pyobjc) and X11, including XWayland; on a pure
Wayland session, whose protocol hides other clients' windows, `list_windows()` returns
an empty list and every window action raises `AutoControlUnsupportedOperationException`
saying why. Opt-in driver-level backends (`JE_AUTOCONTROL_WIN32_BACKEND=interception`,
`JE_AUTOCONTROL_LINUX_BACKEND=uinput`, ViGEm virtual gamepad) exist for apps that
ignore synthetic input, and fall back silently when the driver is absent.

---

## Documentation and examples

| Resource | What's in it |
|---|---|
| [`examples/`](examples/) | 43 self-contained scripts: screenshot + click, OCR, scheduler, remote desktop, agent loop, observability, recording, variables, hotkeys, triggers, reports, MCP, REST, secrets, plugins, computer use, Wayland, cross-host DAGs, chat-ops, pytest/BDD, anchor locators, action journals. |
| [Read the Docs](https://autocontrol.readthedocs.io/en/latest/) | Full API reference, English and 中文. |
| [architecture_explore.md](architecture_explore.md) | Every module's responsibility, layer by layer. |
| [docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md) | Capability × platform matrix. |
| [docs/API_LIFECYCLE.md](docs/API_LIFECYCLE.md) | Stable-API and deprecation policy. |
| [docs/updates/](docs/updates/README.md) | Update log: release notes and finished work, one file per month (formerly `WHATS_NEW.md`). |
| [CHANGELOG.md](CHANGELOG.md) | Compatibility changelog. |
| [SECURITY.md](SECURITY.md) | Security policy and reporting. |

---

## Development

```bash
git clone https://github.com/Integration-Automation/AutoControlGUI.git
cd AutoControl
pip install -r dev_requirements.txt
uv sync                 # or: reproducible install from the committed uv.lock
```

```bash
python -m pytest test/unit_test/headless      # headless unit tests
python -m pytest test/integrated_test/        # cross-module workflows

ruff check je_auto_control/
pylint je_auto_control/
bandit -c pyproject.toml -r je_auto_control/
```

The dev/main headless jobs retain `native-<os>-<python>` artifacts for seven
days: merged process output, package/runtime versions and exit status. Linux
runs under GDB to retain all-thread native backtraces; other platforms retain
Python faulthandler output. Test failures remain failures. From a repository
checkout, reproduce collection with `python scripts/ci_native_diagnostics.py
--artifact-dir test-artifacts -- python -m pytest -v --tb=short --timeout=120`
(one command); add `--native` before `--` on Linux with GDB installed.
Literal argv (including whitespace/quotes) and handled `SIGINT` reach the
child unchanged. Linux first verifies the runner outside the suite's debugger;
its preflight logs are included in the same artifact.

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

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Two rules the CI enforces: `import
je_auto_control` must never pull in PySide6, and every feature needs both a headless
API and a GUI surface.

---

## License

[MIT License](LICENSE) © JE-Chen.
See [Third_Party_License.md](Third_Party_License.md) for the licenses of bundled and
optional third-party components.

- **Homepage**: https://github.com/Integration-Automation/AutoControlGUI
- **PyPI**: https://pypi.org/project/je_auto_control/
- **Documentation**: https://autocontrol.readthedocs.io/en/latest/

Legacy MCP action wrappers, parallel branches and local DAG workers retain the same origin ceilings.

Managed point actions accept observation-local element indices or thumbnail image points. The host checks the current frame and resolves native coordinates, including scaling and negative monitor origins. Receipts retain geometry provenance without image bytes. `AgentObservationStale` identifies rejection before dispatch; local agents reobserve only within their retry budget when the adapter confirms no held or pending input.

Emergency stop returns compact snapshots with metadata.details_deferred; fetch individual task details for full artifact links.

Managed mouse presses normalize button ownership and confirm the actual cursor before input. Windows pointer checks reject foreign overlays. Vision renders the exact scoped window into cleared private GDI storage, rejects geometry changes and releases resources even on rendering/read failure. There is no desktop-crop fallback. Fake-native tests cover these paths; native acceptance remains unverified.

The Agent tasks view groups task scope, workflow settings, triggers, skills and recovery into separate pages. Its observation page lists read-only elements and shows a validated, strictly masked JPEG at one rendered pixel per logical widget pixel. Selecting a row or image point only edits a frame-bound action request; Actions -> Perform observed action sends it through the shared task API. Switching tasks clears the preview, and late replies cannot replace the selected task. A new frame requires reselection before an old reference can be sent. Closing the view only detaches its requests.

Managed workflow waits (workflow_wait / AC_workflow_wait) poll only exact scoped control values or states, with cancellation and a deadline capped by the action budget (default five seconds, maximum sixty). They never replay a write or submit. Fixed skills require all previous receipts to match the pinned sequence before continuing, including after resume; autonomous model loops retain stuck detection. New form/transfer drafts refuse an already-matching confirmation before submit and wait for a fresh transition afterward. Batch configurations may provide new_record_selector to reset each record; confirmations prove the configured UI transition, and transaction-specific receipt values should be used when available. Archive drafts also re-read the exact reviewed manifest and current file digests at finish (one-megabyte manifest and sixty-four-megabyte total evidence limit).

AgentHumanReview identifies an unsaved-content or unknown-dialog gate. It persists waiting_user and retires input ownership, including for external observe requests; explicit resume still rechecks the gate. Windows detection uses native dialog/disabled-owner evidence and known English/Chinese/Japanese unsaved labels. Workspace tasks also pause for leading/trailing asterisks in document titles; a window entry may supply unsaved_selector and unsaved_value for an application-specific indicator before layout changes. These checks do not infer every application's dirty state. Recognized standard file pickers use a context-local driver on the existing AC_handle_file_dialog executor: exact unique title, same PID, confirmed foreground and canonical rooted absolute paths. UIA control patterns must belong to the actual owned root window, even when another window shares its PID. All behavior has fake-native/loopback coverage; actual platform acceptance remains unverified.

Host-reviewed targets use AgentTargetProfile and manage_agent_target (AC_agent_target; register/get/disable/enable/probe). Names and configuration are immutable; desktop/file/browser adapters are currently supported; unimplemented kinds are rejected and optional browser helper_python is host-reviewed. Tasks pin the host profile digest and cannot expand its tools, applications, roots or network origins. Availability persists across restart and is checked at dispatch; disabling requests pause/cleanup, while enabling requires explicit task resume. list_agent_targets / AC_agent_target_list / CLI agent-task targets expose passive metadata with readiness=not_probed and native_evidence=not_recorded. Full configuration requires manage_hosts; CLI agent-task target and the GUI Host targets page use the same service. Live anonymous MCP tool sessions have operator authority across direct and legacy wrapper calls; MCP host management requires an authenticated administrator. Trusted direct Python callers remain unchanged. Browser automation belongs to WebRunner (je_web_runner), with D:/Codes/WebRunner as the development source; browser profiles use the managed je_web_runner SDK contract, and dependency probes do not establish native readiness.

Existing browser automation, including open_path(URL) and AC_open_path, delegates to WebRunner (Python package je_web_runner). URL plans now report backend=je_web_runner; callers inspecting the previous webbrowser descriptor should use the new value. Signatures and local-file opening stay compatible. URL execution requires the configured WebRunner project and propagates WebRunnerBridgeError when unavailable, without opening an OS browser as a fallback. The development source is D:/Codes/WebRunner. Planning and injected-opener tests remain usable without that package; browser protocol support is determined by WebRunner and its selected browser. Existing dedicated browser GUI/MCP/AC paths and recorded WR_* actions share the same bridge.
