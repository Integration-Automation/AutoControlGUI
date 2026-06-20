"""Headless tests for the rate limiters. Pure stdlib, deterministic clock."""
import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rate_limit import (
    SlidingWindowLimiter, TokenBucket, throttle)

import pytest


class FakeClock:
    """A manually-advanced monotonic clock for deterministic tests."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, delta: float) -> None:
        self.t += delta


def test_token_bucket_burst_then_empty():
    clock = FakeClock()
    bucket = TokenBucket(rate=2.0, capacity=5.0, clock=clock)
    assert all(bucket.try_acquire() for _ in range(5))
    assert bucket.try_acquire() is False


def test_token_bucket_refills_at_rate():
    clock = FakeClock()
    bucket = TokenBucket(rate=2.0, capacity=5.0, clock=clock)
    for _ in range(5):
        bucket.try_acquire()
    assert bucket.time_until_available(1) == pytest.approx(0.5)
    clock.advance(0.5)
    assert bucket.try_acquire() is True


def test_token_bucket_caps_at_capacity():
    clock = FakeClock()
    bucket = TokenBucket(rate=2.0, capacity=5.0, clock=clock)
    bucket.try_acquire()
    clock.advance(100)
    assert bucket.tokens == pytest.approx(5.0)


def test_token_bucket_blocking_acquire_with_fake_sleep():
    clock = FakeClock()
    bucket = TokenBucket(rate=1.0, capacity=1.0, clock=clock)
    assert bucket.try_acquire() is True  # drain
    assert bucket.acquire(1.0, sleep=clock.advance) is True
    assert clock.t == pytest.approx(1.0)


def test_token_bucket_acquire_timeout():
    clock = FakeClock()
    bucket = TokenBucket(rate=1.0, capacity=1.0, clock=clock)
    bucket.try_acquire()
    assert bucket.acquire(1.0, timeout=0.5, sleep=clock.advance) is False


def test_token_bucket_rejects_bad_args():
    with pytest.raises(AutoControlException):
        TokenBucket(rate=0, capacity=1)
    with pytest.raises(AutoControlException):
        TokenBucket(rate=1, capacity=-1)


def test_sliding_window_limits_per_window():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=3, window_s=10, clock=clock)
    assert all(limiter.try_acquire() for _ in range(3))
    assert limiter.try_acquire() is False


def test_sliding_window_weighted_rollover():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=3, window_s=10, clock=clock)
    for _ in range(3):
        limiter.try_acquire()
    clock.advance(10)  # new window; previous count still fully weighted
    assert limiter.try_acquire() is False
    clock.advance(10)  # previous window now drops out
    assert limiter.try_acquire() is True


def test_throttle_leading_edge():
    clock = FakeClock()
    calls = []

    @throttle(5.0, clock=clock)
    def record(value):
        calls.append(value)
        return value

    assert record(1) == 1
    assert record(2) is None      # within interval -> dropped
    clock.advance(5)
    assert record(3) == 3
    assert calls == [1, 3]


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_rate_limit",
        {"name": "test-exec", "rate": 1.0, "capacity": 1.0},
    ]])
    payload = next(v for v in rec.values() if isinstance(v, dict))
    assert payload["acquired"] is True
    # second immediate call is rate limited (capacity 1, no refill yet)
    rec2 = ac.execute_action([[
        "AC_rate_limit",
        {"name": "test-exec", "rate": 1.0, "capacity": 1.0},
    ]])
    payload2 = next(v for v in rec2.values() if isinstance(v, dict))
    assert payload2["acquired"] is False
    assert payload2["wait"] > 0


def test_wiring():
    assert "AC_rate_limit" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_rate_limit" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_rate_limit" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("TokenBucket", "SlidingWindowLimiter", "throttle"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
