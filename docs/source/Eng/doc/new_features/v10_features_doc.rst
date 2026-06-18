================================================
New Features (2026-06-19) — Transactional Queue
================================================

Turn AutoControl from a "run a script" tool into "run a robot." A
SQLite-backed work queue implements the standard production-RPA
dispatcher/performer pattern: a *dispatcher* enqueues work items, and a
*performer* processes them one at a time with per-item status, dedup and
retry — so a run of thousands of items is **resumable after a crash** and
parallelizable across workers.

Pure standard library, fully headless, wired through the full stack
(facade, ``AC_*`` executor commands, MCP tools, Script Builder). Surfaced
by the competitor research as the missing piece vs UiPath Orchestrator
queues / REFramework.

.. contents::
   :local:
   :depth: 2


Dispatcher / performer
======================

::

    from je_auto_control import WorkQueue

    q = WorkQueue("run.db", name="invoices")

    # Dispatcher: enqueue work (dedupes on a live reference).
    for inv in invoices:
        q.add({"path": inv}, reference=inv)

    # Performer: drain the queue, resumable across restarts.
    item = q.get_next()
    while item is not None:
        try:
            process(item.data)
            q.complete(item.id, output={"ok": True})
        except BusinessError as exc:           # bad data — don't retry
            q.fail(item.id, str(exc), kind="business")
        except Exception as exc:               # transient — retry
            q.fail(item.id, str(exc), kind="application")
        item = q.get_next()

``get_next`` atomically claims the oldest ``new`` item (marking it
``in_progress``) so multiple performers don't double-process.


Failure semantics
=================

Two failure kinds, mirroring REFramework:

* **application** (transient — a timeout, a stale element): the item is
  retried up to ``max_retries`` (default 3), then marked ``failed``.
* **business** (the data itself is invalid): never retried — marked
  ``failed`` immediately. Raise :class:`BusinessError` or pass
  ``kind="business"``.

``stats()`` returns per-status counts (``new`` / ``in_progress`` /
``success`` / ``failed``) for dashboards and run reports.


Executor commands
=================

* ``AC_queue_add`` — enqueue ``data`` (dedup by ``reference``).
* ``AC_queue_next`` — claim the next item (or null when drained).
* ``AC_queue_complete`` — mark an item successful.
* ``AC_queue_fail`` — fail with ``kind`` (``application`` / ``business``).
* ``AC_queue_stats`` — per-status counts.

The same ``db`` file + ``name`` identify a queue, so a dispatcher script
and a performer script (or many parallel performers) share it.
