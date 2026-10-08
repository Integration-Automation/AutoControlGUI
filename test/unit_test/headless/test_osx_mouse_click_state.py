"""macOS multi-click: the click count rides on the event, not on the clock.

Windows and X11 recognise a double-click from two clicks close together in
time and space, so `click_mouse(clicks=2)` only had to click twice. A macOS
application reads the count off the event instead -- the
`kCGMouseEventClickState` field -- and `osx_mouse.py` never wrote it, so two
clicks arrived as two single clicks whatever the interval.

Three layers, tested separately:

* the osx backend, loaded here against a fake `Quartz` so it runs on every
  CI square, not only the Darwin ones (the module refuses to import off
  macOS, so `sys.platform` is patched for the load and the module is loaded
  under a private name that never enters `sys.modules`);
* the wrapper, which numbers the clicks on macOS and nowhere else;
* the real framework, on the macOS squares only: an event is built and read
  back, never posted. That holds the backend to real API names and to the
  field actually taking the value. It does **not** show that an application
  treats the result as a double-click; nothing here posts an event.

No Qt imports.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

import pytest

import je_auto_control
from je_auto_control.utils.exception.exceptions import AutoControlMouseException
from je_auto_control.wrapper import auto_control_mouse

_OSX_MOUSE = (pathlib.Path(je_auto_control.__file__).parent
              / "osx" / "mouse" / "osx_mouse.py")
_OSX_VK = "je_auto_control.osx.core.utils.osx_vk"

#: The Quartz names `osx_mouse.py` uses to build and post a button event.
QUARTZ_MOUSE_NAMES = (
    "CGEventCreateMouseEvent", "CGEventSetIntegerValueField", "CGEventPost",
    "kCGHIDEventTap", "kCGMouseEventClickState", "kCGEventMouseMoved",
    "kCGEventLeftMouseDown", "kCGEventLeftMouseUp",
    "kCGEventRightMouseDown", "kCGEventRightMouseUp",
    "kCGEventOtherMouseDown", "kCGEventOtherMouseUp",
    "kCGMouseButtonLeft", "kCGMouseButtonRight", "kCGMouseButtonCenter",
    "NSEvent",
)


class _FakeQuartz(types.ModuleType):
    """Builds events as dicts and records what was posted."""

    def __init__(self) -> None:
        super().__init__("Quartz")
        self.posted = []
        self.double_click_seconds = 0.5
        for name in QUARTZ_MOUSE_NAMES:
            if name.startswith("k"):
                setattr(self, name, name)
        self.NSEvent = types.SimpleNamespace(
            doubleClickInterval=lambda: self.double_click_seconds)

    def CGEventCreateMouseEvent(self, source, kind, point, button):  # noqa: N802  # reason: the Quartz name
        return {"source": source, "kind": kind, "point": point,
                "button": button, "fields": {}}

    def CGEventSetIntegerValueField(self, event, field, value):  # noqa: N802  # reason: the Quartz name
        event["fields"][field] = value

    def CGEventPost(self, tap, event):  # noqa: N802  # reason: the Quartz name
        self.posted.append((tap, event))


@pytest.fixture
def osx(monkeypatch):
    """`osx_mouse` bound to a fake Quartz, leaving `sys.modules` as it was."""
    quartz = _FakeQuartz()
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "Quartz", quartz)
    had_vk = _OSX_VK in sys.modules
    spec = importlib.util.spec_from_file_location("_osx_mouse_under_test",
                                                  _OSX_MOUSE)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        # The module's own name, not `time.sleep` itself: the real module
        # object is shared with everything else in the process.
        monkeypatch.setattr(module, "time", types.SimpleNamespace(
            sleep=lambda _seconds: None))
        yield types.SimpleNamespace(mouse=module, quartz=quartz)
    finally:
        if not had_vk:
            # Imported for the first time by the load above, under a patched
            # platform. Left behind it would make `import ...osx_vk` succeed
            # on Windows and Linux for the rest of the session.
            sys.modules.pop(_OSX_VK, None)


def _states(quartz):
    return [(event["kind"], event["fields"].get("kCGMouseEventClickState"))
            for _tap, event in quartz.posted]


# --- the backend --------------------------------------------------------------

def test_a_single_click_builds_the_event_it_always_did(osx):
    # No field is written at all, so the default path is unchanged rather
    # than "changed to something believed equivalent".
    osx.mouse.click_mouse(10, 20, "Left")
    assert osx.quartz.posted == [
        ("kCGHIDEventTap", {"source": None, "kind": "kCGEventLeftMouseDown",
                            "point": (10, 20), "button": "kCGMouseButtonLeft",
                            "fields": {}}),
        ("kCGHIDEventTap", {"source": None, "kind": "kCGEventLeftMouseUp",
                            "point": (10, 20), "button": "kCGMouseButtonLeft",
                            "fields": {}}),
    ]


def test_the_second_click_carries_two_on_both_the_press_and_the_release(osx):
    # An application reads the count on the down *and* the up; a release
    # still saying 1 ends a double-click as a single one.
    osx.mouse.click_mouse(10, 20, "Left", 2)
    assert _states(osx.quartz) == [("kCGEventLeftMouseDown", 2),
                                   ("kCGEventLeftMouseUp", 2)]


@pytest.mark.parametrize("button,down,up", [
    ("Left", "kCGEventLeftMouseDown", "kCGEventLeftMouseUp"),
    ("Right", "kCGEventRightMouseDown", "kCGEventRightMouseUp"),
    ("Middle", "kCGEventOtherMouseDown", "kCGEventOtherMouseUp"),
])
def test_every_button_carries_the_count(osx, button, down, up):
    osx.mouse.press_mouse(1, 2, button, 3)
    osx.mouse.release_mouse(1, 2, button, 3)
    assert _states(osx.quartz) == [(down, 3), (up, 3)]


def test_press_and_release_default_to_a_single_click(osx):
    osx.mouse.press_mouse(1, 2, "Left")
    osx.mouse.release_mouse(1, 2, "Left")
    assert _states(osx.quartz) == [("kCGEventLeftMouseDown", None),
                                   ("kCGEventLeftMouseUp", None)]


def test_moving_the_cursor_writes_no_click_state(osx):
    osx.mouse.set_position(5, 6)
    [(_tap, event)] = osx.quartz.posted
    assert event["fields"] == {}


@pytest.mark.parametrize("count", [0, -1, True, 1.5, "2", None])
def test_a_click_count_that_is_not_a_positive_integer_posts_nothing(osx,
                                                                    count):
    with pytest.raises(AutoControlMouseException, match="click_count"):
        osx.mouse.click_mouse(1, 2, "Left", count)
    assert osx.quartz.posted == []


def test_an_unknown_button_is_still_refused_with_a_count(osx):
    with pytest.raises(AutoControlMouseException, match="unknown mouse button"):
        osx.mouse.press_mouse(1, 2, 99, 2)
    assert osx.quartz.posted == []


def test_the_double_click_interval_is_the_systems_own(osx):
    osx.quartz.double_click_seconds = 0.25
    assert osx.mouse.double_click_interval() == pytest.approx(0.25)


def test_loading_the_backend_here_leaves_no_macos_module_behind(osx):
    assert "_osx_mouse_under_test" not in sys.modules
    assert "je_auto_control.osx.mouse.osx_mouse" not in sys.modules or (
        sys.modules["je_auto_control.osx.mouse.osx_mouse"] is not osx.mouse)


# --- the wrapper --------------------------------------------------------------

class _DarwinBackend:
    """The macOS seam: point first, then the button, then the count."""

    def __init__(self, interval=0.5):
        self.clicks = []
        self.interval = interval
        self.interval_reads = 0

    def click_mouse(self, x, y, mouse_button, click_count=1):
        self.clicks.append((x, y, mouse_button, click_count))

    def double_click_interval(self):
        self.interval_reads += 1
        return self.interval


@pytest.fixture
def wrapper(monkeypatch):
    backend = _DarwinBackend()
    sleeps = []
    monkeypatch.setattr(auto_control_mouse, "mouse", backend)
    monkeypatch.setattr(auto_control_mouse, "time",
                        types.SimpleNamespace(sleep=sleeps.append))
    monkeypatch.setattr(auto_control_mouse, "mouse_keys_table",
                        {"mouse_left": "Left"})
    monkeypatch.setattr(auto_control_mouse, "record_action_to_list",
                        lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sys, "platform", "darwin")
    return types.SimpleNamespace(backend=backend, sleeps=sleeps)


def test_a_double_click_on_macos_numbers_its_clicks(wrapper):
    auto_control_mouse.click_mouse("mouse_left", 5, 6, clicks=2)
    assert wrapper.backend.clicks == [(5, 6, "Left", 1), (5, 6, "Left", 2)]


def test_a_triple_click_counts_to_three(wrapper):
    auto_control_mouse.click_mouse("mouse_left", 5, 6, clicks=3, interval=0.05)
    assert [click[3] for click in wrapper.backend.clicks] == [1, 2, 3]
    assert wrapper.sleeps == [0.05, 0.05]


def test_the_system_interval_is_only_read_when_there_is_a_pause_to_judge(
        wrapper):
    auto_control_mouse.click_mouse("mouse_left", 5, 6)
    auto_control_mouse.click_mouse("mouse_left", 5, 6, clicks=2)
    assert wrapper.backend.interval_reads == 0
    auto_control_mouse.click_mouse("mouse_left", 5, 6, clicks=2, interval=0.1)
    assert wrapper.backend.interval_reads == 1


def test_clicks_further_apart_than_a_double_click_stay_single(wrapper):
    # `clicks=3, interval=2` is "click three times", not a triple-click: no
    # platform reads it as one, and a text view sent a count of 3 would
    # select the paragraph.
    wrapper.backend.interval = 0.5
    auto_control_mouse.click_mouse("mouse_left", 5, 6, clicks=3, interval=2)
    assert [click[3] for click in wrapper.backend.clicks] == [1, 1, 1]


def test_an_interval_exactly_at_the_limit_still_counts(wrapper):
    wrapper.backend.interval = 0.5
    auto_control_mouse.click_mouse("mouse_left", 5, 6, clicks=2, interval=0.5)
    assert [click[3] for click in wrapper.backend.clicks] == [1, 2]


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_no_other_platform_is_passed_a_count(wrapper, monkeypatch, platform):
    calls = []
    monkeypatch.setattr(auto_control_mouse, "mouse", types.SimpleNamespace(
        click_mouse=lambda *args: calls.append(args)))
    monkeypatch.setattr(sys, "platform", platform)
    auto_control_mouse.click_mouse("mouse_left", 5, 6, clicks=2)
    assert calls == [("Left", 5, 6), ("Left", 5, 6)], (
        "three positional arguments, and no double_click_interval lookup "
        "on a backend that has none"
    )


def test_the_wrapper_and_the_backend_agree_end_to_end(osx, monkeypatch):
    # The two halves joined: what the wrapper sends is what the backend the
    # fake Quartz is bound to accepts, with nothing renumbered in between.
    monkeypatch.setattr(auto_control_mouse, "mouse", osx.mouse)
    monkeypatch.setattr(auto_control_mouse, "mouse_keys_table",
                        {"mouse_left": "Left"})
    monkeypatch.setattr(auto_control_mouse, "record_action_to_list",
                        lambda *_args, **_kwargs: None)
    auto_control_mouse.click_mouse("mouse_left", 5, 6, clicks=2)
    assert _states(osx.quartz) == [
        ("kCGEventLeftMouseDown", None), ("kCGEventLeftMouseUp", None),
        ("kCGEventLeftMouseDown", 2), ("kCGEventLeftMouseUp", 2),
    ]


# --- the real framework, on the macOS squares ---------------------------------

def _real_quartz():
    if sys.platform != "darwin":
        pytest.skip("pyobjc is a macOS-only dependency")
    return pytest.importorskip("Quartz")


@pytest.mark.parametrize("name", QUARTZ_MOUSE_NAMES)
def test_every_quartz_name_the_mouse_backend_uses_exists(name):
    assert hasattr(_real_quartz(), name), f"Quartz.{name}"


def test_the_real_double_click_interval_is_a_positive_number():
    _real_quartz()
    from je_auto_control.osx.mouse import osx_mouse
    assert osx_mouse.double_click_interval() > 0


@pytest.mark.parametrize("count", [2, 3])
def test_a_real_event_takes_the_click_count_it_is_given(count):
    # Built and read back, never posted: this moves no cursor and clicks
    # nothing, and it says only that the field holds the number -- not that
    # an application acts on it.
    quartz = _real_quartz()
    from je_auto_control.osx.mouse import osx_mouse
    event = osx_mouse._build_mouse_event(
        quartz.kCGEventLeftMouseDown, 10, 10, quartz.kCGMouseButtonLeft, count)
    assert quartz.CGEventGetIntegerValueField(
        event, quartz.kCGMouseEventClickState) == count
