"""Cross-platform argument-binding tests for the mouse wrapper.

The wrapper is a Strategy consumer: it dispatches to a per-OS backend whose
signature it must match. A mismatch is invisible on the developer's own OS and
only crashes — or silently no-ops — on someone else's, which is exactly the
class of bug that reaches users.

These tests run anywhere. Each stub below mirrors the *real* signature of the
backend it stands in for (checked against the source), so binding the wrong
argument order raises TypeError here just as it would on the real platform.
Keep a stub's signature in sync with its backend:

    windows  je_auto_control/windows/mouse/win32_ctype_mouse_control.py
    osx      je_auto_control/osx/mouse/osx_mouse.py
    x11      je_auto_control/linux_with_x11/mouse/x11_linux_mouse_control.py
    wayland  je_auto_control/linux_wayland/mouse.py
"""
import sys
import types

import pytest

from je_auto_control.wrapper import auto_control_mouse


class _RecordingMouse:
    """Stand-in backend that records how the wrapper bound its arguments."""

    def __init__(self):
        self.calls: list = []

    # (mouse_keycode, x, y) — windows / x11 / uinput / wayland convention
    def click_mouse_keycode_first(self, mouse_keycode, x=None, y=None):
        self.calls.append(("click", mouse_keycode, x, y))

    # (x, y, mouse_button) — the osx convention, matching osx press/release
    def click_mouse_xy_first(self, x, y, mouse_button):
        self.calls.append(("click", mouse_button, x, y))


@pytest.fixture()
def stub_env(monkeypatch):
    """Neutralise everything the wrapper touches except the backend call."""
    monkeypatch.setattr(auto_control_mouse, "record_action_to_list",
                        lambda *a, **k: None)
    monkeypatch.setattr(auto_control_mouse, "mouse_keys_table",
                        {"mouse_left": 1, "mouse_right": 2})

    def _fail_position():
        raise AssertionError(
            "get_mouse_position() must not be called when x and y are given")

    monkeypatch.setattr(auto_control_mouse, "get_mouse_position",
                        _fail_position)
    return monkeypatch


def _install_backend(monkeypatch, click_impl):
    backend = types.ModuleType("stub_mouse")
    recorder = _RecordingMouse()
    backend.click_mouse = click_impl(recorder)
    monkeypatch.setattr(auto_control_mouse, "mouse", backend)
    return recorder


@pytest.mark.parametrize("platform", ["win32", "linux", "linux2", "cygwin"])
def test_click_binds_keycode_first_on_non_darwin(stub_env, platform):
    recorder = _install_backend(
        stub_env, lambda r: r.click_mouse_keycode_first)
    stub_env.setattr(sys, "platform", platform)

    auto_control_mouse.click_mouse("mouse_left", 100, 200)

    assert recorder.calls == [("click", 1, 100, 200)]


def test_click_binds_xy_first_on_darwin(stub_env):
    """Regression: the wrapper called the osx backend keycode-first.

    That bound x=<keycode>, y=<x>, button=<y>. Because the osx button table
    holds strings, the int button matched no branch and the click was dropped
    with no exception — a silent no-op on macOS only.
    """
    recorder = _install_backend(stub_env, lambda r: r.click_mouse_xy_first)
    stub_env.setattr(sys, "platform", "darwin")

    auto_control_mouse.click_mouse("mouse_left", 100, 200)

    assert recorder.calls == [("click", 1, 100, 200)]


def test_click_with_explicit_coords_never_queries_the_cursor(stub_env):
    """Regression: mouse_preprocess always called get_mouse_position().

    Wayland's position() raises NotImplementedError by design, so every mouse
    op failed there even when the caller supplied explicit coordinates. The
    stub_env fixture asserts the query never happens.
    """
    recorder = _install_backend(
        stub_env, lambda r: r.click_mouse_keycode_first)
    stub_env.setattr(sys, "platform", "linux")

    auto_control_mouse.click_mouse("mouse_left", 10, 20)

    assert recorder.calls == [("click", 1, 10, 20)]


def _scroll_env(monkeypatch, platform, *, cursor=(7, 7)):
    """Wire mouse_scroll up to a recording backend on a chosen platform."""
    events: list = []
    backend = types.ModuleType("stub_mouse")
    backend.scroll = lambda *a: events.append(("scroll",) + a)
    backend.set_position = lambda x, y: events.append(("move", x, y))
    monkeypatch.setattr(auto_control_mouse, "mouse", backend)
    monkeypatch.setattr(auto_control_mouse, "record_action_to_list",
                        lambda *a, **k: None)
    monkeypatch.setattr(auto_control_mouse, "screen_size",
                        lambda: (1920, 1080))
    monkeypatch.setattr(auto_control_mouse, "special_mouse_keys_table",
                        {"scroll_down": 5})
    monkeypatch.setattr(auto_control_mouse, "get_mouse_position",
                        lambda: cursor)
    monkeypatch.setattr(sys, "platform", platform)
    return events


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
def test_scroll_moves_the_cursor_when_coords_are_given(monkeypatch, platform):
    """Regression: mouse_scroll documented x/y but every backend ignored them.

    Win32 needs MOVE|ABSOLUTE alongside WHEEL for dwData's x/y to mean
    anything, and the mac/linux backends were never handed them at all — so
    scrolling always happened wherever the cursor already was.
    """
    events = _scroll_env(monkeypatch, platform)

    auto_control_mouse.mouse_scroll(5, x=100, y=200)

    assert events[:1] == [("move", 100, 200)]


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
def test_scroll_without_coords_never_queries_the_cursor(monkeypatch, platform):
    """Regression: the cursor was queried unconditionally, so mouse_scroll
    raised on backends that cannot report it (Wayland) even with no x/y."""
    events = _scroll_env(monkeypatch, platform)

    def _fail():
        raise AssertionError("cursor must not be queried without x/y")

    monkeypatch.setattr(auto_control_mouse, "get_mouse_position", _fail)

    auto_control_mouse.mouse_scroll(5)

    assert not any(e[0] == "move" for e in events)


def test_scroll_clamps_and_fills_a_partial_coordinate(monkeypatch):
    """Only one coordinate given: fill the other, clamp to the screen."""
    events = _scroll_env(monkeypatch, "win32", cursor=(7, 7))

    auto_control_mouse.mouse_scroll(5, x=99999)

    assert events[:1] == [("move", 1919, 7)]  # NOSONAR python:S6466  # reason: slice, not index — cannot raise IndexError


def test_missing_coords_still_fall_back_to_the_cursor(monkeypatch):
    """The cursor query must still happen when a coordinate is omitted."""
    monkeypatch.setattr(auto_control_mouse, "record_action_to_list",
                        lambda *a, **k: None)
    monkeypatch.setattr(auto_control_mouse, "mouse_keys_table",
                        {"mouse_left": 1})
    monkeypatch.setattr(auto_control_mouse, "get_mouse_position",
                        lambda: (55, 66))
    recorder = _install_backend(
        monkeypatch, lambda r: r.click_mouse_keycode_first)
    monkeypatch.setattr(sys, "platform", "linux")

    auto_control_mouse.click_mouse("mouse_left")

    assert recorder.calls == [("click", 1, 55, 66)]
