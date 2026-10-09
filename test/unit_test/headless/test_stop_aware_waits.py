"""A stop wakes every polling wait an ``AC_*`` command can reach.

Each wait here is given a probe that never succeeds, a timeout of a minute and
a poll interval of half a minute, and is run inside a stoppable run on a worker
thread. Before the fix they slept on ``time.sleep`` and returned only at their
own timeout; now the stop ends them within the join below. Every probe is a
fake: nothing reads the screen, a window list or the keyboard.
"""
import threading
import time
from typing import Any, Callable, Dict, List

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.executor import run_control
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.executor.run_control import (
    ExecutionStopped, StopToken, stoppable_run,
)

_JOIN_S = 10.0
_TIMEOUT_S = 60.0
_POLL_S = 30.0


def _stop_while_waiting(wait: Callable[[threading.Event], Any]) -> BaseException:
    """Run ``wait(started)`` in a stoppable run, stop it once it probed; return what it raised."""
    token = StopToken()
    started = threading.Event()
    outcome: Dict[str, Any] = {}

    def target() -> None:
        try:
            with stoppable_run(token=token):
                outcome["result"] = wait(started)
        except BaseException as error:  # noqa: BLE001  # reason: handed to the asserting thread
            outcome["error"] = error

    thread = threading.Thread(target=target, daemon=True)
    began = time.monotonic()
    thread.start()
    assert started.wait(_JOIN_S), "the wait never probed"
    token.stop("test")
    thread.join(_JOIN_S)
    assert not thread.is_alive(), "the wait slept through the stop"
    assert time.monotonic() - began < _POLL_S, "the wait ran to its own poll interval"
    assert "error" in outcome, f"the wait returned {outcome.get('result')!r} instead of stopping"
    return outcome["error"]


def _never(started: threading.Event, value: Any = False) -> Callable[..., Any]:
    def probe(*_args: Any, **_kwargs: Any) -> Any:
        started.set()
        return value
    return probe


def test_wait_for_window_is_woken(monkeypatch):
    from je_auto_control.wrapper import auto_control_window

    def wait(started):
        monkeypatch.setattr(auto_control_window, "find_window", _never(started, None))
        return auto_control_window.wait_for_window("nope", timeout=_TIMEOUT_S, poll=_POLL_S)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_ac_wait_window_is_woken_through_the_executor(monkeypatch):
    from je_auto_control.wrapper import auto_control_window
    executor = Executor()

    def wait(started):
        monkeypatch.setattr(auto_control_window, "find_window", _never(started, None))
        return executor.execute_action(
            [["AC_wait_window", {"title_substring": "nope", "timeout": _TIMEOUT_S, "poll": _POLL_S}]])

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_wait_for_text_is_woken(monkeypatch):
    from je_auto_control.utils.ocr import ocr_engine

    def wait(started):
        def missing(*_args, **_kwargs):
            started.set()
            raise AutoControlActionException("not on screen")
        monkeypatch.setattr(ocr_engine, "locate_text_center", missing)
        return ocr_engine.wait_for_text("nope", timeout=_TIMEOUT_S, poll=_POLL_S)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_smart_wait_until_gone_is_woken():
    from je_auto_control.utils.smart_waits.waits import wait_until_gone

    def wait(started):
        return wait_until_gone(_never(started, True), timeout_s=_TIMEOUT_S, poll_interval_s=_POLL_S)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_smart_wait_for_file_is_woken(tmp_path, monkeypatch):
    from je_auto_control.utils.smart_waits import waits
    real_monotonic = time.monotonic

    def wait(started):
        def clock() -> float:
            started.set()
            return real_monotonic()
        monkeypatch.setattr(waits.time, "monotonic", clock)
        return waits.wait_until_file(str(tmp_path / "never.txt"),
                                     timeout_s=_TIMEOUT_S, poll_interval_s=_POLL_S)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_expect_poll_is_woken():
    from je_auto_control.utils.expect_poll.expect_poll import expect_poll

    def wait(started):
        return expect_poll(_never(started, 0), lambda value: value == 1,
                           timeout_s=_TIMEOUT_S, interval_s=_POLL_S)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_assert_eventually_is_woken(monkeypatch):
    from je_auto_control.utils.assertion import combinators

    class _Failing:
        passed = False
        message = "no"

    def wait(started):
        monkeypatch.setattr(combinators, "run_assertion_spec", _never(started, _Failing()))
        return combinators.assert_eventually({"type": "fake"}, timeout=_TIMEOUT_S, interval=_POLL_S)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_wait_until_app_idle_is_woken():
    from je_auto_control.utils.app_idle.app_idle import wait_until_app_idle

    def wait(started):
        return wait_until_app_idle(busy_probe=_never(started, True),
                                   timeout_s=_TIMEOUT_S, interval_s=_POLL_S)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_wait_for_composition_commit_is_woken():
    from je_auto_control.utils.ime_state.ime_state import wait_for_composition_commit
    composing = {"open": True, "conversion": 0, "composition": "ni"}

    def wait(started):
        return wait_for_composition_commit(reader=_never(started, composing),
                                           timeout_s=_TIMEOUT_S, interval_s=_POLL_S)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


@pytest.mark.parametrize("name, locked", [("wait_for_unlock", True), ("wait_for_lock", False)])
def test_lock_waits_are_woken(name, locked):
    from je_auto_control.utils.lock_session.lock_session import wait_for_lock, wait_for_unlock
    waits = {"wait_for_unlock": wait_for_unlock, "wait_for_lock": wait_for_lock}

    def wait(started):
        return waits[name](probe=_never(started, locked),
                           timeout_s=_TIMEOUT_S, interval_s=_POLL_S)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_wait_actionable_is_woken():
    from je_auto_control.utils.actionability.actionability import GateConfig, wait_actionable

    def wait(started):
        return wait_actionable(_never(started, None),
                               config=GateConfig(timeout_s=_TIMEOUT_S, poll_interval_s=_POLL_S))

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_heal_verifier_is_woken(monkeypatch):
    from je_auto_control.utils.self_healing import verification

    def wait(started):
        monkeypatch.setattr(verification, "text_on_screen", _never(started, False))
        verify = verification.build_verifier(
            {"type": "text_present", "text": "Saved", "timeout_s": _TIMEOUT_S, "poll_s": _POLL_S})
        return verify(None)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_state_machine_timer_is_woken():
    from je_auto_control.utils.state_machine.engine import StateMachine
    spec = {"initial": "idle", "global_timeout_s": 120,
            "states": {"idle": {"on_enter": [["AC_fake_enter", {}]],
                                "transitions": [{"after": _TIMEOUT_S, "go_to": "done"}]},
                       "done": {"final": True}}}

    def wait(started):
        return StateMachine(spec, execute_action=lambda _action: started.set()).run()

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_retry_budget_backoff_is_woken():
    from je_auto_control.utils.retry_budget.retry_budget import RetryBudget, run_with_budget
    budget = RetryBudget(max_attempts=3, base_delay_s=_POLL_S, max_delay_s=_POLL_S,
                         jitter="none", exceptions=(ValueError,))

    def wait(started):
        def failing() -> None:
            started.set()
            raise ValueError("again")
        return run_with_budget(failing, budget)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_rate_limit_acquire_is_woken():
    from je_auto_control.utils.rate_limit.rate_limit import TokenBucket
    bucket = TokenBucket(rate=1.0 / _POLL_S, capacity=1.0)
    assert bucket.try_acquire(1.0)

    def wait(started):
        started.set()
        return bucket.acquire(1.0, timeout=_TIMEOUT_S)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_file_dialog_wait_is_woken(monkeypatch):
    from je_auto_control.utils.file_dialog.file_dialog import FileDialogDriver
    from je_auto_control.wrapper import window_backends

    class _Backend:
        def __init__(self, started: threading.Event) -> None:
            self._started = started

        def list_windows(self) -> list:
            self._started.set()
            return []

    def wait(started):
        monkeypatch.setattr(window_backends, "get_backend", lambda: _Backend(started))
        return FileDialogDriver().wait_window("Open", _TIMEOUT_S)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_hold_key_is_woken_and_lets_go_of_the_key():
    from je_auto_control.utils.key_hold.key_hold import hold_key
    events: List[Dict[str, Any]] = []

    def wait(started):
        def sink(event: Dict[str, Any]) -> None:
            events.append(event)
            started.set()
        return hold_key("a", _TIMEOUT_S, sink=sink)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)
    assert [event["op"] for event in events] == ["press", "release"]


def test_input_sequence_wait_is_woken_and_releases_what_it_holds():
    from je_auto_control.utils.input_macro.input_macro import run_sequence
    events: List[Dict[str, Any]] = []

    def wait(started):
        def sink(event: Dict[str, Any]) -> None:
            events.append(event)
            started.set()
        return run_sequence([{"op": "press", "key": "shift"},
                             {"op": "wait", "ms": _TIMEOUT_S * 1000}], sink=sink)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)
    assert [event["op"] for event in events] == ["press", "release"]


def test_wait_for_app_is_woken():
    from je_auto_control.wrapper import mobile_extensions
    from je_auto_control.wrapper.device_context import AppState

    class _Session:
        def __init__(self, started: threading.Event) -> None:
            self._started = started
            self.usable_checks = 0

        def app_state(self, _app_id: str) -> AppState:
            self._started.set()
            return AppState.BACKGROUND

        def wait_cancelled(self, timeout_s: float) -> bool:
            time.sleep(min(timeout_s, 0.05))
            return False

        def check_usable(self) -> None:
            self.usable_checks += 1

    def wait(started):
        return mobile_extensions.wait_for_app(_Session(started), "com.example", timeout_s=_TIMEOUT_S)

    assert isinstance(_stop_while_waiting(wait), ExecutionStopped)


def test_outside_a_stoppable_run_the_waits_still_sleep_on_time_sleep(monkeypatch):
    from je_auto_control.utils.expect_poll.expect_poll import expect_poll
    slept: List[float] = []
    monkeypatch.setattr(run_control.time, "sleep", slept.append)
    values = iter([0, 0, 1])
    result = expect_poll(lambda: next(values), lambda value: value == 1,
                         timeout_s=5.0, interval_s=0.01)
    assert result.ok
    assert result.attempts == 3
    assert slept == [0.01, 0.01]
    assert run_control.current_stop_token() is None


def test_a_wait_that_succeeds_inside_a_stoppable_run_returns_normally():
    from je_auto_control.utils.expect_poll.expect_poll import expect_poll
    values = iter([0, 1])
    with stoppable_run() as token:
        result = expect_poll(lambda: next(values), lambda value: value == 1,
                             timeout_s=5.0, interval_s=0.01)
    assert result.ok
    assert not token.stopped
