"""R3 regression: expect_poll clamps its sleep to the remaining time. No Qt.

A large interval_s could otherwise overshoot timeout_s by nearly a full
interval (and run an extra getter well past the deadline).
"""
from je_auto_control.utils.expect_poll import expect_poll, to_equal


def test_sleep_is_clamped_to_remaining_time():
    times = [0.0]
    sleeps = []

    def clock():
        return times[0]

    def sleep(seconds):
        sleeps.append(seconds)
        times[0] += seconds

    result = expect_poll(lambda: 1, to_equal(2), timeout_s=0.05,
                         interval_s=100.0, clock=clock, sleep=sleep)

    assert result.ok is False
    # No single sleep may exceed the time left, and the poll must not overshoot
    # the deadline. The old code slept the full 100s on the first miss.
    assert sleeps and max(sleeps) <= 0.05 + 1e-9
    assert times[0] <= 0.05 + 1e-9


def test_clamp_does_not_change_evenly_divided_timeline():
    # interval_s divides timeout_s evenly: clamping must not change attempts.
    times = [0.0]

    def clock():
        return times[0]

    def sleep(seconds):
        times[0] += seconds

    result = expect_poll(lambda: 0, to_equal(9), timeout_s=5.0,
                         interval_s=0.25, clock=clock, sleep=sleep)
    assert result.ok is False
    assert result.attempts == 21          # 20 sleeps + the first attempt
