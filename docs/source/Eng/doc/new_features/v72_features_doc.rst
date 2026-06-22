Service-Level Objectives (SLO)
==============================

The framework emits raw signals (``observability`` metrics, ``run_history``
durations) but had no operational layer turning them into an SLO, an error
budget, or burn-rate alerts. This adds that: compute the SLI over a window of
outcome records, the error budget against a target, and the **multi-window
multi-burn-rate** alerts from the Google SRE workbook.

Records are plain data (``[{"timestamp": float, "ok": bool}, ...]``) so the
whole thing is offline and deterministic; the clock is injectable. Pure
standard library; imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import evaluate_slo, burn_alerts

    report = evaluate_slo(records, target=0.99)
    # {"sli": 0.995, "good": 995, "total": 1000, "target": 0.99,
    #  "budget_total": 10.0, "budget_remaining": 5.0,
    #  "budget_remaining_fraction": 0.5, "burn_rate": 0.5}

    for alert in burn_alerts(records, target=0.99):
        page_oncall(alert)        # severity, threshold, long/short burn rates

``evaluate_slo`` computes the SLI (good / total), the error budget
(``(1 - target) * total`` events) and the burn rate (``bad_rate / (1 -
target)`` — 1.0 means spending budget exactly on pace, > 1 means too fast).
``burn_rate`` is the bare number over a window. ``burn_alerts`` evaluates the
canonical Google SRE tiers from :func:`default_burn_rules` — page at 14.4× over
1h (and 5m), page at 6× over 6h (and 30m), ticket at 1× over 3d (and 6h) — and
fires a tier only when **both** its long and short windows exceed the
threshold, which gives fast reset and few false positives. Supply your own
``rules`` (``BurnRule`` list) to customise.

Executor commands
-----------------

``AC_evaluate_slo`` takes ``records`` (a list or JSON string), a ``target`` and
optional ``window_s``, and returns the SLI/budget report. ``AC_burn_alerts``
returns ``{alerts, firing}``. Both are exposed as MCP tools
(``ac_evaluate_slo`` / ``ac_burn_alerts``) and as Script Builder commands under
**Report**.
