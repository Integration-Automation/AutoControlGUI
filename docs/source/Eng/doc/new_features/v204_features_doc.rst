Idle Detection + Keep the Machine Awake
=======================================

Long unattended automation runs get derailed two ways: the screensaver / power
policy sleeps the box mid-run, or the run should hold while a human is actively
using the machine. The framework had neither signal. ``idle_keepawake`` adds
both, behind injectable seams so all logic is testable without touching the OS.

* :func:`idle_seconds` / :func:`is_idle` — seconds since the last user keyboard /
  mouse input (``GetLastInputInfo`` on Windows), through an injectable ``probe``.
* :func:`plan_keep_awake` — pure planner describing which wake flags a request
  maps to.
* :func:`keep_awake` — scoped context manager that keeps the machine awake for
  the duration of a ``with`` block, restoring the prior state on exit.
* :func:`keep_awake_on` / :func:`allow_sleep` — a process-global on / off pair
  for JSON action flows.

All three keep-awake entry points apply the plan through an injectable ``driver``
(``SetThreadExecutionState`` on Windows, ``caffeinate`` on macOS,
``systemd-inhibit`` on Linux by default). Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        idle_seconds, is_idle, keep_awake, keep_awake_on, allow_sleep,
    )

    idle_seconds()          # e.g. 3.4 — seconds since last input
    is_idle(300)            # True once nobody has touched the machine for 5 min

    # Scoped: keep awake only while a long step runs
    with keep_awake():
        run_long_batch()

    # Flow-style: on at the start, off at the end
    keep_awake_on(display=True, system=True)
    try:
        run_long_batch()
    finally:
        allow_sleep()

:func:`is_idle` is the gate for "only run when the user has stepped away";
:func:`keep_awake` / :func:`keep_awake_on` stop the display and system sleeping
so an overnight run is not interrupted. ``display=False`` keeps the system awake
but lets the screen blank (battery-friendly for headless boxes).

Executor commands
-----------------

``AC_idle_seconds`` (→ ``{idle_seconds}``), ``AC_is_idle`` (``threshold`` →
``{idle, idle_seconds}``), ``AC_plan_keep_awake`` (``display`` / ``system`` → the
plan), ``AC_keep_awake_on`` (``display`` / ``system`` → the active plan) and
``AC_allow_sleep`` (→ ``{released}``). They are exposed as the matching ``ac_*``
MCP tools (reads read-only, keep-awake on/off side-effect-only) and as Script
Builder commands under **Shell**. The :func:`keep_awake` context manager is the
Python-API surface for scoped use.
