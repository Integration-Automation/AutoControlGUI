Moving-Average Smoothing
========================

``stats.describe`` summarises a whole sample and ``timeseries`` rolls counters
into rates, but nothing smoothed a noisy signal or weighted recent points. This
adds trailing simple / weighted / exponentially-weighted moving averages and a
generic rolling reducer.

Pure standard library; imports no ``PySide6``. Every function is pure (values
in, list out), so it is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import sma, wma, ewma, rolling

    sma([1, 2, 3, 4], 2)            # [1.0, 1.5, 2.5, 3.5]
    ewma([1, 2, 3], alpha=0.5)      # [1.0, 1.5, 2.25]
    wma(values, [1, 2, 3])          # weights align to the latest points
    rolling(values, 5, max)         # generic trailing-window reduction

``sma`` averages each trailing window of ``window`` points; ``wma`` applies the
given weights (latest-aligned); ``ewma`` smooths with factor ``alpha`` in
``(0, 1]``; ``rolling`` applies any reducer over each trailing window. All
return a same-length list, so the result lines up with the input timeline (a
``resource_profiler`` FPS/CPU series, a latency stream, etc.).

Executor commands
-----------------

``AC_sma`` returns ``{series}`` for ``values`` over a ``window``; ``AC_ewma``
returns ``{series}`` for an ``alpha``. Both are exposed as MCP tools (``ac_sma``
/ ``ac_ewma``) and as Script Builder commands under **Data**.
