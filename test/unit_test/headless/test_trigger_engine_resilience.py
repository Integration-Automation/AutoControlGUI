"""One bad trigger must never stop the trigger engine.

The engine polls every registered trigger on a single background thread. That
makes any escaping exception a poison pill: the thread dies, *every* trigger
silently stops firing, and the offender stays registered so a restart dies the
same way. Nothing logs a failure and the UI still lists the triggers as active.
"""
import threading
import time

import pytest

from je_auto_control.utils.triggers.trigger_engine import (
    CronTrigger, TriggerEngine, _TriggerBase,
)


class _RogueTrigger(_TriggerBase):
    """is_fired() reaches out to the screen/clock/filesystem — it can raise."""

    def is_fired(self) -> bool:
        raise RuntimeError("boom")


@pytest.fixture()
def engine():
    made = TriggerEngine(executor=lambda actions: None, tick_seconds=0.05)
    yield made
    made.stop()


def test_a_bad_cron_expression_is_rejected_at_construction():
    """Regression: parse_cron ran on the polling thread, not the caller.

    The Triggers tab passes its cron QLineEdit text straight to add(), so a
    typo used to register fine and then kill the engine on the next tick.
    """
    with pytest.raises(ValueError, match="cron"):
        CronTrigger(trigger_id="bad", script_path="b.json", cron="not a cron")


def test_a_valid_cron_still_constructs():
    trigger = CronTrigger(trigger_id="ok", script_path="s.json",
                          cron="*/5 * * * *")
    assert trigger.cron == "*/5 * * * *"


def test_a_trigger_whose_is_fired_raises_is_disabled_not_fatal(engine):
    """Regression: an exception from is_fired() killed the polling thread."""
    caught: list = []
    original = threading.excepthook
    threading.excepthook = lambda args: caught.append(
        type(args.exc_value).__name__)
    try:
        engine.add(_RogueTrigger(trigger_id="rogue", script_path="r.json",
                                 repeat=True))
        engine.start()
        time.sleep(0.4)

        assert engine._thread.is_alive(), "polling thread died"
        assert caught == []
        assert engine._triggers["rogue"].enabled is False, (
            "the offender should be disabled so it stops re-raising each tick"
        )
    finally:
        threading.excepthook = original


def test_a_trigger_pointing_at_a_missing_script_is_not_fatal(engine):
    """Regression: _fire caught only (OSError, ValueError, RuntimeError).

    read_action_json raises AutoControlJsonActionException, which is none of
    those — so merely renaming a trigger's script file killed the engine.
    """
    caught: list = []
    original = threading.excepthook
    threading.excepthook = lambda args: caught.append(
        type(args.exc_value).__name__)
    try:
        engine.add(CronTrigger(trigger_id="missing",
                               script_path="does-not-exist.json",
                               cron="* * * * *", repeat=True))
        engine.start()
        time.sleep(0.4)

        assert engine._thread.is_alive(), "polling thread died"
        assert caught == []
    finally:
        threading.excepthook = original


def test_a_healthy_trigger_keeps_firing_alongside_a_broken_one(engine):
    """The whole point: one poison pill must not take the others down."""
    fired: list = []
    engine._execute = lambda actions: fired.append(actions)
    engine.add(_RogueTrigger(trigger_id="rogue", script_path="r.json",
                             repeat=True))
    healthy = CronTrigger(trigger_id="healthy", script_path="h.json",
                          cron="* * * * *", repeat=True)
    engine.add(healthy)

    engine.start()
    time.sleep(0.4)

    assert engine._thread.is_alive()
    assert engine._triggers["rogue"].enabled is False
    assert engine._triggers["healthy"].enabled is True
