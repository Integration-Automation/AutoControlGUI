"""Audit round 3 regressions for modifier hold + key hold (findings 9, 10).

Both primitives must guarantee that keys they press are released even when a
press part-way through fails, a release fails, or the hold is interrupted.
"""
import pytest

from je_auto_control.utils.key_hold.key_hold import hold_key
from je_auto_control.utils.modifier_state.modifier_state import hold_modifiers


# --- Finding 9: hold_modifiers --------------------------------------

def test_hold_modifiers_releases_pressed_when_a_later_press_fails():
    events = []

    def sink(event):
        events.append((event["op"], event["key"]))
        if event["op"] == "press" and event["key"] == "shift":
            raise RuntimeError("second press failed")

    with pytest.raises(RuntimeError):
        with hold_modifiers(["ctrl", "shift"], sink=sink):
            pass

    # ctrl went down before shift's press failed, so ctrl must be released;
    # shift was never pressed, so it must never be released.
    assert ("press", "ctrl") in events
    assert ("release", "ctrl") in events
    assert ("release", "shift") not in events


def test_hold_modifiers_release_failure_does_not_skip_others():
    released = []

    def sink(event):
        if event["op"] == "release":
            released.append(event["key"])
            if event["key"] == "shift":
                raise RuntimeError("release failed")

    # Must not raise: a failing release is logged, not propagated, and the
    # remaining modifier is still released.
    with hold_modifiers(["ctrl", "shift"], sink=sink):
        pass

    assert "shift" in released  # reversed order releases shift first
    assert "ctrl" in released


def test_hold_modifiers_happy_path_release_reversed():
    events = []
    with hold_modifiers(["ctrl", "alt"],
                        sink=lambda e: events.append((e["op"], e["key"]))):
        pass
    assert events == [
        ("press", "ctrl"), ("press", "alt"),
        ("release", "alt"), ("release", "ctrl"),
    ]


# --- Finding 10: hold_key -------------------------------------------

def test_hold_key_releases_on_interrupt_during_wait():
    dispatched = []

    def _interrupt(_seconds):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        hold_key("a", 1.0,
                 sink=lambda e: dispatched.append((e["op"], e["key"])),
                 sleep=_interrupt)

    assert ("press", "a") in dispatched
    assert ("release", "a") in dispatched


def test_hold_key_retries_release_when_first_release_fails():
    calls = []

    def sink(event):
        calls.append((event["op"], event["key"]))
        if event["op"] == "release" and calls.count(("release", "a")) == 1:
            raise RuntimeError("first release failed")

    with pytest.raises(RuntimeError):
        hold_key("a", 0.01, sink=sink, sleep=lambda _s: None)

    # The finally block re-attempts the release the plan step failed to run.
    assert calls.count(("release", "a")) == 2


def test_hold_key_happy_path_single_release():
    calls = []
    hold_key("a", 0.01,
             sink=lambda e: calls.append((e["op"], e["key"])),
             sleep=lambda _s: None)
    assert calls == [("press", "a"), ("release", "a")]


def test_hold_key_autorepeat_has_no_dangling_release():
    ops = []
    hold_key("a", 1.0, rate_hz=2.0,
             sink=lambda e: ops.append(e["op"]),
             sleep=lambda _s: None)
    assert "press" not in ops
    assert "release" not in ops
    assert ops.count("key") >= 1
