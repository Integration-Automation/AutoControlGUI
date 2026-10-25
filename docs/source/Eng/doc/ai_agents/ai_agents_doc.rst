AI agents and computer use
===========================

Reviewed completion after confirmed effects
-------------------------------------------

When input has retired but a stopped task has not published completion, review a separate read-only task::

    review = manage_agent_recovery("preview_completion", {"task_id": source_id})
    child = manage_agent_recovery("create_completion", {
        "task_id": source_id, "snapshot": review["snapshot"],
        "note": "Reviewed confirmed effects and independent completion conditions",
    })
    result = finish_agent_task(child["task_id"])

Read ``verification_spec`` before approval; it is derived by the host and is not accepted as a create
argument. The exact source snapshot, human review note and private atomic proof bind one real successor.
The original stays stopped. Finite skills require every action confirmed; dynamic sources require no
dormant finite plan or unknown effects. Historical action/result clauses are never sufficient alone:
fresh independent file/screen criteria and successful input retirement must also pass. Existing native
capability diagnostics remain passive; native desktop acceptance is separate from owned-file tests.
The child may be observed before finish. Exact identical helper configuration reruns readiness without
replacing its authority; changed spec/owner/profile refuses. Readiness and observations are never cached.

The new task runs no model or executable actions. Ordinary ``act`` and executable recovery upgrades
refuse before action preparation. Roots/origins, both source/effect owners and the actual reviewer remain
live, including after helper cleanup. Cancellation, restart, budgets and broker generations retain their
existing gates. Explicit retry reviews preserve the original effect owner. Completed successors carry
bounded ``completion_review`` metadata and can be adopted by the existing reviewed whole-DAG workflow.
Use the existing explicit ``owner_policy="source_owner"`` and returned ``ownership.review`` token when
creating a successor that must remain visible to the source owner; default caller ownership is unchanged.

Python/API/AC/MCP/REST/CLI/Builder use the same recovery operation enum. The GUI exposes two Actions
for preview/create and reuses the reviewed-request editor. Browser/remote readers and expired-scope
completion renewal remain open; they never fall back to an ordinary helper or a new browser context.

Fresh read-only completion observation seam
-------------------------------------------

The host SDK's standard desktop/file ``NativeDesktopTarget.completion_reader(spec)`` creates a separate
owned helper under the exact parent operation and live scope. It requires source input retirement and
the same host profile/resource, then negotiates exact read-only contract 1 with input_supported=false
before configuration. The reviewed workflow above binds this host seam to a separately admitted task.
Merely opening or retiring a reader never marks a task complete.

The helper permanently refuses perform/upgrade RPC, nested executor calls, input acknowledgments and
nonempty cleanup. The host proxy also refuses local workflow launch and resource recovery. Unexpected
input is recorded without ACK or release injection, the process is retired and its witness remains
quarantined. Existing unknown witnesses cannot be cleared by observation. Closed views cannot restart
helpers; retirement is confirmed only after successful cleanup. Owner/root/parent checks surround reads,
different operations/owners cannot borrow a view, and browser clauses must be pinned to its specification.

Target API/AC/MCP/REST/CLI/Builder and GUI views expose passive ``readonly_completion`` status only.
Custom adapter descriptors are not evaluated, and no native readiness probe runs. Standard browser
fresh-start, ordinary/custom helper fallback and unsupported remote readers remain refused. Future
browser/remote observation contracts and expired-scope completion renewal remain open.
Host adapters are trusted code; these protocol/dispatcher/input-observer guards are not an OS sandbox.

Compare the accepted task specification
----------------------------------------

``lookup_agent_task("key", reviewed_spec)`` optionally compares the destination-normalized spec with
the immutable digest stored for the original owner's request. The additive ``spec_match_contract=1``
response advertises matching support; a supplied spec yields ``spec_match`` of ``matches``, ``differs``,
``unverifiable`` or ``not_found``. CLI lookup accepts ``--spec reviewed.json``; shared AC/MCP/REST/Builder
use the optional ``spec`` object. Matching never submits or activates a task.

DAG inspection first looks up the key. When the destination advertises the exact contract, it sends the
reviewed node spec in a second read-only lookup and verifies the same task identity. Older destinations
stay unverified; local origin witnesses are never sent to a remote destination. Changed request mappings
invalidate the previous completion snapshot. Matching binds an individual task spec, not the graph's
topology or original batch approval. Explicit continuation remains unapproved.
Matched task completion also checks the exact count/kinds of independently passed criterion reports,
the durable completion contract and input retirement; partial reports remain unconfirmed.

Inspect an interrupted DAG
---------------------------

``inspect_agent_dag(definition, timeout_seconds=30)`` queries up to 100 existing local/registered-host
task keys without submitting, pausing or resuming work. ``AC_agent_dag_inspect``, MCP
``ac_agent_dag_inspect``, REST action execution, CLI ``agent-task inspect-dag reviewed.json``, Builder
and DAG Actions share the operation. The maximum inspection budget is 300 seconds; remote lookup still
requires host-management authority. Local principals/store paths/origin metadata are never forwarded.
Snapshots omit remote artifact paths and raw errors. GUI results are discarded after graph edits.

``recorded_completion`` concerns the found task alone. Node-spec matching is optional and
``resume_permitted=false`` leaves graph/batch approval and continuation unapproved. Missing
records remain snapshots, not rejection evidence. Review and specification binding are separate recovery
steps; inspecting never replays effects or treats a recorded task as proof for an edited DAG.

Inspect a lost submission reply
--------------------------------

``lookup_agent_task("original-key")`` reads the current principal/store namespace without submitting,
resuming or acquiring input. The same operation is available as ``AC_agent_task_lookup``, MCP
``ac_agent_task_lookup``, ``POST /agent/lookup`` with ``idempotency_key`` and optional ``spec``, CLI
``agent-task lookup original-key`` and the task view's Actions menu. Results contain ``found`` and an
optional ``task`` status snapshot. Missing records are not proof of rejection: an outstanding request
can arrive later. Task access remains required for this read-only lookup. GUI results are discarded if
the key or selected task changes. DAG inspection shares this lookup; specification-bound recovery approval remains open.

Managed tasks in a DAG
----------------------

The existing Python ``run_dag``, ``AC_run_dag``, MCP ``ac_run_dag``, REST action execution, CLI action
files, Script Builder and DAG Actions accept a mutually exclusive ``task`` node payload::

    {"nodes": [{"id": "collect", "host": "reviewed-host", "task": {
        "spec": reviewed_spec, "idempotency_key": "batch-20261024-collect", "wait_seconds": 300}}]}

DAG types and functions are also available from ``je_auto_control.api`` and ``je_auto_control.api.core``.

``reviewed_spec`` is a skill or explicitly configured local-model specification with tools, destination
roots and completion criteria. External mode is refused. Omit ``host`` for the explicitly started local
service; remote hosts must already expose an authenticated runtime with background dispatch. No listener
is deployed. Destination paths are interpreted and authorized at the destination, not on the coordinator.

Nodes submit once, then poll the exact task. Only matching passed criteria, durable completion contract 1
and confirmed input retirement allow dependants to run. The explicit deduplication key must remain stable
for recovery of the same reviewed batch. Rerunning polls the same task; paused/recovering work is never
automatically resumed. Stop, cancellation, timeout or a transport/authority error requests bounded pause
when the task ID is known. Missing acknowledgements remain uncertain; no action replay or lease stealing
is inferred. Failed results retain the task ID/key and skip dependants. GUI results show retained task IDs.
Local role/store metadata and origin witnesses never cross the remote boundary; registered host tokens
determine remote authority. Nested managed-task dispatch is refused. Destination resource locks serialize
shared input; independent target resources may run concurrently. Production multi-host configuration,
cross-host artifact transfer and native/device acceptance remain separately tracked.

Completion and input retirement
--------------------------------

Task success is committed only after owned input cleanup is confirmed. Failed or busy cleanup requires
review and retains the lease; a crash before confirmation leaves the task recoverable. Conditional
transitions preserve concurrent cancellation. Existing task status/results include
``metadata.input_released`` and ``completion_contract``. Version 1 is stored atomically with new success
and survives restart; legacy success stays version zero. Final artifacts and history reflect the committed outcome. This evidence
covers the owning runtime's input retirement. Remote-device acknowledgement remains a separate contract.

DAG worker authority
---------------------

Default and custom DAG runners preserve the caller's authorization, cancellation, command guards and
managed operation context. Store-backed identity is refreshed before every node; removing the owner
fails dispatch and skips dependent nodes. Role changes apply to each operation's authorization check.
Default remote nodes require ``manage_hosts`` before accessing the host address book or action files.
Administrators and trusted direct Python retain remote dispatch. Caller contexts stay local; registered
remote credentials determine remote authority. Managed task nodes use the lifecycle above; production
configuration and native/device evidence remain open.

AutoControl is an open-source, cross-platform computer-use and GUI automation framework for AI agents.

Use it when an agent needs to control a real desktop GUI rather than only a browser DOM or API.

When to use AutoControl
-----------------------

AutoControl is a good fit for:

* real mouse and keyboard input;
* screenshots and screen-coordinate interaction;
* OCR and accessibility-tree discovery;
* image/template matching;
* vision-language-model UI localization;
* anchor and self-healing locators;
* native desktop applications and real browsers;
* cross-platform desktop and mobile automation;
* deterministic JSON action files;
* MCP-based computer use.

MCP for AI agents
-----------------

Install and start the stdio MCP server:

.. code-block:: bash

   pip install je_auto_control
   je_auto_control_mcp

The server exposes the canonical ac_* tools and short, model-friendly aliases for common actions:

* click
* move_mouse
* scroll
* type
* press
* hotkey
* screenshot
* screen_size
* find_image
* find_text
* click_text
* drag
* list_windows
* focus_window
* wait_image
* wait_pixel

Disable aliases when a client needs only canonical tools:

.. code-block:: bash

   JE_AUTOCONTROL_MCP_ALIASES=0 je_auto_control_mcp

Use read-only mode for inspection-only clients:

.. code-block:: bash

   je_auto_control_mcp --read-only

Recommended agent loop
----------------------

#. Observe the current screen.
#. Identify the target with accessibility, OCR, image matching, or VLM.
#. Perform the smallest required action.
#. Wait for the interface to settle.
#. Verify the expected result.
#. Retry with another locator strategy if the UI changed.

OpenAI tool selection
---------------------

OpenAI Chat Completions has a provider-side tool-count limit. Do not pass the complete AutoControl catalogue to an OpenAI agent. Export a focused allow-list:

.. code-block:: python

   from je_auto_control.utils.tool_use_schema import export_openai_tools

   tools = export_openai_tools(only=[
       "AC_screenshot",
       "AC_click_mouse",
       "AC_write",
       "AC_hotkey",
       "AC_click_text",
   ])

Focused toolsets are also safer: keep shell, process execution, package loading, and recursive agent commands out of the list unless explicitly required.

Examples
--------

For the closed-loop Python agent see the repository example at examples/05_agent_loop.py.

A stdio MCP client can launch AutoControl with:

.. code-block:: json

   {
     "mcpServers": {
       "autocontrol": {
         "command": "je_auto_control_mcp"
       }
     }
   }

Security
--------

An AI-controlled GUI process has control over the host machine.

* Keep servers on loopback unless remote access is intentional.
* Use --read-only for inspection-only clients.
* Prefer explicit tool allow-lists.
* Do not expose shell/process/package-loading tools to untrusted models.
* Use authentication, audit, rate limiting, and confirmation controls for service deployments.

Single-command dispatch
-----------------------

``executor.execute_one(name, arguments)`` and ``run_tool_call`` share script authorization,
interpolation, cancellation and journal capture while returning raw command results.
Private executor arguments are rejected. Identity-scoped calls require command capability.

Managed tasks
-------------

Start the local task service explicitly with ``je_auto_control agent-task start``.
Python, AC, MCP, REST, CLI and the Agent Tasks view share submit/observe/act/finish,
pause/resume/cancel and owner-scoped status. Completion requires deterministic evidence;
model stop text is not proof. Skills use WorkQueue and local inference uses a configured
Ollama model without downloads, redirects or external fallback. Closing the view leaves
submitted work owned by the service. Native/platform acceptance and remaining workflows
are tracked in ``Progress.md``; full contracts are in ``docs/AGENT_TASKS.md``.

Native calls use an owned helper process tree with cancellation/deadlines, a host input ledger
and per-session exclusion across databases. Native platform acceptance remains deferred.

Use ``draft_agent_workflow`` or ``agent-task draft`` to preview download/archive, CSV/XLSX form,
cross-application transfer and workspace templates. Review the compiled scope, per-step read-back
checks and completion conditions before submission. The Agent Tasks Actions menu exposes preview.

Windows shared-desktop tasks require unlocked inactivity for sixty seconds. Physical input requests
pause through an independent helper notice. ``stop_all_agent_tasks`` or ``agent-task stop-all`` cancels
visible tasks. Other shared desktops need an activity adapter. Monotonic budget history survives restart.

HTTP pause/cancel/stop-all/shutdown use a separate per-IP bucket (120 requests/minute, burst 30).
Status polling cannot consume this reserve; authentication, live roles, ownership and retirement remain.
The shared client reserves transport slots for DAG pauses too. On ``POST /agent/dag``, the internal
``X-AutoControl-Agent-Control: 1`` marker requires an exact ``pause_batch`` request or ``local_task``
whose operation is ``pause`` and body contains only ``task_id``. Other marked bodies return 400 before
dispatch; the reserve itself still returns 429 when exhausted. Custom gates retain their own contract.
This is bounded HTTP admission, not an OS/network scheduling guarantee.

Use ``get_agent_task_receipts`` for per-row results and ``reconcile_agent_task`` to record an explicit
owner witness for an uncertain effect before resume. Task metadata links history, journal and reports.
Generated cache expires after thirty days; user outputs and external journals are preserved. Images
are ephemeral unless strict-redacted persistence is explicitly enabled.

``manage_agent_trigger`` captures approved interval/cron/file/event templates and refreshes the owner
on each fire. Event/task deduplication commits atomically. ``submit_agent_task`` accepts an optional
idempotency key; CLI and Actions expose trigger controls. Managed scopes reject ambient vault resolution.

Input ownership writes a private, fsynced per-resource crash witness before native dispatch and input ACK. An unfinished witness blocks new owners across databases. Explicit host-only recovery requires a review note and a trusted no-held-input probe, never replays persisted input or signals persisted PIDs, and does not reconcile/resume the old task. POSIX input helpers monitor their actual parent and retire only their own live session group. Approved document handoff runs outside the input helper tree, so user applications survive normal task cleanup; bounded, preapproved focus steps wait for scoped windows. Observations also expire against a host monotonic clock. Native desktop/device acceptance remains unverified.

Managed skill candidates store sealed task scopes, typed explicit data slots and source-task provenance in the runtime SQLite database. Recording requires confirmed receipts and independently verified completion. Validation creates a distinct pinned task; publication requires verified completion evidence for that exact trial, an explicit review note and a compare-and-set version. Semantic selector repairs create new candidates. In-flight tasks retain their original version/digest; arbitrary pointer receipts are not guessed into semantic skills. Legacy mutable SkillLibrary behavior is preserved.

When all actions of an interrupted trial are confirmed, finish its separately reviewed read-only
completion task, then ``manage_agent_skill("accept", request)`` may include ``completion_task_id``.
``task_id`` remains the original real validation trial. Its exact candidate/spec hash/pin and the
reader's private proof, derived scope, independent completion/retirement and up to sixteen real recovery
links are required. The SQLite publication transaction checks live caller/owner/reviewer authority and
records both identities without changing the stopped source or replaying effects. Lost authority is a
typed review refusal; version/publication/adoption writes roll back together. Actions can prepare the
request without publishing. ``publication.completion_review`` stores historical IDs/hashes after reader
retention; it is not a live-evidence claim. Missing evidence before acceptance still refuses.

Example after explicit recovery review and successful reader finish::

    {"candidate_id":"reviewed-candidate", "task_id":"original-validation-trial",
     "completion_task_id":"verified-read-only-child", "expected_version":0,
     "note":"Reviewed the actual trial and separate completion evidence"}

For a stopped source, explicitly select ``completion_task_id`` on ``record``, keeping ``task_id``
equal to the original workflow. Its actual confirmed semantic actions, not the reader's empty plan,
become the draft. An ordinary external workflow needs no pre-existing validation-trial row. Private
reader admission, exact derived scope, real ancestry, independent completion/retirement and current
caller/source-owner/reviewer authority are required. Source/proof checks and candidate insertion use
one SQLite write transaction, with post-write proof and live authority rechecks; failures leave no
draft. ``provenance.completion_review`` is historical IDs/hashes and grants no live authority after reader
retention. The new draft still requires its own exact validation trial; added ``validation_criteria``
cannot inherit the old reader's result. Source state and receipts stay intact, with no replay or
fabricated trial. GUI Actions prepare the request without recording or publishing.

Example recording request::

    {"task_id":"original-workflow", "completion_task_id":"verified-read-only-child",
     "name":"Reviewed workflow"}

Reviewed complete execution chains
----------------------------------------------------------------

For a partially executed validation trial, first call ``manage_agent_skill("review_execution", request)``
with ``candidate_id``, the original ``task_id`` and a separate final ``execution_task_id``. Then explicitly
``accept`` those same IDs with the returned ``execution_review``, ``expected_version`` and a nonempty ``note``.
At most sixteen actual executable recovery links must confirm the complete original semantic plan;
a successful different remainder is insufficient. Comparison includes JSON types, captured values,
expectations and grounding, without restoring captures or rebuilding historical UI state. Each task
retains its existing limits and separate approval. Current callers, all owners and actual admission
reviewers must remain authorized. Version, publication and historical ``publication.execution_review``
commit atomically, with post-write evidence/authority checks. The original stays stopped and retains
``publication.task_id``; no recovery child becomes a fabricated validation trial. An optional
``completion_task_id`` must verify the final executable effect and is nested in this execution audit.
Expired evidence cannot approve an unpublished candidate. Two Actions examples prepare review and
accept requests without executing them; ``agent_skill_execution_review.json`` and
``agent_skill_execution_accept.json`` are editable request examples.


Accepted tasks, trigger templates and skill trials retain live origin policy references. A private witness contains only current root ceilings; missing/revoked/corrupt witnesses fail closed. Authenticated local HTTP forwards the current caller's additional restrictive ceiling without granting identity or capability. Every operation checkpoint and lease maintenance rechecks roots. MCP client roots and asynchronous roots refresh are session-local; stale replies cannot renew retired authorities. Static host policies persist until replacement, while retiring client-supplied root authority revokes its references. HTTP client roots do not overwrite the shared resource provider's configured workspace. Workers/maintenance run in fresh contexts, shutdown tracks actual in-flight deliveries before lease acquisition, and unstarted queued work remains durable.

Legacy MCP wrappers and parallel/local DAG workers retain the intersection of source ceilings. Pure tool-context binding stays inert; task-aware dispatch resolves the metadata lazily.

Managed action references resolve observation-local element centers or rendered image pixels into native coordinates only after identity/freshness/fingerprint checks. Explicit coordinates cannot conflict with a reference; invalid/disabled/out-of-frame targets fail before preparing an action. SQLite atomically links grounding metadata to each prepared receipt, including requested arguments, frame ID/hash and non-image geometry; reports expose the same provenance. Local-model schemas carry an observed_target extension while legacy executor signatures stay unchanged. AgentObservationStale round-trips over local HTTP, and bounded pre-dispatch replanning requires an adapter's explicit can_reobserve guarantee. Native adapters deny it while any owned input or unsettled operation remains. Native acceptance stays unverified.

Native helper bootstrap is a bounded read-only fifteen-second handshake; actual native operations retain their configured action deadline. Rendered image geometry must match the validated JPEG dimensions.

Managed mouse presses normalize button ownership and confirm the actual cursor before input. Windows pointer checks reject foreign overlays. Vision renders the exact scoped window into cleared private GDI storage, rejects geometry changes and releases resources even on rendering/read failure. There is no desktop-crop fallback. Fake-native tests cover these paths; native acceptance remains unverified.

The Agent tasks view groups task scope, workflow settings, triggers, skills and recovery into separate pages. Its observation page lists read-only elements and shows a validated, strictly masked JPEG at one rendered pixel per logical widget pixel. Selecting a row or image point only edits a frame-bound action request; ``Actions → Perform observed action`` sends it through the shared task API. Switching tasks clears the preview, and late replies cannot replace the selected task. A new frame requires reselection before an old reference can be sent. Closing the view only detaches its requests.

Managed workflow waits (workflow_wait / AC_workflow_wait) poll only exact scoped control values or states, with cancellation and a deadline capped by the action budget (default five seconds, maximum sixty). They never replay a write or submit. Fixed skills require all previous receipts to match the pinned sequence before continuing, including after resume; autonomous model loops retain stuck detection. New form/transfer drafts refuse an already-matching confirmation before submit and wait for a fresh transition afterward. Batch configurations may provide new_record_selector to reset each record; confirmations prove the configured UI transition, and transaction-specific receipt values should be used when available. Archive drafts also re-read the exact reviewed manifest and current file digests at finish (one-megabyte manifest and sixty-four-megabyte total evidence limit).

AgentHumanReview identifies an unsaved-content or unknown-dialog gate. It persists waiting_user and retires input ownership, including for external observe requests; explicit resume still rechecks the gate. Windows detection uses native dialog/disabled-owner evidence and known English/Chinese/Japanese unsaved labels. Workspace tasks also pause for leading/trailing asterisks in document titles; a window entry may supply unsaved_selector and unsaved_value for an application-specific indicator before layout changes. These checks do not infer every application's dirty state. Recognized standard file pickers use a context-local driver on the existing AC_handle_file_dialog executor: exact unique title, same PID, confirmed foreground and canonical rooted absolute paths. UIA control patterns must belong to the actual owned root window, even when another window shares its PID. All behavior has fake-native/loopback coverage; actual platform acceptance remains unverified.

Host-reviewed targets use AgentTargetProfile and manage_agent_target (AC_agent_target; register/get/disable/enable/probe). Names and configuration are immutable; desktop/file/browser adapters are currently supported; unimplemented kinds are rejected and optional browser helper_python is host-reviewed. Tasks pin the host profile digest and cannot expand its tools, applications, roots or network origins. Availability persists across restart and is checked at dispatch; disabling requests pause/cleanup, while enabling requires explicit task resume. list_agent_targets / AC_agent_target_list / CLI agent-task targets expose passive metadata with readiness=not_probed and native_evidence=not_recorded. Full configuration requires manage_hosts; CLI agent-task target and the GUI Host targets page use the same service. Live anonymous MCP tool sessions have operator authority across direct and legacy wrapper calls; MCP host management requires an authenticated administrator. Trusted direct Python callers remain unchanged. Browser automation belongs to WebRunner (je_web_runner), with D:/Codes/WebRunner as the development source; browser profiles use the managed je_web_runner SDK contract, and dependency probes do not establish native readiness.

Existing browser automation, including open_path(URL) and AC_open_path, delegates to WebRunner (Python package je_web_runner). URL plans now report backend=je_web_runner; callers inspecting the previous webbrowser descriptor should use the new value. Signatures and local-file opening stay compatible. URL execution requires the configured WebRunner project and propagates WebRunnerBridgeError when unavailable, without opening an OS browser as a fallback. The development source is D:/Codes/WebRunner. Planning and injected-opener tests remain usable without that package; browser protocol support is determined by WebRunner and its selected browser. Existing dedicated browser GUI/MCP/AC paths and recorded WR_* actions share the same bridge.


MCP tool metadata discovery
------------------------------------------------------------

MCP tool discovery is available through ``search_mcp_tools(query, limit=10)`` and
``get_mcp_tool_schema(name)``, corresponding AC/MCP commands, and Diagnostics → Actions.
Search returns bounded summaries with category and required capability; full schemas require a
single-tool lookup. Both queries refresh role authority and respect the registry's read-only filter.
MCP queries use that server's live registry, including plugin changes. CLI inspection:
``je_auto_control_mcp --search-tools document --limit 5`` or ``--tool-schema ac_mcp_tool_search``.

MCP session tool availability
------------------------------------------------------------

MCP supports opt-in session disclosure: ``je_auto_control_mcp --tool-mode progressive`` starts
with five discovery controls; ``ac_mcp_tools_enable`` / ``ac_mcp_tools_disable`` change only that session.
``--tool-mode static --tool-profile ac_screen_size,ac_list_windows`` supplies a fixed profile for clients
that do not refresh tool lists. The default ``full`` mode retains its unpaginated permitted list.
Progressive/static pages use opaque, single-use cursors bound to a snapshot and caller; changed tools,
roles, view configuration or expired cursors require restarting ``tools/list``. Enable/disable notify
the owning connection. Session closure retires outstanding metadata callbacks and clears cursors.
Use ``MCPServer.configure_tool_disclosure(...)`` for HTTP/embedded servers, or host environment
``JE_AUTOCONTROL_MCP_DISCLOSURE`` and comma-separated ``JE_AUTOCONTROL_MCP_TOOL_PROFILE``.
``plan_mcp_tool_profile(...)`` and Diagnostics Actions preview startup arguments without starting a server.
Stateless requests use a fixed, unpaginated initial profile; they do not retain session enablement.
Read-only ceilings cover later plugin registrations. Unauthenticated/shared-token peers see operator
tools, matching their existing invocation ceiling; host-management tools require authenticated authority.

MCP handoff and metadata measurements
----------------------------------------------------------------------

MCP asynchronous calls preserve the accepting caller's role, session, exact root policy and
disclosure view; retired sessions and path policies reject late dispatch. Stateless async calls keep
their fixed profile. HTTP tool-list changes reach all live session streams for plugin updates, while
session enable/disable targets one owner and avoids duplicate delivery. Stream registration and HTTP
headers share one lock so an early notification cannot precede the response headers.
The metadata-only ``benchmarks/mcp_discovery.py --repeats 20`` benchmark records count, JSON bytes,
warm in-process handshake, search and enable latency. The captured Windows/Python 3.14.4 run has
732 permitted tools / 358,029 initial response bytes in full mode and 5 / 2,029 in progressive mode
(99.43% fewer response bytes). Handshake is 58.263 / 47.439 ms; search median is 16.243 / 19.718 ms.
Progressive enable median is 42.486 ms. These local timings exclude cold imports and native work.
See the dated JSON report under ``docs/benchmarks/``; argument-policy coverage limits remain in ``Progress.md``.


Managed WebRunner targets and DOM references
----------------------------------------------------------------------

Managed browser profiles (``kind: browser``) now delegate to the owned ``je_web_runner`` SDK from
WebRunner (``D:\Codes\WebRunner``; integration source on its isolated managed-session branch).
Profiles require exact ``settings.allowed_origins``, browser-only tools and no desktop apps; every task
also declares a narrower nonempty ``options.allowed_origins``. Profile/task grants are checked again on
activation. Registration stays inert. Install the reviewed managed-session SDK and its Chromium runtime
in the helper environment explicitly; absent dependencies fail readiness and nothing is installed automatically.
``AC_browser_navigate``, ``AC_browser_click``, ``AC_browser_fill``, ``AC_browser_select``, ``AC_browser_check``
and ``AC_browser_read`` share Python/core, executor, MCP and Builder schemas. They operate inside the
managed helper; drive them through the existing task submit/observe/act lifecycle, not an ambient browser.
The read operation is ``text``, ``value`` or ``visible``; secret form controls are refused by WebRunner.
Observation-local DOM indexes resolve selectors and frames after the runtime's freshness check.
Failed effects remain uncertain and require reconciliation; pause/cancel retire owned resources.
GUI Actions can draft a browser target example for review, and DOM selection only edits the action request.
The dedicated helper preserves one fresh session across readiness checks, acknowledges browser cleanup
and then reaps its owned process tree. Existing desktop input ownership is not acquired for browser tasks.
Controlled cross-source tests use the real SDK with fake Chromium and owned IPC/loopback. Browser/native
acceptance, reviewed transfers and browser workflow compilation remain tracked in ``Progress.md``.

Profile example (review and register with ``manage_agent_target("register", profile)``)::

    {"name": "reviewed-browser", "kind": "browser",
     "allowed_tools": ["AC_browser_navigate", "AC_browser_fill", "AC_browser_read"],
     "settings": {"allowed_origins": ["https://example.invalid"]}}

A task selects that name, repeats its allowed tools and supplies
``options.allowed_origins``. A skill can navigate, fill a CSS selector and read its value
with an independent ``expect_result`` before completion. External agents observe then call
``act_agent_task`` with ``reference: {"element_index": 0}`` and the current observation ID;
its arguments supply the fill value or read operation, without a competing selector/frame.
The initial page is blank and has no DOM references until an explicitly authorized navigation.


Browser form and field-transfer drafts
----------------------------------------------------------------------

``draft_agent_workflow("batch_form", config)`` and ``transfer`` accept ``backend: browser`` with
explicit ``allowed_origins`` and a reviewed browser target. CSV/XLSX sources stay rooted; browser drafts
emit only ``AC_browser_*`` actions and never fall back to desktop input. Forms take ``url``, CSS ``fields``,
optional frame selectors/new-record control, and submit plus confirmation selectors. Each fill has an
independent exact value readback. Optional ``confirmation_column`` supplies a per-row expected marker.
Transfers take ``source_url``/``destination_url``, capture text/value fields, apply an allowlisted transform,
fill and read back destination fields, then verify saving. A stale confirmation is refused before submit.
``AC_browser_wait`` / ``browser_wait`` polls text/value reads only, including a newly visible element;
``wait_seconds`` defaults to 5, is capped by the action budget, and late matching replies are refused.
It never repeats a fill or click. Python/core, catalog/model schemas, MCP, CLI/REST task operations,
Builder and GUI workflow preview use the shared compiler. Browser readback can serve as independent
skill evidence. Actual application acceptance and reviewed upload/download grants remain open.
Managed browser startup requires WebRunner contract version 1 with complete bounded readback.

Exact WebRunner readback compatibility
----------------------------------------------------------------------

Managed browser startup now requires the exact WebRunner ``ManagedBrowserSession.contract_version == 1``
contract before constructing its policy or opening a proxy/browser. Missing, boolean, string, older or
unknown markers fail with an actionable readiness reason. SDK source ``575e5d2`` provides complete text/value
readback: at most 8,000 UTF-16 code units, with over-limit/invalid Unicode refusal instead of truncation.
AutoControl applies matching Unicode bounds to browser arguments and workflow preview data before effects.
The consumer/SDK source contract is tested through the real owned helper with fake Chromium; deployment
and real-browser/native acceptance remain separate from that evidence.

Independent browser completion checks
----------------------------------------------------------------------

Browser tasks accept pinned completion clauses such as
``{"kind":"browser","operation":"value","selector":"#field","value":"expected"}``.
Operations are exact ``text``, ``value``, ``visible`` (boolean), or ``url`` (no locator). They require an explicit
``AC_browser_read`` grant and task origins; completion cannot add permissions. At finish, the same owned
helper checks a current allowed HTTP(S) page and independently reads the full SDK value through guarded
read commands. Receipts, bounded previews and model stop messages do not substitute for those reads.
Blank/unavailable/out-of-scope pages, refused readbacks and invalid verifier replies remain unknown;
failed comparisons remain failed. Cancellation, authority revocation and human-review errors propagate.
GUI Actions can draft an inert browser completion example; API/MCP/REST/CLI finish share the verifier.
SPA URL fragments remain intact while origin checks exclude only the fragment. Browser/native
application acceptance and reviewed transfers remain open.

Rooted browser file transfers
----------------------------------------------------------------------

Managed browser file commands ``browser_link``, ``browser_download`` and ``browser_upload`` (with matching
``AC_browser_*`` commands) delegate to WebRunner transfer contract version 1. Download and upload grants
require explicit host/task roots. Downloads preserve scoped browser cookies inside the owned SDK/helper,
check complete length and optional SHA256, and publish without overwriting an existing file; reuse
requires its matching SHA256. Uploads read one regular file up to 4 MiB into a checked immutable snapshot,
verify optional SHA256 and SDK metadata, and never submit a form. Network operations remain in ``je_web_runner``.
The browser ``download_archive`` preview accepts a query ``url``, explicit ``allowed_origins``, rooted ``directory``
and ``files`` with a plain ``name`` and either ``url`` or link ``selector``/optional ``frame``; ``page_url`` can override
the query page per file. It captures fresh links, downloads at most 16 MiB per file and writes a manifest
whose names/sizes/hashes are independently verified. GUI Actions draft file target/workflow/upload examples
without starting resources. MCP/REST/CLI/Builder/model tools share these commands; link reads still require
drive-input authority. Deployment and real-browser acceptance remain open; existing acceptance pauses hold.

Local authority, API and concurrent budgets
----------------------------------------------------------------------

Local runtime principal and live-root forwarding now requires an explicit local-service call.
Generic authenticated HTTP requests carry the supplied bearer token; local user/store/witness metadata
is attached only by the runtime client after validating the loopback service destination and route.
The versioned ``je_auto_control.api`` namespace exposes every advertised ``api.core`` name, including
managed browser commands, target recovery and skills. Executor typing stubs include all shipped commands;
unresolved postponed project types use the generator's existing ``Any`` fallback instead of invalid names.
Concurrent budget readers sample clocks inside the exclusive database transaction, preventing false
task timeouts when readers acquire locks in a different order. Actual clock rollback remains fail-closed.
GUI/MCP/REST/CLI share these repaired client and API contracts. Production checkouts and existing
native/browser/device/24-hour acceptance pauses remain unchanged.

Browser skill context continuity
----------------------------------------------------------------------

A finite browser skill's verified prefix now requires its original live browser/helper context.
After pause, cleanup, helper loss or runtime restart, retained action history cannot prove that the
form still contains its previous values. Continuation enters human review before launching a replacement
helper or sending the next action. Review the remaining steps and create a new task explicitly.
Pausing before any retained attempt and attempts reviewed as failed/not-applied permit a fresh start.
External owners can reobserve a new context and plan fresh scoped actions; ordinary uninterrupted skills
continue on their existing session. Restoring authenticated/draft browser state remains open work.

Desktop skill context continuity
----------------------------------------------------------------------

Desktop finite skills now use the same context-continuity fence as browser skills. Retiring a
desktop scope or its owned helper requires review before an old prefix can continue; paused form/window
state is not established by historical receipts. Live uninterrupted contexts continue normally. File
adapters retain their persistent-artifact recovery. Target checks run before helper replacement, and
existing resume/status/receipt interfaces expose the human-review result. Draft/authentication/window
state restoration and reviewed remaining-step reconstruction remain open; native acceptance stays paused.

Isolated browser Python and dependency diagnostics
----------------------------------------------------------------------

Browser host profiles can select a reviewed installed Python environment through optional
``settings.helper_python`` (an absolute local interpreter path). Explicit helpers run with ``-I``, using
installed packages rather than the caller's ``PYTHONPATH`` or working directory. Virtualenv executable
symlinks retain their environment identity. Task options cannot select the interpreter.
Host managers can call ``manage_agent_target("probe", {"name":"reviewed-browser"})`` or use
``AC_agent_target``, MCP/REST, ``agent-task target probe request.json`` and the GUI Host targets operation.
The probe uses a separate bounded owned helper, imports browser dependencies through ``je_web_runner``,
then retires it without acquiring input ownership or starting a browser. Its result can say
``python_dependencies_ready``; ``browser_launch=not_probed`` and ``native_evidence=not_recorded`` stay explicit.
``last_probe`` is an in-memory timestamped diagnostic snapshot; passive readiness and task permissions
are unchanged by probing. Disabled targets stay disabled. Desktop/device native probes remain open.
The prepared isolated environment installs wheels from both feature worktrees. Shared environments
and production checkouts remain untouched; production service configuration and real-browser acceptance
remain separate work. Browser automation still belongs entirely to WebRunner (``je_web_runner``).

Remote-device lifecycle prerequisite
----------------------------------------------------------------------

Android/iOS managed adapters are not yet available. Internal ``remote_journal`` and
``remote_target`` bind a host-proven physical device to an OS lock and a durable controller/sequence
witness. A closed capability handshake is mandatory; begin/end events are fsynced before host ACK.
Configure and observe cannot authorize effects. An unconfirmed effect survives local helper retirement
and blocks transfer; cleanup never starts a replacement helper or replays remote commands.
An end event must certify settled device work with no held input or queued writes; merely returning
from a transport call is insufficient. This guarantee belongs to the trusted SDK adapter contract.

Recovery requires a host-trusted provider certifying the same physical device and all old writers
retired. It first persists a post-retirement epoch baseline, then requires a different epoch whose
provider contract invalidates old commands without replay. SDK epochs and idle guarantees are not
assumed. Generic desktop recovery cannot clear this witness. SDK adapters, app scope, device profiles,
public surfaces, real-device proof providers and native acceptance remain open in ``Progress.md``.

Explicit existing ADB server transport
----------------------------------------------------------------------

Internal ``android_transport.ManagedAdbServer`` uses the ADB smart-socket protocol against one reviewed
literal loopback address and port. It never invokes the CLI or starts, kills, upgrades or reconnects a
server. Device-list parsing is shared with the existing Android SDK. Shell calls select an exact numeric
transport ID, require shell-v2 raw framing, close stdin and require a one-byte exit packet followed by EOF.
A missing exit, late output, malformed/oversize frame, packet flood, timeout or disconnect is an error;
there is no automatic retry or old-shell fallback. Byte limits cover stdout and stderr together.

The original deadline covers the whole exchange; blocked reads/writes refresh cancellation and live
authority. Failure diagnostics cannot publish typed command data or server-provided text. This is a
host-only adapter prerequisite: raw shell is not in the task/model catalog. Numeric IDs can be reused
when an ADB server restarts. A finite adapter still needs physical-device/boot/app checks on the same
selected command connection, durable remote-effect fencing and independent completion evidence.
Shell exit alone does not prove input retirement. No managed Android profile or native readiness is added.

Protocol references: `AOSP smart-socket overview
<https://android.googlesource.com/platform/packages/modules/adb/+/refs/tags/android-14.0.0_r27/OVERVIEW.TXT>`_,
`AOSP transport selection
<https://android.googlesource.com/platform/packages/modules/adb/+/refs/tags/android-14.0.0_r27/client/adb_client.cpp>`_
and `AOSP shell packet layout
<https://android.googlesource.com/platform/packages/modules/adb/+/refs/tags/android-14.0.0_r27/shell_protocol.h>`_.

Android identity sessions and finite proposals
----------------------------------------------------------------------

Internal ``AndroidDeviceSession`` selects only an exact reviewed connection serial with one ready,
nonambiguous numeric transport. Read-only evidence validates the expected physical ``ro.serialno``,
kernel boot UUID and a single app/user focus on display zero. Bounded fixed-format AOSP window evidence
is parsed without retaining the raw window dump; unknown OEM formats fail closed. A boot is pinned
atomically after live checks and cannot be replaced by a later or concurrent inspection. Discovery and
identity reads share one deadline. No app is started and no device reset is requested.

``compile_android_action`` accepts only the existing tap/swipe/text/key names with closed arguments.
It builds a host-only proposal, never a model shell tool. The same selected command connection checks
physical identity, boot, focused display/window/activity both before and after its finite input.
Serial/boot sentinels preserve trailing evidence. Focus uses one labeled extraction and an exact quoted
comparison across all six field orders; labels preserve empty duplicate values despite trailing-newline
stripping. Missing/duplicate/empty/wrong values refuse before input or retain possible effects after it.
Pre/post scope and input-security checks stay in place, and no action budget is extended. Owned POSIX
fixtures use byte-exact Bash builtin file reads (including NUL/trailing newlines), falling back to cat
on other shells. Bounded fixture phase/timing/error diagnostics withhold commands, arguments and output.
Text is bounded printable ASCII, rejects lossy literal ``%s`` and is shell-quoted; keys are a finite
app-input set. Coordinate/duration and combined encoded command limits are checked before dispatch.
Only closed phase markers may be emitted; post-action scope changes or command failure are explicit failures,
never automatic retries or independent completion evidence.

Proposals retain ``input_authorized=false``. Focus identity alone is not an input-window hit test,
occlusion proof, unlock check or human-activity gate. Real device-control providers, scoped
hierarchy observations, independent completion checks, target profiles and shared user surfaces remain
open in ``Progress.md``. The existing native/device acceptance pause remains unchanged.

The recognized focus fields are based on the fixed AOSP Android 14 implementations of
`DisplayContent.dump
<https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-14.0.0_r27/services/core/java/com/android/server/wm/DisplayContent.java>`_
and `WindowManagerService.dumpWindowsNoHeaderLocked
<https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-14.0.0_r27/services/core/java/com/android/server/wm/WindowManagerService.java>`_.

Android native input/security evidence
----------------------------------------------------------------------

Internal ``inspect_input`` and ``propose_checked`` read current dispatcher and keyguard state in a
pinned device/app command connection, sharing the original deadline. The parser requires one default
display with a known identity display transform, a unique native app window/channel and quiescent
pending/inbound/outbound/wait queues. Both keyguard delegate and monitor must show the correct user,
unlocked, interactive and boot-complete state. Current state is separated from old ANR data. Historical
recent events and dynamic Looper clocks are excluded from stable security fingerprints.

``android_geometry`` uses exact rational intervals and native half-open rectangle edges to verify a
whole tap/swipe path, including internal gaps and isolated uncovered points. Input-window records are
front-to-back; visible occlusion, touch interception, outside-touch listeners and background spies are
checked without retaining foreign display names. Transparent windows can still intercept; an irrelevant
bounding-box overlap does not falsely block a diagonal path. Unsupported display transforms, scales,
formats or ambiguous targets fail closed. Window transforms are decoded without confusing local-window
coordinates with native global touch regions.

Checked command proposals hash the validated current routing/channel/queue block and keyguard block.
They reread both on the same command connection before input; a changed lock, channel, geometry or queue
refuses execution. The original device/boot/focus guards and fixed-result protocol remain. Global
monitors are explicit metadata requiring separate trusted review, not implicit approval. Evidence and
proposals retain ``input_authorized=false``. Trusted activity/held-input and device-fencing providers,
observation grounding and independent completion remain open in ``Progress.md``.

The internal action protocol v2 emits a closed ordered phase trace. A complete pre-input refusal has
one fixed refusal phase and matching shell-v2 exit. Once input may have been invoked, failure and
post-input refusal preserve that possibility, even when their exit codes match a pre-input check.
``parse_android_action_result`` requires exact bytes, no stderr and a matching exit from a complete
transport result. Old markers, truncation, transport errors and malformed traces remain unknown.
The returned-input phase certifies the script path only: it cannot settle a remote journal, prove
queues/held input retired, authorize retries or satisfy independent task completion.

Owned remote SDK worker
----------------------------------------------------------------------

``remote_worker.serve_remote_worker`` starts parent retirement monitoring before invoking a fixed
trusted host factory. No task/RPC field chooses the SDK, server, app binding or factory. The internal
``RemoteDeviceAdapter`` contract requires read-only readiness/observation/preparation, live physical
activity checks and a finite host-only ``PreparedRemoteAction``. Exact JSON scope binding distinguishes
booleans, integers and floats; both the host proxy and child refuse owner/scope replacement.

``RemoteEffectController`` waits for the host's durable begin ACK before invoking the SDK once.
The worker refreshes store-backed authority around input, checks deadlines and latches physical
takeover. An exact device/epoch proof must certify released input and an empty remote write queue before
end is emitted and acknowledged. A shell return or parsed Android phase cannot supply that proof.
Malformed/missing ACK, lost replies, revocation, timeout or failed settlement never trigger replay,
replacement or desktop release input. Cleanup retires the owned helper; unknown remote effects remain
quarantined. Real device-control providers, the WDA adapter, target profiles and shared
user surfaces remain open; simulated SDK contracts do not establish native device readiness.

Checked Android SDK dispatch
----------------------------------------------------------------------

Internal ``AndroidRemoteAdapter`` connects the session to the owned worker. It requires the exact
host-bound package and finite input tools, and withholds readiness before any ADB connection when no
``AndroidControlProvider`` is configured. The provider must independently enforce human activity/idle,
held-input state, global-monitor review and real device-side suppression of old writes on physical
takeover, cancellation or expiry. A host lock/context manager or local helper exit cannot implement that
contract. No default provider, managed profile or native readiness claim is supplied.

An action requires a fresh metadata-only native observation. Preparation rereads identity/routing/
security, refuses changed evidence and consumes that observation. A host-only ``AndroidCommandLease``
binds the checked proposal to a random request ID and epoch. After the worker's durable begin ACK,
``dispatch_checked`` recompiles the exact finite command and rejects altered arguments/body, unchecked
evidence or a different session/boot before transport. Calls execute only inside the trusted device
fence and are never replayed. Complete v2 phase/exit evidence is returned without claiming application
completion; partial results remain unknown. Settlement must separately match request ID, boot, device
and epoch and certify released input/no queued writes before end ACK. Old proof cannot settle a later
command. Without an explicit hierarchy reader, observations contain identity/security metadata only.
Real capture/control providers, protected field-value verification, Unicode/IME and shared profile/API/GUI
delivery remain open.

Reviewed Android semantic observations
----------------------------------------------------------------------

An optional host-only ``hierarchy_reader`` callable returns ``AndroidHierarchySample`` for the exact
capture request, native device/window and display size. The reader must attest its actual source and
preserve other accessibility owners; echoing requested metadata around an unverified SDK result is
insufficient. No default device, SDK connection, installation, CLI, reconnect or fallback is selected.
The pinned AOSP ``DumpCommand`` creates a ``UiAutomation`` connection; its default connection suppresses
other accessibility services. It is therefore not silently used as a read-only capture substitute.

``android_hierarchy`` accepts bounded UTF-8, single-window, rotation-zero XML with closed attributes and
exact booleans. Defused XML rejects DTD/entities/external sources. Depth, node/element counts, text and
native display bounds are limited; duplicate sibling indexes and ambiguous text grants fail closed.
Foreign-package subtrees are excluded. Only fresh explicit host path grants reveal non-sensitive,
read-only labels; XML attributes cannot grant permission. Password/editable values and protected
descendants stay masked. Native routing/occlusion checks mark whether a visible element is actionable.

Private keyed source witnesses detect even masked changes but are never published. Public observation
revisions are random, remain stable only for unchanged observations, and are replaced after source
changes/reversions and prepared actions, including input no-ops. They cannot serve as reusable hashes
of hidden values. Capture is bracketed by native scope checks; preparation and the device fence reread
the hierarchy before finite input. Indexed ``AC_android_tap`` references require a current actionable
Android semantic element, with no screenshot-coordinate fallback.

Existing observe/act/finish APIs carry reviewed post-action readback. A fresh ``screen.text_present``
condition can pass from a known reviewed match; absent content in an unavailable/redacted observation
is unknown, never proof of absence. A known visible match can contradict ``text_absent``. Other partial
screen predicates stay unknown until sufficient evidence exists. Source capability flags are exact
booleans; malformed elements/flags cannot turn verification green. This does not add protected input
value comparison, Unicode/IME, default managed profiles or native acceptance evidence.
Built-in ``DesktopTarget`` and ``BrowserTarget`` declare ``semantic_observation=True`` and
``text_redacted=True``: bounded controls, omitted values, masked edits and incomplete frames do not
establish complete text coverage. ``FileTarget`` and desktop window bootstrap declare
``semantic_observation=False``. An empty list from these sources cannot prove screen absence.
Partial-text checks ignore password/sensitive/redacted rows, explicitly hidden or invalid visibility,
and non-string labels. A mask placeholder is not a completion label. Combined clauses fail on a known
contradiction; otherwise any unknown requirement keeps the result unknown. Count/state/change clauses
remain unknown with partial evidence. Exact browser DOM/value conditions use the existing fresh
``kind=browser`` completion reads, with task read/origin grants. Targets that omit capability flags
retain legacy verification behavior and must supply their own reviewed coverage contract.

Primary format/lifecycle references:
`AOSP API 34 DumpCommand
<https://android.googlesource.com/platform/prebuilts/fullsdk/sources/+/88c7ff1cd72d6305ec59f97aadc2198cc2dc3592/android-34/com/android/commands/uiautomator/DumpCommand.java>`_,
`AccessibilityNodeInfoDumper
<https://android.googlesource.com/platform/prebuilts/fullsdk/sources/+/88c7ff1cd72d6305ec59f97aadc2198cc2dc3592/android-34/com/android/uiautomator/core/AccessibilityNodeInfoDumper.java>`_
and `UiAutomation default connection flags
<https://android.googlesource.com/platform/prebuilts/fullsdk/sources/+/88c7ff1cd72d6305ec59f97aadc2198cc2dc3592/android-34/android/app/UiAutomation.java>`_.

The pinned formats come from AOSP Android 14
`InputDispatcher <https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-14.0.0_r27/services/inputflinger/dispatcher/InputDispatcher.cpp>`_,
`WindowInfo <https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-14.0.0_r27/libs/gui/include/gui/WindowInfo.h>`_,
`Connection <https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-14.0.0_r27/services/inputflinger/dispatcher/Connection.cpp>`_,
`InputTransport <https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-14.0.0_r27/libs/input/InputTransport.cpp>`_,
and the framework ``KeyguardServiceDelegate``/``KeyguardStateMonitor`` implementations. Native/device
acceptance remains paused; simulated evidence does not advertise a managed Android target.

Reviewed successor tasks
--------------------------------

Review stopped tasks, reconstruct remaining work and explicitly approve a scoped successor.

.. toctree::
   :maxdepth: 2

   agent_recovery_doc
   agent_dag_batches_doc

Explicit local DAG evidence handoffs
----------------------------------------------------------------------

Existing recovery children held by another caller can provide completion evidence to their
original local DAG through an explicit revocable handoff. In ``manage_agent_recovery``, use
``review_handoff`` with the final ``task_id``, ``batch_id`` and ``node_id``; an authorized manager then calls
``create_handoff`` with the same IDs, returned ``handoff_review`` as ``review``, and a nonempty ``note``.
The service derives the recipient from the real original admission. In a ``review_continuation``
successor decision, explicitly include ``handoff_id`` alongside ``node_id``, ``action`` and ``task_id``, then
review and approve the whole continuation. At most sixteen real recovery links are supported,
including a privately admitted permanent read-only final verifier. Ordinary task ownership remains.

``get_handoff`` and ``revoke_handoff`` take ``handoff_id``; ``list_handoffs`` takes ``batch_id`` and ``node_id``.
Issuance and consumption refresh actual owners, admitting reviewers, issuing-session root witnesses,
current consumer ceilings, fixed scope, effect snapshots, independent completion and retirement.
Approval, start and late dependency validation recheck consent; revocation or evidence loss blocks
adoption. Grants expire no later than the earliest retained terminal witness's existing thirty-day
deadline. Returned data contains bounded IDs, hashes and status, without private task arguments,
captures or principal-store paths. No ordinary task-read/input access, ownership transfer or replay is
granted. Cross-host and non-DAG handoff contracts remain outstanding in ``Progress.md``.

The Agent Tasks Handoffs page has an operation selector and JSON editor; Actions prepare review,
create and revoke requests without dispatching them. Five editable ``agent_handoff_*.json`` examples
cover review/create/get/list/revoke. Python, AC, CLI, authenticated MCP, REST and Builder use the
same recovery operations. These checks establish contract and owned-file behavior; deferred native
desktop, browser, device and 24-hour acceptance still require their own evidence.
