"""The sign of ``scroll_value`` picks the direction on every platform.

Windows and macOS have always read the direction off the sign. X11 encodes
direction as a button (4/5/6/7) rather than a signed delta, so it took the
direction from ``scroll_direction`` and discarded the sign — deliberately,
because a negative count used to make ``range()`` empty and scroll nothing.

The cost was that ``mouse_scroll(-3)`` written and tested on Windows scrolled
*down* three notches on Linux instead of up, with no exception and no warning.
The maintainer settled it: the sign reverses the direction everywhere, and
``scroll_direction`` names the direction a positive count takes.

The real X server side of this is pinned by ``docker/x11_verify.py``, which
reads the buttons back out of ``xev``. These tests hold the same contract
without a display, so a change to the mapping fails on every runner rather than
only in the container job.
"""
from __future__ import annotations

import importlib
import sys
import types

import pytest


@pytest.fixture()
def x11_mouse(monkeypatch):
    """Import the X11 mouse backend with python-Xlib and the display faked."""
    monkeypatch.setattr(sys, "platform", "linux")

    fake_xlib = types.ModuleType("Xlib")
    fake_xlib.X = types.SimpleNamespace(
        ZPixmap=2, ButtonPress=4, ButtonRelease=5, CurrentTime=0)
    fake_xlib.protocol = types.SimpleNamespace(event=types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "Xlib", fake_xlib)
    monkeypatch.setitem(sys.modules, "Xlib.protocol", fake_xlib.protocol)

    xtest = types.ModuleType("Xlib.ext.xtest")
    xtest.fake_input = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "Xlib.ext", types.ModuleType("Xlib.ext"))
    monkeypatch.setitem(sys.modules, "Xlib.ext.xtest", xtest)

    display_mod = types.ModuleType("x11_linux_display")
    display_mod.display = types.SimpleNamespace(sync=lambda: None)
    monkeypatch.setitem(
        sys.modules,
        "je_auto_control.linux_with_x11.core.utils.x11_linux_display",
        display_mod)
    monkeypatch.delitem(
        sys.modules,
        "je_auto_control.linux_with_x11.mouse.x11_linux_mouse_control",
        raising=False)

    module = importlib.import_module(
        "je_auto_control.linux_with_x11.mouse.x11_linux_mouse_control")
    clicked: list[int] = []
    monkeypatch.setattr(module, "click_mouse", clicked.append)
    module.clicked = clicked          # for the assertions below
    return module


UP, DOWN, LEFT, RIGHT = 4, 5, 6, 7


@pytest.mark.parametrize(("direction", "expected"), [
    (UP, UP), (DOWN, DOWN), (LEFT, LEFT), (RIGHT, RIGHT),
])
def test_a_positive_count_scrolls_the_named_direction(x11_mouse, direction,
                                                      expected):
    """``scroll_direction`` still means what it always meant."""
    x11_mouse.scroll(3, direction)
    assert x11_mouse.clicked == [expected] * 3


@pytest.mark.parametrize(("direction", "expected"), [
    (UP, DOWN), (DOWN, UP), (LEFT, RIGHT), (RIGHT, LEFT),
])
def test_a_negative_count_reverses_it(x11_mouse, direction, expected):
    """This is the behaviour change: the sign wins, as it does elsewhere."""
    x11_mouse.scroll(-3, direction)
    assert x11_mouse.clicked == [expected] * 3


def test_the_magnitude_is_still_the_notch_count(x11_mouse):
    """A negative count must not go back to scrolling nothing at all."""
    x11_mouse.scroll(-5, DOWN)
    assert len(x11_mouse.clicked) == 5


def test_zero_scrolls_nothing(x11_mouse):
    """Zero is neither direction and must stay a no-op."""
    x11_mouse.scroll(0, DOWN)
    assert x11_mouse.clicked == []


def test_an_unknown_direction_is_passed_through(x11_mouse):
    """A button this table does not know is forwarded, not silently remapped."""
    x11_mouse.scroll(-1, 99)
    assert x11_mouse.clicked == [99]


def test_the_wrapper_routes_the_bsds_to_the_x11_backend(monkeypatch):
    """``["linux", "linux2"]`` left FreeBSD outside every branch.

    The wrapper matched Windows, then macOS, then a literal list of Linux
    names — so on a BSD ``mouse_scroll`` fell off the end, raised nothing and
    scrolled nothing. It asks ``platform_id`` which input stack this is now.
    """
    from je_auto_control.wrapper import auto_control_mouse

    calls: list[tuple] = []
    monkeypatch.setattr(auto_control_mouse, "mouse",
                        types.SimpleNamespace(
                            scroll=lambda *args: calls.append(args)))
    monkeypatch.setattr(auto_control_mouse, "special_mouse_keys_table",
                        {"scroll_down": DOWN})
    monkeypatch.setattr(sys, "platform", "freebsd14")

    auto_control_mouse.mouse_scroll(2, scroll_direction="scroll_down")

    assert calls == [(2, DOWN)], (
        "a BSD must reach the X11 backend; it used to match no branch at all")


# --- the Wayland backend, which had the same abs() ------------------------


def _wayland_mouse():
    """The Wayland mouse module, or a skip when its imports are unavailable."""
    return pytest.importorskip(
        "je_auto_control.linux_wayland.mouse", exc_type=ImportError)


@pytest.mark.parametrize(("direction_name", "expected"), [
    ("wayland_scroll_direction_up", (0, 3)),
    ("wayland_scroll_direction_down", (0, -3)),
    ("wayland_scroll_direction_left", (-3, 0)),
    ("wayland_scroll_direction_right", (3, 0)),
])
def test_wayland_positive_count_keeps_the_named_direction(direction_name,
                                                          expected):
    """Unchanged behaviour, pinned so the sign fix cannot have moved it."""
    mouse = _wayland_mouse()
    direction = getattr(mouse, direction_name)
    assert mouse._wheel_deltas(3, direction) == expected


@pytest.mark.parametrize(("direction_name", "expected"), [
    ("wayland_scroll_direction_up", (0, -3)),
    ("wayland_scroll_direction_down", (0, 3)),
    ("wayland_scroll_direction_left", (3, 0)),
    ("wayland_scroll_direction_right", (-3, 0)),
])
def test_wayland_negative_count_reverses_it(direction_name, expected):
    """``_wheel_deltas`` took ``abs()`` of the count, so the sign was lost.

    Wayland reaches the same wrapper branch as X11, so it had the same defect
    and needed the same fix — otherwise "the sign wins everywhere" would have
    been true of three backends out of four.
    """
    mouse = _wayland_mouse()
    direction = getattr(mouse, direction_name)
    assert mouse._wheel_deltas(-3, direction) == expected


def test_wayland_zero_is_still_a_no_op():
    """Zero has no direction, and must not become a one-notch scroll."""
    mouse = _wayland_mouse()
    assert mouse._wheel_deltas(0, mouse.wayland_scroll_direction_down) == (0, 0)
