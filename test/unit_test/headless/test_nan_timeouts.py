"""A NaN timeout is refused instead of turning a poll loop into a hang.

``json`` accepts ``NaN``, so action files and MCP arguments can carry one.
``start + NaN`` is NaN and ``clock() >= NaN`` is never true: every
``while True`` poll loop below used to run forever. Each call runs in a
thread with a bound, so a regression fails here instead of hanging the suite.
"""
import math
import threading

import pytest

from je_auto_control.utils.app_idle.app_idle import wait_until_app_idle
from je_auto_control.utils.expect_poll.expect_poll import expect_poll
from je_auto_control.utils.ime_state.ime_state import wait_for_composition_commit
from je_auto_control.utils.lock_session.lock_session import wait_for_unlock
from je_auto_control.utils.smart_waits import waits
from je_auto_control.utils.timeouts import deadline_after

NAN = float("nan")


def _outcome(call):
    """Run ``call`` with a bound; return the exception it raised, or 'hang'."""
    box = {}

    def _run():
        try:
            box["value"] = call()
        except Exception as error:  # noqa: BLE001  # reason: the outcome is the assertion
            box["error"] = error

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(3.0)
    if worker.is_alive():
        return "hang"
    return box.get("error", box.get("value"))


def test_the_helper_refuses_nan_and_keeps_other_values():
    with pytest.raises(ValueError, match="timeout_s"):
        deadline_after(0.0, NAN, "timeout_s")
    assert deadline_after(10.0, "2.5") == 12.5
    assert deadline_after(10.0, -1) == 9.0
    assert math.isinf(deadline_after(0.0, float("inf")))


@pytest.mark.parametrize("call", [
    lambda: expect_poll(lambda: 0, lambda _v: False, timeout_s=NAN, interval_s=0.01,
                        sleep=lambda _s: None),
    lambda: wait_until_app_idle(timeout_s=NAN, interval_s=0.01,
                                busy_probe=lambda: True, sleep=lambda _s: None),
    lambda: wait_for_composition_commit(reader=lambda: True, timeout_s=NAN,
                                        interval_s=0.01, sleep=lambda _s: None),
    lambda: wait_for_unlock(probe=lambda: True, timeout_s=NAN, interval_s=0.01,
                            sleep=lambda _s: None),
], ids=["expect_poll", "app_idle", "ime_state", "lock_session"])
def test_a_nan_timeout_is_refused_rather_than_polled_forever(call):
    assert isinstance(_outcome(call), ValueError)


def test_a_nan_stable_window_is_refused():
    with pytest.raises(ValueError):
        waits.wait_until_file("nope", timeout_s=1.0, stable_for_s=NAN)


def test_ac_wait_image_refuses_a_nan_timeout(monkeypatch):
    from je_auto_control.utils.executor import flow_control
    monkeypatch.setattr(flow_control, "_image_present", lambda *_a: False)
    monkeypatch.setattr(flow_control.time, "sleep", lambda _s: None)
    outcome = _outcome(lambda: flow_control.exec_wait_image(
        None, {"image": "x.png", "timeout": NAN, "poll": 0.01}))
    assert isinstance(outcome, ValueError)
