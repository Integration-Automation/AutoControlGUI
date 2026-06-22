Stuck-Loop Guard (Agent Loop Progress Detection)
================================================

The dominant computer-use failure mode is an agent burning its budget repeating
an action that has no effect — and the model usually can't see its own loop, so
it must be caught **mechanically** from outside, by watching the stream of
``(tool, args, result)`` triples. ``LoopGuard`` flags three patterns:

- ``repeat`` — the same ``(tool, args)`` fired many times in a row;
- ``ping_pong`` — two actions alternating A-B-A-B with no progress;
- ``no_op`` — the observation (a screenshot/state digest) never changes.

It complements a step/time budget (which can't tell a productive loop from a
stuck one) and the offline trajectory evaluator. Pure standard library
(``collections`` + ``hashlib``), deterministic; imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import LoopGuard, digest_result

    guard = LoopGuard(warn=8, critical=15)
    for step in agent_steps:
        verdict = guard.observe(step.tool, step.args,
                                digest_result(step.screenshot))
        if verdict.level == "critical":
            break                       # abort: stuck loop
        if verdict.level == "warn":
            nudge_the_model(verdict.pattern)

``observe`` returns ``{pattern, level, count}`` where ``level`` is ``ok`` /
``warn`` / ``critical`` once the run length crosses the thresholds. ``count`` is
the length of the detected run. ``digest_result`` makes a stable short hash of a
screenshot/observation (bytes or any JSON-able value). ``reset`` clears history.

Executor commands
-----------------

A module-level default guard backs the executor/MCP surfaces so a flow can track
progress across steps:

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_loop_guard_observe``        Feed a step; returns ``{pattern, level, count}``.
``AC_loop_guard_reset``          Clear the default guard's history.
================================ ===================================================

The same operations are exposed as MCP tools (``ac_loop_guard_observe`` /
``ac_loop_guard_reset``) and as Script Builder commands under **Agent**.
