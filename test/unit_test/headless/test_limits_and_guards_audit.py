"""Rate limiter, retry budget, loop guard and repair-plan defects (2026-09-24 audit).

NaN passed every ``<= 0`` validation: a NaN rate, capacity or window let
every request through (or spun a waiter at full CPU), and a NaN retry
deadline retried forever. ``LoopGuard.observe`` raced on the process-wide
guard, and a negative ``max_attempts`` still produced repair tactics.
"""
import threading

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.loop_guard.loop_guard import LoopGuard
from je_auto_control.utils.rate_limit.rate_limit import SlidingWindowLimiter, TokenBucket
from je_auto_control.utils.retry_budget.retry_budget import RetryBudget
from je_auto_control.utils.step_repair.step_repair import RepairPolicy, plan_repair

NAN, INF = float("nan"), float("inf")


@pytest.mark.parametrize("rate, capacity", [(NAN, 1), (1, NAN), (INF, 1), (1, INF), (0, 1)])
def test_a_token_bucket_needs_finite_positive_numbers(rate, capacity):
    with pytest.raises(AutoControlException):
        TokenBucket(rate, capacity)


@pytest.mark.parametrize("window_s", [NAN, INF, 0, -1])
def test_a_sliding_window_needs_a_finite_positive_window(window_s):
    with pytest.raises(AutoControlException):
        SlidingWindowLimiter(1, window_s)


def test_valid_limiters_still_build():
    TokenBucket(2.5, 3)
    SlidingWindowLimiter(5, 0.5)


def test_a_nan_retry_deadline_is_refused():
    with pytest.raises(ValueError):
        RetryBudget(deadline_s=NAN)
    assert RetryBudget(deadline_s=1.5).deadline_s == 1.5


def test_the_loop_guard_survives_concurrent_observers():
    guard = LoopGuard(window=50)
    errors = []
    start = threading.Barrier(4)

    def observe(worker):
        start.wait()
        try:
            for step in range(3000):
                guard.observe("click", {"worker": worker, "step": step % 3}, "digest")
        except RuntimeError as error:
            errors.append(error)

    threads = [threading.Thread(target=observe, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert errors == []


@pytest.mark.parametrize("max_attempts", [-1, -3, 0])
def test_no_repair_tactics_for_a_non_positive_budget(max_attempts):
    assert plan_repair("no_op", policy=RepairPolicy(max_attempts=max_attempts)) == []
