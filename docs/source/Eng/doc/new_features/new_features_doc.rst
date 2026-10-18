======================
New Features (2026-04)
======================

This page documents the April 2026 additions to AutoControl. Every new
feature ships with a headless Python API **and** a GUI affordance, and is
wired into the executor so it works from JSON scripts, the socket server,
the REST API, and the CLI without any Python glue.

.. contents::
   :local:
   :depth: 2


Clipboard
=========

Headless::

   import je_auto_control as ac
   ac.set_clipboard("hello")
   text = ac.get_clipboard()

Action-JSON commands::

   [["AC_clipboard_set", {"text": "hello"}]]
   [["AC_clipboard_get", {}]]

Backends: Windows (Win32 via ``ctypes``), macOS (``pbcopy``/``pbpaste``),
Linux (``xclip`` or ``xsel``). A ``RuntimeError`` is raised if no backend
is available.


Dry-run / step-debug executor
=============================

Run an action list through the executor without invoking any side effects
— useful for validating JSON scripts::

   from je_auto_control.utils.executor.action_executor import executor
   record = executor.execute_action(actions, dry_run=True)

``step_callback`` lets you observe each action before it runs::

   executor.execute_action(actions, step_callback=lambda a: print(a))

From the CLI::

   python -m je_auto_control.cli run script.json --dry-run


Global hotkey daemon (Windows)
==============================

Bind OS-level hotkeys to action-JSON scripts::

   from je_auto_control import default_hotkey_daemon
   default_hotkey_daemon.bind("ctrl+alt+1", "scripts/greet.json")
   default_hotkey_daemon.start()

Supported modifiers: ``ctrl``, ``alt``, ``shift``, ``win`` / ``super`` /
``meta``. Keys: letters, digits, ``f1`` … ``f12``, arrows, ``space``,
``enter``, ``tab``, ``escape``, ``home``, ``end``, ``insert``, ``delete``,
``pageup``, ``pagedown``.

macOS and Linux currently raise ``NotImplementedError`` on
``start()`` — the Strategy-pattern interface is in place so backends can
be added later.

GUI: **Hotkeys** tab (bind/unbind, start/stop daemon, live fired count).


Event triggers
==============

Poll-based triggers fire an action script when a screen/state change is
detected::

   from je_auto_control import default_trigger_engine, ImageAppearsTrigger
   default_trigger_engine.add(ImageAppearsTrigger(
       trigger_id="", script_path="scripts/click_ok.json",
       image_path="templates/ok_button.png", threshold=0.85,
       repeat=True,
   ))
   default_trigger_engine.start()

Available trigger types:

- ``ImageAppearsTrigger`` — template match on the current screen
- ``WindowAppearsTrigger`` — title substring match
- ``PixelColorTrigger`` — pixel color within tolerance
- ``FilePathTrigger`` — mtime change on a path

GUI: **Triggers** tab (add/remove/start/stop, live fired count).


Cron scheduling
===============

Five-field cron (``minute hour day-of-month month day-of-week``) with
``*``, comma-lists, ``*/step``, and ``start-stop`` ranges::

   from je_auto_control import default_scheduler
   job = default_scheduler.add_cron_job(
       script_path="scripts/daily.json",
       cron_expression="0 9 * * 1-5",   # 09:00 on weekdays
   )
   default_scheduler.start()

Interval and cron jobs coexist in the same scheduler; ``job.is_cron``
tells them apart. GUI: **Scheduler** tab has cron/interval radio.


Plugin loader
=============

A plugin file is any ``.py`` defining top-level callables whose names
start with ``AC_``. Each one becomes a new executor command::

   # my_plugins/greeting.py
   def AC_greet(args=None):
       return f"hello, {args['name']}"

::

   from je_auto_control import (
       load_plugin_directory, register_plugin_commands,
   )
   commands = load_plugin_directory("my_plugins/")
   register_plugin_commands(commands)

   # Now usable from JSON:
   # [["AC_greet", {"name": "world"}]]

A file that fails to import is logged and skipped; the rest of the directory
still loads. ``register_plugin_commands`` skips (and logs) a value that is not a
function and a name that already belongs to a built-in command such as
``AC_click_mouse``; pass ``allow_override=True`` to replace one on purpose.
A plugin may always re-register its own commands (a reload).

GUI: **Plugins** tab (browse directory, one-click register).

.. warning::
   Plugin files execute arbitrary Python. Only load from directories
   under your own control.


REST API server
===============

A stdlib-only HTTP server that exposes the executor and scheduler::

   from je_auto_control import start_rest_api_server
   server = start_rest_api_server(host="127.0.0.1", port=9939)

Endpoints:

- ``GET /health`` — liveness probe
- ``GET /jobs`` — scheduler job list
- ``POST /execute`` with body ``{"actions": [...]}`` — run actions

GUI: **Socket Server** tab now has a separate REST section with its own
host/port and a ``0.0.0.0`` opt-in.

.. note::
   Defaults to ``127.0.0.1`` per CLAUDE.md policy. Bind to ``0.0.0.0``
   only when you have authenticated the network boundary.


CLI runner
==========

A thin subcommand-based CLI over the headless APIs::

   python -m je_auto_control.cli run script.json
   python -m je_auto_control.cli run script.json --var name=alice --dry-run
   python -m je_auto_control.cli list-jobs
   python -m je_auto_control.cli start-server --port 9938
   python -m je_auto_control.cli start-rest --port 9939

``--var name=value`` is parsed as JSON when possible (so ``count=10``
becomes an int), otherwise treated as a string.


Multi-language GUI (i18n)
=========================

Live language switching via the **Language** menu. Built-in packs:

- English
- Traditional Chinese (繁體中文)
- Simplified Chinese (简体中文)
- Japanese (日本語)

Register additional languages at runtime::

   from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
       language_wrapper,
   )
   language_wrapper.register_language("French", {"menu_file": "Fichier", ...})

Missing keys fall through to the English default, so a feature ships
with usable labels even before its translations land.


Closable tabs + menu bar
========================

The main window is now a ``QMainWindow`` with:

- **File** → Open Script, Exit
- **View → Tabs** → checkable entries for every tab (restore closed tabs)
- **Tools** → Start hotkey daemon / scheduler / trigger engine
- **Language** → select a registered language pack
- **Help** → About

Close any tab with its ✕ button; re-open it via *View → Tabs*.

Factory-built feature panels are deleted on the next Qt event-loop turn, releasing
their destruction-bound subscriptions and timers. Reopening creates a fresh panel,
so save edits first. View-menu hiding and ``hide_tab`` preserve the existing panel.
Embedders can use ``tab_registry.open(key)`` / ``close(key)`` or ``close_tab(key)``;
a panel that refuses its close event stays open. Legacy owner-built forms and
Remote Desktop retain their widgets pending lifecycle migration.


OCR (text on screen)
====================

Tesseract-backed text locator. Useful when a button or label has no
stable accessibility name and no template image::

   import je_auto_control as ac

   matches = ac.find_text_matches("Submit")
   cx, cy = ac.locate_text_center("Submit")
   ac.click_text("Submit")
   ac.wait_for_text("Loading complete", timeout=15.0)

If Tesseract isn't on ``PATH``::

   ac.set_tesseract_cmd(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

Action-JSON commands: ``AC_locate_text``, ``AC_click_text``,
``AC_wait_text``.


Accessibility element finder
============================

Query the OS accessibility tree (Windows UIA via ``comtypes``, macOS AX
via pyobjc, Linux AT-SPI over D-Bus) by name / role / app name::

   import je_auto_control as ac

   elements = ac.list_accessibility_elements(app_name="Calculator")
   ok = ac.find_accessibility_element(name="OK", role="Button")
   ac.click_accessibility_element(name="OK", app_name="Calculator")
   field = ac.focused_accessibility_element()   # keyboard focus, or None

``focused_accessibility_element(app_name=None)`` returns the element holding
keyboard focus, or ``None`` when nothing is focused; with ``app_name`` it is
``None`` unless the focused element belongs to that application. The
accessibility recorder follows this element.

Matches with an on-screen rectangle come first; one without (a control on a
hidden tab page reports ``(0, 0, 0, 0)``) comes last, and
``click_accessibility_element`` returns ``False`` rather than click it at the
corner of the screen.

Raises ``AccessibilityNotAvailableError`` on platforms where no backend
is installed. Action-JSON commands: ``AC_a11y_list``, ``AC_a11y_find``,
``AC_a11y_find_all``, ``AC_a11y_focused``, ``AC_a11y_click``. GUI:
**Accessibility** tab (Actions menu: *Show focused element*).


VLM (AI) element locator
========================

When neither template matching nor accessibility can find the element,
describe it in plain language and let a vision-language model return
pixel coordinates::

   import je_auto_control as ac

   x, y = ac.locate_by_description("the green Submit button")
   ac.click_by_description(
       "the cookie-banner 'Accept all' button",
       screen_region=[0, 800, 1920, 1080],  # optional crop
   )

``None`` / ``False`` means the model did not find the element. A request that
fails (network, authentication, rate limit) raises ``VLMRequestError`` instead
of reading as "not found". The Anthropic backend sends the capture fitted to
the model's image limits and maps the reply back to its pixels; replies such as
``x=512, y=300``, ``{"x": 512, "y": 300}`` or ``512.4, 300.6`` are all read.

Backends (loaded lazily, zero imports at package import time):

- Anthropic (``anthropic`` SDK, ``ANTHROPIC_API_KEY``)
- OpenAI (``openai`` SDK, ``OPENAI_API_KEY``)

Environment variables (keys are never logged or persisted):

- ``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``
- ``AUTOCONTROL_VLM_BACKEND=anthropic|openai``
- ``AUTOCONTROL_VLM_MODEL=<model-id>``

Action-JSON commands: ``AC_vlm_locate``, ``AC_vlm_click``. GUI:
**AI Locator** tab.


Run history + error-snapshot artifacts
======================================

Every run from the scheduler, trigger engine, hotkey daemon, REST API,
and manual GUI replay is recorded to ``~/.je_auto_control/history.db``
(SQLite). When a run finishes with an error, a screenshot is captured
automatically and attached to the row::

   from je_auto_control import default_history_store

   for run in default_history_store.list_runs(limit=20):
       print(run.id, run.source, run.status, run.artifact_path)

Artifacts are stored under ``~/.je_auto_control/artifacts/`` and are
removed when the matching run is pruned or the history is cleared. GUI:
**Run History** tab — double-click the artifact column to open the
screenshot in the OS image viewer.


OCR — region dump and regex search
==================================

The OCR module already exposed substring / exact-match helpers. Two new
APIs cover scenarios the existing ones could not::

   import je_auto_control as ac

   # Dump every recognised text record in a region (or full screen)
   for match in ac.read_text_in_region(region=[0, 0, 800, 600]):
       print(match.text, match.center, match.confidence)

   # Regex search — useful when text varies (order numbers, error codes)
   for match in ac.find_text_regex(r"Order#\d+"):
       print(match.text, match.center)

   # Compiled patterns and flags work too
   import re
   ac.find_text_regex(re.compile(r"foo", re.IGNORECASE))

Action-JSON commands::

   [["AC_read_text_in_region", {"region": [0, 0, 800, 600]}]]
   [["AC_find_text_regex", {"pattern": "Order#\\d+"}]]

GUI: **OCR Reader** tab. Pick a region with the existing overlay (or
leave blank for full screen), set language / minimum confidence, then
hit *Dump region text* or *Find by regex*. Results are returned as a
JSON list with text, bounding box, and confidence per hit.


Runtime variables and data-driven control flow
==============================================

Pre-execution interpolation in ``script_vars.interpolate`` only
substituted ``${var}`` placeholders once against a static mapping;
scripts had no way to mutate state during execution. ``VariableScope``
is a runtime mapping the executor exposes to flow-control commands so
they can read and write the same bag the runtime interpolator consults.

The executor now resolves ``${var}`` per command call (not pre-flattened),
so nested ``body`` / ``then`` / ``else`` lists keep their placeholders
and re-bind each time they execute — letting ``AC_for_each`` iterate
over a list while the body sees the current item.

Variable scope per run
----------------------

Variables live for one top-level run, not for the life of the process.
``execute_action_with_vars``, a REST ``/execute`` or ``/execute_file``
request, an MCP tool call, a socket-server command, a scheduler job, a
trigger / hotkey / webhook / e-mail firing, a ChatOps ``/run`` and a voice
command each open a fresh ``VariableScope``. ``AC_set_var``, loop variables
and macro parameters work as before inside that run and are gone when it
ends, so a later run's ``${user}`` fails with ``Unknown variable`` instead of
reading what an earlier caller set. To carry a value from one run to the
next, pass it in again (``execute_action_with_vars(actions, variables)``, a
webhook payload) or keep it outside the scope (a file, the secrets vault).

Plain Python calls are unchanged: ``executor.execute_action(...)`` and the
module-level ``execute_action(...)`` use the module executor's own scope,
which lasts as long as the process -- this is the scope the GUI's Variables
tab shows and scripts run from the GUI use. Wrap such calls in
``execution_scope`` to isolate them the same way::

   import je_auto_control as ac

   with ac.execution_scope({"user": "alice"}) as scope:
       ac.execute_action([["AC_set_var", {"name": "n", "value": 1}]])
       ac.execute_action([["AC_inc_var", {"name": "n"}]])
       scope.get_value("n")          # 2
   # "user" and "n" are gone here

The binding is per thread: concurrent server requests never see each other's
variables, and the previous scope is restored when the block ends, error or
not. Nested action lists (``AC_circuit_call``, ``AC_bulkhead_run``,
``AC_run_chaos``, ``AC_run_dag`` and the like) run in the scope of the list
that called them, also inside an ``AC_parallel`` branch; a branch starts from
a copy of its parent's variables and its own writes stay in the branch.
An executor you construct yourself (``Executor()``) always owns its scope.

CLI ``run`` (including ``--dry-run``), top-level ``run_from_description`` and
``StateMachine.run()`` also isolate variables. A planner or FSM called inside an
existing ``execution_scope`` shares it, so variables survive across the plan's
actions and the machine's states, then end with the outer run. The FSM's mutable
``context`` remains a separate caller-owned scratch pad.

New threads inherit context when Python's thread context inheritance is enabled
(the free-threaded default), or when the caller explicitly copies the context.
Use a fresh ``execution_scope`` in an independent worker to isolate its variables.

::

   import je_auto_control as ac
   from je_auto_control.utils.executor.action_executor import executor

   executor.execute_action([
       ["AC_set_var", {"name": "items", "value": ["alpha", "beta"]}],
       ["AC_set_var", {"name": "i", "value": 0}],
       ["AC_for_each", {
           "items": "${items}", "as": "name",
           "body": [
               ["AC_inc_var", {"name": "i"}],
               ["AC_if_var", {
                   "name": "i", "op": "ge", "value": 2,
                   "then": [["AC_break"]], "else": [],
               }],
           ],
       }],
   ])

Comparison operators for ``AC_if_var`` (and ``AC_while_var``): ``eq``,
``ne``, ``lt``, ``le``, ``gt``, ``ge``, ``contains``, ``startswith``,
``endswith``.

``AC_while_var`` loops a ``body`` while a variable comparison holds. The
condition is re-evaluated against the live scope before every iteration,
so a body that mutates the variable (e.g. ``AC_inc_var``) terminates the
loop; ``max_iter`` (default 1000) caps a condition that never turns
false. ``AC_break`` / ``AC_continue`` work as in any loop::

   executor.execute_action([
       ["AC_set_var", {"name": "i", "value": 0}],
       ["AC_while_var", {
           "name": "i", "op": "lt", "value": 5,
           "body": [["AC_inc_var", {"name": "i"}]],
       }],
   ])

``AC_try`` adds try / catch / finally. When ``body`` raises, the
``catch`` branch runs instead of aborting the script; ``finally`` always
runs (on success, on a caught error, or while a ``reraise`` / loop
break/continue propagates). The error text is exposed to ``error_var``
for the ``catch`` branch to inspect, and ``reraise=true`` re-raises after
cleanup. A failure anywhere inside ``body`` counts, including inside a loop,
an ``AC_if_*`` branch or a macro it runs: nested bodies inherit the strictness
of the list running them, which also makes ``AC_retry`` retry them and
``execute_action(..., raise_on_error=True)`` raise from them::

   executor.execute_action([
       ["AC_try", {
           "body": [["AC_click_image", {"image": "dialog_ok.png"}]],
           "catch": [["AC_set_var", {"name": "dismissed", "value": False}]],
           "finally": [["AC_screenshot", {"file_path": "after.png"}]],
           "error_var": "err",
       }],
   ])

Action-JSON commands: ``AC_set_var``, ``AC_get_var``, ``AC_inc_var``,
``AC_if_var``, ``AC_for_each``, ``AC_while_var``, ``AC_try``.

GUI: **Variables** tab — live view of ``executor.variables`` with
single-set, JSON seed, and clear-all controls; reflects what
``AC_set_var`` / ``AC_for_each`` mutate at runtime.


LLM action planner
==================

Translate a plain-language description into a validated ``AC_*``
action list by asking an LLM (Anthropic Claude by default). Output is
parsed leniently (strips code fences, extracts the first JSON array
from prose) and then validated by the same schema the executor uses,
so the result can be piped straight into ``execute_action``::

   import je_auto_control as ac
   from je_auto_control.utils.executor.action_executor import executor

   actions = ac.plan_actions(
       "click the Submit button, then type 'done' and save",
       known_commands=executor.known_commands(),
   )
   executor.execute_action(actions)

   # Or in one call:
   ac.run_from_description("open Notepad and type hello", executor=executor)

Backend selection mirrors ``vision.backends``:

- Anthropic (``anthropic`` SDK, ``ANTHROPIC_API_KEY``) — default
- ``AUTOCONTROL_LLM_BACKEND`` and ``AUTOCONTROL_LLM_MODEL`` for overrides

Action-JSON commands: ``AC_llm_plan``, ``AC_llm_run``.

GUI: **LLM Planner** tab. Description box, ``QThread``-backed *Plan*
button, action-list preview, and a *Run plan* button — long calls run
off the GUI thread so the UI stays responsive.


Remote desktop (host + viewer)
==============================

Stream this machine's screen to another machine, **or** view and
control a remote machine — both directions ship with a headless API
and a GUI tab.

The wire format is a length-prefixed framing on raw TCP (no extra
deps), starting with an HMAC-SHA256 challenge/response handshake;
viewers that fail auth are dropped before they can see a frame. JPEG
frames are produced at the configured FPS / quality and broadcast to
authenticated viewers via a shared latest-frame slot, so a slow viewer
drops frames instead of blocking the rest. Viewer input messages are
JSON, validated against an allowlist, and applied through the existing
mouse / keyboard wrappers.

Headless host (be remoted by someone else)::

   from je_auto_control import RemoteDesktopHost

   host = RemoteDesktopHost(
       token="hunter2",          # shared secret (HMAC key)
       bind="127.0.0.1",         # default; expose externally only via
                                 # SSH tunnel or trusted VPN
       port=0,                   # 0 = auto-assigned
       fps=10, quality=70,
   )
   host.start()
   print("listening on", host.port, "viewers:", host.connected_clients)
   # ...
   host.stop()

Headless viewer (control someone else)::

   from je_auto_control import RemoteDesktopViewer

   viewer = RemoteDesktopViewer(
       host="10.0.0.5", port=51234, token="hunter2",
       on_frame=lambda jpeg_bytes: ...,   # render or save
   )
   viewer.connect()
   viewer.send_input({"action": "mouse_move", "x": 100, "y": 200})
   viewer.send_input({"action": "type", "text": "hello"})
   viewer.disconnect()

Input message allowlist (validated on the host before dispatch):

- ``mouse_move`` ``{x, y}``
- ``mouse_click`` ``{x?, y?, button}``
- ``mouse_press`` / ``mouse_release`` ``{button}``
- ``mouse_scroll`` ``{x?, y?, amount}``
- ``key_press`` / ``key_release`` ``{keycode}``
- ``type`` ``{text}``
- ``ping``

Action-JSON commands (use the singleton in
``utils.remote_desktop.registry``)::

   AC_start_remote_host       # token, bind, port, fps, quality, region
   AC_stop_remote_host
   AC_remote_host_status      # → {running, port, connected_clients, host_id, owner}

   AC_remote_connect          # host, port, token, timeout
   AC_remote_disconnect
   AC_remote_viewer_status    # → {connected, host_id, owner}
   AC_remote_send_input       # action: {...}

**Who owns the host and the viewer.** The registry holds one host and one
viewer per transport (TCP, WebSocket), and records the *owner* that opened
each: ``"script"`` for these commands, the ``AC_ws_*`` ones and the MCP
``ac_remote_*`` tools, and a token of its own (``quick-connect#1``,
``viewer-tab#2``, ``host-tab#3``) for each GUI panel. The ``*_status``
results name it under ``owner`` (``None`` when nothing is active).

- A script that uses only these commands behaves as it always did: a second
  ``AC_remote_connect`` replaces the first, ``AC_remote_disconnect`` ends it.
- In a process that also runs the GUI, the commands still act on *the*
  active host or viewer of that transport, whoever opened it:
  ``AC_remote_viewer_status`` and ``AC_remote_send_input`` see a session a
  panel opened, ``AC_remote_connect`` replaces it and
  ``AC_remote_disconnect`` / ``AC_stop_remote_host`` end it. The panel is
  told, closes its remote-screen window and returns to idle.
- A panel only reads, drives and disconnects the viewer it opened itself.
  *Connect* on one panel still replaces the other panel's session on the
  same transport — there is one viewer per transport — but the replaced
  panel closes its window instead of freezing on the last frame, and its
  *Disconnect* no longer reaches the session that replaced it. Starting a
  host no longer disconnects any viewer. *Stop* on either host surface
  stops the host shown as running, whoever started it.

From Python the same model is ``remote_desktop_registry.adopt(slot,
resource, owner, on_displaced)``, ``owned(slot, owner)``, ``release(slot,
owner)``, ``evict(slot, by)`` and ``owner_of(slot)``, with ``slot`` one of
``"host"``, ``"viewer"``, ``"ws_host"``, ``"ws_viewer"`` and owner tokens
from ``je_auto_control.utils.remote_desktop.registry.new_owner(label)``.
``stop_host`` / ``disconnect_viewer`` (and the ``ws`` pair) take an optional
``owner=`` that limits them to that owner's host or viewer.
``on_displaced(slot, by)`` runs on the thread that did the replacing.

GUI: **Remote Desktop** tab opens to the **Quick Connect** screen
(AnyDesk-style) by default — huge Host ID on one side, a single input
that accepts ``host:port``, ``ws://``, ``wss://``, or a 9-digit Host
ID on the other, with *Connect* and *Start hosting* as the two primary
buttons. The session opens in a popup window that forwards your mouse
and keyboard to the host. A ``wss://`` target verifies the host's
certificate against the system trust store; for a self-signed host, use
the Advanced viewer and tick *Skip cert verification (self-signed)*. Recent connections are remembered across sessions. Advanced
per-transport sub-tabs (legacy TCP / WS host + viewer, WebRTC host +
viewer with manual SDP / custom codecs / TLS pinning) stay one click
away. WebRTC sub-tabs lazy-load so a stock install without the
``[webrtc]`` extra still opens the tab.

.. warning::
   Anyone with the host:port and token gets full mouse / keyboard
   control of the host machine. Defaults bind to ``127.0.0.1``;
   exposing this to untrusted networks should be paired with an SSH
   tunnel or TLS front-end. The token is the *only* line of defence —
   treat it like a password.


Remote desktop — Quick Connect + Phase 4/5 hardening
====================================================

Quick Connect headless API
--------------------------

The transport coordinator that backs the GUI input box is also
exported, so scripts can dispatch the same way::

   from je_auto_control import parse_remote_desktop_target
   parse_remote_desktop_target("192.168.1.10:5555")
   # ConnectTarget(kind='tcp', host='192.168.1.10', port=5555, ...)
   parse_remote_desktop_target("ws://hub:8765/desk")
   # ConnectTarget(kind='ws', host='hub', port=8765, path='/desk')
   parse_remote_desktop_target("123-456-789")
   # ConnectTarget(kind='webrtc_id', host_id='123456789')

Connection approval + view-only mode
------------------------------------

Optional callback gates every incoming session AnyDesk-style.
Returning ``"view_only"`` admits the viewer but drops their ``INPUT``,
``CLIPBOARD`` and file-transfer messages; returning a falsy value (or
raising) sends ``AUTH_FAIL`` "rejected by host"::

   from je_auto_control import RemoteDesktopHost, PendingViewer

   def gate(p: PendingViewer) -> str:
       if p.address[0].startswith("10."):
           return "view_only"
       return "full"  # or True

   host = RemoteDesktopHost(token="tok", on_pending_viewer=gate)

IP allowlist (CIDR + exact IPs)
-------------------------------

Reject peers outside the configured ranges *before* TLS / auth runs,
so attackers can't probe further. Invalid entries are dropped with a
warning; a list whose every entry is invalid admits nobody::

   host = RemoteDesktopHost(
       token="tok",
       ip_allowlist=["10.0.0.0/8", "192.168.1.100"],
   )

One-time share codes
--------------------

Extra tokens that self-destruct on first successful auth, ideal for
client-support workflows::

   host = RemoteDesktopHost(token="tok", single_use_tokens=["abc123"])
   host.add_single_use_token("9k4ndx")    # rotate at runtime
   host.revoke_single_use_token("abc123") # cancel before it's used

TOTP 2FA (RFC 6238, stdlib only)
--------------------------------

Layer a 6-digit OTP on top of the token; host accepts ±1 step of
clock drift::

   from je_auto_control.utils.remote_desktop.totp import (
       generate_secret, generate_code, provisioning_uri,
   )
   secret = generate_secret()
   # otpauth:// URI for Google Authenticator / Authy / 1Password QR code
   print(provisioning_uri(secret, account="alice"))

   host = RemoteDesktopHost(token="tok", totp_secret=secret)
   viewer = RemoteDesktopViewer(
       host=..., token="tok", totp_code=generate_code(secret),
   )

Multi-monitor selection
-----------------------

Capture one specific monitor instead of the combined virtual desktop::

   from je_auto_control import list_host_monitors, RemoteDesktopHost
   print(list_host_monitors())
   # [{'index': 0, 'is_combined': True, ...},
   #  {'index': 1, 'left': 0,   'top': 0, ...},
   #  {'index': 2, 'left': 1920, ...}]
   host = RemoteDesktopHost(token="tok", monitor_index=1)

Remote cursor overlay
---------------------

Host broadcasts cursor position at 30 Hz (deduped on still desktops);
the viewer's popup window draws an arrow on top of the JPEG stream so
operators can see exactly where the host's pointer is. Disable via
``enable_cursor_broadcast=False``.

Multi-viewer collaborative cursors + chat
-----------------------------------------

Two new message types (``CHAT`` and ``CURSOR`` with ``viewer_id``).
Use ``MultiViewerHost`` to relay one viewer's pointer to the others;
pair with the chat channel for ad-hoc text between operators::

   host = RemoteDesktopHost(
       token="tok",
       on_chat=lambda sender, text: print(sender, ":", text),
   )
   host.broadcast_chat("session starts in 30s")
   host.broadcast_viewer_cursor("alice", 200, 300)

   viewer = RemoteDesktopViewer(
       host=...,
       on_chat=lambda s, t: ...,
       on_viewer_cursor=lambda vid, x, y: ...,
   )
   viewer.send_chat("ack")

Relative mouse mode (FPS / CAD)
-------------------------------

New input action that sends deltas instead of absolute coordinates::

   viewer.send_input(
       {"action": "mouse_move_relative", "dx": 5, "dy": -3},
   )

Motion-aware capture
--------------------

The capture loop now hashes each encoded JPEG; identical frames are
skipped, so a static desktop produces ~zero bandwidth. New viewers
are seeded with the latest frame on auth so they never see a black
popup.

Live stats
----------

Rolling 3-second window of FPS / kbps + session totals::

   viewer.stats()
   # {'fps': 24.3, 'kbps': 4801.2, 'frames': 720.0,
   #  'bytes': 1.8e7, 'uptime': 30.2}

JPEG sequence recorder (no PyAV needed)
---------------------------------------

TCP-path session capture: each frame written to disk plus
``manifest.json`` so it can be replayed at original cadence::

   from je_auto_control.utils.remote_desktop.jpeg_recorder import (
       JpegSequenceRecorder,
   )
   rec = JpegSequenceRecorder("~/recordings/2026-05-23")
   rec.start()
   viewer = RemoteDesktopViewer(host=..., on_frame=rec.record_frame)
   # ... session ...
   rec.stop()  # writes manifest.json next to the .jpg files

TCP relay (WebRTC fallback)
---------------------------

When P2P fails (strict NAT, mobile CGNAT, hotel Wi-Fi), both peers
connect outbound to a relay and exchange a shared 32-byte session ID;
the relay pipes bytes between them. Same module ships an
``encode_handshake(role, session_id)`` helper for clients::

   from je_auto_control.utils.remote_desktop.relay import RelayServer
   relay = RelayServer(bind="0.0.0.0", port=9000)
   relay.start()

Service installer (unattended host)
-----------------------------------

``python -m je_auto_control.utils.remote_desktop.host_service ...``
exposes ``configure`` / ``init`` / ``run`` plus per-platform
installers: ``install-windows-service`` / ``uninstall-windows-service``
(needs pywin32), ``generate-launchd`` / ``uninstall-launchd``,
``generate-systemd`` / ``uninstall-systemd``.


Remote desktop — secure transports, audio, clipboard, file transfer
===================================================================

Host ID handshake
-----------------

Every host now exposes a stable 9-digit numeric ID, persisted at
``~/.je_auto_control/remote_host_id`` so it stays the same across
restarts. The ID is announced inside ``AUTH_OK`` (so only authenticated
viewers see it), and viewers can verify ``expected_host_id`` to defend
against a different process listening on the same address::

   from je_auto_control import RemoteDesktopHost, RemoteDesktopViewer
   host = RemoteDesktopHost(token="tok")
   print(host.host_id)        # e.g. "123456789"

   viewer = RemoteDesktopViewer(
       host="10.0.0.5", port=51234, token="tok",
       expected_host_id="123456789",
   )
   viewer.connect()           # raises AuthenticationError on mismatch

Helpers ``format_host_id("123456789") == "123 456 789"`` and
``parse_host_id("123 456 789") == "123456789"`` are also exported. The
GUI displays the formatted ID with a *Copy* button, and the viewer
panel accepts any common spacing / dashing.

TLS
---

Both ``RemoteDesktopHost`` and ``RemoteDesktopViewer`` accept an
``ssl.SSLContext``. When provided, the host wraps each accepted
connection server-side; the viewer wraps the connect socket
client-side. Failed handshakes are logged and silently dropped before
they can register as connected clients::

   import ssl
   ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
   ctx.load_cert_chain("cert.pem", "key.pem")
   host = RemoteDesktopHost(token="tok", ssl_context=ctx)

   client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
   client_ctx.load_verify_locations("cert.pem")
   viewer = RemoteDesktopViewer(host=..., ssl_context=client_ctx)

For self-signed loopback testing, set
``ctx.check_hostname = False`` and ``ctx.verify_mode = ssl.CERT_NONE``
on the client context. The Remote Desktop GUI host panel has TLS cert
/ key file pickers; the viewer panel has a *Skip cert verification*
checkbox.

WebSocket transport
-------------------

A new ``WebSocketDesktopHost`` / ``WebSocketDesktopViewer`` pair
speaks the same typed-message protocol over RFC 6455 BINARY frames.
The implementation is in-tree (no extra deps); each application
message rides as one full WebSocket frame, so reassembly machinery is
unnecessary. The same ``ssl_context`` parameter doubles as the
``wss://`` switch::

   from je_auto_control import (
       WebSocketDesktopHost, WebSocketDesktopViewer,
   )
   host = WebSocketDesktopHost(token="tok", ssl_context=ctx)   # wss://
   viewer = WebSocketDesktopViewer(
       host="example.com", port=443, token="tok",
       ssl_context=client_ctx, path="/rd",
   )

Why WS: friendly to corporate firewalls and reverse proxies, and
compatible with browser viewers. The GUI viewer's transport dropdown
(*TCP* / *WebSocket* / *TLS* / *WSS*) chooses the right class
automatically.

Audio streaming
---------------

A new ``AUDIO`` message type carries 16-bit signed PCM blocks (default
16 kHz mono, 50 ms / 1600 bytes per block). The optional
``sounddevice`` dependency is loaded lazily — without it, audio is
reported disabled and the host stays up::

   from je_auto_control.utils.remote_desktop import AudioCaptureConfig
   host = RemoteDesktopHost(
       token="tok",
       audio_config=AudioCaptureConfig(
           enabled=True, device=None,             # default mic
           sample_rate=16000, channels=1,
       ),
   )

   from je_auto_control.utils.remote_desktop import AudioPlayer
   player = AudioPlayer(); player.start()
   viewer = RemoteDesktopViewer(host=..., on_audio=player.play)

The host fans each captured block out to all authenticated viewers
through a bounded per-client deque (~2.5 s of buffering), so a slow
viewer drops old audio chunks instead of stalling capture for
everyone else. To capture system audio (rather than the mic), pick a
loopback / monitor device by index — Windows WASAPI loopback on
Windows, the PulseAudio monitor source on Linux, BlackHole on macOS.
GUI: *Stream system audio* on the Host panel, *Play received audio*
on the Viewer panel.

Clipboard sync (text + image)
-----------------------------

A new ``CLIPBOARD`` message type carries a JSON envelope so kinds can
grow without a protocol bump:

* ``{"kind": "text", "text": "..."}``
* ``{"kind": "image", "format": "png", "data_b64": "..."}``

``utils/clipboard/clipboard.py`` is extended with
``get_clipboard_image`` / ``set_clipboard_image``; Windows uses
CF_DIB via ctypes (Pillow rasterises PNG → BMP → DIB), Linux shells
out to ``xclip -t image/png``, macOS get works via Pillow ImageGrab
and set raises until a PyObjC backend lands. Sync is explicit per
call — no auto-poll loops to avoid paste storms::

   # Viewer pushes its local clipboard to the host
   viewer.send_clipboard_text("hello")
   viewer.send_clipboard_image(open("logo.png", "rb").read())

   # Host pushes to all viewers
   host.broadcast_clipboard_text("greetings")
   host.broadcast_clipboard_image(png_bytes)

   # Viewer wires a callback so it can choose when to paste
   viewer = RemoteDesktopViewer(
       host=..., on_clipboard=lambda kind, data: ...,
   )

GUI: *Push clipboard text to host* button on the Viewer panel; the
host applies inbound clipboards via the helpers above.

File transfer with progress
---------------------------

Three new message types form one transfer:

* ``FILE_BEGIN`` — JSON ``{transfer_id, dest_path, size}``
* ``FILE_CHUNK`` — 36-byte ASCII transfer id + raw payload
* ``FILE_END``   — JSON ``{transfer_id, status, error?}``

Transfers are bidirectional, chunked (256 KiB per chunk), and have
*no aggregate size limit*. The two directions treat ``dest_path``
differently, because the trust runs one way:

* **Viewer → host**: ``dest_path`` is a path on the host, used as given.
  The viewer holds the token, and token holders are trusted users.
* **Host → viewer**: ``dest_path`` is a path *relative to the viewer's
  download directory*. A viewer cannot vouch for the host it dialled, so
  an absolute path, a drive or UNC path, a ``..`` component or a symlink
  leading out of that directory fails the transfer (``on_complete`` gets
  ``ok=False``) and nothing is written.

The download directory is ``~/Downloads/AutoControl`` unless
``JE_AUTOCONTROL_REMOTE_DOWNLOAD_DIR`` names another; it is created when
the first file arrives. To choose it per viewer, pass
``FileReceiver(base_dir=...)`` to ``set_file_receiver``. A receiver built
without ``base_dir`` is unconfined — that is what the host uses.

Progress is reported locally on both sides without an extra wire message::

   from je_auto_control.utils.remote_desktop import (
       FileReceiver, RemoteDesktopHost, RemoteDesktopViewer, send_file,
   )

   # Viewer uploads to host
   viewer.send_file("local.bin", "/tmp/uploaded.bin",
                    on_progress=lambda tid, done, total: print(done, total))

   # Host pushes to all viewers; each one stores it under its own
   # download directory, here <download dir>/from_host/local.bin
   viewer.set_file_receiver(FileReceiver(
       on_progress=..., on_complete=...,
       base_dir="~/Downloads/AutoControl",
   ))
   host.send_file_to_viewers("local.bin", "from_host/local.bin")

GUI: *Send file...* opens a file picker + destination-path prompt and
runs the upload on a ``QThread`` with a ``QProgressBar`` bound to the
sender's progress events. The frame display widget also accepts
dragEnter / drop of local files; each dropped file kicks off the same
upload flow.

.. warning::
   On the host, the path is unrestricted and there is no size cap.
   Anyone with the token can write any file to any location on the
   host, and can fill the disk. Keep ``trusted token holders == trusted
   users`` in mind, or give the host a confined receiver with
   ``host.set_file_receiver(FileReceiver(base_dir=...))``. A viewer is
   confined to its download directory, but a host can still fill that
   disk.

.. note::
   Before this change a host-pushed ``dest_path`` was an absolute path
   on the viewer. Scripts that call
   ``host.send_file_to_viewers(src, "/tmp/x.bin")`` now fail on the
   viewer; send a relative path instead.


Remote desktop — AnyDesk-style popout window
============================================

The viewer panel no longer renders the live remote screen inline —
when the viewer authenticates, a dedicated top-level
``RemoteScreenWindow`` opens with the remote desktop, and the
panel shrinks back to the connection card + controls. Closing the
popup ✕ disconnects the session, matching AnyDesk's session-window
ergonomics.

* New module: ``je_auto_control/gui/remote_desktop/remote_screen_window.py``
* Wraps a ``_FrameDisplay`` and re-emits its mouse / keyboard /
  drag-and-drop / annotation signals so the panel keeps a single
  signal source after the popout.
* Bottom footer carries the optional file-transfer progress label /
  bar; hidden when no transfer is active.
* Both the TCP ``_ViewerPanel`` and the WebRTC
  ``_WebRTCViewerPanel`` open the popup on connect / on auth_ok and
  close it on disconnect / on stop.

Why
   The previous layout fought for vertical space: a frame display +
   connection card + collapsibles + action row + stats + sparklines
   + transfer progress + status bar all stacked on one tab. Pulling
   the live screen out into its own window leaves the operator with
   a real workspace and keeps the control surface uncluttered.


Remote desktop — responsive sub-tab sizing
==========================================

Every Remote Desktop sub-tab is now wrapped in a ``QScrollArea``
with ``setWidgetResizable(True)``. The wrapper lives in
``gui/remote_desktop/tab.py`` (helper ``_wrap_in_scroll_area``).

* Small / shrunk window: a vertical scrollbar appears instead of
  clipping the dense WebRTC panels.
* Enlarged / 4K window: the inner panel widget grows horizontally
  with the viewport, so the connection card and session table
  stretch edge-to-edge instead of clustering at the top-left.
* The bottom ``addStretch(1)`` in each panel still pushes content
  up when there is leftover height, so the layout doesn't sag.

Heavy / rarely used groups (Manual SDP, Remote Files, Sync) on the
WebRTC viewer tab are also wrapped in collapsed-by-default
``_CollapsibleSection`` shells via the new ``_wrap_collapsed``
helper, halving the panel's first-paint height.

Removed the previous hard ``setMaximumHeight(140)`` on the WebRTC
host's session table: ``setMinimumHeight(140)`` keeps 140 px as a
starting hint without capping the table on large displays.


Remote desktop — MCP tool surface
=================================

The MCP server now wraps the same singleton remote-desktop
registry the GUI uses. The tools live under a new
``remote_desktop_tools()`` factory in
``je_auto_control/utils/mcp_server/tools/_factories.py``:

``ac_remote_host_start``
   Start (or restart) the singleton TCP host with ``token``,
   ``bind``, ``port``, ``fps``, ``quality``, ``max_clients``,
   ``host_id``. Returns
   ``{running, port, host_id, connected_clients}``.

``ac_remote_host_stop``
   Stop the host (no-op when nothing is running).

``ac_remote_host_status``
   Read-only snapshot of the host registry. Survives
   ``--readonly`` mode.

``ac_remote_viewer_connect``
   Open the singleton viewer to a remote host, supporting
   ``expected_host_id`` to verify the 9-digit ID before accepting
   the session.

``ac_remote_viewer_disconnect`` / ``ac_remote_viewer_status``
   Close / observe the active viewer (status is read-only).

``ac_remote_viewer_send_input``
   Forward an input action dict (``mouse_move``, ``mouse_press``,
   ``mouse_release``, ``mouse_scroll``, ``key_press``,
   ``key_release``, ``type``, ``hotkey``) through the connected
   viewer to the remote host. Destructive — stripped under
   ``--readonly``.

A model can now drive a complete remote-control flow without
clicking through the GUI:

.. code-block:: text

   ac_remote_host_start(token="tok", bind="127.0.0.1", port=0)
     → {"running": true, "port": 51234, "host_id": "123456789",
        "connected_clients": 0}

   # … on a different machine …
   ac_remote_viewer_connect(host="10.0.0.5", port=51234, token="tok",
                            expected_host_id="123456789")
     → {"connected": true, "host_id": "123456789"}

   ac_remote_viewer_send_input(action={
       "action": "mouse_move", "x": 100, "y": 200,
   })
   ac_remote_viewer_send_input(action={
       "action": "type", "text": "hello",
   })

The MCP tools are the same ``"script"`` owner as the ``AC_remote_*``
commands: they act on the active host or viewer whoever opened it, and a
GUI panel whose session they replace or end is told and closes its window.

The status / observer tools (``ac_remote_host_status``,
``ac_remote_viewer_status``) are read-only and survive the MCP
server's ``--readonly`` filter; everything that mutates state is
correctly tagged ``destructiveHint: true`` so MCP clients can
prompt for user confirmation.


Driver-level input backends — drive games that ignore SendInput / XTest
========================================================================

The default Windows (SendInput) and Linux (XTest) input paths sit at
the user-mode / X-server layer. Modern games that read input via
``GetRawInputData`` (Win) or ``evdev`` (Linux) skip those layers
entirely and ignore synthetic events. Three optional backends bridge
the gap.

Interception (Windows)
----------------------

Oblita's WHQL-signed Interception driver
(https://github.com/oblitum/Interception) injects keyboard / mouse
events at the HID layer; the OS sees them as real-hardware events.

* New sub-package: ``je_auto_control/windows/interception/``
  (``_dll.py`` ctypes bindings + ``keyboard.py`` + ``mouse.py``).
* Same public surface as ``win32_ctype_keyboard_control`` /
  ``win32_ctype_mouse_control`` — the platform wrapper just swaps
  modules, no caller changes.
* Opt-in via ``JE_AUTOCONTROL_WIN32_BACKEND=interception``; the
  wrapper falls back to SendInput with a warning when the driver is
  missing, so deployments can roll the driver out lazily.
* Override device IDs with ``JE_AUTOCONTROL_INTERCEPTION_KEYBOARD``
  / ``JE_AUTOCONTROL_INTERCEPTION_MOUSE`` (defaults: ``1`` / ``11``).

Operator setup::

   # 1. Install the driver as Administrator (one-time, requires reboot)
   install-interception.exe /install

   # 2. Tell AutoControl to route through it
   setx JE_AUTOCONTROL_WIN32_BACKEND interception

uinput (Linux)
--------------

The kernel's synthetic-input gateway. Events emitted via
``/dev/uinput`` show up as a brand-new HID device, so anything reading
``evdev`` (most games + SDL2 apps) sees them as real input.

* New sub-package: ``je_auto_control/linux_with_x11/uinput/``
  (``_device.py`` ctypes wrapper around ``ioctl`` + ``keyboard.py`` +
  ``mouse.py``).
* No third-party dependency — direct ``ctypes`` + ``ioctl`` to
  ``/dev/uinput``.
* Opt-in via ``JE_AUTOCONTROL_LINUX_BACKEND=uinput``; falls back to
  XTest with a warning when ``/dev/uinput`` isn't writable.

Operator setup::

   # Load the kernel module if it isn't already.
   sudo modprobe uinput

   # Grant write access. For one-off testing:
   sudo chmod 666 /dev/uinput

   # For persistent provisioning, drop a udev rule:
   echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' \
     | sudo tee /etc/udev/rules.d/99-autocontrol-uinput.rules
   sudo udevadm control --reload && sudo udevadm trigger
   sudo usermod -aG input $USER  # log out / back in to apply

   # Then opt in:
   export JE_AUTOCONTROL_LINUX_BACKEND=uinput

ViGEm virtual gamepad (Windows)
-------------------------------

For games that don't take keyboard input at all but read controllers,
ViGEmBus exposes a virtual Xbox 360 / DualShock 4 controller that
AutoControl drives through the third-party ``vgamepad`` Python
package.

* New module: ``je_auto_control/utils/gamepad/`` with a friendly
  ``VirtualGamepad`` API (string-keyed buttons / dpad / sticks /
  triggers, context manager).
* Headless::

     from je_auto_control import VirtualGamepad
     with VirtualGamepad() as pad:
         pad.click_button("a")               # face button A
         pad.set_left_stick(16000, 0)        # int16 stick offsets
         pad.set_right_trigger(255)          # 0..255 pressure
         pad.set_dpad("up")                  # hold dpad up
         pad.update()                        # flush → driver

* Executor commands: ``AC_gamepad_press``, ``AC_gamepad_release``,
  ``AC_gamepad_click``, ``AC_gamepad_dpad``,
  ``AC_gamepad_left_stick`` / ``_right_stick``,
  ``AC_gamepad_left_trigger`` / ``_right_trigger``, and
  ``AC_gamepad_reset``.

* MCP tools: same names with the ``ac_`` prefix
  (``ac_gamepad_press``, ``ac_gamepad_left_stick``, …) — so a model
  can play a gamepad-only game over MCP.

Operator setup::

   # 1. Install the ViGEmBus driver (one-time, requires reboot)
   #    https://github.com/nefarius/ViGEmBus/releases
   # 2. Install the Python wrapper:
   pip install vgamepad

Anti-cheat caveat (all three)
-----------------------------

Driver-level injection is harder to detect than SendInput / XTest,
but anti-cheat systems with a kernel-mode driver of their own
(Vanguard, Easy Anti-Cheat with kernel module, BattlEye) can still
enumerate Interception / ViGEmBus / a freshly-created uinput device
and refuse to launch.

These backends target legitimate use cases — accessibility software,
GUI testing of games that lock out user-mode input, controlling a
remote game-running machine from a headless setup — and aren't a
generic anti-cheat bypass.


Per-action profiler
===================

Records wall-clock duration for every ``AC_*`` action so you can answer
"which step is dominating this script's runtime?" without external
tooling. Profiling is opt-in — when disabled, the executor wrapper has
zero overhead::

   import je_auto_control as ac
   ac.default_profiler.enable()
   ac.execute_action([["AC_locate_image_center", {"image": "btn.png"}],
                      ["AC_click_mouse"]])
   for row in ac.default_profiler.hot_spots(limit=5):
       print(row.name, row.calls, row.average_seconds)

Action-JSON commands::

   [["AC_profiler_enable"]]
   [["AC_profiler_stats", {"limit": 10}]]
   [["AC_profiler_hot_spots", {"limit": 5}]]
   [["AC_profiler_reset"]]
   [["AC_profiler_disable"]]

GUI: **Profiler** tab — live hot-spot table (calls / total / avg / min /
max / share) refreshed every second. Toggle recording, reset stats, or
export the snapshot through the headless API.


Run history timeline + failure thumbnails
=========================================

The Run History tab gains a Gantt-style strip beneath the filter row:
each scheduler / trigger / hotkey / webhook / email fire is rendered as
a coloured bar on a horizontal time axis (green = ok, red = error,
amber = still running). Selecting a bar syncs the table row, and a
right-hand preview panel surfaces the failure screenshot already
captured by the artifact manager.

Headless callers query the same data through the existing run history
store::

   import je_auto_control as ac
   for row in ac.default_history_store.list_runs(limit=20):
       print(row.id, row.status, row.duration_seconds, row.artifact_path)

No new commands — the store API is unchanged. The GUI is purely a
thin visualization wrapper over the existing `runs` table.


Encrypted secret manager
========================

Action scripts that need API tokens, IMAP passwords, etc. should never
embed plaintext. The new vault stores Fernet-encrypted entries under
``~/.je_auto_control/secrets/vault.json``; a passphrase derives the
key via PBKDF2-HMAC-SHA256 (600,000 iterations, 16-byte salt)::

   import je_auto_control as ac
   ac.default_secret_manager.initialize("my-vault-passphrase")
   ac.default_secret_manager.set("github_token", "ghp_xxxxx")
   ac.default_secret_manager.lock()

   # later — in the same process or a new run:
   ac.default_secret_manager.unlock("my-vault-passphrase")

Action-JSON commands::

   [["AC_secret_init",   {"passphrase": "..."}]]
   [["AC_secret_unlock", {"passphrase": "..."}]]
   [["AC_secret_set",    {"name": "github_token", "value": "ghp_xxx"}]]
   [["AC_secret_list"]]
   [["AC_secret_remove", {"name": "github_token"}]]
   [["AC_secret_lock"]]
   [["AC_secret_status"]]

Action scripts reference vault entries through ``${secrets.NAME}``
placeholders. The interpolator routes the ``secrets.`` namespace to the
vault directly rather than looking up an ordinary variable::

   [["AC_shell_command",
     {"command": "curl -H \"Authorization: Bearer ${secrets.github_token}\" ..."}]]

``AC_shell_command`` logs only the program it starts, never its arguments,
so a filled-in secret stays out of the log; a program that cannot start
fails the action.

During executor execution, resolved ``${secrets.NAME}`` values are replaced
with ``***`` in ``AutoControlGUI`` application messages, exception text and
stack information before handlers receive them. Exact values and common
Python/JSON escaped forms are masked. Nested actions and joined local
parallel/DAG workers share the run's mask; concurrent independent runs have
separate masks. CLI/REST/MCP requests and scheduled, trigger, hotkey and email
owners keep their mask through outer error handling and audit/history writes.
Standalone DAG calls own a mask too. Each node worker binds the owner mask
through runner execution, outcome handling, final error logging and timing,
including custom local runners. Returned node-error payloads remain unchanged.
Independent watchdog/observer rules and callback-executor invocations keep a
mask through their matcher/predicate, trigger, callback and final error log.
Nested calls reuse the enclosing run's mask; independent rules and subsequent
invocations clear their values separately.
CLI stderr is masked. Report records snapshot known values before the mask is
cleared; cyclic and opaque diagnostic objects are replaced without calling
arbitrary repr or deepcopy. Audit fields are sanitized before JSON encoding,
and history error text before SQLite writes. Owner exit clears the mask even
on failure. API outcomes, raised exceptions and CLI result payloads retain
their original values. This masking covers values learned during the owned
run; transformed/encoded values and other applications' loggers require
their own handling.

GUI: **Secrets** tab — initialize the vault, unlock it, add / remove
entries, change passphrase. The vault file is created with mode 0o600
on POSIX systems; on Windows the default ACL already restricts
read access to the owning user.


Webhook (HTTP push) trigger
===========================

A bundled ``http.server`` dispatcher fires an action script when an
external service POSTs to a registered path. Configure path, allowed
methods (``GET``, ``POST``, ``PUT``, ``PATCH``, ``DELETE``; any other verb
is refused when the webhook is added), and an optional bearer token; the request method, path, query,
headers, raw body, and parsed JSON are seeded into the variable scope::

   import je_auto_control as ac
   ac.default_webhook_server.add(
       path="/jobs/build", script_path="hooks/on_build.json",
       methods=["POST"], token="topsecret",
   )
   host, port = ac.default_webhook_server.start("127.0.0.1", 0)
   print("listening on", host, port)

The bound script reads the request through ``${webhook.*}`` placeholders::

   [
     ["AC_set_var", {"name": "branch", "value": "${webhook.query.ref}"}],
     ["AC_shell_command",
      {"command": "echo received build for ${webhook.body}"}]
   ]

Action-JSON commands::

   [["AC_webhook_start", {"host": "127.0.0.1", "port": 8765}]]
   [["AC_webhook_add",   {"path": "/jobs", "script_path": "...",
                          "methods": ["POST"], "token": "..."}]]
   [["AC_webhook_list"]]
   [["AC_webhook_remove", {"webhook_id": "abcd1234"}]]
   [["AC_webhook_status"]]
   [["AC_webhook_stop"]]

Each fire is recorded in run history as ``trigger`` with source id
``webhook:<id>`` so the dashboard surfaces webhook activity alongside
other triggers; a fire in which any action failed is recorded as an error
(with an error snapshot), as scheduled, triggered and hotkey runs are. The body is capped at 1 MiB and bearer-token comparison
uses ``hmac.compare_digest``. Bind to ``127.0.0.1`` unless the
listener genuinely needs to be reachable from elsewhere on the network.

GUI: **Webhooks** tab — start/stop the server, register paths, view the
fire counter and auth state per route.


IMAP email trigger
==================

Poll-based watcher that logs into a mailbox on a configurable interval
and runs an action script once per matching message::

   import je_auto_control as ac
   ac.default_email_trigger_watcher.add(
       host="imap.gmail.com", username="user@example.com",
       password="app-specific-password",
       script_path="hooks/on_alert.json",
       mailbox="INBOX", search_criteria='UNSEEN FROM "alerts@..."',
       poll_seconds=120, mark_seen=True,
   )
   ac.default_email_trigger_watcher.start()

The bound script sees the message metadata via ``${email.*}``::

   [
     ["AC_if_var", {
       "name": "email.subject", "op": "contains", "value": "CRITICAL",
       "then": [["AC_hotkey", {"keys": ["ctrl", "alt", "p"]}]]
     }]
   ]

Variables seeded per fire: ``email.uid``, ``email.from``, ``email.to``,
``email.subject``, ``email.message_id``, ``email.date``, ``email.body``.

Action-JSON commands::

   [["AC_email_trigger_add",       {"host": "...", "username": "...",
                                    "password": "${secrets.imap_pw}",
                                    "script_path": "...",
                                    "mailbox": "INBOX",
                                    "search_criteria": "UNSEEN",
                                    "poll_seconds": 120,
                                    "mark_seen": true,
                                    "use_ssl": true}]]
   [["AC_email_trigger_start"]]
   [["AC_email_trigger_poll_once"]]
   [["AC_email_trigger_list"]]
   [["AC_email_trigger_remove", {"trigger_id": "abcd1234"}]]
   [["AC_email_trigger_stop"]]

The watcher tracks already-fired UIDs in process memory, and optionally
flags messages ``\\Seen`` so the same mail isn't replayed across
restarts. TLS is pinned at 1.2 minimum. Combine ``AC_email_trigger_add``
with ``${secrets.NAME}`` so passwords never appear in the JSON.

GUI: **Email Triggers** tab — register IMAP triggers, start/stop the
watcher, run a manual poll, inspect last error and fire counter.

Structured action journals (partial integration)
================================================

B1 exports storage and explicit capture/read APIs from ``je_auto_control`` and
``je_auto_control.utils.action_journal``. CLI capture and bounded snapshot reads
are available, along with action commands, Script Builder forms and dedicated
MCP capture/read tools. Dedicated GUI browsing and manual-run history controls
remain pending integration. The journal/provenance APIs remain experimental during B1.
Applications can explicitly write schema-v1 snapshots::

   import time
   from dataclasses import replace
   from pathlib import Path
   from je_auto_control import ActionEvent, ActionJournal, read_events

   journal = ActionJournal(Path("actions.jsonl"))
   started = ActionEvent(
       run_id="review", step_id="step-1", command="AC_set_var",
       parameters={"name": "login", "value": "${secrets.LOGIN}"},
       started_at=time.time(),
   )
   journal.append(started)  # status: incomplete
   journal.append(replace(started, status="ok", finished_at=time.time()))
   snapshots = read_events(journal.path, run_id="review")

Every append preserves run/step/parent IDs and receives a file-wide sequence under
an interprocess lock. Complete lines are fsynced; a final fragment after a valid
record is ignored by readers and recovered before the next append. Existing
non-journal files and ambiguous torn first records are refused without truncation;
both the file identity and preceding complete record are validated before repair. Complete malformed lines,
unknown schemas/fields and invalid order raise ``ActionJournalError``.
Records are bounded to 8 MiB of UTF-8 bytes and read one at a time.

Secret argument names and secret commands are masked before append. Explicit
``${secrets.NAME}`` / ``secret://NAME`` references survive as references. Unsupported
objects, cycles and non-finite values receive non-replayable markers; arbitrary
``repr`` is never invoked. Opaque results and error text are redacted, including
result dictionary keys; ``outcome_type`` preserves a fixed safe type category.
Reading returns lifecycle snapshots, including unfinished ``incomplete`` starts,
and does not infer a completed step from a missing final record.

Explicit executor capture is also available::

   from pathlib import Path
   from je_auto_control import execute_action_with_journal, read_events

   summary = execute_action_with_journal(
       [["AC_set_var", {"name": "count", "value": 1}]],
       Path("captured.jsonl"), run_id="demo", dry_run=True,
   )
   snapshots = read_events(Path(summary["journal_path"]), run_id=summary["run_id"])

``journal_scope(ActionJournal(path))`` captures existing executor calls without
changing a private executor's variable ownership. The convenience runner uses
the module executor in fresh variables and returns ``JournalRunResult`` with
``run_id``, ``journal_path``, the original ``record`` and ``failed_actions``.
Local loop, parallel and default DAG workers preserve the run and parent step;
remote DAG execution requires separate capture on the remote endpoint.
Soft/strict failures, cancellation and ``dry_run`` stay distinct. ``ok`` reports
dispatch completion; domain verification is a separate check. A process killed
mid-command retains its durable incomplete start. Completion-storage failure
preserves an original cancellation/error and leaves the start incomplete.


Action commands and Script Builder
----------------------------------

``AC_journal_capture`` requires named parameters (a JSON object) and executes
its nested ``body`` on the current executor. Positional bodies are rejected
to avoid eagerly interpolating nested data twice.
It keeps the caller's variables, strictness and loop/cancellation signals.
The body is structurally validated and linted, and is interpolated only when
its own steps run. A new capture starts a new journal root and restores any
outer capture on exit; an existing history owner receives the provenance link::

   ["AC_journal_capture", {
       "path": "run.jsonl", "run_id": "example",
       "body": [
           ["AC_set_var", {"name": "message", "value": "hello"}],
           ["AC_get_var", {"name": "message"}]
       ]
   }]

Optional ``device_id`` and ``session_id`` label the capture. Identifiers and
the destination must not contain values known to the enclosing
run's resolved-secret mask; capture rejects them before history linking, file
creation or body execution. The summary has ``run_id``, ``journal_path``, the original ``record`` and
``failed_actions``. This command retains the caller's scope; the Python
``execute_action_with_journal`` convenience function starts fresh variables.
An outer executor dry-run previews the capture command without running its
body or opening a journal. Use Python/CLI run-level capture with ``dry_run``
to capture individual previewed steps.

``AC_journal_read`` accepts ``path``, optional ``run_id`` and ``limit`` (default
100, range 1–10,000). It uses public ``inspect_journal`` to validate the whole
file and then return a bounded list of sanitized lifecycle snapshots in append
order. Filtering precedes the output limit; reads preserve the source and never
infer completion. The CLI uses the same reader. These operation paths use the
default allowed-root guard; configure ``AUTOCONTROL_ALLOWED_PATH_ROOTS`` for
additional destinations. Both commands require ``drive_input`` under RBAC;
private journal reads are not screen observation.

In Script Builder, add **Capture Action Journal** (Flow) to edit metadata and
nested body steps, or **Read Action Journal** (Data) to edit path, run filter
and limit. ``examples/28_action_journal.py`` demonstrates variable-only capture
and inspection without desktop input.


Observed runs and MCP integration
----------------------------------

``execute_journal_run(actions, path, options=JournalRunOptions(...))`` starts
fresh variables and returns the existing four-field ``JournalRunResult``.
Options group ``variables``, ``dry_run``, ``run_id``, ``device_id``,
``session_id``, ``observer`` and ``path_policy``. The original seven-parameter
``execute_action_with_journal`` API delegates to this runner and keeps its
signature. For example::

   from pathlib import Path
   from je_auto_control import JournalRunOptions, execute_journal_run

   statuses = []
   result = execute_journal_run(
       [["AC_set_var", {"name": "message", "value": "hello"}]],
       Path("run.jsonl"),
       options=JournalRunOptions(run_id="observed", observer=statuses.append),
   )
   # statuses == ["incomplete", "ok"]

Observers receive a status string before a step's durable start and after its
completion snapshot is persisted. They may raise to stop execution. A secondary
completion-observer failure cannot replace a pending original error or control
signal. Joined workers invoke observers on their own threads. Nested captures
retain enclosing observers and intersect path policies, including captures
opened by existing convenience APIs. The bound policy's live roots are checked
at each append. A refused completion leaves the durable start incomplete.

``inspect_journal`` and ``read_events`` accept count observers for cooperative
read cancellation. Counts include every validated record before filtering;
file handles close before callback exceptions propagate. ``inspect_journal``
also intersects enclosing journal policies and an optional explicit policy.

MCP exposes ``ac_journal_capture`` and ``ac_journal_read``. Capture accepts
``actions``, ``path``, optional ``metadata`` (``run_id``, ``device_id``,
``session_id``), ``variables`` and ``dry_run``. It reports durable completed-step
counts, observes cancellation at action boundaries and returns structured run
metadata. Recorded executor failures set ``isError: true`` while preserving
that metadata and the original record. Domain outcomes such as a failed DAG
node remain in ``record`` and require separate inspection.

Read accepts ``path``, optional ``run_id`` and ``limit`` and returns
``{"events": [...]}``. It checks cancellation between validated records,
reports scan progress every 100 records and sends a final count. Limits bound
output, while the whole file is validated. Both tools require ``drive_input``
under RBAC. Read-only mode keeps read and omits capture.

The MCP context carries the server's path policy into journal operations,
including nested journal commands and local workers. Default journal roots
must also allow the path; configure ``AUTOCONTROL_ALLOWED_PATH_ROOTS`` for an
additional destination alongside MCP roots. General nested-action argument
policy integration remains tracked in ``Progress.md``. Cancellation is
cooperative at the described boundaries; running native I/O is not forcibly
interrupted. ``examples/29_mcp_journal.py`` demonstrates the JSON-RPC workflow
in process without desktop input or an external service.


History provenance links
------------------------

Scheduler, trigger, hotkey, webhook and email owners bind their existing history
row during execution. Explicit ``journal_scope`` capture automatically attaches
a canonical journal path and journal run ID to that row before dispatch. Local
parallel and default DAG workers carry this owner when they open captures too.
Multiple captures can link to one history row; duplicate links are idempotent.
Plain capture without an owner does not create a history row or open a history
database. For an explicitly managed manual row::

   from pathlib import Path
   from je_auto_control.utils.action_journal import ActionJournal, journal_scope
   from je_auto_control.utils.executor.action_executor import executor
   from je_auto_control.utils.run_history.context import HistoryBinding, bound_history
   from je_auto_control.utils.run_history.history_store import HistoryStore, SOURCE_MANUAL, STATUS_OK

   history = HistoryStore("history.sqlite")
   try:
       row_id = history.start_run(SOURCE_MANUAL, "example", "actions.json")
       with bound_history(HistoryBinding(history, row_id)):
           with journal_scope(ActionJournal(Path("run.jsonl")), run_id="example"):
               executor.execute_action([["AC_set_var", {"name": "count", "value": 1}]])
       history.finish_run(row_id, STATUS_OK)
       links = history.journals_for_run(row_id)
   finally:
       history.close()

``HistoryStore.attach_journal`` stores metadata only: it does not open, validate,
copy or take ownership of the target file. ``journals_for_run`` returns immutable
``JournalLink`` values with ``run_id``, ``journal_path`` and ``journal_run_id``.
Clearing/pruning history removes links and preserves journal files. Existing
history schemas migrate on opening; original rows and screenshot links survive.
An unknown bound history row refuses capture before device effects. GUI and
manual-run convenience wiring remain pending integration.


Interrupted run outcomes
------------------------

A raised ``KeyboardInterrupt``, ``SystemExit``, ``GeneratorExit``, asyncio/future
cancellation or MCP ``OperationCancelledError`` must not turn an interrupted
attempt into a successful history row. History records ``error``; captured
journal steps record ``cancelled``. Interrupted attempts do not take an error
screenshot. Ordinary failures retain their existing snapshot/recovery behavior.

Cancellation bypasses non-strict executor failure recording, ``AC_try`` recovery,
``AC_retry`` retries, image-condition absence handling and callback failure
guards. Explicit script ``finally`` cleanup still runs. Local parallel and DAG
workers return the original signal to the owner; already-started parallel
branches are joined first. These are propagation rules once a signal is raised,
not forcible interruption of a blocking native operation.

Hard control signals propagate unchanged. If history completion fails while a
hard signal is already pending, diagnostic storage cannot replace that signal;
the history row remains unfinished rather than being marked successful.
MCP cancellation keeps its existing ``RuntimeError`` control-signal contract,
separate from ordinary framework failures, and its JSON-RPC cancellation reply.
