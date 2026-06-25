Adaptive Timeout from Observed Durations
========================================

Hard-coded waits are a perennial source of flakiness: too short and a slow
machine races the UI; too long and every failure pays the full timeout. The
durable fix is to *learn* the timeout from how long a step has actually taken.
``adaptive_timeout`` turns a sample of observed durations into a robust timeout
— a high percentile (the slow-but-real case) scaled by a safety ``factor``,
then clamped to a sane ``[min_s, max_s]`` band.

* :func:`recommend_timeout` — the single number to feed a wait or ``GateConfig``.
* :func:`timeout_stats` — the same with the percentiles and clamp flags exposed
  for logging / tuning.

Both are pure and reuse :func:`stats.percentile`; with no samples they fall back
to ``default_s`` (or ``min_s``). Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import recommend_timeout, timeout_stats

    # The dialog has historically taken these seconds to appear:
    seen = [0.8, 1.1, 0.9, 3.2, 1.0, 1.3]

    recommend_timeout(seen)                 # ~ p95 * 1.5, clamped to [1, 60]
    recommend_timeout(seen, percentile_q=99.0, factor=2.0, max_s=30.0)

    timeout_stats(seen)
    # {'n': 6, 'p50': 1.05, 'p_high': 2.7..., 'percentile_q': 95.0,
    #  'recommended': 4.1..., 'floored': False, 'capped': False}

Use the recommendation as the ``timeout_s`` for the next ``wait_for_*`` /
actionability gate, recomputing it as the duration sample grows. With no samples
yet, pass ``default_s`` for the cold-start value.

Executor commands
-----------------

``AC_adaptive_timeout`` (``durations`` + ``percentile_q`` / ``factor`` /
``min_s`` / ``max_s`` → ``{timeout_s}``) and ``AC_timeout_stats`` (same inputs →
``{n, p50, p_high, percentile_q, recommended, floored, capped}``). ``durations``
accepts a JSON list. They are the matching read-only ``ac_*`` MCP tools and
Script Builder commands under **Flow**.
