"""Deterministic chaos experiments: steady-state hypothesis + fault injection.

``resilience`` *recovers* from failures (retry, circuit breaker); this is the
inverse — it *causes* controlled failures and checks a steady-state hypothesis
still holds. Modelled on the Chaos Toolkit lifecycle: verify steady state
before, run the method (fault activities), verify steady state after, then
always run rollbacks (LIFO). Returns a journal.

Probes, faults and rollbacks are caller-supplied callables, and the clock /
RNG / sleep are injectable, so an experiment runs deterministically in tests
with fakes — no real failures, no real sleeping. Pure standard library
(``random`` + ``time``); imports no ``PySide6``.
"""
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence


@dataclass
class Probe:
    """A steady-state probe: ``call`` returns a value checked against ``tolerance``."""

    name: str
    call: Callable[[], Any]
    tolerance: Any = True


@dataclass
class Fault:
    """A fault-injection activity run during the experiment method."""

    name: str
    apply: Callable[[], Any]


@dataclass
class ChaosExperiment:
    """An experiment: a steady-state hypothesis, a method, and rollbacks."""

    title: str
    probes: Sequence[Probe] = ()
    method: Sequence[Fault] = ()
    rollbacks: Sequence[Callable[[], Any]] = field(default_factory=tuple)


def _check_tolerance(value: Any, tolerance: Any) -> bool:
    if callable(tolerance):
        return bool(tolerance(value))
    if isinstance(tolerance, (list, tuple)) and len(tolerance) == 2:
        return tolerance[0] <= value <= tolerance[1]
    return value == tolerance


def _verify_probes(probes: Sequence[Probe]) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    ok = True
    for probe in probes:
        try:
            value = probe.call()
            met = _check_tolerance(value, probe.tolerance)
            results.append({"name": probe.name, "ok": met, "value": value})
        except Exception as exc:  # pylint: disable=broad-exception-caught
            met = False
            results.append({"name": probe.name, "ok": False,
                            "error": str(exc)})
        ok = ok and met
    return {"ok": ok, "probes": results}


def _apply_fault(fault: Fault) -> Dict[str, Any]:
    try:
        return {"name": fault.name, "ok": True, "result": fault.apply()}
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return {"name": fault.name, "ok": False, "error": str(exc)}


def _run_rollbacks(rollbacks: Sequence[Callable[[], Any]]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for rollback in reversed(list(rollbacks)):
        try:
            rollback()
            results.append({"ok": True})
        except Exception as exc:  # pylint: disable=broad-exception-caught
            results.append({"ok": False, "error": str(exc)})
    return results


def run_experiment(experiment: ChaosExperiment, *,
                   clock: Callable[[], float] = time.monotonic) -> Dict[str, Any]:
    """Run ``experiment`` and return a journal dict (Chaos-Toolkit shape)."""
    start = clock()
    before = _verify_probes(experiment.probes)
    journal: Dict[str, Any] = {
        "title": experiment.title,
        "steady_states": {"before": before, "after": None},
        "run": [], "rollbacks": [], "deviated": False, "status": "completed",
    }
    if not before["ok"]:
        journal["status"] = "failed-before-method"
        journal["duration"] = clock() - start
        return journal
    try:
        for fault in experiment.method:
            journal["run"].append(_apply_fault(fault))
        after = _verify_probes(experiment.probes)
        journal["steady_states"]["after"] = after
        journal["deviated"] = not after["ok"]
        if not after["ok"]:
            journal["status"] = "deviated"
    finally:
        journal["rollbacks"] = _run_rollbacks(experiment.rollbacks)
    journal["duration"] = clock() - start
    return journal


def latency_fault(name: str, *, delay_s: float, rate: float = 1.0,
                  rng: Optional[random.Random] = None,
                  sleep: Callable[[float], None] = time.sleep) -> Fault:
    """A fault that sleeps ``delay_s`` with probability ``rate``."""
    generator = rng or random.Random()  # nosec B311  # reason: non-crypto chaos rate sampling

    def apply() -> Dict[str, Any]:
        if generator.random() < rate:
            sleep(delay_s)
            return {"injected": "latency", "delay_s": delay_s}
        return {"injected": None}

    return Fault(name=name, apply=apply)


def exception_fault(name: str, *, exc: type = RuntimeError,
                    message: str = "chaos", rate: float = 1.0,
                    rng: Optional[random.Random] = None) -> Fault:
    """A fault that raises ``exc`` with probability ``rate``."""
    generator = rng or random.Random()  # nosec B311  # reason: non-crypto chaos rate sampling

    def apply() -> Dict[str, Any]:
        if generator.random() < rate:
            raise exc(message)
        return {"injected": None}

    return Fault(name=name, apply=apply)
