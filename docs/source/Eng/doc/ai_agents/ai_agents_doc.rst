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

Start with a small tool list and let the session search and enable the rest
(see "Tool modes" in the MCP server chapter):

.. code-block:: bash

   je_auto_control_mcp --tool-mode progressive

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
