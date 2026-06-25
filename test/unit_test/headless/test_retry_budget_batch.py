"""Headless tests for retry_budget (injected uniform / clock / sleep)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.retry_budget import (
    JITTER_EQUAL, JITTER_FULL, JITTER_NONE, RetryBudget, backoff_delay,
    jittered_delay, run_with_budget,
)


# --- pure backoff / jitter ------------------------------------------------

def test_backoff_delay_exponential_capped():
    assert backoff_delay(1, base=0.1, max_delay=5.0,
                         multiplier=2.0) == pytest.approx(0.1)
    assert backoff_delay(3, base=0.1, max_delay=5.0,
                         multiplier=2.0) == pytest.approx(0.4)
    # capped
    assert backoff_delay(10, base=0.1, max_delay=1.0,
                         multiplier=2.0) == pytest.approx(1.0)
    assert backoff_delay(0, base=0.1, max_delay=5.0,
                         multiplier=2.0) == pytest.approx(0.0)


def test_jittered_delay_none_is_identity():
    assert jittered_delay(0.8, JITTER_NONE) == pytest.approx(0.8)


def test_jittered_delay_full_uses_uniform_in_bounds():
    # full jitter samples [0, raw); inject a uniform returning the high bound
    assert jittered_delay(0.8, JITTER_FULL,
                          uniform=lambda lo, hi: hi) == pytest.approx(0.8)
    assert jittered_delay(0.8, JITTER_FULL,
                          uniform=lambda lo, hi: lo) == pytest.approx(0.0)


def test_jittered_delay_equal_half_plus_sample():
    # equal jitter = raw/2 + uniform(0, raw/2); with uniform->low gives raw/2
    assert jittered_delay(1.0, JITTER_EQUAL,
                          uniform=lambda lo, hi: lo) == pytest.approx(0.5)


# --- RetryBudget schedule -------------------------------------------------

def test_budget_plan_deterministic_without_jitter():
    budget = RetryBudget(base_delay_s=0.1, max_delay_s=5.0, multiplier=2.0,
                         jitter=JITTER_NONE)
    assert budget.plan(4) == pytest.approx([0.1, 0.2, 0.4, 0.8])


def test_budget_next_delay_full_jitter_bounded():
    budget = RetryBudget(base_delay_s=1.0, jitter=JITTER_FULL)
    high = budget.next_delay(1, uniform=lambda lo, hi: hi)
    low = budget.next_delay(1, uniform=lambda lo, hi: lo)
    assert high == pytest.approx(1.0)
    assert low == pytest.approx(0.0)


# --- run_with_budget ------------------------------------------------------

def test_run_with_budget_returns_on_success():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"

    result = run_with_budget(
        flaky, RetryBudget(max_attempts=5, jitter=JITTER_NONE),
        clock=lambda: 0.0, sleep=lambda _s: None)
    assert result == "ok"
    assert calls["n"] == 3


def test_run_with_budget_exhausts_attempts_and_reraises():
    attempts = {"n": 0}

    def always_fail():
        attempts["n"] += 1
        raise ValueError("nope")

    with pytest.raises(ValueError):
        run_with_budget(
            always_fail, RetryBudget(max_attempts=3, jitter=JITTER_NONE),
            clock=lambda: 0.0, sleep=lambda _s: None)
    assert attempts["n"] == 3


def test_run_with_budget_respects_deadline():
    attempts = {"n": 0}
    ticks = iter([0.0, 0.0, 10.0, 20.0, 30.0])  # 2nd elapsed check > deadline

    def always_fail():
        attempts["n"] += 1
        raise RuntimeError("slow")

    with pytest.raises(RuntimeError):
        run_with_budget(
            always_fail,
            RetryBudget(max_attempts=None, deadline_s=5.0, jitter=JITTER_NONE),
            clock=lambda: next(ticks), sleep=lambda _s: None)
    # gave up on the deadline, not after many attempts
    assert attempts["n"] == 2


def test_run_with_budget_propagates_unlisted_exception():
    def boom():
        raise KeyError("uncaught")

    with pytest.raises(KeyError):
        run_with_budget(
            boom, RetryBudget(max_attempts=5, exceptions=(ValueError,)),
            clock=lambda: 0.0, sleep=lambda _s: None)


def test_run_with_budget_caps_sleep_to_remaining_deadline():
    slept = []
    ticks = iter([0.0, 0.0, 0.0])  # elapsed stays 0 -> remaining = deadline

    run_args = {"n": 0}

    def fail_then_ok():
        run_args["n"] += 1
        if run_args["n"] == 1:
            raise ValueError("x")
        return "done"

    out = run_with_budget(
        fail_then_ok,
        RetryBudget(max_attempts=5, deadline_s=0.3, base_delay_s=10.0,
                    jitter=JITTER_NONE),
        clock=lambda: next(ticks), sleep=slept.append)
    assert out == "done"
    # raw backoff was 10s but capped to the 0.3s remaining deadline
    assert slept == pytest.approx([0.3])


# --- wiring ---------------------------------------------------------------

def test_executor_pure_paths():
    from je_auto_control.utils.executor.action_executor import (
        _plan_retry_delays, _retry_delay,
    )
    assert _retry_delay(2, 0.1, 5.0, 2.0, "none")["delay"] == pytest.approx(0.2)
    delays = _plan_retry_delays(3, 0.1, 5.0, 2.0, "none")["delays"]
    assert delays == pytest.approx([0.1, 0.2, 0.4])
    # full jitter stays within [0, raw]
    jittered = _retry_delay(1, 1.0, 5.0, 2.0, "full")["delay"]
    assert 0.0 <= jittered <= 1.0


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_retry_delay", "AC_plan_retry_delays"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_retry_delay", "ac_plan_retry_delays"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_retry_delay", "AC_plan_retry_delays"} <= specs


def test_facade_exports():
    for name in ("RetryBudget", "run_with_budget", "backoff_delay",
                 "jittered_delay"):
        assert hasattr(ac, name) and name in ac.__all__
