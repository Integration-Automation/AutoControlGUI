==================================================
New Features (2026-06-19) — Checkpoint & Resume
==================================================

Durable execution for long action lists, plus a ``py.typed`` marker so the
package's inline type hints are honored by type checkers. Pure standard
library; wired through the full stack (facade, ``AC_*`` executor commands,
MCP tools, Script Builder).

.. contents::
   :local:
   :depth: 2


Flow checkpoint & resume
=======================

A multi-hour unattended flow that dies at step 400 should not restart from
zero. :func:`run_resumable` persists ``{run_id, step_index, variables}``
after each executed step to a pluggable store; on a later run with the same
``run_id`` it fast-forwards past completed steps and rehydrates the script
variables::

    from je_auto_control import run_resumable, CheckpointStore

    store = CheckpointStore("runs.db")
    result = run_resumable(actions, run_id="nightly-invoices", store=store)
    result["resumed_from"]   # 0 on a fresh run, N when resuming after a crash

On normal completion the checkpoint is cleared. The store is injectable, so
resume is unit-tested deterministically without a real crash:
``CheckpointStore.save`` / ``load`` / ``clear``.

Executor / MCP commands:

* ``AC_run_resumable`` — run ``actions`` with checkpoint/resume keyed by
  ``run_id`` (persisted to ``db``).
* ``AC_checkpoint_status`` — the saved checkpoint for a run (or null).
* ``AC_checkpoint_clear`` — delete a run's checkpoint.

(and the matching ``ac_run_resumable`` / ``ac_checkpoint_status`` /
``ac_checkpoint_clear`` MCP tools).


``py.typed`` marker
==================

The package now ships a PEP 561 ``py.typed`` marker, so Mypy / Pyright /
Pylance honor AutoControl's inline type annotations in downstream code —
completing the value of the typed public API. No code change for callers;
just better editor autocompletion and type checking out of the box.
