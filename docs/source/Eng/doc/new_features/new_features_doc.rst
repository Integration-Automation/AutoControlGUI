=====================
New Features (2026-04)
=====================

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

Query the OS accessibility tree (Windows UIA via ``uiautomation``,
macOS AX) by name / role / app name::

   import je_auto_control as ac

   elements = ac.list_accessibility_elements(app_name="Calculator")
   ok = ac.find_accessibility_element(name="OK", role="Button")
   ac.click_accessibility_element(name="OK", app_name="Calculator")

Raises ``AccessibilityNotAvailableError`` on platforms where no backend
is installed. Action-JSON commands: ``AC_a11y_list``, ``AC_a11y_find``,
``AC_a11y_click``. GUI: **Accessibility** tab.


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

Pre-execution interpolation in :mod:`script_vars.interpolate` only
substituted ``${var}`` placeholders once against a static mapping;
scripts had no way to mutate state during execution. ``VariableScope``
is a runtime mapping the executor exposes to flow-control commands so
they can read and write the same bag the runtime interpolator consults.

The executor now resolves ``${var}`` per command call (not pre-flattened),
so nested ``body`` / ``then`` / ``else`` lists keep their placeholders
and re-bind each time they execute — letting ``AC_for_each`` iterate
over a list while the body sees the current item.

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

Comparison operators for ``AC_if_var``: ``eq``, ``ne``, ``lt``, ``le``,
``gt``, ``ge``, ``contains``, ``startswith``, ``endswith``.

Action-JSON commands: ``AC_set_var``, ``AC_get_var``, ``AC_inc_var``,
``AC_if_var``, ``AC_for_each``.

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

Backend selection mirrors :mod:`vision.backends`:

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
:mod:`utils.remote_desktop.registry`)::

   AC_start_remote_host       # token, bind, port, fps, quality, region
   AC_stop_remote_host
   AC_remote_host_status      # → {running, port, connected_clients}

   AC_remote_connect          # host, port, token, timeout
   AC_remote_disconnect
   AC_remote_viewer_status    # → {connected}
   AC_remote_send_input       # action: {...}

GUI: **Remote Desktop** tab with two sub-tabs.

- **Host** — token field with a *Generate* button that emits 24 random
  URL-safe bytes, security warning about the bind address, start / stop
  controls, refreshing port + viewer-count status, and a 4 fps preview
  pane below the controls so the user being remoted sees what viewers
  see.
- **Viewer** — address / port / token form, *Connect* / *Disconnect*,
  and a custom frame-display widget that paints incoming JPEG frames
  scaled with ``KeepAspectRatio``. Mouse / wheel / key events on the
  display are remapped from widget coordinates back to the remote
  screen's pixel space using the latest frame's dimensions, then
  forwarded as ``INPUT`` messages.

.. warning::
   Anyone with the host:port and token gets full mouse / keyboard
   control of the host machine. Defaults bind to ``127.0.0.1``;
   exposing this to untrusted networks should be paired with an SSH
   tunnel or TLS front-end. The token is the *only* line of defence —
   treat it like a password.


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
*no aggregate size limit* and *no path restriction* on the
destination — token holders are trusted users. Progress is reported
locally on both sides without an extra wire message::

   from je_auto_control.utils.remote_desktop import (
       FileReceiver, RemoteDesktopHost, RemoteDesktopViewer, send_file,
   )

   # Viewer uploads to host
   viewer.send_file("local.bin", "/tmp/uploaded.bin",
                    on_progress=lambda tid, done, total: print(done, total))

   # Host pushes to all viewers (each viewer needs a FileReceiver)
   viewer.set_file_receiver(FileReceiver(
       on_progress=..., on_complete=...,
   ))
   host.send_file_to_viewers("local.bin", "/tmp/from_host.bin")

GUI: *Send file...* opens a file picker + destination-path prompt and
runs the upload on a ``QThread`` with a ``QProgressBar`` bound to the
sender's progress events. The frame display widget also accepts
dragEnter / drop of local files; each dropped file kicks off the same
upload flow.

.. warning::
   Path is unrestricted and there is no size cap. Anyone with the
   token can write any file to any location, and can fill the disk.
   Keep ``trusted token holders == trusted users`` in mind, or wrap
   the headless API in your own restricted ``FileReceiver`` subclass
   that vets the destination path.
