Time-Series Transforms
======================

``observability`` counters and gauges store only the *current* value — nothing
turned a counter into a per-second rate — and ``cost_telemetry`` only buckets by
a fixed day. This adds Prometheus-style ``rate`` / ``irate`` / ``increase`` /
``delta`` (reset-aware) plus tumbling-bucket ``downsample`` and grid
``resample`` over ``(timestamp, value)`` sequences.

Pure standard library (``bisect``); imports no ``PySide6``. No wall clock is
read — windows use the series' own timestamps — so every function is fully
deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import ts_rate, ts_increase, ts_downsample, ts_resample

    series = [(0, 0), (10, 50), (20, 120)]      # (timestamp_s, counter_value)
    ts_rate(series)                              # 6.0  (120 over 20s)
    ts_rate(series, window_s=10)                 # rate over the last 10s only
    ts_increase(series)                          # 120.0 (reset-aware)

    ts_downsample([(0, 1), (3, 3), (5, 10)], 5, "avg")   # [(0, 2.0), (5, 10.0)]
    ts_resample([(0, 0), (20, 20)], 10, fill="linear")   # [(0,0),(10,10),(20,20)]

``ts_rate`` / ``ts_increase`` treat a value drop as a counter reset (Prometheus
semantics); ``ts_irate`` is the instant rate from the last two samples;
``ts_delta`` / ``ts_idelta`` are gauge first-to-last and last-two differences.
``ts_downsample`` rolls the series into ``bucket_s`` tumbling buckets aggregated
by ``avg`` / ``sum`` / ``min`` / ``max`` / ``first`` / ``last`` / ``count``.
``ts_resample`` aligns to a fixed grid, filling with ``"last"`` (carry forward),
``"linear"`` (interpolate), or ``None`` (gaps).

Executor commands
-----------------

``AC_ts_rate`` returns ``{rate}`` for a ``series`` (optional ``window_s``);
``AC_ts_downsample`` returns ``{buckets}`` for a ``series`` and ``bucket_s``
(optional ``agg``). Both are exposed as MCP tools (``ac_ts_rate`` /
``ac_ts_downsample``) and as Script Builder commands under **Data**.
