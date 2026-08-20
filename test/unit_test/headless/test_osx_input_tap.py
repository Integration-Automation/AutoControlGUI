"""The macOS event tap, driven by real CGEvents. Runs on macOS CI only.

These build genuine Quartz events with ``CGEventCreate*`` and hand them to the
decoder directly, which needs **no** Accessibility grant and no user at the
keyboard — only creating a live *tap* needs the grant, and that is verified
separately by ``test/verify/macos_verify.py`` on a real runner.

The regression being guarded is why macOS shipped without a recorder at all:
the old listener built an ``NSApplication`` at import and stopped recording
via ``AppHelper.runEventLoop()``, a loop that never returns. Both would have
landed on the path of ``import je_auto_control``.
"""
import sys
import threading

import pytest

if sys.platform != "darwin":                    # pragma: no cover
    pytest.skip("macOS event tap", allow_module_level=True)

import Quartz                                                    # noqa: E402

from je_auto_control.osx.listener import osx_listener             # noqa: E402
from je_auto_control.osx.listener.osx_listener import OSXInputTap  # noqa: E402
from je_auto_control.osx.record.osx_record import OSXRecorder      # noqa: E402
from je_auto_control.utils.exception.exceptions import (           # noqa: E402
    AutoControlRecordException,
)


def _key_event(keycode, down):
    return Quartz.CGEventCreateKeyboardEvent(None, keycode, down)


def _mouse_event(event_type, x, y, button=0):
    return Quartz.CGEventCreateMouseEvent(None, event_type, (x, y), button)


def _decode(events):
    """Feed ``(type, event)`` pairs to a fresh tap and return what it kept."""
    tap = OSXInputTap()
    for event_type, event in events:
        tap.decode(event_type, event)
    return tap.events


# --- the regression that kept the recorder unwired ------------------------

def test_importing_the_listener_builds_no_application():
    # The old module ran NSApplication.sharedApplication() at module scope, so
    # every `import je_auto_control` on a Mac created one, and stopping a
    # recording meant AppHelper.runEventLoop(). Neither name is here now.
    assert not hasattr(osx_listener, "app")
    assert not hasattr(osx_listener, "NSApplication")
    assert not hasattr(osx_listener, "AppHelper")


def test_the_platform_wrapper_now_selects_a_recorder():
    from je_auto_control.wrapper import platform_wrapper

    assert isinstance(platform_wrapper.recorder, OSXRecorder)


def test_recording_does_not_block_the_caller():
    # AppHelper.runEventLoop() never returns, so record() used to be a call
    # you could not come back from. The tap runs on its own thread.
    recorder = OSXRecorder()
    finished = threading.Event()

    def _drive():
        try:
            recorder.record()
        except AutoControlRecordException:
            pass                # no Accessibility grant here; still returned
        finally:
            finished.set()

    threading.Thread(target=_drive, daemon=True).start()
    assert finished.wait(timeout=osx_listener.START_TIMEOUT + 5.0), (
        "record() did not return; a blocking run loop is back")
    recorder.stop_record()


# --- decoding -------------------------------------------------------------

def test_tap_records_key_press_and_release():
    events = _decode([
        (Quartz.kCGEventKeyDown, _key_event(0, True)),
        (Quartz.kCGEventKeyUp, _key_event(0, False)),
    ])
    assert [e["op"] for e in events] == ["key_down", "key_up"]
    assert events[0]["vk"] == 0                 # kVK_ANSI_A
    assert all("time" in e for e in events)


def test_tap_records_button_release_not_just_press():
    # Without the release a drag is indistinguishable from a click.
    events = _decode([
        (Quartz.kCGEventLeftMouseDown,
         _mouse_event(Quartz.kCGEventLeftMouseDown, 10, 20)),
        (Quartz.kCGEventLeftMouseUp,
         _mouse_event(Quartz.kCGEventLeftMouseUp, 90, 60)),
    ])
    assert [(e["op"], e["button"], e["x"], e["y"]) for e in events] == [
        ("mouse_down", "left", 10, 20), ("mouse_up", "left", 90, 60)]


def test_tap_records_every_button_this_project_addresses():
    events = _decode([
        (Quartz.kCGEventRightMouseDown,
         _mouse_event(Quartz.kCGEventRightMouseDown, 1, 2,
                      Quartz.kCGMouseButtonRight)),
        (Quartz.kCGEventOtherMouseDown,
         _mouse_event(Quartz.kCGEventOtherMouseDown, 3, 4,
                      Quartz.kCGMouseButtonCenter)),
    ])
    assert [e["button"] for e in events] == ["right", "middle"]


def test_recorded_coordinates_are_the_ones_a_replay_posts():
    # CGEventGetLocation has a top-left origin, which is the space osx_mouse
    # posts into. The old listener read NSEvent.mouseLocation(), a bottom-left
    # origin, so every recorded click replayed vertically mirrored.
    height = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size.height
    near_top = int(height * 0.1)
    events = _decode([
        (Quartz.kCGEventLeftMouseDown,
         _mouse_event(Quartz.kCGEventLeftMouseDown, 40, near_top)),
    ])
    assert events[0]["y"] == near_top
    assert events[0]["y"] < height / 2


def test_tap_decodes_a_scroll_with_its_sign():
    # Reading the wheel unsigned turns a scroll down into a scroll up.
    down = Quartz.CGEventCreateScrollWheelEvent(
        None, Quartz.kCGScrollEventUnitLine, 1, -3)
    up = Quartz.CGEventCreateScrollWheelEvent(
        None, Quartz.kCGScrollEventUnitLine, 1, 3)
    events = _decode([(Quartz.kCGEventScrollWheel, down),
                      (Quartz.kCGEventScrollWheel, up)])
    assert [e["op"] for e in events] == ["scroll", "scroll"]
    assert [e["delta"] for e in events] == [-3, 3]


def test_a_held_modifier_becomes_a_press_and_a_release():
    # macOS sends no key-down for Shift, only a flagsChanged carrying the new
    # flag set. Without decoding it a recording cannot say a modifier was held
    # across the actions that followed.
    pressed = _key_event(56, True)
    Quartz.CGEventSetFlags(pressed, Quartz.kCGEventFlagMaskShift)
    released = _key_event(56, False)
    Quartz.CGEventSetFlags(released, 0)
    events = _decode([(Quartz.kCGEventFlagsChanged, pressed),
                      (Quartz.kCGEventFlagsChanged, released)])
    assert [(e["op"], e["vk"]) for e in events] == [
        ("key_down", 56), ("key_up", 56)]


def test_a_flags_change_for_no_known_modifier_is_dropped():
    other = _key_event(0, True)
    Quartz.CGEventSetFlags(other, Quartz.kCGEventFlagMaskShift)
    assert _decode([(Quartz.kCGEventFlagsChanged, other)]) == []


def test_mouse_movement_is_not_recorded():
    # Every pixel of travel would drown the events that matter, exactly as on
    # Windows, where WM_MOUSEMOVE is ignored for the same reason.
    assert _decode([
        (Quartz.kCGEventMouseMoved,
         _mouse_event(Quartz.kCGEventMouseMoved, 5, 5))]) == []


def test_tap_stops_itself_at_the_event_cap():
    # A forgotten recording must not grow without bound.
    tap = OSXInputTap(max_events=3)
    for _ in range(10):
        tap.decode(Quartz.kCGEventKeyDown, _key_event(0, True))
    assert len(tap.events) == 3


# --- failure and lifecycle ------------------------------------------------

def test_a_tap_that_cannot_be_created_fails_loudly(monkeypatch):
    # Without Accessibility, CGEventTapCreate returns None. Recording silence
    # would look like "the user did nothing" for the rest of the session.
    monkeypatch.setattr(Quartz, "CGEventTapCreate",
                        lambda *args, **kwargs: None)
    tap = OSXInputTap()
    with pytest.raises(AutoControlRecordException) as caught:
        tap.start()
    assert "Accessibility" in str(caught.value)


def test_stopping_a_tap_that_never_started_returns_nothing():
    assert OSXInputTap().stop() == []


def test_a_decode_failure_does_not_end_the_recording(monkeypatch):
    # An exception escaping the callback tears down the run loop, and the
    # recording then stops without saying so — so one unusable event must not
    # cost the session. The next event still has to be decoded.
    tap = OSXInputTap()
    calls = []

    def _explode(*_args, **_kwargs):
        calls.append(1)
        raise RuntimeError("unexpected event shape")

    monkeypatch.setattr(tap, "decode", _explode)
    event = _key_event(0, True)
    assert tap._callback(None, Quartz.kCGEventKeyDown, event, None) is event
    assert tap._callback(None, Quartz.kCGEventKeyUp, event, None) is event
    assert len(calls) == 2
    assert tap.events == []


def test_a_disabled_tap_is_re_armed_rather_than_left_deaf(monkeypatch):
    # The window server disables a tap that takes too long. Leaving it
    # disabled records silence for the rest of the session.
    enabled = []
    monkeypatch.setattr(Quartz, "CGEventTapEnable",
                        lambda tap, state: enabled.append((tap, state)))
    tap = OSXInputTap()
    tap._callback("proxy", Quartz.kCGEventTapDisabledByTimeout, None, None)
    assert enabled == [("proxy", True)]
    assert tap.events == []
