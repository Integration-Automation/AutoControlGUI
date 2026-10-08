=========================================
Capabilities and authorisation on Wayland
=========================================

On Windows the backend either works or raises. On Wayland the interesting
answers are in between: input may go through the desktop portal or through
``/dev/uinput``; the user may have refused the consent dialog, or there may
be no portal to ask; the X11 backend may be serving a Wayland session through
XWayland and reaching only some windows. ``probe_capabilities()`` reports all
of that as data.

Probing
=======

.. code-block:: python

   import je_auto_control as ac

   snapshot = ac.probe_capabilities()
   print(snapshot.display_server, snapshot.xwayland)
   for capability in snapshot.capabilities:
       print(capability.name, capability.state.value, capability.backend,
             capability.desktop_wide, capability.recovery)

**Probing has no side effect.** It reads the environment, looks names up on
``PATH``, asks the loader whether a library exists and reads the authorisation
ledger. It never opens a portal request, never shows a consent dialog, never
connects a libei sender and never sends an event.

The same data is available everywhere:

* JSON action: ``[["AC_probe_capabilities"]]``
* MCP tool: ``ac_probe_capabilities`` (read-only)
* GUI: the second table of the **Diagnostics** tab

Four capabilities are diagnosed independently, because they fail
independently:

.. list-table::
   :header-rows: 1

   * - Name
     - What it is
   * - ``input``
     - synthesising keyboard and pointer events
   * - ``capture``
     - reading pixels off the screen
   * - ``recording``
     - reading what the *user* types and clicks
   * - ``stop_shortcut``
     - a global key that stops a running script

States
======

.. list-table::
   :header-rows: 1

   * - ``state``
     - Meaning
   * - ``available``
     - usable now
   * - ``not_requested``
     - usable, but the desktop has not been asked yet; it is on first use
   * - ``requesting``
     - a consent request is on screen right now
   * - ``needs_permission``
     - a consent was refused or left unanswered, or a device is not readable
   * - ``needs_setup``
     - something has to be installed or configured
   * - ``session_closed``
     - this process closed its session; the next use asks again
   * - ``revoked``
     - the compositor ended a session it had granted
   * - ``compositor_restarted``
     - the grant came from a compositor that is no longer the one running
   * - ``unknown``
     - could not be read without side effects (a query that failed, a macOS
       call ``pyobjc`` does not expose)

Each capability also carries ``backend`` (what serves it), ``desktop_wide``,
``detail``, ``recovery`` (what to do, in English) and ``recovery_key`` (the
same advice as a GUI catalogue key). The snapshot carries
``backend_version``: what the serving backend can say without running anything
(``Windows 10.0.26200``, ``macOS 14.5; pyobjc 10.3``, ``python-xlib 0.33``).
It is empty on Wayland, whose tools report a version only when run, and the
Diagnostics tab shows it above the capability table.

Windows and macOS
=================

The same probe reads a Windows or macOS session, again without changing
anything: no input is sent, no window shown, no hook installed, no hotkey
registered and no permission requested.

.. list-table::
   :header-rows: 1

   * - Platform
     - What is read
     - What follows
   * - Windows
     - the process's integrity level (token opened for query)
     - ``low`` / ``untrusted``: ``input`` is ``needs_permission``. ``medium``:
       ``available``, with the note that input to an elevated window is
       dropped by UIPI
   * - Windows
     - the session id
     - session 0 (a service): every capability ``unsupported``
   * - Windows
     - the name of the desktop receiving input
     - ``Winlogon`` or unopenable (locked, UAC, Ctrl+Alt+Del): every
       capability ``needs_permission``
   * - Windows
     - a 1x1 ``BitBlt`` off the screen into a memory bitmap
     - failure: ``capture`` is ``needs_setup`` with the error
   * - Windows
     - whether the input desktop opens with ``DESKTOP_HOOKCONTROL``
     - ``recording`` and ``stop_shortcut``; refused: ``needs_permission``
   * - macOS
     - ``AXIsProcessTrusted()``
     - ``input`` — Accessibility
   * - macOS
     - ``CGPreflightScreenCaptureAccess()``
     - ``capture`` — Screen Recording
   * - macOS
     - ``CGPreflightListenEventAccess()``
     - ``recording`` and ``stop_shortcut`` — Input Monitoring

Only the *preflight* calls are made on macOS; the ``CGRequest…`` ones, which
put a prompt on screen, are never called. A fact that could not be read is
``unknown`` — it is never rounded up to ``available``. Describe someone else's
session the same way a Wayland desktop is described::

    from je_auto_control import BackendContext, WindowsFacts, probe_capabilities

    locked = probe_capabilities(BackendContext(
        platform="win32",
        windows_facts=lambda: WindowsFacts(
            integrity="medium", session_id=1, input_desktop="Winlogon",
            hook_access=False, capture_ok=False)))
    locked.input.state.value      # "needs_permission"

The Windows queries have been run on a real Windows 11 session. The macOS
calls have been run against fakes only; the ``pytest-headless`` jobs on
``macos-14`` (``quality.yml`` / ``dev.yml``) call them on a real runner.

``restore_token`` is ``unsupported`` on the libei path: this binding does not
ask the portal for a restore token, so consent is asked once per process and
does not survive a restart.

A refusal is not worked around
==============================

``JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=auto`` (the default) tries libei first
and falls back to the ``ydotool`` CLI when libei *cannot be brought up*: no
libei, no RemoteDesktop portal, a handshake that never completes. That is
unchanged.

Two outcomes no longer fall back, because both are someone with the authority
to say no, saying it:

* the portal **denied** the request (``state == "needs_permission"``);
* the compositor **revoked** a session that had been live
  (``state == "revoked"``).

Input actions then raise ``WaylandAuthorisationError`` — which carries
``state``, ``capability`` and a ``recovery`` instruction — instead of driving
the desktop through ``/dev/uinput`` behind the refusal. To recover:

.. code-block:: python

   ac.reset_input_authorisation()   # the next input action asks again
   ac.close_input_session()         # end the session now (revokes the grant)

or ``[["AC_reset_input_authorisation"]]``, or **Actions > Ask for input
permission again** in the Diagnostics tab. To use ydotool on purpose, set
``JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=cli`` before starting; that path never
asks the portal at all.

A revoked session is also never written to again: the libei backend refuses
every emission after the compositor disconnects it.

.. note::

   A denial is recognised from liboeffis's own error text. Whether real
   desktops word it that way is measured by the ``portal-verification`` CI
   job, not asserted here. Where the text is not recognised the old behaviour
   applies (fall back to ydotool): the authorisation is recorded as
   ``failed`` and the capability shows ``ydotool`` as its backend.

XWayland
========

When the X11 backend serves a Wayland session — because
``JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11`` is set, or because the Wayland
backend could not load — ``snapshot.xwayland`` is ``True`` and every
capability has ``desktop_wide == False``: X11 applications are reachable,
native Wayland windows neither receive the input nor appear in captures.

Recording
=========

Wayland has no global input hook, so ``record()`` still raises there. Two
narrower things are available.

**What the program executed** needs no hook on any platform:

.. code-block:: python

   journal = ac.InputStepLog()
   journal.run(actions)             # the list you would give execute_action
   print(journal.steps)

**What you physically typed and clicked** can be read from kernel devices you
name. This is opt-in per device, excludes virtual (uinput) devices so that
this program's own ydotool output is never recorded as yours, and never takes
privilege:

.. code-block:: python

   devices = [d for d in ac.list_input_devices() if not d.is_virtual]
   recorder = ac.PhysicalRecorder()
   recorder.start(devices[:1])          # raises InputPermissionError if denied
   events = recorder.stop()             # list of InputEvent(type, code, value)

``JE_AUTOCONTROL_WAYLAND_RECORD_DEVICES`` (comma-separated
``/dev/input/event*`` paths) records the choice for the capability probe. A
device this user may not read raises ``InputPermissionError`` with the fix:
add the user to the ``input`` group, or install a udev rule. Do not run the
program as root for this.

The portal's *InputCapture* interface is not used: the compositor decides
when it starts, so it cannot be a recorder that starts when a script asks.

A global stop key
=================

``StopShortcutSession`` registers one named shortcut through the
``GlobalShortcuts`` portal and calls back when it is pressed. It reports only
that shortcut, never other keys.

.. code-block:: python

   import threading

   stop = threading.Event()
   with ac.StopShortcutSession(stop.set) as session:
       session.start()
       ...                              # run; check stop.is_set()
   # leaving the block closes the portal session

If the desktop has no GlobalShortcuts portal or the user declines, a
``ShortcutUnavailable`` (or ``ShortcutPermissionError``) names the stop
methods that still work. This path has no CI coverage; see
``test/manual_test/wayland_authorisation_checklist.md``.

The libei helper process (opt-in)
=================================

``JE_AUTOCONTROL_WAYLAND_EI_WORKER=1`` runs the libei session in a helper
process. It is **off by default**. The in-process path, including its
deliberate leak of one context and one descriptor when a handshake never
completes, is unchanged and remains the default; the upstream ``ei_unref``
crash it works around is not fixed by this.

With the helper, a session that cannot be released safely is reclaimed by the
operating system when the helper exits. Requests are bounded (64 events per
batch, 64 KiB per frame), carry ids, honour a deadline and a cancellation,
and keys still held are released when the helper is closed. The cost is a
pipe round trip per emission; ``docker/eis_verify.py`` measures it.

Failures split by one question — may another backend redo this?
``EiWorkerError`` (including ``EiDependencyMissing``) is a
``LibeiUnavailable``: nothing was sent, ydotool may take over.
``EiWorkerTimeout``, ``EiWorkerCancelled`` and ``EiWorkerDied`` are not: the
request was written and its fate is unknown, so they reach the caller.
