Single-Series Anomaly Detection
===============================

``data_drift`` answers "did the *distribution* shift between two batches" — it
cannot point at *which* value in one live series is anomalous — and
``slo.burn_alerts`` only thresholds error-budget burn, not arbitrary metric
values (latency spikes, cost spikes, CPU). This flags outliers in a single
series via z-score, robust MAD (modified z-score), and an EWMA control chart.

Pure standard library (``math`` / ``statistics``); imports no ``PySide6``. Every
function is pure (values in, flags out), so it is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import detect_anomalies, mad_anomalies, ewma_control

    series = [10, 11, 9, 10, 12, 10, 95, 11, 10]    # index 6 is the spike
    mad_anomalies(series)                            # [6]  (robust)
    detect_anomalies(series, method="mad")
    # [{index, value, score, is_anomaly}, ...]

    ewma_control(values, alpha=0.5, target_mean=10, target_sigma=1)  # shift indices

``detect_anomalies`` scores each value (``mad`` default, or ``zscore``) and flags
those past the threshold (3.5 for MAD, 3.0 for z-score). ``mad_anomalies`` /
``zscore_anomalies`` return just the flagged indices, and ``mad_scores`` /
``zscore_scores`` the raw scores. MAD (Iglewicz-Hoaglin modified z-score) is
robust to outliers inflating the spread, so it stays sensitive where a plain
z-score would not. ``ewma_control`` is an EWMA control chart for sustained
level shifts — pass ``target_mean`` / ``target_sigma`` for an in-control
baseline (else the series' own stats).

Executor command
----------------

``AC_detect_anomalies`` takes a ``values`` list (optional ``method`` /
``threshold``) and returns ``{results}``. It is exposed as the MCP tool
``ac_detect_anomalies`` and as a Script Builder command under **Data**.
