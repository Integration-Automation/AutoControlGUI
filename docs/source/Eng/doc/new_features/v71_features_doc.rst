Chaos Experiments
=================

``resilience`` *recovers* from failures (retry, circuit breaker); this is the
inverse — it *causes* controlled failures and checks that a steady-state
hypothesis still holds. Modelled on the Chaos Toolkit lifecycle: verify steady
state **before**, run the **method** (fault activities), verify steady state
**after**, then always run **rollbacks** (LIFO). It returns a journal.

Probes, faults and rollbacks are caller-supplied callables, and the clock / RNG
/ sleep are injectable, so an experiment runs deterministically in tests with
fakes — no real failures, no real sleeping. Pure standard library (``random`` +
``time``); imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        ChaosExperiment, Probe, run_experiment, latency_fault)

    experiment = ChaosExperiment(
        title="checkout survives slow payments",
        probes=[Probe("service_up", check_health, tolerance=True),
                Probe("p95_latency", measure_p95, tolerance=[0, 500])],
        method=[latency_fault("payment_delay", delay_s=2.0, rate=0.5)],
        rollbacks=[restore_network])

    journal = run_experiment(experiment)
    if journal["deviated"]:
        print("hypothesis broke under fault:", journal["status"])

A ``Probe`` returns a value checked against its ``tolerance`` (a literal, a
``[low, high]`` range, or a predicate callable). ``run_experiment`` verifies the
hypothesis first — if it fails, the status is ``failed-before-method`` and the
method never runs — then applies each fault, re-verifies (setting ``deviated``
and status ``deviated`` if it no longer holds), and always runs rollbacks LIFO
in a ``finally``. Probe/fault/rollback errors are caught and recorded in the
journal rather than crashing the run. ``latency_fault`` and ``exception_fault``
are ready-made fault factories with an injectable RNG (rate) and sleep.

Executor command
----------------

``AC_run_chaos`` takes a ``spec`` (object or JSON string) whose probes, method
and rollbacks are **action lists** — ``{title, probes:[{name, action:[AC...]}],
method:[{name, action:[AC...]}], rollbacks:[[AC...]]}`` — and returns the
journal. A probe's steady state holds when its actions run without error. The
same operation is exposed as the MCP tool ``ac_run_chaos`` and as a Script
Builder command under **Flow**.
