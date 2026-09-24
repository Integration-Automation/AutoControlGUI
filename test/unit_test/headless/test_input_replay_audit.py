"""Regression tests for the record / replay and input-helper defects of the 2026-09-23 audit.

Recorded presses, releases and scrolls replayed wherever the cursor was, a
recording's gaps were truncated, ``speed`` 0 slept for years, unknown ops were
skipped while reported as played, and a failing step left keys and mouse
buttons held down (``run_sequence``, ``tween_drag``, ``drag_path``). Windows
had no ``ctrl`` key name and the mouse tables no ``left``. Every path here
uses a recording sink or patched wrapper functions -- no real input.
"""
import sys

import pytest

from je_auto_control.utils.input_macro import input_macro
from je_auto_control.utils.input_macro.input_macro import replay_timeline, run_sequence
from je_auto_control.utils.input_macro.recorder_base import timeline
from je_auto_control.utils.mouse_path.mouse_path import drag_path
from je_auto_control.utils.tween_drag.tween_drag import tween_drag


@pytest.fixture
def wrapper_calls(monkeypatch):
    from je_auto_control.wrapper import auto_control_mouse
    calls = []
    monkeypatch.setattr(auto_control_mouse, "set_mouse_position",
                        lambda x, y: calls.append(("move", x, y)))
    monkeypatch.setattr(auto_control_mouse, "press_mouse",
                        lambda button, x=None, y=None: calls.append(("press", button)))
    monkeypatch.setattr(auto_control_mouse, "release_mouse",
                        lambda button, x=None, y=None: calls.append(("release", button)))
    monkeypatch.setattr(auto_control_mouse, "mouse_scroll",
                        lambda value, *args, **kwargs: calls.append(("scroll", value)))
    return calls


def test_a_recorded_drag_replays_at_its_positions(wrapper_calls):
    replay_timeline([{"op": "mouse_down", "button": "left", "x": 500, "y": 300, "delta_ms": 0},
                     {"op": "mouse_up", "button": "left", "x": 900, "y": 700, "delta_ms": 0}])
    assert wrapper_calls == [("move", 500, 300), ("press", "mouse_left"),
                             ("move", 900, 700), ("release", "mouse_left")]


def test_a_recorded_scroll_replays_at_its_position(wrapper_calls):
    replay_timeline([{"op": "scroll", "delta": -2, "x": 40, "y": 50}])
    assert wrapper_calls == [("move", 40, 50), ("scroll", -2)]


def test_recorded_gaps_add_up_to_the_recording():
    events = [{"op": "move", "time": index * 0.0079} for index in range(1001)]
    assert sum(event["delta_ms"] for event in timeline(events)) == 7900


@pytest.mark.parametrize("speed", [0, -1, float("nan")])
def test_replay_refuses_a_non_positive_speed(speed):
    with pytest.raises(ValueError):
        replay_timeline([{"op": "move", "delta_ms": 100}], speed=speed,
                        sink=lambda e: None, sleep=lambda s: None)


@pytest.mark.parametrize("call", [
    lambda: replay_timeline([{"op": "tpyo"}], sleep=lambda s: None),
    lambda: run_sequence([{"op": "presss", "key": "a"}]),
])
def test_an_unknown_op_raises(call):
    with pytest.raises(ValueError, match="unknown input op"):
        call()


def _failing_sink(fail_on):
    sent = []

    def sink(event):
        if event.get("key") == fail_on:
            raise RuntimeError("no such key")
        sent.append(event)
    return sink, sent


def test_run_sequence_releases_keys_held_when_a_step_fails():
    sink, sent = _failing_sink("bogus")
    with pytest.raises(RuntimeError):
        run_sequence([{"op": "press", "key": "shift"}, {"op": "key", "key": "bogus"},
                      {"op": "release", "key": "shift"}], sink=sink)
    assert sent == [{"op": "press", "key": "shift"}, {"op": "release", "key": "shift"}]


def test_replay_releases_recorded_keys_held_when_an_event_fails():
    sent = []

    def sink(event):
        if event["op"] == "move":
            raise OSError("display gone")
        sent.append(event)

    with pytest.raises(OSError):
        replay_timeline([{"op": "key_down", "vk": 16}, {"op": "move", "x": 1, "y": 1}],
                        sink=sink, sleep=lambda s: None)
    assert sent == [{"op": "key_down", "vk": 16}, {"op": "key_up", "vk": 16}]


@pytest.mark.parametrize("drag", [
    lambda sink: tween_drag((0, 0), (10, 10), steps=5, sink=sink),
    lambda sink: drag_path([(0, 0), (5, 5), (10, 10)], sink=sink),
])
def test_drags_release_the_button_when_a_move_fails(drag):
    sent = []

    def sink(event):
        sent.append(event["op"])
        if event["op"] == "move" and sent.count("move") == 3:
            raise OSError("cursor stuck")

    with pytest.raises(OSError):
        drag(sink)
    assert sent[0] == "press" and sent[-1] == "release"


def test_plain_mouse_button_names_resolve():
    from je_auto_control.wrapper.auto_control_mouse import mouse_preprocess
    from je_auto_control.wrapper.platform_wrapper import mouse_keys_table
    assert mouse_preprocess("left", 1, 2)[0] == mouse_keys_table["mouse_left"]


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows key table loads on Windows only")
def test_windows_knows_ctrl():
    from je_auto_control.wrapper import _platform_windows
    table = _platform_windows.keyboard_keys_table
    assert table["ctrl"] == table["control"]


def test_the_default_sink_table_is_unchanged():
    assert {"move", "click", "press", "release", "key_down", "mouse_up"} <= set(input_macro._SINKS)
