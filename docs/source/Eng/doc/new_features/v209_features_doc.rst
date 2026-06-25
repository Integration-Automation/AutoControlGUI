Retry Budget — Deadline + Jitter
================================

:class:`resilience.RetryPolicy` retries a fixed number of attempts with plain
exponential backoff. Two things it can't express are exactly what flaky,
contended UI automation needs:

* a **wall-clock deadline** — "keep retrying, but give up after 30 s total",
  independent of how many attempts that takes; and
* **jitter** — randomized backoff so many retrying workers don't resynchronize
  into a thundering herd.

``retry_budget`` adds both. :class:`RetryBudget` is bounded by ``max_attempts``
*and / or* ``deadline_s``; :func:`run_with_budget` honours whichever is hit
first and never sleeps past the deadline. Delays use capped exponential backoff
with a selectable jitter strategy (``full`` / ``equal`` / ``none``). The
randomness source (``uniform``), the clock and the sleeper are all injectable,
so every delay and decision is deterministic in tests. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import RetryBudget, run_with_budget

    budget = RetryBudget(max_attempts=8, deadline_s=30.0,
                         base_delay_s=0.2, max_delay_s=5.0)

    # Retry the click until it lands, capped at 8 tries OR 30 seconds total
    run_with_budget(lambda: click_and_verify("Save"), budget)

``RetryBudget`` is bounded by attempts and / or a deadline — set either to
``None`` to bound only by the other. :func:`backoff_delay` (pure, no jitter) and
:meth:`RetryBudget.plan` give the delay schedule for inspection:

.. code-block:: python

    RetryBudget(jitter="none").plan(4)   # [0.1, 0.2, 0.4, 0.8]

For deterministic tests inject ``uniform`` / ``clock`` / ``sleep``:

.. code-block:: python

    run_with_budget(flaky, budget, clock=fake_clock, sleep=fake_sleep,
                    uniform=lambda lo, hi: lo)   # always the low bound

Executor commands
-----------------

``AC_retry_delay`` (``attempt`` / ``base`` / ``max_delay`` / ``multiplier`` /
``jitter`` → ``{delay}``) and ``AC_plan_retry_delays`` (``attempts`` … →
``{delays}``) expose the pure backoff schedule (``jitter`` defaults to ``none``
for a deterministic result). They are the matching read-only ``ac_*`` MCP tools
and Script Builder commands under **Flow**. :func:`run_with_budget` (which wraps
a callable) is the Python-API surface.
