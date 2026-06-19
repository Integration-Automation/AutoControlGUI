==================================================
New Features (2026-06-19) — Reactive Observer
==================================================

A non-blocking **screen observer**: register watches on a region/predicate
and get a callback (or run an action list) when the watched thing
**appears**, **vanishes**, or **changes**. This is the complement to the
blocking ``wait_for_*`` helpers — a flow can react to dialogs, progress, or
status changes *while doing other work* (the SikuliX ``observe`` model).

Pure standard library; wired through the full stack (facade, ``AC_*``
executor commands, MCP tools, Script Builder).

.. contents::
   :local:
   :depth: 2


Python API
=========

::

    from je_auto_control import ScreenObserver, image_predicate, EVENT_APPEAR

    obs = ScreenObserver(poll_interval_s=0.5)
    obs.add("error-dialog",
            image_predicate("error.png", threshold=0.9),
            on_event=lambda event, value: dismiss(),
            events=(EVENT_APPEAR,))
    obs.start()                 # background polling thread
    ...
    obs.stop()

Detection is decoupled from the screen: a watch's ``predicate`` just
returns the current value (truthy = present), so transition logic is
unit-tested with synthetic values via ``poll_once()``. Built-in predicate
builders — :func:`image_predicate`, :func:`text_predicate`,
:func:`pixel_predicate` — wrap the existing locate / OCR / pixel helpers.

Transitions: ``appear`` (absent -> present), ``vanish`` (present ->
absent), ``change`` (present, value differs). Subscribe to a subset via
``events=``.


Executor / MCP commands
======================

* ``AC_observe_add`` — watch ``kind`` (``image`` / ``text`` / ``pixel``)
  for ``event`` and run ``actions`` when it fires (the watchdog pattern,
  generalised to screen content).
* ``AC_observe_remove`` / ``AC_observe_list`` — manage watches.
* ``AC_observe_poll`` — evaluate every watch once and return fired events
  (deterministic, thread-free — ideal in scripts/tests).
* ``AC_observe_start`` / ``AC_observe_stop`` — background poll thread.

The matching ``ac_observe_*`` MCP tools expose the same surface.
