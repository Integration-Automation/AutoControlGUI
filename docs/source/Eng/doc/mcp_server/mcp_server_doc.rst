==========================================
MCP Server (Use AutoControl from Claude)
==========================================

The MCP server exposes AutoControl as a Model Context Protocol
service so any MCP-compatible client (Claude Desktop, Claude Code,
custom Anthropic / OpenAI tool-use loops) can drive the host machine
through AutoControl. Implementation is stdlib-only — JSON-RPC 2.0
over stdio or HTTP+SSE — no extra runtime dependencies.

Roughly 90 tools are exposed, plus the full set of MCP protocol
capabilities: tools, resources, prompts, sampling, roots, logging,
progress, cancellation, list-changed notifications, and elicitation.

Tool catalogue
==============

The default registry pairs every canonical ``ac_*`` tool with a
short alias (``click``, ``type``, ``screenshot``, ...) so prompts
can stay terse. Use ``--list-tools`` (see *CLI inspection* below) to
dump the live catalogue as JSON.

Mouse / keyboard
  ``ac_click_mouse``, ``ac_set_mouse_position``,
  ``ac_get_mouse_position``, ``ac_mouse_scroll``,
  ``ac_drag``, ``ac_send_mouse_to_window``,
  ``ac_type_text``, ``ac_press_key``, ``ac_hotkey``,
  ``ac_send_key_to_window``.

Screen / image / OCR
  ``ac_screen_size``, ``ac_screenshot`` (returns base64 PNG image
  content + optional file save, supports ``monitor_index`` for
  multi-display setups), ``ac_list_monitors``, ``ac_get_pixel``,
  ``ac_diff_screenshots``, ``ac_locate_image_center``,
  ``ac_locate_and_click``, ``ac_locate_text``, ``ac_click_text``,
  ``ac_wait_for_image``, ``ac_wait_for_pixel``.

Window management (Windows)
  ``ac_list_windows``, ``ac_focus_window``, ``ac_wait_for_window``,
  ``ac_close_window``, ``ac_window_move``, ``ac_window_minimize``,
  ``ac_window_maximize``, ``ac_window_restore``. The last three answer with
  a tool error (``isError``) when the window is gone or, for maximise and
  restore, when Windows refuses to bring it to the foreground -- the window
  may then have changed state without becoming the active one. They used to
  return the window handle either way.

Semantic locators
  ``ac_a11y_list``, ``ac_a11y_find``, ``ac_a11y_click``,
  ``ac_vlm_locate``, ``ac_vlm_click``.

Clipboard / processes / shell
  ``ac_get_clipboard``, ``ac_set_clipboard``,
  ``ac_get_clipboard_image``, ``ac_set_clipboard_image``,
  ``ac_launch_process``, ``ac_list_processes``,
  ``ac_kill_process``, ``ac_shell``.

Recording / replay
  ``ac_record_start``, ``ac_record_stop``,
  ``ac_read_action_file``, ``ac_write_action_file``,
  ``ac_trim_actions``, ``ac_adjust_delays``,
  ``ac_scale_coordinates``,
  ``ac_screen_record_start``, ``ac_screen_record_stop``,
  ``ac_screen_record_list``.

Action executor / history
  ``ac_execute_actions``, ``ac_execute_action_file``,
  ``ac_list_action_commands``, ``ac_list_run_history``.

Scheduler / triggers / hotkeys
  ``ac_scheduler_add_job``, ``ac_scheduler_remove_job``,
  ``ac_scheduler_list_jobs``, ``ac_scheduler_start``,
  ``ac_scheduler_stop``, ``ac_trigger_add``, ``ac_trigger_remove``,
  ``ac_trigger_list``, ``ac_trigger_start``, ``ac_trigger_stop``,
  ``ac_hotkey_bind``, ``ac_hotkey_unbind``, ``ac_hotkey_list``,
  ``ac_hotkey_daemon_start``, ``ac_hotkey_daemon_stop``.

Remote desktop (TCP host + viewer registry)
  ``ac_remote_host_start``, ``ac_remote_host_stop``,
  ``ac_remote_host_status``, ``ac_remote_viewer_connect``,
  ``ac_remote_viewer_disconnect``, ``ac_remote_viewer_status``,
  ``ac_remote_viewer_send_input``. These wrap the same singleton
  registry the GUI's Remote Desktop tab uses and act on its active host
  or viewer whoever opened it (the status results name that ``owner``;
  a GUI panel whose session a tool replaces or ends closes its window), so a model can spin
  up a host (``token``, ``bind``, ``port``, ``fps``, ``quality``,
  ``host_id``), open a viewer to another machine, query status, and
  forward mouse / keyboard / type / hotkey actions through the
  active viewer. Status tools are read-only and survive
  ``--readonly`` mode; ``send_input`` is destructive by design.

Every tool carries the MCP 2025-06-18 ``annotations`` block
(``readOnlyHint``, ``destructiveHint``, ``idempotentHint``,
``openWorldHint``) so well-behaved clients can auto-approve
read-only queries and require user confirmation before destructive
ones.

A tool is destructive when it sends input, runs an action list, script or
code (now, or later from a scheduler, trigger, hotkey, watch or voice
command), deletes data, sends data off the machine, or loosens a security
control (egress, USB ACL, approvals, secret leases, hosting a remote
session). A tool that writes a file at a path the caller chooses is never
read-only, and a read-only tool given a ``db`` that does not exist answers
with an empty result instead of creating the file. ``ac_assert_http`` only
sends ``GET`` or ``HEAD``.

Arguments that fail the tool's input schema -- a missing or mistyped
property, a value outside an ``enum``, or one the schema does not declare --
are refused before the tool runs, as a tool execution error: a result with
``isError: true`` whose text says what was wrong, so the model can retry with
corrected arguments (MCP 2025-11-25). An unknown tool or a request that is not
a ``tools/call`` at all is still a ``-32602`` protocol error.

A tool that fails with any exception is answered the same way, ``isError: true``
with the error's type and message, so no call is left without a reply. A tool
that ran is not reported as failed because the audit log could not be written;
that is logged instead. A message that is not a JSON-RPC 2.0 request -- no or a
wrong ``jsonrpc``, a ``method`` that is not a string, an ``id`` that is not a
string, a number or ``null`` -- is ``-32600``. A request with ``"id": null`` is
answered with ``"id": null``; only a message without an ``id`` member is a
notification.

Resources, prompts, sampling
============================

Resources
  - ``autocontrol://files/<name>`` — every JSON action file in the
    workspace root (re-targets when the client publishes
    ``roots/list``). Only a plain ``*.json`` name is readable; other
    files in the root, subdirectories and ``:`` stream names are not.
  - ``autocontrol://history`` — recent run-history snapshot.
  - ``autocontrol://commands`` — full ``AC_*`` executor catalogue.
  - ``autocontrol://screen/live`` — base64 PNG screenshots, with
    ``resources/subscribe`` push notifications when content changes.

Prompts
  Five built-in templates: ``automate_ui_task``,
  ``record_and_generalize``, ``compare_screenshots``,
  ``find_widget``, ``explain_action_file``.

Sampling
  Tools can call ``server.request_sampling(messages, ...)`` to ask
  the connected client model a question — useful when an automation
  step needs an LLM judgment (e.g. "is this dialog showing an
  error?"). Bridges through the same writer that handles tool
  responses.

Logging notifications, progress, cancellation
=============================================

- The project logger is forwarded to the client as
  ``notifications/message`` while a stdio session is active.
  Clients can retune the level with ``logging/setLevel``. A 2026-07-28
  request gets the records it produces, and only when it sets
  ``io.modelcontextprotocol/logLevel`` (see `Stateless requests
  (2026-07-28)`_).
- Long-running tools that accept a ``ctx`` parameter receive a
  :class:`ToolCallContext` and can call
  ``ctx.progress(value, total, message)`` to push
  ``notifications/progress`` (when the client supplied a
  ``progressToken``) and ``ctx.check_cancelled()`` to abort
  cooperatively when ``notifications/cancelled`` arrives.

Starting the server (programmatic)
==================================

.. code-block:: python

   import je_auto_control as ac

   # Blocks until stdin closes — typical entry point for an MCP client.
   ac.start_mcp_stdio_server()

You can also build a custom registry, swap in a fake backend, or
attach plugin hot-reload:

.. code-block:: python

   import je_auto_control as ac

   tools = ac.build_default_tool_registry(read_only=False, aliases=True)
   server = ac.MCPServer(tools=tools)
   watcher = ac.PluginWatcher(server, "./plugins")
   watcher.start()
   server.serve_stdio()

Starting the server (command line)
==================================

After ``pip install -e .`` (or ``pip install je_auto_control``), the
console script ``je_auto_control_mcp`` is on ``$PATH``. You can also
run it as a module:

.. code-block:: shell

   je_auto_control_mcp
   # or
   python -m je_auto_control.utils.mcp_server

Both forms speak MCP over stdin/stdout — they are not meant to be
run interactively from a terminal.

CLI inspection flags
====================

Without any flags the entry point starts the stdio dispatcher.
Supplying one of the following prints the catalogue as JSON and
exits — useful in CI smoke tests and prompt prep:

.. code-block:: shell

   je_auto_control_mcp --list-tools
   je_auto_control_mcp --list-tools --read-only
   je_auto_control_mcp --list-resources
   je_auto_control_mcp --list-prompts
   je_auto_control_mcp --read-only          # serve only the read-only tools
   je_auto_control_mcp --tool-mode progressive   # a small core; see "Tool modes"
   je_auto_control_mcp --list-tools --tool-mode progressive   # what a new session sees
   je_auto_control_mcp --fake-backend       # swap in the in-memory backend

One ``--list-*`` flag prints its array; several print one object keyed
``tools`` / ``resources`` / ``prompts``. Output, and the stdio server's
messages, are UTF-8 whatever the console's code page.

Registering with Claude Desktop
===============================

Edit ``claude_desktop_config.json`` and add an entry under
``mcpServers``:

.. code-block:: json

   {
     "mcpServers": {
       "autocontrol": {
         "command": "python",
         "args": ["-m", "je_auto_control.utils.mcp_server"]
       }
     }
   }

Restart Claude Desktop. The AutoControl tools appear in the tool
picker and the model can call them automatically.

Registering with Claude Code
============================

.. code-block:: shell

   claude mcp add autocontrol -- python -m je_auto_control.utils.mcp_server

Or add to your project's ``.claude/mcp.json``:

.. code-block:: json

   {
     "mcpServers": {
       "autocontrol": {
         "command": "python",
         "args": ["-m", "je_auto_control.utils.mcp_server"]
       }
     }
   }

HTTP transport (with SSE, auth, TLS)
====================================

When stdio is awkward (long-running GUI host, container, remote
box), start the same dispatcher behind HTTP:

.. code-block:: python

   import je_auto_control as ac
   import ssl

   ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
   ssl_context.load_cert_chain("server.crt", "server.key")

   server = ac.start_mcp_http_server(
       host="127.0.0.1", port=9940,
       auth_token="hunter2",
       ssl_context=ssl_context,
   )

- ``POST /mcp`` accepts JSON-RPC bodies. Returns
  ``application/json`` by default; if ``Accept`` includes
  ``text/event-stream`` the response streams progress notifications
  followed by the final result as SSE events.
- A missing or wrong ``Authorization: Bearer <token>`` returns 401
  with a ``WWW-Authenticate: Bearer`` challenge (``error="invalid_token"``
  when a wrong token was sent), as the MCP authorization specification
  requires; the compare is constant-time (``hmac.compare_digest``).
- ``ssl_context`` wraps the listening socket so the same transport
  can serve HTTPS.
- The default bind is ``127.0.0.1`` per the project's
  least-privilege policy — opt into ``0.0.0.0`` only with explicit
  reason.

Bearer token can also come from ``JE_AUTOCONTROL_MCP_TOKEN``.

**Roles (opt-in RBAC).** Set ``JE_AUTOCONTROL_RBAC_USERS`` to a user store
file, or pass ``user_store=UserStore(path)`` to ``start_mcp_http_server`` /
``HttpMCPServer``, and the HTTP transport authenticates each request as one
user of that store instead of comparing a shared token (``auth_token`` and
``JE_AUTOCONTROL_MCP_TOKEN`` are then not accepted, and a bearer token is
always required). The store, its roles and how to create users are described
under *Roles* in the operations-layer REST API chapter; both servers can
share one file. Without a store nothing changes. The stdio transport has no
bearer token and is never subject to RBAC.

- A tool needs ``read_screen`` when it is marked ``readOnlyHint`` and
  ``drive_input`` otherwise. ``ac_remote_host_start`` / ``_stop``,
  ``ac_usb_acl_add`` / ``_remove`` / ``_set_default``,
  ``ac_usb_passthrough_enable``, ``ac_egress_allow`` / ``_reset`` and
  ``ac_load_plugins`` need ``manage_hosts`` (``admin``); ``ac_user_add`` /
  ``_remove`` / ``_set_role`` / ``_rotate_token`` / ``_list`` need
  ``manage_users`` (``admin``).
- Read-only is not the same as harmless to show: the read-only tools that
  return the host's data rather than the state of its screen need
  ``read_data``, which ``operator`` and ``admin`` hold and ``viewer`` does
  not. They are the clipboard tools (``ac_get_clipboard`` and its
  ``_csv`` / ``_files`` / ``_html`` / ``_image`` / ``_rtf`` variants,
  ``ac_clipboard_formats``, ``ac_assert_clipboard``, ``ac_clip_history_list``
  / ``_search``); the file readers (``ac_load_dotenv``, ``ac_load_data``,
  ``ac_read_action_file``, ``ac_read_document``, ``ac_read_presentation``,
  ``ac_read_workbook``, ``ac_extract_pdf_text``, ``ac_assert_pdf_text``,
  ``ac_assert_file``, ``ac_build_provenance``, ``ac_verify_provenance``); the
  database and store readers (``ac_sql_query``, ``ac_assert_db``,
  ``ac_get_asset``, ``ac_list_assets``, ``ac_cas_get``, ``ac_outbox_pending``,
  ``ac_checkpoint_status``, ``ac_memory_recall``, ``ac_memory_recent``,
  ``ac_s3_list``); references and tokens (``ac_resolve_ref``,
  ``ac_resolve_refs``, ``ac_generate_otp``, ``ac_jwt_encode``,
  ``ac_jwt_decode``); and the process list, network and microphone probes
  (``ac_list_processes``, ``ac_assert_process``, ``ac_wait_for_process``,
  ``ac_assert_http``, ``ac_wait_for_port``, ``ac_assert_audio``). The list is
  ``DATA_TOOLS`` in ``je_auto_control.utils.rbac.policy``. A ``viewer`` keeps
  every other read-only tool: screen size, windows, pixels, image and text
  location, accessibility reads, waits.
- ``tools/list`` returns only the tools the caller may call, and
  ``tools/call`` on any other answers JSON-RPC error ``-32003``
  (``Forbidden: ...``, ``data.required_capability``) without running it.
- A tool that takes an action list (``ac_execute_actions`` and the like) is
  refused the same way when the list contains a command the caller's role
  does not grant, such as ``AC_sign_action_file`` for an operator.
- A token whose role the store does not define gets HTTP 403.
- Each audit line carries ``user_id`` and ``role``; a refused call is
  recorded with ``"status": "denied"``.

Browser requests are refused unless they come from this machine: a request
whose ``Origin`` header is not a loopback origin gets 403, and when the
server is bound to loopback so does one whose ``Host`` header does not name
loopback (DNS rebinding). Clients that are not browsers send no ``Origin``
and are unaffected. To let a browser-based client on another origin in, list
its exact origins in ``JE_AUTOCONTROL_MCP_ALLOWED_ORIGINS``
(comma-separated, e.g. ``https://tool.example:8443``).

With ``JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE=1``, a handshake-era client that
advertised ``elicitation`` must have its session's event stream open for a
destructive call to be confirmed; without one the call is refused rather than run. Only
the session a prompt was sent to can answer it.

Sessions
========

``initialize`` agrees on a protocol version: the client's, when it is one the
server speaks (``2025-11-25``, ``2025-06-18``, ``2025-03-26``, ``2024-11-05``),
otherwise the newest of those. A 2025-11-25 client also gets a ``description``
in ``serverInfo``. 2026-07-28 drops ``initialize`` altogether and is served
per request instead (see `Stateless requests (2026-07-28)`_); an
``initialize`` naming it gets 2025-11-25. Over HTTP a request whose
``MCP-Protocol-Version`` header names a version the server does not speak is
refused with 400 and an ``UnsupportedProtocolVersion`` (``-32022``) error
listing the ones it does. The server declares only server
capabilities (tools, resources, prompts, logging); it sends
``sampling/createMessage``, ``roots/list`` and ``elicitation/create`` only to a
client that declared the matching capability.

``initialize`` mints a session and returns it in an
``Mcp-Session-Id`` response header. Echo that header on every later
request and the server keeps one scope for you — the capabilities
you advertised, and the slots your in-flight calls occupy — no
matter how many TCP connections you use. Without it each request is
scoped to its own connection, which is all the transport used to
offer.

- ``GET /mcp`` with ``Accept: text/event-stream`` and a valid
  ``Mcp-Session-Id`` opens the **standing server-to-client stream**.
  Server-initiated traffic that is not a reply to a specific request
  travels down it: progress notifications, and the
  ``elicitation/create`` behind the confirmation gate below. One
  stream per session; a second ``GET`` gets 409. The stream carries
  an SSE comment as a heartbeat so an abandoned socket surfaces as a
  write error rather than a parked thread.
- Answer a server request by ``POST``\ ing an ordinary JSON-RPC
  response — with the session header — on any connection. It is
  matched to the waiting call by id, and acked with 202.
- ``DELETE /mcp`` with the header terminates the session and
  releases everything scoped to it. Without the header it is
  accepted as a no-op, so sessionless clients keep working.
- An unknown or expired id is refused with **404**, not served under
  a fresh scope: the client holds state the server does not, and
  needs to know to re-initialize.
- With roles on (RBAC), a session belongs to the user whose ``initialize``
  minted it. Any other user who presents its id -- on a ``POST``, on the
  ``GET`` stream or on ``DELETE`` -- is refused with **403**, and the attempt
  does not keep the session alive. The id used to be honoured for every
  authenticated user, so one user could attach to another's stream, end
  their session, or read which tools they had enabled. Without a user store
  nobody is identified and the id works as before.
- A tool registered or removed outside any request -- a plugin picked up by
  the watcher thread -- sends ``notifications/tools/list_changed`` down the
  standing stream of every session. A session with no ``GET`` stream has
  nowhere to receive it.
- Sessions are bounded. They are swept after ten minutes untouched
  (a standing stream keeps its own session fresh), and the registry
  evicts the least recently seen once it holds 128.

Stateless requests (2026-07-28)
===============================

The server speaks both protocol eras and decides per request. A request
whose ``params._meta`` carries ``io.modelcontextprotocol/protocolVersion``
is served statelessly, from that request alone; ``initialize``, and every
request without the key, is served as described under `Sessions`_. So an
existing client keeps working unchanged next to a 2026-07-28 one.

- **Per-request fields.** ``io.modelcontextprotocol/clientCapabilities``
  (an object) is required next to the version; ``clientInfo`` and
  ``logLevel`` are optional. A missing or malformed field is ``-32602``.
  A version the server does not serve statelessly is ``-32022``, whose
  ``data`` lists ``supported`` (``2026-07-28`` first, then the
  handshake-era versions, which need ``initialize``) and ``requested``.
- **``server/discover``** answers ``supportedVersions``, the server's
  ``capabilities`` (tool-list changes and resource subscriptions, both
  through ``subscriptions/listen``) and its identity. Without the per-request fields it is
  ``-32602``.
- **Methods.** ``tools/list``, ``tools/call``, ``resources/list``,
  ``resources/read``, ``prompts/list``, ``prompts/get`` and
  ``subscriptions/listen``. The revision removed ``ping``,
  ``logging/setLevel`` and ``resources/(un)subscribe``; they are ``-32601``
  in a stateless request.
- **``subscriptions/listen``** opens one subscription per request. Its
  ``notifications`` filter may ask for ``toolsListChanged`` and for
  ``resourceSubscriptions`` (a list of URIs; ``autocontrol://screen/live`` is
  the subscribable one). The first message is
  ``notifications/subscriptions/acknowledged`` with the part the server
  will send: ``promptsListChanged`` and ``resourcesListChanged`` are left
  out, since those lists never change, and so is a URI that cannot be
  subscribed. Every notification after it carries the request's id under
  ``_meta["io.modelcontextprotocol/subscriptionId"]``. The request gets an
  answer only when the server ends the subscription (``serve_stdio``
  finishing, ``HttpMCPServer.stop()``): a ``complete`` result with the same
  ``_meta``. The client ends it with ``notifications/cancelled`` on stdio or
  by closing the stream over HTTP, which needs ``Accept: text/event-stream``
  (406 otherwise). An id that is already listening is ``-32600``, and a
  malformed filter is ``-32602``.
- **Results.** Every result carries ``resultType`` (``complete``, or
  ``input_required`` below) and the server's name, version and description
  under ``_meta["io.modelcontextprotocol/serverInfo"]``. ``server/discover``,
  the three lists and ``resources/read`` also carry caching hints:
  ``cacheScope`` is always ``private``; ``ttlMs`` is an hour for
  ``server/discover``, a minute for the lists, and ``0`` for
  ``resources/read``, whose content is live.
- **Nothing the client did not ask for.** The capabilities the gates read
  are the request's own, not a connection's; the server sends no request of
  its own (``request_sampling`` and ``refresh_roots`` raise inside a
  stateless request); log records go out only for a request that set
  ``logLevel``, at that level or above; and a stdio peer whose first
  request was stateless is sent no background log records, and list changes
  and resource updates only through its ``subscriptions/listen``.
- **Confirmation** of destructive tools is a multi round-trip: see
  `Confirmation prompts (elicitation)`_.
- **Over HTTP** a request is stateless when its ``MCP-Protocol-Version``
  header or its ``_meta`` says 2026-07-28. It must mirror its body into
  headers: ``MCP-Protocol-Version`` equal to the ``_meta`` version,
  ``Mcp-Method`` equal to ``method``, and for ``tools/call`` / ``prompts/get``
  / ``resources/read`` also ``Mcp-Name`` equal to the tool or prompt name or
  the resource URI (``=?base64?...?=`` for a value that is not plain ASCII).
  A missing or disagreeing header is 400 with ``HeaderMismatch``
  (``-32020``); a bad version, missing metadata or a missing client
  capability is 400; an unknown method is 404. No session is kept:
  ``Mcp-Session-Id`` is ignored and none is minted, and ``GET`` / ``DELETE``
  naming 2026-07-28 are 405. A plain JSON ``POST`` works for everything,
  confirmation included, since the question comes back in the result; an
  SSE ``POST`` additionally carries the call's progress notifications.

Tool modes: full, progressive, static
=====================================

By default ``tools/list`` answers with every registered tool. That is the
**full** mode; it is the default and its replies are unchanged. Two other
modes exist for a client that should not carry several hundred schemas it
will never use:

.. list-table::
   :header-rows: 1
   :widths: 16 84

   * - Mode
     - What ``tools/list`` offers
   * - ``full``
     - Every tool, in one reply. The default.
   * - ``progressive``
     - Five core tools. A session searches the registry, reads the schema of
       what it wants and enables it; from then on the tool is in *that
       session's* list and can be called.
   * - ``static``
     - A fixed profile and nothing else; nothing can be enabled. For a client
       that reads the list once and never again.

Choose the mode with ``JE_AUTOCONTROL_MCP_TOOL_MODE``, with
``je_auto_control_mcp --tool-mode {full,progressive,static}``, or in code:

.. code-block:: python

   import je_auto_control as ac

   ac.start_mcp_stdio_server(tool_mode="progressive")
   ac.start_mcp_http_server(tool_mode="progressive")
   ac.HttpMCPServer(tool_mode="static")

``AC_start_mcp_server`` and ``AC_start_mcp_http_server`` take the same
``tool_mode`` argument, and the variable reaches every way of starting a
server. A value that is none of the three stops the server from starting
rather than quietly offering everything. A dispatcher's mode is fixed when it
is built, so ``tool_mode`` passed together with an ``mcp=`` that is in
another mode raises ``ToolDisclosureError``.

**The core tools** (progressive mode only):

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - Tool
     - What it does
   * - ``ac_tools_search``
     - ``query``, ``limit`` (1-50, default 10), optional ``category`` and
       ``capability``. Returns rows of ``name`` / ``summary`` / ``category`` /
       ``capability`` / ``read_only`` / ``takes_paths`` / ``enabled`` plus
       ``total`` and ``truncated`` -- never a schema.
   * - ``ac_tools_schema``
     - The full descriptor of one tool, by ``name``.
   * - ``ac_tools_enable``
     - ``names``: tool names, or ``category:<name>`` for a whole category.
       Replies with ``enabled`` / ``already_enabled`` / ``unavailable`` and
       whether ``notifications/tools/list_changed`` was sent.
   * - ``ac_tools_disable``
     - Removes tools the session enabled.
   * - ``ac_tools_state``
     - The mode, what the session has enabled, the categories and their
       sizes, and the limits calls are held to (read-only, path roots,
       ``env://`` allowlist, role).

A category is the name of the factory that builds the tools (``mouse``,
``screen``, ``window`` ...); a plugin's tools are in ``plugin``.

**Sessions.** The enabled set belongs to one session and to nobody else:
an ``Mcp-Session-Id`` over HTTP (or, for a client that ignores the header,
its connection), and the one implicit session of a stdio server. It is
released when the session is deleted, swept, evicted, when the connection
closes or when the stdio loop ends. Enabling or disabling sends
``notifications/tools/list_changed`` to that session only; a plain HTTP
``POST`` with no standing ``GET`` stream has nowhere to receive it, so the
reply says ``"list_changed_sent": false`` and the client should request
``tools/list`` again.

**Paging.** In these two modes ``tools/list`` is paged, 100 tools to a page
(``server.disclosure.page_size``): a result with more to come carries
``nextCursor``, to be sent back as ``cursor``. Every page carries the id of
the list it belongs to under ``_meta``
``io.github.integration-automation/toolSnapshot``. A cursor continues the
list as it was when its first page was requested, even if a plugin was
loaded or removed in between, so no page mixes two registries. A cursor that
is malformed, belongs to another session, or names a list the server no
longer keeps (it remembers the last eight per session) is answered
``-32602``; request ``tools/list`` again without one. The full mode is not
paged and ignores ``cursor``, as before.

**The static profile.** ``JE_AUTOCONTROL_MCP_TOOL_PROFILE`` is a
comma-separated list of tool names and ``category:<name>`` entries. In
static mode it is the whole list; unset, the profile is the 19 tools behind
the short aliases (``ac_click_mouse``, ``ac_type_text``, ``ac_screenshot``
...). In progressive mode a configured profile is offered to every session
beside the core, so a client that never refreshes its list still has those
tools. MCP has no client capability that says "I follow
``tools/list_changed``", so the server cannot detect such a client: use the
static mode, or a profile, for one. A 2026-07-28 request is always served
the static profile in progressive mode -- that revision has no session for
an enabled set to live in.

**What the mode does not change.** It decides what is *offered*, never what
is *allowed*:

* Every call still goes through the same gates in the same order -- role,
  input schema, path roots and ``env://`` allowlist, rate limit,
  confirmation -- and is audited as before.
* Search, schema and enable answer from what the caller may call. A tool the
  caller's role does not grant, or that read-only mode rules out, is not
  found, not described and reported as ``unavailable`` when enabled.
* A call to a tool the session's list does not hold is answered ``-32602``
  and recorded in the audit log as ``denied``. A role refusal keeps its own
  code, ``-32003``.
* In read-only mode a mutating tool cannot be enabled, including one a
  plugin registers after the server started.
* A tool a plugin removes is gone from every session at once. If the same
  name is registered again later, it has to be enabled again.
* The core tools' names cannot be registered over or removed.

**What it costs.** ``benchmarks/mcp_discovery.py`` measures both modes
in-process through the dispatcher both transports use. On the 680-tool
registry (2026-10-09, one Windows 11 machine, median of 30):

.. list-table::
   :header-rows: 1
   :widths: 40 30 30

   * - Figure
     - ``full``
     - ``progressive``
   * - Tools in a new session's ``tools/list``
     - 680
     - 5
   * - Size of that result
     - 327,378 bytes
     - 2,411 bytes (0.74 %)
   * - ``initialize`` + ``initialized`` + ``tools/list``
     - 43.7 ms
     - 1.0 ms
   * - One ``ac_tools_search`` (10 rows, 2,390 bytes)
     - --
     - 3.1 ms
   * - One ``ac_tools_schema``
     - --
     - 0.3 ms
   * - One ``ac_tools_enable`` + ``ac_tools_disable``
     - --
     - 0.9 ms

.. code-block:: shell

   python benchmarks/mcp_discovery.py --rounds 30

Read-only / safe mode
=====================

Set ``JE_AUTOCONTROL_MCP_READONLY=1`` (or pass ``--read-only`` to
``je_auto_control_mcp``, or ``read_only=True`` to
:func:`build_default_tool_registry`) to drop every tool whose
``readOnlyHint`` is false. Only observers (positions, OCR queries,
clipboard reads, history, ...) survive:

.. code-block:: json

   {
     "mcpServers": {
       "autocontrol_safe": {
         "command": "python",
         "args": ["-m", "je_auto_control.utils.mcp_server"],
         "env": {"JE_AUTOCONTROL_MCP_READONLY": "1"}
       }
     }
   }

Confining file arguments to root directories
============================================

Read-only mode limits *which tools* exist, not *which files* they open:
``ac_load_dotenv``, ``ac_read_document`` or ``ac_extract_pdf_text`` will read
any file the server process can. To bound that, give the server roots. It is
off by default — a server with neither variable set behaves exactly as
before, read-only mode included.

``JE_AUTOCONTROL_MCP_PATH_ROOTS``
    Directories separated by ``os.pathsep`` (``;`` on Windows, ``:``
    elsewhere). Setting it turns the check on.

``JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT``
    ``1`` / ``true`` / ``yes`` / ``on`` to also accept the directories the
    client reports through ``roots/list``, in addition to the variable
    above. It turns the check on by itself too; until the client has
    answered, every file argument is refused rather than let through. Only
    use it with a client you trust to describe the workspace — over HTTP any
    caller that can reach the server can report roots.

.. code-block:: json

   {
     "mcpServers": {
       "autocontrol_safe": {
         "command": "python",
         "args": ["-m", "je_auto_control.utils.mcp_server"],
         "env": {"JE_AUTOCONTROL_MCP_READONLY": "1",
                 "JE_AUTOCONTROL_MCP_PATH_ROOTS": "C:/work/project"}
       }
     }
   }

With roots in force, every tool argument whose schema says
``"format": "path"`` is resolved with ``os.path.realpath`` and must land
inside a root. ``..``, a symlink or junction leading out, another drive and a
UNC share are all judged by where they really lead; a path starting with
``~`` has to be inside the roots both expanded and taken literally. A
refusal is a tool execution error (``isError: true``, ``Invalid arguments
for <tool>: ...``), like any other bad argument. The tool then receives the
canonical absolute path that was checked, so a relative path is relative to
the server's working directory.

The annotation follows meaning, not the property's name: ``ac_json_query``'s
``path`` is a JSONPath expression and is left alone. What it does **not**
reach:

* ``ac_execute_actions`` and the other tools that run an action list — an
  action can open any file, which is why they are not read-only tools.
* Arguments that are a path only sometimes: ``target`` of ``ac_open_path`` /
  ``ac_plan_open`` / ``ac_file_association`` (path or URL or extension) and of
  ``ac_act_in_view`` (template path or text), ``ac_handle_file_dialog``'s
  ``path`` (keystrokes typed into another application), ``argv`` of
  ``ac_launch_process`` / ``ac_shell``, and paths inside free-form objects
  (``ac_run_suite`` ``spec``, ``ac_run_dag`` ``definition``,
  ``ac_assert_all`` ``specs``).
* Tools registered by plugins, unless their schema carries the annotation.

``ac_resolve_ref`` / ``ac_resolve_refs`` follow the same roots for
``file://`` references, and have a switch of their own for ``env://``:

``JE_AUTOCONTROL_MCP_ENV_REF_ALLOW``
    Comma-separated variable names, ``fnmatch`` patterns allowed
    (``APP_*,HOME``). When set, ``env://NAME`` resolves only for a matching
    name and anything else is a tool execution error. Unset, every variable
    is readable, as before — including the ones that hold API keys.

Programmatically, the same policy is ``server.argument_policy``
(:class:`ArgumentPolicy` holding a :class:`je_auto_control.PathPolicy` and
the allowlist); assign another to a server you build yourself.

Confirmation prompts (elicitation)
==================================

Set ``JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE=1`` to gate every
destructive tool behind an MCP ``elicitation/create`` request. The
client surfaces a confirmation prompt; declining returns a clean
error to the model without running the action. Requires the client
to advertise the ``elicitation`` capability — older clients fall
through with a logged warning.

The prompt is a question the server asks *between* receiving a call
and answering it, so it needs a channel the client is listening on
at that moment. What that means per transport:

- **stdio** — always available; the client is on the other end of
  the same pipe.
- **HTTP** — available to a client that echoes ``Mcp-Session-Id``
  (see `Sessions`_) and gives the server somewhere to send the
  question. Either channel does: the standing ``GET`` stream, or an
  SSE ``POST``, whose own response stream carries the
  ``elicitation/create`` before the result. Either way the answer
  comes back as a separate ``POST`` — the client is busy reading the
  stream it asked on.

A **2026-07-28** request is never sent ``elicitation/create``. The first
call is answered with ``resultType: "input_required"``: the question under
``inputRequests["confirm"]`` and a ``requestState``. The client asks the
user and retries the same call, with the same arguments, the answer in
``inputResponses["confirm"]`` (for example ``{"action": "accept"}``) and the
``requestState`` echoed back. The state is signed with a key that lives only
in the server process, names the tool and a digest of its arguments,
expires after five minutes and is accepted once; a state that fails any of
that is ``-32602``. Over HTTP this needs no session and no open stream. ``decline`` or ``cancel`` is a tool execution error
(``isError: true``) and the tool does not run; a retry without an answer is
asked again. A stateless client that did not declare ``elicitation`` gets
``-32021`` with ``data.requiredCapabilities`` naming it, instead of the
handshake era's unprompted run.

.. warning::

   A client that ignores ``Mcp-Session-Id``, or that only ever sends
   plain JSON ``POST``\ s with no stream open, has given the server
   nowhere to ask — so
   destructive tools run **unprompted**, exactly as they do for a
   stdio client that never advertised ``elicitation``. That fallback
   is logged, but it is a fallback: on an HTTP-exposed server treat
   the bearer token, the ``127.0.0.1`` bind and
   ``JE_AUTOCONTROL_MCP_READONLY`` as the controls that do not
   depend on the client behaving.

Audit log
=========

Set ``JE_AUTOCONTROL_MCP_AUDIT=/path/to/audit.jsonl`` to append one
JSONL record per ``tools/call``: timestamp, tool name, sanitised
arguments (``password`` / ``passphrase`` / ``token`` / ``secret`` /
``api_key`` / ``key`` / ``authorization`` and similar names are redacted at
any depth, and action lists are masked like the executor log), status
(``ok`` / ``error`` /
``cancelled``), duration, optional error text, and optional
auto-screenshot artifact path (see below).

Auto-screenshot on tool error
=============================

Set ``JE_AUTOCONTROL_MCP_ERROR_SHOTS=/path/to/dir`` to write a
``<tool>_<ts>.png`` screenshot every time a tool errors. The path
is included in both the audit record and the error message
returned to the model — fast forensic trail for flaky automations.

Rate limiting
=============

Pass a :class:`RateLimiter` to :class:`MCPServer` to guard against
runaway loops:

.. code-block:: python

   import je_auto_control as ac

   server = ac.MCPServer(rate_limiter=ac.RateLimiter(
       rate_per_sec=20.0, capacity=40,
   ))

Exceeding the limit returns a ``-32000`` ``Rate limit exceeded``
JSON-RPC error.

Plugin hot-reload
=================

Drop ``*.py`` files exposing top-level ``AC_*`` callables into a
directory and let :class:`PluginWatcher` keep the registry in sync:

.. code-block:: python

   import je_auto_control as ac

   server = ac.MCPServer()
   watcher = ac.PluginWatcher(server, directory="./plugins",
                                poll_seconds=2.0)
   watcher.start()
   ac.start_mcp_stdio_server()

Each register / unregister fires
``notifications/tools/list_changed`` so the client refreshes its
cached catalogue automatically.

CI smoke tests with the fake backend
====================================

The fake backend swaps the wrapper layer with in-memory recorders
so headless CI runners can exercise every MCP tool without a
display server:

.. code-block:: shell

   JE_AUTOCONTROL_FAKE_BACKEND=1 python -m je_auto_control.utils.mcp_server

Programmatically:

.. code-block:: python

   from je_auto_control.utils.mcp_server.fake_backend import (
       fake_state, install_fake_backend, reset_fake_state,
       uninstall_fake_backend,
   )

   install_fake_backend()
   try:
       # Run tests / tools — actions accumulate in fake_state().
       ...
   finally:
       uninstall_fake_backend()
       reset_fake_state()

Security notes
==============

- The MCP server can move the mouse, send keystrokes, screenshot
  the screen, and execute arbitrary ``AC_*`` actions. Only register
  it with MCP clients you trust.
- Local stdio is the default transport — no network exposure unless
  you opt into HTTP. HTTP defaults to ``127.0.0.1``; binding to
  ``0.0.0.0`` requires an explicit, documented reason and **must**
  be paired with ``auth_token`` and (for non-localhost) ``ssl_context``.
- File paths supplied to ``ac_screenshot``, ``ac_screen_record_start``,
  ``ac_execute_action_file``, ``ac_read_action_file``,
  ``ac_write_action_file``, and the FileSystem resource provider are
  normalised via ``os.path.realpath``; the resource provider blocks
  path traversal at the boundary.
- Subprocess calls (``ac_launch_process`` / ``ac_shell``) accept
  argv lists or a command line (POSIX-split, or passed to
  ``CreateProcess`` as written on Windows) — never an OS shell.
