AI agents and computer use
===========================

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
