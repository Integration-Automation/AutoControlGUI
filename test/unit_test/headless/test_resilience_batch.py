"""Headless tests for resilience primitives: retry-with-backoff and a
circuit breaker. Injected clock/sleep make timing deterministic. Pure
stdlib; no Qt imports."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.resilience import (
    CircuitBreaker, CircuitOpenError, RetryPolicy, retry_call)


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}
    slept = []

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    policy = RetryPolicy(max_attempts=5, backoff=0.1, multiplier=2.0)
    assert policy.run(flaky, sleep=slept.append) == "ok"
    assert calls["n"] == 3
    assert slept == [pytest.approx(0.1), pytest.approx(0.2)]  # backoff grows


def test_retry_exhausts_and_reraises():
    def always_fail():
        raise KeyError("nope")

    with pytest.raises(KeyError):
        RetryPolicy(max_attempts=2, backoff=0).run(always_fail,
                                                    sleep=lambda s: None)


def test_retry_call_convenience():
    assert retry_call(lambda: 42) == 42


def test_circuit_breaker_opens_and_resets():
    clock = _Clock()
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=10.0,
                             clock=clock)

    def boom():
        raise RuntimeError("down")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            breaker.call(boom)
    assert breaker.state == "open"
    # while open, calls short-circuit without invoking func
    with pytest.raises(CircuitOpenError):
        breaker.call(boom)
    # after the reset timeout it half-opens; a success closes it
    clock.now = 10.0
    assert breaker.state == "half_open"
    assert breaker.call(lambda: "ok") == "ok"
    assert breaker.state == "closed"


# --- wiring ---------------------------------------------------------------

def test_executor_wiring():
    # circuit breaker runs a trivially-succeeding action and stays closed
    rec = ac.execute_action([["AC_circuit_call", {
        "name": "t", "actions": [["AC_seed_everything", {"seed": 1}]]}]])
    assert any("'state': 'closed'" in str(v) for v in rec.values())
    assert "AC_circuit_call" in ac.executor.known_commands()


def test_mcp_and_builder_wiring():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_circuit_call" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert "AC_circuit_call" in cmds


def test_facade_exports():
    for attr in ("RetryPolicy", "CircuitBreaker", "CircuitOpenError",
                 "retry_call"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
