Lock the Workstation + Wait for Unlock
======================================

:mod:`session_guard` answers "is the session locked right now?" and raises if it
is. The missing half is *acting* on the lock state: lock the machine at the end
of an unattended run, block until a human unlocks it before resuming, or reduce
a stream of lock-state samples to lock / unlock events. ``lock_session`` adds
that, behind injectable seams so the logic is testable without touching the OS.

* :func:`lock_session` — lock the workstation now (``LockWorkStation`` on
  Windows, ``loginctl lock-session`` on Linux, ``CGSession -suspend`` on macOS)
  through an injectable ``driver``.
* :func:`plan_lock_session` — pure planner: how the lock would be performed on
  this OS and whether a default is available (``{backend, argv, available}``).
* :func:`wait_for_unlock` / :func:`wait_for_lock` — poll
  :func:`is_session_locked` until the state flips or a timeout, with injectable
  ``clock`` / ``sleep`` / ``probe`` for deterministic tests.
* :func:`classify_lock_transitions` — pure: a list of lock-state samples to a
  list of ``{event, locked}`` lock / unlock transitions.

The lock probe reused by the wait helpers is :mod:`session_guard`'s — the
Windows ``OpenInputDesktop`` check — so ``wait_for_unlock`` is the blocking
companion to ``ensure_interactive_session`` (which only raises). Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        lock_session, wait_for_unlock, classify_lock_transitions,
    )

    # ... unattended run finishes ...
    lock_session()                 # secure the machine

    # Resume only once a human has unlocked the box
    if wait_for_unlock(timeout_s=600):
        run_next_stage()

    # Reduce a sampled lock-state log to events
    classify_lock_transitions([False, True, True, False])
    # -> [{'event': 'lock', 'locked': True},
    #     {'event': 'unlock', 'locked': False}]

For tests (or any host) pass a ``driver`` / ``probe``:

.. code-block:: python

    locked = lock_session(driver=lambda: True)        # no real lock
    wait_for_unlock(probe=lambda: False)              # already unlocked

Executor commands
-----------------

``AC_lock_session`` (→ ``{locked}``), ``AC_plan_lock_session`` (→ the plan),
``AC_wait_for_unlock`` (``timeout`` / ``interval`` → ``{unlocked}``) and
``AC_classify_lock_transitions`` (``states`` JSON list → ``{events}``). They are
exposed as the matching ``ac_*`` MCP tools (``ac_lock_session`` is destructive —
it interrupts the session; the rest are read-only) and as Script Builder
commands under **Shell**.
