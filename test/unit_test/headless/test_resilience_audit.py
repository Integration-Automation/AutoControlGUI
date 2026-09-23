"""Regression tests for the resilience-primitive defects of the 2026-09-23 audit.

Backoff overflowed instead of capping and ``RetryPolicy`` slept past
``max_backoff`` first; token buckets accepted negative / impossible requests;
the sliding window under-estimated its wait; ``Retry-After`` read asctime
dates as local time and crashed on ``²``; ``LoopGuard`` let a short pattern
hide a long one; NaN lease TTLs never expired; approval commands without a
``db`` forgot every request and an empty approver passed; re-created CAS keys
reused versions; an interrupted half-open trial jammed the breaker; and the
idempotency store raced and timed out long work. Clocks are fakes.
"""
import threading

import pytest

from je_auto_control.utils.bulkhead.bulkhead import parse_retry_after
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils import governance
from je_auto_control.utils.governance import ApprovalGate, CredentialBroker
from je_auto_control.utils.governance.credential_broker import CredentialBrokerError
from je_auto_control.utils.idempotency.idempotency import IdempotencyStore
from je_auto_control.utils.loop_guard.loop_guard import LoopGuard
from je_auto_control.utils.optimistic.optimistic import VersionConflict, VersionedStore
from je_auto_control.utils.rate_limit.rate_limit import SlidingWindowLimiter, TokenBucket
from je_auto_control.utils.resilience.resilience import CircuitBreaker, RetryPolicy
from je_auto_control.utils.retry_budget.retry_budget import backoff_delay


def test_backoff_caps_a_huge_attempt():
    assert backoff_delay(1100, base=0.1, max_delay=5.0, multiplier=2.0) == 5.0


def test_the_first_retry_sleep_respects_max_backoff():
    slept = []

    def fail():
        raise ValueError("x")

    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=3, backoff=10, max_backoff=1).run(fail, sleep=slept.append)
    assert slept == [1, 1]


@pytest.mark.parametrize("n", [-5, 0, 3])
def test_a_token_bucket_refuses_impossible_requests(n):
    bucket = TokenBucket(capacity=2, rate=1.0, clock=lambda: 0.0)
    with pytest.raises(AutoControlException):
        bucket.try_acquire(n)


def test_the_sliding_window_wait_is_long_enough():
    now = [0.0]
    limiter = SlidingWindowLimiter(2, 10.0, clock=lambda: now[0])
    assert limiter.try_acquire() and limiter.try_acquire()
    now[0] = 5.0
    wait = limiter.time_until_available()
    now[0] = 5.0 + wait - 0.5
    assert not limiter.try_acquire(), "the advised wait is not too long by much"
    now[0] = 5.0 + wait
    assert limiter.try_acquire(), "and not too short"


@pytest.mark.parametrize("value", ["Tue Jan  1 01:00:37 2030", "Tue, 01 Jan 2030 01:00:37 GMT"])
def test_retry_after_dates_are_gmt(value):
    import datetime
    now = datetime.datetime(2030, 1, 1, 1, 0, tzinfo=datetime.timezone.utc).timestamp()
    assert parse_retry_after({"Retry-After": value}, now=now) == 37.0


def test_retry_after_ignores_non_ascii_digits():
    assert parse_retry_after({"Retry-After": chr(0xB2)}) is None


def test_loop_guard_reports_the_longest_pattern():
    guard = LoopGuard()
    for index in range(15):
        guard.observe(f"step{index}", result_digest="same")
    verdict = guard.observe("step14", result_digest="same")
    assert (verdict.pattern, verdict.level) == ("no_op", "critical")


@pytest.mark.parametrize("ttl", [float("nan"), float("inf"), 0, -1])
def test_a_lease_needs_a_finite_positive_ttl(ttl):
    with pytest.raises(CredentialBrokerError):
        CredentialBroker(clock=lambda: 0.0).lease("db", ttl)


def test_approval_commands_share_a_gate_without_db():
    from je_auto_control.utils.executor.action_executor import (
        _approval_approve, _approval_request, _approval_status,
    )
    token = _approval_request("deploy", "alice")["token"]
    assert _approval_approve(token, "bob")["approved"] is True
    assert _approval_status(token) == {"status": "approved", "approved": True}
    assert governance.approval_gate() is governance.approval_gate()


@pytest.mark.parametrize("approver", ["", "   ", " alice "])
def test_an_anonymous_or_self_approval_is_refused(tmp_path, approver):
    gate = ApprovalGate(str(tmp_path / "a.json"))
    token = gate.request("deploy", "alice")
    assert gate.approve(token, approver) is False
    assert gate.status(token) == "pending"


def test_a_recreated_key_does_not_reuse_a_version():
    store = VersionedStore()
    stale = store.put("k", "old")
    store.delete("k")
    store.put("k", "new")
    with pytest.raises(VersionConflict):
        store.put("k", "stale write", expected_version=stale)


def test_an_interrupted_trial_does_not_jam_the_breaker():
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=10.0, clock=lambda: now[0])
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("down")))
    now[0] = 10.0

    def interrupted():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        breaker.call(interrupted)
    assert breaker.call(lambda: "ok") == "ok"
    assert breaker.state == "closed"


def test_idempotency_claims_are_atomic():
    gate = threading.Event()
    calls = []

    def slow_clock():
        calls.append(1)
        if len(calls) == 1:
            gate.wait(0.5)
        return 0.0

    store = IdempotencyStore(clock=slow_clock, ttl=60.0)
    results = []
    first = threading.Thread(target=lambda: results.append(store.begin("k")["status"]))
    first.start()
    second = threading.Thread(target=lambda: results.append(store.begin("k")["status"]))
    second.start()
    second.join(0.3)   # without the lock the duplicate finishes here, also as "new"
    gate.set()
    first.join(2)
    second.join(2)
    assert sorted(results) == ["in_progress", "new"]


def test_idempotency_ttl_runs_from_completion():
    now = [0.0]
    store = IdempotencyStore(clock=lambda: now[0], ttl=10.0)
    store.begin("k")
    now[0] = 9.0
    store.complete("k", {"r": 1})
    now[0] = 15.0
    assert store.begin("k") == {"status": "completed", "response": {"r": 1}}
