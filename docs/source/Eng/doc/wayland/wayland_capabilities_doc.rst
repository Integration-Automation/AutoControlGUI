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
     - not determinable without side effects (macOS permissions, for example)

Each capability also carries ``backend`` (what serves it), ``desktop_wide``,
``detail``, ``recovery`` (what to do, in English) and ``recovery_key`` (the
same advice as a GUI catalogue key).

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
