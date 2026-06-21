"""Headless tests for the chaos experiment runner. Pure stdlib, no Qt."""
import json
import random

import je_auto_control as ac
from je_auto_control.utils.chaos import (
    ChaosExperiment, Fault, Probe, exception_fault, latency_fault,
    run_experiment)


def test_steady_state_holds_no_deviation():
    state = {"healthy": True}
    experiment = ChaosExperiment(
        "ok",
        probes=[Probe("health", lambda: state["healthy"], True)],
        method=[latency_fault("lat", delay_s=0.5, sleep=lambda _d: None)],
        rollbacks=[lambda: state.update(healthy=True)])
    journal = run_experiment(experiment)
    assert journal["status"] == "completed"
    assert journal["deviated"] is False
    assert len(journal["rollbacks"]) == 1


def test_failed_before_method_bails():
    journal = run_experiment(ChaosExperiment(
        "bad", probes=[Probe("p", lambda: False, True)],
        method=[Fault("x", lambda: 1)]))
    assert journal["status"] == "failed-before-method"
    assert journal["run"] == []


def test_deviation_after_method():
    counter = {"n": 0}

    def probe():
        counter["n"] += 1
        return counter["n"] < 2          # ok before, fails after

    journal = run_experiment(ChaosExperiment(
        "dev", probes=[Probe("p", probe, True)],
        method=[Fault("break", lambda: "boom")]))
    assert journal["status"] == "deviated"
    assert journal["deviated"] is True


def test_tolerance_range_and_predicate():
    assert run_experiment(ChaosExperiment(
        "r", probes=[Probe("lat", lambda: 50, [0, 100])]))[
            "steady_states"]["before"]["ok"] is True
    assert run_experiment(ChaosExperiment(
        "p", probes=[Probe("even", lambda: 4, lambda v: v % 2 == 0)]))[
            "steady_states"]["before"]["ok"] is True


def test_exception_fault_recorded():
    fault = exception_fault("boom", rate=1.0, rng=random.Random(0))
    journal = run_experiment(ChaosExperiment(
        "ex", probes=[Probe("p", lambda: True, True)], method=[fault]))
    assert journal["run"][0]["ok"] is False
    assert "error" in journal["run"][0]


def test_rollbacks_run_lifo():
    order = []
    run_experiment(ChaosExperiment(
        "lifo", probes=[Probe("p", lambda: True, True)], method=[],
        rollbacks=[lambda: order.append(1), lambda: order.append(2)]))
    assert order == [2, 1]


def test_injectable_clock():
    journal = run_experiment(
        ChaosExperiment("c", probes=[Probe("p", lambda: True, True)]),
        clock=lambda: 5.0)
    assert journal["duration"] == 0.0


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    spec = {
        "title": "exec-chaos",
        "probes": [{"name": "noop", "action": [["AC_sleep", {"seconds": 0}]]}],
        "method": [{"name": "noop", "action": [["AC_sleep", {"seconds": 0}]]}],
        "rollbacks": [[["AC_sleep", {"seconds": 0}]]],
    }
    rec = ac.execute_action([["AC_run_chaos", {"spec": json.dumps(spec)}]])
    journal = next(v for v in rec.values() if isinstance(v, dict))
    assert journal["status"] == "completed"
    assert len(journal["rollbacks"]) == 1


def test_wiring():
    assert "AC_run_chaos" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_run_chaos" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_run_chaos" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("ChaosExperiment", "Probe", "Fault", "run_experiment",
                 "latency_fault", "exception_fault"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
