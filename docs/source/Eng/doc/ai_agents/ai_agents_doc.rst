AI agents and computer use
===========================

Inspect a lost submission reply
--------------------------------

``lookup_agent_task("original-key")`` reads the current principal/store namespace without submitting,
resuming or acquiring input. The same operation is available as ``AC_agent_task_lookup``, MCP
``ac_agent_task_lookup``, ``POST /agent/lookup`` with only ``idempotency_key``, CLI
``agent-task lookup original-key`` and the task view's Actions menu. Results contain ``found`` and an
optional ``task`` status snapshot. Missing records are not proof of rejection: an outstanding request
can arrive later. Task access remains required for this read-only lookup. GUI results are discarded if
the key or selected task changes. Registered-host DAG review still requires its separate integration.

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

Use ``get_agent_task_receipts`` for per-row results and ``reconcile_agent_task`` to record an explicit
owner witness for an uncertain effect before resume. Task metadata links history, journal and reports.
Generated cache expires after thirty days; user outputs and external journals are preserved. Images
are ephemeral unless strict-redacted persistence is explicitly enabled.

``manage_agent_trigger`` captures approved interval/cron/file/event templates and refreshes the owner
on each fire. Event/task deduplication commits atomically. ``submit_agent_task`` accepts an optional
idempotency key; CLI and Actions expose trigger controls. Managed scopes reject ambient vault resolution.

Input ownership writes a private, fsynced per-resource crash witness before native dispatch and input ACK. An unfinished witness blocks new owners across databases. Explicit host-only recovery requires a review note and a trusted no-held-input probe, never replays persisted input or signals persisted PIDs, and does not reconcile/resume the old task. POSIX input helpers monitor their actual parent and retire only their own live session group. Approved document handoff runs outside the input helper tree, so user applications survive normal task cleanup; bounded, preapproved focus steps wait for scoped windows. Observations also expire against a host monotonic clock. Native desktop/device acceptance remains unverified.

Managed skill candidates store sealed task scopes, typed explicit data slots and source-task provenance in the runtime SQLite database. Recording requires confirmed receipts and independently verified success. Validation creates a distinct pinned task; publication requires that exact trial's successful completion, an explicit review note and a compare-and-set version. Semantic selector repairs create new candidates. In-flight tasks retain their original version/digest; arbitrary pointer receipts are not guessed into semantic skills. Legacy mutable SkillLibrary behavior is preserved.

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
