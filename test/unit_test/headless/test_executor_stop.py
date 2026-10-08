"""A running action list can be stopped from another thread; nothing changes without a token.

Every command here is a fake registered on a private ``Executor``: no test
touches the mouse, the keyboard or the screen.
"""
import threading
import time

import pytest

import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor import run_control
from je_auto_control.utils.executor.action_executor import Executor, execute_action_with_vars
from je_auto_control.utils.executor.run_control import (
    ExecutionStopped, StopToken, active_executions, current_stop_token,
    stop_execution, stoppable_run,
)

_WAIT = 10.0


class _Fakes:
    """An executor whose only side effects are entries in ``calls``."""

    def __init__(self) -> None:
        self.calls: list = []
        self.entered = threading.Event()
        self.executor = Executor()
        self.executor.event_dict.update({
            "AC_fake": self._fake,
            "AC_fake_fail": self._fail,
            "AC_fake_mark": self._mark,
            "AC_press_keyboard_key": lambda keycode: self.calls.append(("press", keycode)),
            "AC_release_keyboard_key": lambda keycode: self.calls.append(("release", keycode)),
            "AC_press_mouse": lambda mouse_keycode: self.calls.append(("mouse_down", mouse_keycode)),
        })

    def _fake(self, tag: str = "x") -> str:
        self.calls.append(tag)
        return tag

    def _mark(self) -> None:
        self.calls.append("marked")
        self.entered.set()

    def _fail(self) -> None:
        raise AutoControlException("boom")


@pytest.fixture()
def fakes() -> _Fakes:
    return _Fakes()


def _run_in_thread(fakes: _Fakes, actions: list, token: StopToken, **kwargs):
    outcome: dict = {}

    def target() -> None:
        try:
            with stoppable_run(token=token):
                outcome["result"] = fakes.executor.execute_action(actions, **kwargs)
        except BaseException as error:  # noqa: BLE001  # reason: handed to the asserting thread
            outcome["error"] = error

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, outcome


def test_without_a_token_nothing_changes(fakes):
    record = fakes.executor.execute_action([["AC_fake", {"tag": "a"}], ["AC_sleep", {"seconds": 0}]])
    assert list(record.values()) == ["a", None]
    assert current_stop_token() is None
    assert active_executions() == []
    assert stop_execution() == 0


def test_sleep_outside_a_run_is_plain_time_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(time, "sleep", slept.append)
    run_control.pause(0.25)
    assert slept == [0.25]


def test_stop_wakes_a_sleep_and_skips_the_rest(fakes):
    token = StopToken("sleeper")
    started = time.monotonic()
    thread, outcome = _run_in_thread(
        fakes, [["AC_fake_mark"], ["AC_sleep", {"seconds": 60}], ["AC_fake", {"tag": "after"}]], token)
    assert fakes.entered.wait(_WAIT)
    assert stop_execution("sleeper", reason="user") == 1
    thread.join(_WAIT)
    assert not thread.is_alive()
    assert isinstance(outcome["error"], ExecutionStopped)
    assert outcome["error"].run_id == "sleeper" and outcome["error"].reason == "user"
    assert "after" not in fakes.calls
    assert time.monotonic() - started < 30
    assert active_executions() == []


def test_stop_is_not_recorded_and_not_caught_by_try_or_retry(fakes):
    token = StopToken()
    token.stop()
    actions = [["AC_try", {"body": [["AC_retry", {"body": [["AC_fake"]], "max_attempts": 3}]],
                          "catch": [["AC_fake", {"tag": "catch"}]],
                          "finally": [["AC_fake", {"tag": "finally"}]]}]]
    with pytest.raises(ExecutionStopped):
        with stoppable_run(token=token):
            fakes.executor.execute_action(actions)
    assert fakes.calls == []  # stopped before the first action: no try was entered


def test_try_finally_runs_when_the_body_is_stopped(fakes):
    token = StopToken("cleanup")
    actions = [["AC_try", {"body": [["AC_fake_mark"], ["AC_sleep", {"seconds": 60}]],
                          "catch": [["AC_fake", {"tag": "catch"}]],
                          "finally": [["AC_fake", {"tag": "finally"}]]}],
               ["AC_fake", {"tag": "after"}]]
    thread, outcome = _run_in_thread(fakes, actions, token)
    assert fakes.entered.wait(_WAIT)
    token.stop()
    thread.join(_WAIT)
    assert isinstance(outcome["error"], ExecutionStopped)
    assert fakes.calls == ["marked", "finally"]


def test_a_second_stop_interrupts_cleanup(fakes):
    token = StopToken("forced")
    cleaning = threading.Event()
    fakes.executor.event_dict["AC_fake_cleaning"] = cleaning.set
    actions = [["AC_try", {"body": [["AC_fake_mark"], ["AC_sleep", {"seconds": 60}]],
                          "finally": [["AC_fake_cleaning"], ["AC_loop", {"times": 100000, "body": []}],
                                      ["AC_fake", {"tag": "cleanup-end"}]]}]]
    # The loop above finishes on its own; the point is the shield: while it
    # holds, the cleanup is not interrupted by the first stop.
    thread, outcome = _run_in_thread(fakes, actions, token)
    assert fakes.entered.wait(_WAIT)
    assert token.stop() is True
    assert cleaning.wait(_WAIT)
    assert token.stop() is False
    thread.join(_WAIT)
    assert isinstance(outcome["error"], ExecutionStopped)
    assert token.forced


def test_stop_ends_a_loop_with_an_empty_body(fakes):
    token = StopToken()
    token_seen = []
    fakes.executor.event_dict["AC_fake_stop_self"] = lambda: token_seen.append(current_stop_token().stop())
    actions = [["AC_fake_stop_self"], ["AC_loop", {"times": 5, "body": []}]]
    with pytest.raises(ExecutionStopped):
        with stoppable_run(token=token):
            fakes.executor.execute_action(actions)
    assert token_seen == [True]


def test_stop_under_raise_on_error_false_still_raises(fakes):
    token = StopToken()
    fakes.executor.event_dict["AC_fake_stop_self"] = token.stop
    with pytest.raises(ExecutionStopped):
        with stoppable_run(token=token):
            fakes.executor.execute_action(
                [["AC_fake_fail"], ["AC_fake_stop_self"], ["AC_fake", {"tag": "never"}]],
                raise_on_error=False)
    assert "never" not in fakes.calls


def test_held_key_and_button_are_released_only_when_stopped(fakes, monkeypatch):
    released = []
    monkeypatch.setattr("je_auto_control.wrapper.auto_control_keyboard.release_keyboard_key",
                        lambda code: released.append(("key", code)))
    monkeypatch.setattr("je_auto_control.wrapper.auto_control_mouse.release_mouse",
                        lambda code: released.append(("mouse", code)))
    token = StopToken()
    fakes.executor.event_dict["AC_fake_stop_self"] = token.stop
    actions = [["AC_press_keyboard_key", {"keycode": "shift"}],
               ["AC_press_keyboard_key", ["a"]],
               ["AC_release_keyboard_key", {"keycode": "a"}],
               ["AC_press_mouse", {"mouse_keycode": "mouse_left"}],
               ["AC_fake_stop_self"], ["AC_fake"]]
    with pytest.raises(ExecutionStopped):
        with stoppable_run(token=token):
            fakes.executor.execute_action(actions)
    assert released == [("mouse", "mouse_left"), ("key", "shift")]

    released.clear()
    with stoppable_run():
        fakes.executor.execute_action([["AC_press_keyboard_key", {"keycode": "ctrl"}]])
    assert released == []  # a run that ends normally keeps its meaning


def test_a_failing_release_does_not_stop_the_others(monkeypatch):
    released = []

    def broken(_code):
        raise OSError("device gone")

    monkeypatch.setattr("je_auto_control.wrapper.auto_control_keyboard.release_keyboard_key", broken)
    monkeypatch.setattr("je_auto_control.wrapper.auto_control_mouse.release_mouse", released.append)
    token = StopToken()
    token.note_input("mouse", "mouse_left", True)
    token.note_input("key", "a", True)
    assert run_control.release_held_inputs(token) == 2
    assert released == ["mouse_left"]


def test_parallel_branches_stop_with_the_run(fakes):
    token = StopToken("par")
    actions = [["AC_parallel", {"branches": [
        [["AC_fake_mark"], ["AC_sleep", {"seconds": 60}], ["AC_fake", {"tag": "b0"}]],
        [["AC_sleep", {"seconds": 60}], ["AC_fake", {"tag": "b1"}]],
    ]}], ["AC_fake", {"tag": "after"}]]
    thread, outcome = _run_in_thread(fakes, actions, token)
    assert fakes.entered.wait(_WAIT)
    token.stop()
    thread.join(_WAIT)
    assert not thread.is_alive()
    assert isinstance(outcome["error"], ExecutionStopped)
    assert fakes.calls == ["marked"]


def test_swallowed_stop_is_raised_again_at_the_next_checkpoint(fakes):
    token = StopToken()

    def swallow() -> str:
        token.stop()
        try:
            run_control.checkpoint()
        except ExecutionStopped:
            return "swallowed"
        return "not raised"

    fakes.executor.event_dict["AC_fake_swallow"] = swallow
    with pytest.raises(ExecutionStopped):
        with stoppable_run(token=token):
            fakes.executor.execute_action([["AC_fake_swallow"], ["AC_fake", {"tag": "never"}]])
    assert fakes.calls == []


def test_run_stoppable_block_and_stop_command(fakes):
    listed = []
    fakes.executor.event_dict["AC_fake_list"] = lambda: listed.extend(active_executions())
    actions = [["AC_run_stoppable", {"run_id": "block", "body": [
        ["AC_fake_list"], ["AC_stop_execution", {"run_id": "block", "reason": "self"}],
        ["AC_fake", {"tag": "never"}]]}]]
    with pytest.raises(ExecutionStopped) as raised:
        fakes.executor.execute_action(actions)
    assert raised.value.run_id == "block"
    assert [row["run_id"] for row in listed] == ["block"]
    assert fakes.calls == []
    assert active_executions() == []


def test_stop_without_an_id_spares_the_caller(fakes):
    other = StopToken("other")
    with stoppable_run(token=other):
        pass  # registered and gone: nothing to stop
    blocker = threading.Event()
    thread_fakes = _Fakes()
    thread_fakes.executor.event_dict["AC_fake_block"] = lambda: blocker.wait(_WAIT)
    thread, outcome = _run_in_thread(thread_fakes, [["AC_fake_mark"], ["AC_fake_block"], ["AC_fake"]],
                                     StopToken("victim"))
    assert thread_fakes.entered.wait(_WAIT)
    with stoppable_run("caller"):
        record = fakes.executor.execute_action([["AC_stop_execution"], ["AC_fake", {"tag": "still"}]])
    assert list(record.values())[0] == {"stopped": 1}
    assert fakes.calls == ["still"]
    blocker.set()
    thread.join(_WAIT)
    assert isinstance(outcome["error"], ExecutionStopped)


def test_two_runs_cannot_share_a_name():
    with stoppable_run("dup"):
        with pytest.raises(AutoControlException):
            with stoppable_run("dup"):
                pass
    assert active_executions() == []


def test_nested_block_joins_the_enclosing_run():
    with stoppable_run("outer") as outer:
        with stoppable_run() as inner:
            assert inner is outer
        assert [row["run_id"] for row in active_executions()] == ["outer"]


def test_execute_action_with_vars_run_id(monkeypatch):
    seen = []
    monkeypatch.setitem(ac.executor.event_dict, "AC_fake_seen",
                        lambda: seen.append(current_stop_token().run_id))
    execute_action_with_vars([["AC_fake_seen"]], {}, run_id="named")
    assert seen == ["named"]
    assert active_executions() == []
    monkeypatch.setitem(ac.executor.event_dict, "AC_fake_none", lambda: seen.append(current_stop_token()))
    execute_action_with_vars([["AC_fake_none"]], {})
    assert seen[-1] is None


def test_facade_and_commands():
    for name in ("ExecutionStopped", "StopToken", "active_executions", "stop_execution", "stoppable_run"):
        assert name in ac.__all__ and hasattr(ac, name)
    assert issubclass(ac.ExecutionStopped, AutoControlException)
    assert {"AC_run_stoppable", "AC_stop_execution", "AC_list_executions"} <= ac.executor.known_commands()
