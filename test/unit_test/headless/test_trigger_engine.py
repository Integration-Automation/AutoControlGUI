"""Tests for the poll-based trigger engine (FilePath + engine plumbing)."""
import json
import os
import time

from je_auto_control.utils.triggers.trigger_engine import (
    AllOfTrigger, AnyOfTrigger, FilePathTrigger, SequenceTrigger,
    TriggerEngine,
)


class _Flag:
    """Minimal child trigger whose firing is toggled by ``value`` (duck-typed)."""

    def __init__(self, value: bool = False) -> None:
        self.value = value

    def is_fired(self) -> bool:
        return self.value


def _write_actions(path, actions):
    path.write_text(json.dumps(actions), encoding="utf-8")
    return str(path)


def test_file_path_trigger_fires_on_mtime_change(tmp_path):
    watched = tmp_path / "sentinel.txt"
    watched.write_text("v1", encoding="utf-8")
    trigger = FilePathTrigger(
        trigger_id="f1", script_path="unused.json",
        watch_path=str(watched),
    )
    assert trigger.is_fired() is False  # baseline capture
    # Force a mtime change by bumping the file's mtime forward.
    later = watched.stat().st_mtime + 2
    os.utime(str(watched), (later, later))
    assert trigger.is_fired() is True
    # Subsequent call with no change does not re-fire.
    assert trigger.is_fired() is False


def test_engine_runs_trigger_once_when_non_repeat(tmp_path):
    script_path = _write_actions(tmp_path / "s.json", [["AC_noop"]])
    watched = tmp_path / "w.txt"
    watched.write_text("v1", encoding="utf-8")

    calls = []
    engine = TriggerEngine(
        executor=lambda actions: calls.append(actions),
        tick_seconds=0.05,
    )
    trigger = FilePathTrigger(
        trigger_id="", script_path=script_path,
        watch_path=str(watched), repeat=False,
    )
    engine.add(trigger)
    engine.start()
    try:
        # First poll captures baseline; bump mtime to force firing.
        time.sleep(0.1)
        later = watched.stat().st_mtime + 2
        os.utime(str(watched), (later, later))
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and engine.list_triggers() != []:
            time.sleep(0.05)
            if calls:
                break
    finally:
        engine.stop(timeout=1.0)
    assert calls, "executor should have been invoked"
    # Non-repeating trigger should be removed after firing.
    assert all(t.trigger_id != trigger.trigger_id for t in engine.list_triggers())


def test_engine_set_enabled_suppresses_polling(tmp_path):
    watched = tmp_path / "w.txt"
    watched.write_text("v1", encoding="utf-8")
    engine = TriggerEngine(executor=lambda actions: None, tick_seconds=0.05)
    trigger = FilePathTrigger(
        trigger_id="t1", script_path="unused.json",
        watch_path=str(watched), repeat=True,
    )
    engine.add(trigger)
    assert engine.set_enabled("t1", False) is True
    assert engine.list_triggers()[0].enabled is False
    assert engine.set_enabled("missing", True) is False


def test_engine_remove_returns_false_for_missing():
    engine = TriggerEngine(executor=lambda actions: None)
    assert engine.remove("nope") is False


def test_all_of_trigger_requires_every_child():
    a, b = _Flag(True), _Flag(False)
    trig = AllOfTrigger(trigger_id="all", script_path="s.json", children=[a, b])
    assert trig.is_fired() is False
    b.value = True
    assert trig.is_fired() is True


def test_all_of_trigger_with_no_children_never_fires():
    trig = AllOfTrigger(trigger_id="all", script_path="s.json", children=[])
    assert trig.is_fired() is False


def test_any_of_trigger_fires_when_one_child_holds():
    a, b = _Flag(False), _Flag(False)
    trig = AnyOfTrigger(trigger_id="any", script_path="s.json", children=[a, b])
    assert trig.is_fired() is False
    b.value = True
    assert trig.is_fired() is True


def test_sequence_trigger_requires_ordered_firing():
    a, b = _Flag(False), _Flag(False)
    trig = SequenceTrigger(trigger_id="seq", script_path="s.json",
                           children=[a, b])
    assert trig.is_fired() is False
    # The later child firing first must not advance the sequence.
    b.value = True
    assert trig.is_fired() is False
    # First condition holds → advance one step (not complete yet).
    a.value = True
    assert trig.is_fired() is False
    # Second condition completes the sequence and it resets.
    assert trig.is_fired() is True
    # Re-arms: one poll per step again.
    assert trig.is_fired() is False
    assert trig.is_fired() is True
