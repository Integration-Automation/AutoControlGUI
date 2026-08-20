"""The recorder shaping every platform shares. No Qt, no real input, no OS.

Windows captures input with a low-level hook and macOS with a Quartz event
tap, but everything after the capture is one implementation — the queue the
executor is handed, the timeline a replay consumes, and the mouse-only /
keyboard-only filters. This exercises that shared half on any platform, so a
change to it cannot be merged on the strength of a Windows-only run.
"""
from queue import Queue

import pytest

from je_auto_control.utils.input_macro.recorder_base import (
    ALL_KINDS, InputRecorder, event_kind, legacy_action_queue, timeline,
)


def _events():
    """A press, a release, and a scroll — the three things replay needs."""
    return [
        {"op": "key_down", "vk": 65, "time": 10.0},
        {"op": "key_up", "vk": 65, "time": 10.25},
        {"op": "scroll", "delta": -3, "x": 5, "y": 6, "time": 10.75},
    ]


class _FakeHook:
    """Stands in for Win32InputHook / OSXInputTap: the same two methods."""

    def __init__(self, events):
        self._events = events
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True
        return list(self._events)


class _FakeRecorder(InputRecorder):
    def __init__(self, events):
        super().__init__()
        self._events = events
        self.hooks = []

    def new_hook(self):
        hook = _FakeHook(self._events)
        self.hooks.append(hook)
        return hook


# --- timeline -------------------------------------------------------------

def test_timeline_turns_timestamps_into_gaps():
    # Without the gaps every step replays at once and no real interface keeps
    # up: the window that was supposed to open has not opened yet.
    out = timeline(_events())
    assert [event["delta_ms"] for event in out] == [0, 250, 500]
    assert "time" not in out[0]


def test_timeline_keeps_releases_and_wheel():
    # A press-only recording cannot tell a drag from a click, and loses
    # scrolling entirely.
    out = timeline(_events())
    assert [event["op"] for event in out] == ["key_down", "key_up", "scroll"]
    assert out[2]["delta"] == -3


def test_timeline_of_nothing_is_empty():
    assert timeline([]) == []


def test_timeline_never_reports_a_negative_gap():
    # Monotonic time should not go backwards, but a clamped gap beats a replay
    # that tries to sleep a negative amount.
    out = timeline([{"op": "key_down", "vk": 1, "time": 5.0},
                    {"op": "key_up", "vk": 1, "time": 4.0}])
    assert out[1]["delta_ms"] == 0


def test_timeline_feeds_replay_timeline_unchanged():
    # The two halves are only useful together, so pin that the shape one emits
    # is the shape the other consumes.
    from je_auto_control.utils.input_macro import replay_timeline

    played = []
    count = replay_timeline(timeline(_events()), sink=played.append,
                            sleep=lambda _seconds: None)
    assert count == 3
    assert [event["op"] for event in played] == [
        "key_down", "key_up", "scroll"]


def test_the_default_replay_sink_knows_every_op_a_recorder_emits():
    # These two vocabularies used to be disjoint: the recorder emitted
    # key_down / mouse_up / scroll and the sink table held press / click /
    # key, so feeding stop_record_timeline() to replay_timeline() — the
    # pipeline the docstrings and the MCP tool both prescribe — matched
    # nothing, replayed an empty session, and still reported every event as
    # played.
    from je_auto_control.utils.input_macro.input_macro import _SINKS

    emitted = {"key_down", "key_up", "mouse_down", "mouse_up", "scroll"}
    assert emitted <= set(_SINKS), sorted(emitted - set(_SINKS))


def test_replaying_a_recording_drives_the_matching_input_calls(monkeypatch):
    # Through the real default sink, with only the input calls themselves
    # faked — so the op-to-call routing is what is being exercised.
    from je_auto_control.utils.input_macro import replay_timeline

    calls = []
    monkeypatch.setattr(
        "je_auto_control.wrapper.auto_control_keyboard.press_keyboard_key",
        lambda key, *a, **k: calls.append(("press_key", key)))
    monkeypatch.setattr(
        "je_auto_control.wrapper.auto_control_keyboard.release_keyboard_key",
        lambda key, *a, **k: calls.append(("release_key", key)))
    monkeypatch.setattr(
        "je_auto_control.wrapper.auto_control_mouse.press_mouse",
        lambda button, x, y: calls.append(("press_mouse", button, x, y)))
    monkeypatch.setattr(
        "je_auto_control.wrapper.auto_control_mouse.release_mouse",
        lambda button, x, y: calls.append(("release_mouse", button, x, y)))

    replay_timeline(timeline([
        {"op": "key_down", "vk": 65, "time": 1.0},
        {"op": "key_up", "vk": 65, "time": 1.1},
        {"op": "mouse_down", "button": "right", "x": 1, "y": 2, "time": 1.2},
        {"op": "mouse_up", "button": "right", "x": 1, "y": 2, "time": 1.3},
    ]), sleep=lambda _seconds: None)
    assert calls == [
        ("press_key", 65), ("release_key", 65),
        # "right" as the recorder writes it, "mouse_right" as the input API
        # names it — a mismatch here presses the wrong button silently.
        ("press_mouse", "mouse_right", 1, 2),
        ("release_mouse", "mouse_right", 1, 2)]


def test_the_recorders_wheel_delta_is_not_dropped_by_the_sink(monkeypatch):
    # The DSL calls it `value` and the recorder calls it `delta`; reading only
    # `value` fell back to the default of 1, so a three-notch scroll down
    # replayed as a single notch in the other direction.
    from je_auto_control.utils.input_macro.input_macro import _sink_scroll

    asked = []
    monkeypatch.setattr(
        "je_auto_control.wrapper.auto_control_mouse.mouse_scroll",
        lambda value, *a, **k: asked.append(value))
    _sink_scroll({"op": "scroll", "delta": -3})
    _sink_scroll({"op": "scroll", "value": 7})
    assert asked == [-3, 7]


# --- the legacy queue -----------------------------------------------------

def test_legacy_queue_is_presses_only_as_executor_commands():
    queue = legacy_action_queue([
        {"op": "key_down", "vk": 65},
        {"op": "key_up", "vk": 65},
        {"op": "mouse_down", "button": "left", "x": 7, "y": 8},
        {"op": "mouse_up", "button": "left", "x": 7, "y": 8},
        {"op": "mouse_down", "button": "right", "x": 1, "y": 2},
        {"op": "mouse_down", "button": "middle", "x": 3, "y": 4},
    ])
    assert list(queue.queue) == [
        ("AC_type_keyboard", 65), ("AC_mouse_left", 7, 8),
        ("AC_mouse_right", 1, 2), ("AC_mouse_middle", 3, 4)]


def test_legacy_queue_drops_a_button_it_has_no_command_for():
    # An unknown button must not become a malformed action the executor then
    # rejects at replay time, far from where it was recorded.
    queue = legacy_action_queue([
        {"op": "mouse_down", "button": "x1", "x": 1, "y": 2}])
    assert list(queue.queue) == []


def test_legacy_queue_ignores_the_wheel():
    # stop_record() has never carried scrolling; stop_record_timeline() does.
    assert list(legacy_action_queue(
        [{"op": "scroll", "delta": 1, "x": 0, "y": 0}]).queue) == []


# --- kinds ----------------------------------------------------------------

@pytest.mark.parametrize("op, kind", [
    ("key_down", "keyboard"), ("key_up", "keyboard"),
    ("mouse_down", "mouse"), ("mouse_up", "mouse"), ("scroll", "mouse"),
])
def test_every_op_is_classified(op, kind):
    assert event_kind({"op": op}) == kind


def test_an_unknown_op_counts_as_mouse_rather_than_vanishing():
    # It is recorded by a backend that knows what it is; dropping it silently
    # would be worse than filing it under the broader of the two kinds.
    assert event_kind({"op": "gesture"}) == "mouse"
    assert ALL_KINDS == ("keyboard", "mouse")


# --- the recorder surface -------------------------------------------------

def test_record_then_stop_returns_the_legacy_queue():
    recorder = _FakeRecorder(_events())
    recorder.record()
    assert recorder.hooks[0].started
    queue = recorder.stop_record()
    assert isinstance(queue, Queue)
    assert list(queue.queue) == [("AC_type_keyboard", 65)]
    assert recorder.result_queue is queue
    assert recorder.record_queue is None


def test_timeline_stop_returns_everything():
    recorder = _FakeRecorder(_events())
    recorder.record()
    out = recorder.stop_record_timeline()
    assert [event["op"] for event in out] == ["key_down", "key_up", "scroll"]


def test_keyboard_only_recording_drops_mouse_events():
    recorder = _FakeRecorder([
        {"op": "key_down", "vk": 65, "time": 1.0},
        {"op": "mouse_down", "button": "left", "x": 1, "y": 2, "time": 1.1},
    ])
    recorder.record_keyboard()
    assert [e["op"] for e in recorder.stop_record_timeline()] == ["key_down"]


def test_mouse_only_recording_drops_key_events():
    recorder = _FakeRecorder([
        {"op": "key_down", "vk": 65, "time": 1.0},
        {"op": "scroll", "delta": 1, "time": 1.1},
    ])
    recorder.record_mouse()
    assert [e["op"] for e in recorder.stop_record_timeline()] == ["scroll"]


def test_mouse_only_stop_variant_also_filters():
    recorder = _FakeRecorder([
        {"op": "key_down", "vk": 65, "time": 1.0},
        {"op": "mouse_down", "button": "left", "x": 1, "y": 2, "time": 1.1},
    ])
    recorder.record_mouse()
    assert list(recorder.stop_record_mouse().queue) == [("AC_mouse_left", 1, 2)]


def test_keyboard_only_stop_variant_also_filters():
    recorder = _FakeRecorder([
        {"op": "key_down", "vk": 65, "time": 1.0},
        {"op": "mouse_down", "button": "left", "x": 1, "y": 2, "time": 1.1},
    ])
    recorder.record_keyboard()
    assert list(recorder.stop_record_keyboard().queue) == [
        ("AC_type_keyboard", 65)]


def test_stopping_without_recording_is_not_an_error():
    assert _FakeRecorder([]).stop_record_timeline() == []
    assert list(_FakeRecorder([]).stop_record().queue) == []


def test_a_second_stop_does_not_reuse_the_finished_hook():
    # The hook is dropped on stop, so a stray second stop returns nothing
    # rather than replaying the previous session's events.
    recorder = _FakeRecorder(_events())
    recorder.record()
    recorder.stop_record()
    assert recorder.stop_record_timeline() == []


def test_each_recording_gets_a_fresh_hook():
    # Reusing a stopped hook is how a second recording comes back with the
    # first one's events appended to it.
    recorder = _FakeRecorder(_events())
    recorder.record()
    recorder.stop_record()
    recorder.record()
    assert len(recorder.hooks) == 2
    assert recorder.hooks[0] is not recorder.hooks[1]


def test_a_backend_must_supply_a_hook():
    with pytest.raises(NotImplementedError):
        InputRecorder().record()
