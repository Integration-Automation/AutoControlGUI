Actionability Gate — Wait Until Ready Before Acting
===================================================

Modern UI frameworks (Playwright, Cypress, WebdriverIO) run an *actionability* check
before every click: the target must be present, have stopped moving, be enabled, and
actually receive the event (not be covered). AutoControl had no equivalent —
``self_heal_click`` locates and clicks immediately, and ``wait_until_screen_stable``
only watches the *whole* frame. ``wait_actionable`` composes the four checks into one
gate, so a click lands on a button that is genuinely ready rather than mid-animation,
disabled, or behind a dialog.

Every signal is an injectable callable — ``bbox_provider`` (locate the target),
``region_sampler`` (pixel-stability token), ``enabled_probe``, ``hit_tester`` — plus
an injectable ``clock`` / ``sleep`` via :class:`GateConfig`, so the gate is fully
deterministic and headless-testable. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import wait_actionable, act_when_ready, GateConfig

    report = wait_actionable(
        bbox_provider=lambda: locate_button(),        # () -> (x, y, w, h) or None
        enabled_probe=lambda: not is_greyed_out(),
        config=GateConfig(timeout_s=8.0, stable_for_s=0.4))
    if report.actionable:
        click(*report.point)
    else:
        print("blocked:", report.reason)              # not visible / not stable / …

    # Or gate + act in one call (raises if it never becomes actionable):
    act_when_ready(lambda point: click(*point), bbox_provider=locate_button)

``wait_actionable`` returns an :class:`ActionabilityReport` with ``actionable`` plus
the per-check booleans (``visible`` / ``stable`` / ``enabled`` / ``receives_events``),
the target ``point``, ``waited_s`` and a ``reason`` (the first failing check).
``act_when_ready`` waits and then calls ``action(center_point)``, raising
``AutoControlActionException`` on timeout.

Executor command
----------------

``AC_wait_actionable`` binds the gate to a ``template`` image (located each poll) and
samples that region's pixels for stability: ``timeout_s`` / ``stable_for_s`` /
``min_score`` / ``region`` → the report dict. It is exposed as the MCP tool
``ac_wait_actionable`` and as a Script Builder command under **Flow**.
