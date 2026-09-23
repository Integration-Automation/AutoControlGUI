"""Trigger engine, observer and callback-executor defects (2026-09-24 audit).

A trigger removed by an earlier trigger's script in the same pass still ran;
an infinite poll interval killed the poll thread; an observer rule raising
outside a narrow tuple (``NameError``, ``AssertionError``, a numpy truth
value) stopped every rule; and the callback executor let ``OSError`` escape
although it documents ``None``.
"""
import time

from je_auto_control.utils.callback.callback_function_executor import (
    callback_executor,
)
from je_auto_control.utils.observer.observer import ScreenObserver
from je_auto_control.utils.timeouts import MAX_POLL_INTERVAL_S, clamp_poll_interval
from je_auto_control.utils.triggers import trigger_engine as te


class _Always(te._TriggerBase):
    def is_fired(self):
        return True


def test_a_trigger_removed_mid_pass_does_not_run(monkeypatch):
    monkeypatch.setattr(te, "default_history_store", _NullHistory())
    ran = []
    engine = te.TriggerEngine(executor=lambda actions: ran.append(actions) or engine.remove("second"))
    monkeypatch.setattr(te, "read_executable_action_json", lambda path: [path])
    engine.add(_Always(trigger_id="first", script_path="first.json", repeat=True))
    engine.add(_Always(trigger_id="second", script_path="second.json", repeat=True))
    engine._poll_once()
    assert ran == [["first.json"]]


class _NullHistory:
    def start_run(self, *_args, **_kwargs):
        return 1

    def finish_run(self, *_args, **_kwargs):
        pass


def test_poll_intervals_are_clamped():
    assert clamp_poll_interval(float("inf")) == MAX_POLL_INTERVAL_S
    assert clamp_poll_interval(float("nan")) == 0.05
    assert clamp_poll_interval(0) == 0.05
    assert clamp_poll_interval(2.5) == 2.5
    assert te.TriggerEngine(executor=lambda _a: None, tick_seconds=float("inf"))._tick == MAX_POLL_INTERVAL_S
    assert ScreenObserver(poll_interval_s=float("inf"))._poll == MAX_POLL_INTERVAL_S


def test_one_broken_rule_does_not_stop_the_others():
    observer = ScreenObserver(poll_interval_s=0.05)
    hits = []

    def flipping():
        state = {"n": 0}

        def predicate():
            state["n"] += 1
            return state["n"] % 2
        return predicate

    def broken():
        raise NameError("typo_in_user_predicate")

    def failing_handler(_event, _value):
        raise AssertionError("handler assertion")

    class _Ambiguous:
        def __bool__(self):
            raise ValueError("truth value is ambiguous")

    observer.add("good", flipping(), lambda event, _value: hits.append(event))
    observer.add("bad-predicate", broken, lambda *_a: None)
    observer.add("bad-handler", flipping(), failing_handler)
    observer.add("ambiguous", _Ambiguous, lambda *_a: None)
    observer.start()
    try:
        deadline = time.monotonic() + 5
        while len(hits) < 3 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert observer.running
    finally:
        observer.stop()
    assert len(hits) >= 3


def test_a_trigger_oserror_is_the_documented_none(tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("x", encoding="utf-8")
    assert callback_executor.callback_function(
        "AC_create_project", lambda: None, project_path=str(blocker / "proj")) is None


def test_a_failing_callback_keeps_the_trigger_result():
    callback_executor.event_dict["AC__audit_answer"] = lambda: 42
    try:
        def callback():
            raise OSError("disk gone")
        assert callback_executor.callback_function("AC__audit_answer", callback) == 42
    finally:
        callback_executor.event_dict.pop("AC__audit_answer", None)
