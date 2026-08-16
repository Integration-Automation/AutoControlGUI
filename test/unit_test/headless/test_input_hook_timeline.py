"""Headless tests for the recorder's replayable timeline. No Qt, no real input."""
import sys

import pytest

import je_auto_control as ac

if not sys.platform.startswith("win"):        # pragma: no cover
    pytest.skip("Windows recorder", allow_module_level=True)

from je_auto_control.windows.record.win32_input_hook import (  # noqa: E402
    timeline,
)
from je_auto_control.windows.record.win32_record import Win32Recorder  # noqa: E402


def _events():
    """A press, a release, and a scroll — the three things replay needs."""
    return [
        {"op": "key_down", "vk": 65, "time": 10.0},
        {"op": "key_up", "vk": 65, "time": 10.25},
        {"op": "scroll", "delta": -3, "x": 5, "y": 6, "time": 10.75},
    ]


def test_timeline_turns_timestamps_into_gaps():
    # Without the gaps every step replays at once and no real interface keeps up.
    out = timeline(_events())
    assert [event["delta_ms"] for event in out] == [0, 250, 500]
    assert "time" not in out[0]


def test_timeline_keeps_releases_and_wheel():
    # The whole point: a press-only recording cannot tell a drag from a click,
    # and loses scrolling entirely.
    out = timeline(_events())
    assert [event["op"] for event in out] == ["key_down", "key_up", "scroll"]
    assert out[2]["delta"] == -3


def test_timeline_of_nothing_is_empty():
    assert timeline([]) == []


def test_timeline_never_reports_a_negative_gap():
    # Monotonic time should not go backwards, but a clamped gap is better than
    # a replay that tries to sleep a negative amount.
    out = timeline([{"op": "key_down", "vk": 1, "time": 5.0},
                    {"op": "key_up", "vk": 1, "time": 4.0}])
    assert out[1]["delta_ms"] == 0


class _FakeHook:
    def __init__(self, events):
        self._events = events

    def start(self):
        pass

    def stop(self):
        return list(self._events)


def _recorder(monkeypatch, events):
    recorder = Win32Recorder()
    monkeypatch.setattr(
        "je_auto_control.windows.record.win32_record.Win32InputHook",
        lambda *a, **k: _FakeHook(events))
    return recorder


def test_legacy_stop_record_still_returns_press_only_commands(monkeypatch):
    # Existing callers feed this straight into the executor; it must not change.
    recorder = _recorder(monkeypatch, [
        {"op": "key_down", "vk": 65, "time": 1.0},
        {"op": "key_up", "vk": 65, "time": 1.1},
        {"op": "mouse_down", "button": "left", "x": 7, "y": 8, "time": 1.2},
        {"op": "mouse_up", "button": "left", "x": 7, "y": 8, "time": 1.3},
    ])
    recorder.record()
    assert list(recorder.stop_record().queue) == [
        ("AC_type_keyboard", 65), ("AC_mouse_left", 7, 8)]


def test_timeline_stop_returns_everything(monkeypatch):
    recorder = _recorder(monkeypatch, _events())
    recorder.record()
    out = recorder.stop_record_timeline()
    assert [event["op"] for event in out] == ["key_down", "key_up", "scroll"]


def test_keyboard_only_recording_drops_mouse_events(monkeypatch):
    recorder = _recorder(monkeypatch, [
        {"op": "key_down", "vk": 65, "time": 1.0},
        {"op": "mouse_down", "button": "left", "x": 1, "y": 2, "time": 1.1},
    ])
    recorder.record_keyboard()
    assert [e["op"] for e in recorder.stop_record_timeline()] == ["key_down"]


def test_mouse_only_recording_drops_key_events(monkeypatch):
    recorder = _recorder(monkeypatch, [
        {"op": "key_down", "vk": 65, "time": 1.0},
        {"op": "scroll", "delta": 1, "time": 1.1},
    ])
    recorder.record_mouse()
    assert [e["op"] for e in recorder.stop_record_timeline()] == ["scroll"]


def test_stopping_without_recording_is_not_an_error():
    assert Win32Recorder().stop_record_timeline() == []


# --- hook decoding --------------------------------------------------------
#
# Driven by handing the callbacks fabricated structures, so it needs no real
# input and no particular window in front. That matters here: a game with
# anti-cheat in the foreground blocks both injected input and low-level hooks,
# which makes any live test of this silently return nothing.

class _FakeUser32:
    @staticmethod
    def CallNextHookEx(*_args):       # noqa: N802 (Win32 naming)
        return 0


def _hook():
    from je_auto_control.windows.record.win32_input_hook import Win32InputHook
    return Win32InputHook()


def _key_param(vk):
    import ctypes
    from je_auto_control.windows.record import win32_input_hook as hook
    data = hook._KBDLLHOOKSTRUCT(vkCode=vk)
    return ctypes.cast(ctypes.pointer(data), ctypes.c_void_p).value, data


def _mouse_param(x, y, mouse_data=0):
    import ctypes
    from ctypes import wintypes
    from je_auto_control.windows.record import win32_input_hook as hook
    data = hook._MSLLHOOKSTRUCT(pt=wintypes.POINT(x, y), mouseData=mouse_data)
    return ctypes.cast(ctypes.pointer(data), ctypes.c_void_p).value, data


def test_hook_records_key_press_and_release():
    recorder = _hook()
    proc = recorder._keyboard_proc(_FakeUser32)
    param, _keep = _key_param(65)
    proc(0, 0x0100, param)            # WM_KEYDOWN
    proc(0, 0x0101, param)            # WM_KEYUP
    assert [e["op"] for e in recorder.events] == ["key_down", "key_up"]
    assert recorder.events[0]["vk"] == 65
    assert all("time" in e for e in recorder.events)


def test_hook_records_system_keys_too():
    # Alt combinations arrive as WM_SYSKEYDOWN, not WM_KEYDOWN.
    recorder = _hook()
    proc = recorder._keyboard_proc(_FakeUser32)
    param, _keep = _key_param(0x12)
    proc(0, 0x0104, param)
    assert [e["op"] for e in recorder.events] == ["key_down"]


def test_hook_records_button_release_not_just_press():
    # Without the release a drag is indistinguishable from a click.
    recorder = _hook()
    proc = recorder._mouse_proc(_FakeUser32)
    down, _a = _mouse_param(10, 20)
    up, _b = _mouse_param(90, 60)
    proc(0, 0x0201, down)             # WM_LBUTTONDOWN
    proc(0, 0x0202, up)               # WM_LBUTTONUP
    assert [(e["op"], e["x"], e["y"]) for e in recorder.events] == [
        ("mouse_down", 10, 20), ("mouse_up", 90, 60)]


def test_hook_decodes_a_negative_wheel_delta():
    # mouseData's high word is a *signed* notch count times 120; reading it
    # unsigned turns a scroll down into a scroll up by 65,536 notches.
    recorder = _hook()
    proc = recorder._mouse_proc(_FakeUser32)
    param, _keep = _mouse_param(5, 6, mouse_data=(-240 & 0xFFFF) << 16)
    proc(0, 0x020A, param)            # WM_MOUSEWHEEL
    assert recorder.events[0]["op"] == "scroll"
    assert recorder.events[0]["delta"] == -2


def test_hook_ignores_negative_codes_and_unknown_messages():
    recorder = _hook()
    proc = recorder._mouse_proc(_FakeUser32)
    param, _keep = _mouse_param(1, 2)
    proc(-1, 0x0201, param)           # must pass through untouched
    proc(0, 0x0200, param)            # WM_MOUSEMOVE: too noisy to record
    assert recorder.events == []


def test_hook_stops_itself_at_the_event_cap():
    # A forgotten recording must not grow without bound.
    recorder = _hook()
    recorder.max_events = 3
    proc = recorder._keyboard_proc(_FakeUser32)
    param, _keep = _key_param(65)
    for _ in range(10):
        proc(0, 0x0100, param)
    assert len(recorder.events) == 3


def test_wiring():
    assert "AC_stop_record_timeline" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_record_stop_timeline" in {t.name for t in build_default_tool_registry()}
    assert hasattr(ac, "stop_record_timeline")
    assert "stop_record_timeline" in ac.__all__
