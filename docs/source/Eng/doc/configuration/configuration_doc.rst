=======================
Configuration Reference
=======================

Every environment variable AutoControl reads, in one place. Each row names the
page that explains the feature; this page only says what the variable is, what
it accepts and what happens when it is unset.

Nothing here is required. With no variable set, AutoControl picks the platform
backend by itself, servers bind ``127.0.0.1``, and every opt-in feature
(signature enforcement, RBAC, USB passthrough, tool-path roots) is off.

``test/unit_test/headless/test_modernization_examples.py`` compares this page
with the code: a variable the package reads and this page does not name fails
CI, in both languages.

.. contents::
   :local:
   :depth: 1

Platform backends
=================

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Variable
     - Values (default first)
     - Effect
   * - ``JE_AUTOCONTROL_WIN32_BACKEND``
     - ``sendinput`` / ``interception``
     - Windows keyboard and mouse backend. ``interception`` uses the
       Interception driver and falls back to ``SendInput`` with a warning when
       the driver or DLL is missing.
   * - ``JE_AUTOCONTROL_INTERCEPTION_DLL``
     - unset / a path
     - Full path of ``interception.dll``. Unset: looked up on ``PATH``, then
       next to the package.
   * - ``JE_AUTOCONTROL_INTERCEPTION_KEYBOARD``
     - ``1`` / ``1``–``10``
     - Interception device id keyboard events are sent to.
   * - ``JE_AUTOCONTROL_INTERCEPTION_MOUSE``
     - ``11`` / ``11``–``20``
     - Interception device id mouse events are sent to.
   * - ``JE_AUTOCONTROL_LINUX_BACKEND``
     - ``x11`` / ``uinput``
     - X11 input backend. ``uinput`` writes kernel events and falls back to
       XTest with a warning when ``/dev/uinput`` is not writable.
   * - ``JE_AUTOCONTROL_LINUX_DISPLAY_SERVER``
     - ``auto`` / ``wayland`` / ``x11``
     - Which Linux backend loads. ``auto`` reads ``XDG_SESSION_TYPE`` and
       ``WAYLAND_DISPLAY``; ``x11`` on a Wayland session drives XWayland
       windows only.

Wayland
=======

See :doc:`../wayland/wayland_capabilities_doc`. ``probe_capabilities()`` shows
the effect of each of these without side effects.

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Variable
     - Values (default first)
     - Effect
   * - ``JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND``
     - ``auto`` / ``cli``
     - ``cli`` sends input through ``ydotool`` and never asks the desktop
       portal. It is a choice made before starting: after a refused consent
       AutoControl does not switch to it by itself.
   * - ``JE_AUTOCONTROL_WAYLAND_EI_WORKER``
     - unset / ``1``
     - Runs the libei session in a helper process instead of in-process.
   * - ``JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL``
     - ``warn`` / ``flat`` / ``strict``
     - Applies to absolute moves on the ``ydotool`` path only, which are
       relative motion the compositor accelerates. ``warn`` (also when unset)
       warns once and moves; ``flat`` declares acceleration off and moves
       silently; ``strict`` refuses the move.
   * - ``JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND``
     - unset / a command line
     - Your own screenshot command, with ``{output}`` where the PNG path goes.
       Takes precedence over ``grim``, ``gnome-screenshot``, ``spectacle`` and
       the portal.
   * - ``JE_AUTOCONTROL_WAYLAND_RECORD_DEVICES``
     - unset / comma-separated paths
     - The ``/dev/input/event*`` devices ``PhysicalRecorder`` may read. Unset
       means none: physical recording is opt-in per device.

Logging and local state
=======================

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Variable
     - Values (default first)
     - Effect
   * - ``JE_AUTOCONTROL_LOG_FILE``
     - unset / a path
     - Where the log file is written. Unset:
       ``~/.je_auto_control/logs/AutoControlGUI.log``. The null device
       (``/dev/null``, ``NUL``) switches the file off. Read when the first
       record is written, not at import.
   * - ``JE_AUTOCONTROL_GUI_SETTINGS``
     - unset / a path / ``off``
     - File the main window keeps its theme, text size, navigation panel and
       geometry in. Unset: ``~/.je_auto_control/gui_settings.ini``. ``off``,
       ``0``, ``none``, ``false`` or empty: nothing is read or written.
   * - ``JE_AUTOCONTROL_ENV``
     - ``default`` / a name
     - The active environment of the asset store (``active_environment()``),
       so one script reads different values in ``dev`` and ``prod``.
   * - ``JE_AUTOCONTROL_REDACTION``
     - ``off`` / ``moderate`` / ``strict``
     - Default screenshot redaction policy. An unknown name is an error, not
       ``off``.
   * - ``JE_AUTOCONTROL_REMOTE_DOWNLOAD_DIR``
     - unset / a directory
     - Where a remote-desktop viewer stores files its host sends. Unset:
       ``~/Downloads/AutoControl``. A received path is confined to it.
   * - ``JE_AUTOCONTROL_PYTEST_ARTIFACTS``
     - unset / a directory
     - Where the pytest plugin writes failure screenshots when a test did not
       request the ``autocontrol_screenshot_dir`` fixture. Unset:
       ``./autocontrol_screenshots``.

Executing and signing action files
==================================

See :doc:`../keyword_and_executor/keyword_and_executor_doc` and
:doc:`../new_features/v4_features_doc`.

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Variable
     - Values (default first)
     - Effect
   * - ``JE_AUTOCONTROL_ALLOWED_PACKAGES``
     - unset / comma-separated names
     - Packages ``AC_add_package_to_executor`` may load (submodules included),
       for every entry point. Read once, when the process starts.
   * - ``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS``
     - unset / ``1``
     - Every path that runs an action file refuses one without a valid
       signature sidecar.
   * - ``JE_AUTOCONTROL_ACTION_SIGNING_PRIVATE_KEY``
     - unset / a path
     - Ed25519 private key (PEM). Set it on the signing machine only; signing
       then writes a version-2 sidecar.
   * - ``JE_AUTOCONTROL_ACTION_SIGNING_PUBLIC_KEY``
     - unset / a path
     - The matching public key. Set it on every machine that executes: it
       verifies and cannot sign.
   * - ``JE_AUTOCONTROL_ACTION_SIGNING_PASSPHRASE``
     - unset / a passphrase
     - Passphrase of the private key, when it was created with one.
   * - ``JE_AUTOCONTROL_ACCEPT_LEGACY_ACTION_SIGNATURES``
     - unset / ``1``
     - Migration mode: once a public key is configured, HMAC sidecars written
       before version 2 are refused unless this is set. Switch it off again
       when every file has been re-signed.

MCP server
==========

See :doc:`../mcp_server/mcp_server_doc`.

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Variable
     - Values (default first)
     - Effect
   * - ``JE_AUTOCONTROL_MCP_READONLY``
     - unset / ``1``
     - Only tools marked read-only are offered and callable.
   * - ``JE_AUTOCONTROL_MCP_TOOL_MODE``
     - ``full`` / ``progressive`` / ``static``
     - How much of the registry ``tools/list`` offers. An unknown value is an
       error rather than ``full``.
   * - ``JE_AUTOCONTROL_MCP_TOOL_PROFILE``
     - unset / comma-separated entries
     - Tool names and ``category:<name>`` entries of the ``static`` profile.
   * - ``JE_AUTOCONTROL_MCP_ALIASES``
     - ``1`` / ``0``
     - Whether the short aliases (``click``, ``screenshot``, …) are registered
       beside the ``ac_*`` tools.
   * - ``JE_AUTOCONTROL_MCP_TOKEN``
     - unset / a token
     - Bearer token of the HTTP transport. Not accepted once RBAC is on.
   * - ``JE_AUTOCONTROL_MCP_ALLOWED_ORIGINS``
     - unset / comma-separated origins
     - Extra browser origins (exact, e.g. ``https://example.test:8443``) the
       HTTP transport accepts. Loopback origins always are.
   * - ``JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE``
     - unset / ``1``
     - Destructive tools ask the client for confirmation (MCP elicitation)
       before they run.
   * - ``JE_AUTOCONTROL_MCP_PATH_ROOTS``
     - unset / directories
     - Directories (separated by ``os.pathsep``) every file argument of a tool
       must stay inside. Unset: no confinement.
   * - ``JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT``
     - unset / ``1``
     - Also accept the roots the MCP client reports through ``roots/list``.
   * - ``JE_AUTOCONTROL_MCP_ENV_REF_ALLOW``
     - unset / comma-separated names
     - Environment variables ``ac_resolve_ref`` may read (``fnmatch`` patterns
       allowed). Unset: no restriction; a value that names nothing allows
       none.
   * - ``JE_AUTOCONTROL_MCP_AUDIT``
     - unset / a path
     - JSON-lines file that receives one record per ``tools/call``. Unset or
       empty: no audit log is written, anywhere.
   * - ``JE_AUTOCONTROL_MCP_ERROR_SHOTS``
     - unset / a directory
     - A screenshot is saved there each time a tool fails.
   * - ``JE_AUTOCONTROL_FAKE_BACKEND``
     - unset / ``1``
     - The MCP server records mouse, keyboard and clipboard calls in memory
       instead of performing them, for CI without a display.

Access control and servers
==========================

See :doc:`../operations_layer/operations_layer_doc` and
:doc:`../config_sync/config_sync_doc`.

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Variable
     - Values (default first)
     - Effect
   * - ``JE_AUTOCONTROL_RBAC_USERS``
     - unset / a path
     - The user store file. Setting it is what switches roles on for the REST
       API and the MCP HTTP transport; unset leaves both on their shared
       token.
   * - ``JE_AUTOCONTROL_USB_PASSTHROUGH``
     - unset / ``1``
     - Enables USB passthrough opcodes on the remote-desktop channel.
   * - ``JE_AUTOCONTROL_CHATOPS_SCRIPT_ROOT``
     - unset / a directory
     - The only directory the chat-ops ``run`` command may load action files
       from. Unset: the command is refused.
   * - ``AC_SIGNALING_SECRET``
     - unset / a secret
     - Shared secret of the signaling / config-sync server
       (``X-Signaling-Secret``). Read by the server when ``--shared-secret``
       is not given, and by ``config_sync_run`` when ``secret`` is not.
   * - ``AC_SIGNALING_CONFIG_DB``
     - unset / a path
     - SQLite file the signaling server keeps config-sync buckets in. Unset:
       ``~/.je_auto_control/config_sync.sqlite3``.
