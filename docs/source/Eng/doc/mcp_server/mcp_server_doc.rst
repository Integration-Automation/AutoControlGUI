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
  ``ac_window_maximize``, ``ac_window_restore``.

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
  registry the GUI's Remote Desktop tab uses, so a model can spin
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

Resources, prompts, sampling
============================

Resources
  - ``autocontrol://files/<name>`` — every JSON action file in the
    workspace root (re-targets when the client publishes
    ``roots/list``).
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
  Clients can retune the level with ``logging/setLevel``.
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
   je_auto_control_mcp --fake-backend       # swap in the in-memory backend

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
- Missing / wrong ``Authorization: Bearer <token>`` returns 401 /
  403 (constant-time compare via ``hmac.compare_digest``).
- ``ssl_context`` wraps the listening socket so the same transport
  can serve HTTPS.
- The default bind is ``127.0.0.1`` per the project's
  least-privilege policy — opt into ``0.0.0.0`` only with explicit
  reason.

Bearer token can also come from ``JE_AUTOCONTROL_MCP_TOKEN``.

Read-only / safe mode
=====================

Set ``JE_AUTOCONTROL_MCP_READONLY=1`` (or pass ``read_only=True`` to
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

Confirmation prompts (elicitation)
==================================

Set ``JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE=1`` to gate every
destructive tool behind an MCP ``elicitation/create`` request. The
client surfaces a confirmation prompt; declining returns a clean
error to the model without running the action. Requires the client
to advertise the ``elicitation`` capability — older clients fall
through with a logged warning.

Audit log
=========

Set ``JE_AUTOCONTROL_MCP_AUDIT=/path/to/audit.jsonl`` to append one
JSONL record per ``tools/call``: timestamp, tool name, sanitised
arguments (``password`` / ``token`` / ``secret`` / ``api_key`` /
``authorization`` are redacted), status (``ok`` / ``error`` /
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
  argv lists or ``shlex.split`` parses — never an OS shell.
