==================================
MCP Server (Use AutoControl from Claude)
==================================

The MCP Server exposes AutoControl as a Model Context Protocol server
so any MCP-compatible client (Claude Desktop, Claude Code, custom
Claude API tool-use loops) can drive the host machine through
AutoControl. The transport is JSON-RPC 2.0 over stdio and is
implemented with the Python standard library only — no extra
dependencies are required.

What Claude can do once connected
=================================

After AutoControl is registered as an MCP server, the model gains
access to ~24 tools covering:

- Mouse control: ``ac_click_mouse``, ``ac_set_mouse_position``,
  ``ac_get_mouse_position``, ``ac_mouse_scroll``
- Keyboard: ``ac_type_text``, ``ac_press_key``, ``ac_hotkey``
- Screen: ``ac_screen_size``, ``ac_screenshot``, ``ac_get_pixel``
- Image / OCR: ``ac_locate_image_center``, ``ac_locate_and_click``,
  ``ac_locate_text``, ``ac_click_text``
- Windows (Win32 only): ``ac_list_windows``, ``ac_focus_window``,
  ``ac_wait_for_window``, ``ac_close_window``
- System: ``ac_get_clipboard``, ``ac_set_clipboard``
- Action executor: ``ac_execute_actions`` (run a list of ``AC_*``
  commands), ``ac_execute_action_file``, ``ac_list_action_commands``,
  ``ac_list_run_history``

Starting the server (programmatic)
==================================

.. code-block:: python

   import je_auto_control as ac

   # Blocks until stdin closes — typical entry point for an MCP client.
   ac.start_mcp_stdio_server()

You can also build a custom registry:

.. code-block:: python

   import je_auto_control as ac

   tools = ac.build_default_tool_registry()
   server = ac.MCPServer(tools=tools)
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

Both forms speak MCP over stdin/stdout — they are not meant to be run
interactively from a terminal.

Registering with Claude Desktop
===============================

Edit Claude Desktop's MCP config (``claude_desktop_config.json``) and
add an entry under ``mcpServers``:

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

Security notes
==============

- The MCP server can move the mouse, send keystrokes, screenshot the
  screen, and execute arbitrary ``AC_*`` actions. Only register it
  with MCP clients you trust.
- The transport is local stdio — there is no network exposure.
- File paths supplied to ``ac_screenshot`` and ``ac_execute_action_file``
  are normalised through ``os.path.realpath`` before any I/O.
