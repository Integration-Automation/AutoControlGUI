Settle Detection Over a Churn Series
====================================

``smart_waits.wait_until_screen_stable`` and ``actionability``'s stability check bake the
settle logic *inside* a ``time.sleep`` polling loop over live pixel frames — you cannot feed
them a recorded series of a11y-element counts or screen-diff metrics, and you cannot unit-test
the *decision* independently of capture. ``settle_detector`` extracts that decision: it takes a
stream of *churn* values (how much changed each sample — a pixel delta, an element-count delta,
a digest-changed 0/1, anything) and reports when the churn has stayed at or below ``max_churn``
for ``quiet_samples`` in a row. A spike resets the quiet run, so "settled then changed again"
is handled.

Pure-stdlib; deterministic and unit-testable on an injected series with no capture and no
clock. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import settle_point, is_settled, SettleTracker

    churns = [5, 4, 0.5, 0.3, 0.2]          # per-frame change metric
    settle_point(churns, quiet_samples=3, max_churn=1.0)   # -> 4
    is_settled(churns, quiet_samples=3, max_churn=1.0)     # -> True

    # incremental, for a live loop (you supply the churn each tick)
    tracker = SettleTracker(quiet_samples=3, max_churn=1.0)
    state = tracker.update(current_churn)
    if state.settled:
        observe_now()

``settle_point`` returns the index at which the series first settles (or ``None``);
``is_settled`` is the boolean. ``SettleTracker`` is the incremental form: ``update(churn)``
returns a ``SettleState`` (``settled`` / ``quiet_run`` / ``churn``); ``reset`` clears the run
(e.g. right after acting again).

Executor command
----------------

``AC_settle_point`` (``churns`` / ``quiet_samples`` / ``max_churn`` → ``{settled, index}``) is
exposed as the MCP tool ``ac_settle_point`` (read-only) and as the Script Builder command
**Settle Point (churn series)** under **Flow**.
