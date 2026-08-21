"""What the platform seam promises, exercised on every platform from one host.

``wrapper/platform_wrapper.py`` picks one backend and re-exports its names;
everything above it is written against those names. These tests stand a
recording stub in each name's place and drive the wrapper with ``sys.platform``
set to somebody else's OS, so a branch that reaches no backend — the failure
mode that is invisible on the developer's own machine — fails here.

They also pin the answers the wrapper must give when a backend cannot answer:
"I don't know where the cursor is" and "there is no such key" have documented
results, and both used to be a bare ``TypeError`` from an unpacking or a
``None`` handed to a native call.
"""
import sys
import types

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlMouseException
from je_auto_control.wrapper import (
    auto_control_keyboard, auto_control_mouse, auto_control_record,
)

# The BSDs run the same X11 stack as Linux, and ``sys.platform`` there carries
# the major version — which is why a literal ["linux", "linux2"] list missed it.
BSD = "freebsd14"


@pytest.fixture()
def keyboard_env(monkeypatch):
    """A recording keyboard backend, with the key table and recorder silenced."""
    calls: list = []
    backend = types.ModuleType("stub_keyboard")
    backend.press_key = lambda keycode, **kwargs: calls.append(
        ("press", keycode, kwargs))
    backend.release_key = lambda keycode, **kwargs: calls.append(
        ("release", keycode, kwargs))
    monkeypatch.setattr(auto_control_keyboard, "keyboard", backend)
    monkeypatch.setattr(auto_control_keyboard, "keyboard_keys_table", {"a": 65})
    monkeypatch.setattr(auto_control_keyboard, "record_action_to_list",
                        lambda *a, **k: None)
    return calls


@pytest.mark.parametrize("platform", ["win32", "cygwin", "msys", "linux",
                                      "linux2", BSD])
def test_a_key_press_reaches_the_backend_on_every_x11_and_win32_platform(
        keyboard_env, monkeypatch, platform):
    """Regression: a BSD matched no branch, so no key was pressed.

    ``press_keyboard_key`` tested ``sys.platform`` against a literal list of
    Linux and Windows names and then against ``darwin``. On FreeBSD it fell
    off the end: nothing was pressed, nothing was raised, and the keycode came
    back as if it had worked. ``mouse_scroll`` had the same hole and was fixed;
    this is the same family.
    """
    monkeypatch.setattr(sys, "platform", platform)

    assert auto_control_keyboard.press_keyboard_key("a") == "65"
    assert keyboard_env == [("press", 65, {})]


@pytest.mark.parametrize("platform", ["win32", "linux", BSD])
def test_a_key_release_reaches_the_backend_too(keyboard_env, monkeypatch,
                                               platform):
    """The release path carried the identical list, and the identical hole."""
    monkeypatch.setattr(sys, "platform", platform)

    auto_control_keyboard.release_keyboard_key("a")

    assert keyboard_env == [("release", 65, {})]


def test_macos_still_gets_its_shift_argument(keyboard_env, monkeypatch):
    """macOS is the one backend whose press_key takes ``is_shift``."""
    monkeypatch.setattr(sys, "platform", "darwin")

    auto_control_keyboard.press_keyboard_key("a", is_shift=True)

    assert keyboard_env == [("press", 65, {"is_shift": True})]


def test_an_unknown_key_name_never_reaches_the_backend(keyboard_env,
                                                       monkeypatch):
    """Regression: the table miss was handed to the backend as ``None``.

    ``check_key_is_press("no_such_key")`` looked the name up, got ``None`` and
    passed it on: a ``TypeError`` on Windows, and on X11 a silent ``False`` —
    "that key is not pressed" for a key that does not exist.
    """
    checked: list = []
    monkeypatch.setattr(
        auto_control_keyboard, "keyboard_check",
        types.SimpleNamespace(
            check_key_is_press=lambda keycode: checked.append(keycode) or True))

    assert auto_control_keyboard.check_key_is_press("no_such_key") is None
    assert checked == []
    # A key the table does know still gets through untouched.
    assert auto_control_keyboard.check_key_is_press("a") is True
    assert checked == [65]


@pytest.fixture()
def mouse_env(monkeypatch):
    """A recording mouse backend with an X11-shaped button table."""
    calls: list = []
    backend = types.ModuleType("stub_mouse")
    backend.press_mouse = lambda *args: calls.append(("press",) + args)
    backend.release_mouse = lambda *args: calls.append(("release",) + args)
    backend.scroll = lambda *args: calls.append(("scroll",) + args)
    backend.set_position = lambda x, y: calls.append(("move", x, y))
    monkeypatch.setattr(auto_control_mouse, "mouse", backend)
    monkeypatch.setattr(auto_control_mouse, "mouse_keys_table",
                        {"mouse_left": 1})
    monkeypatch.setattr(auto_control_mouse, "record_action_to_list",
                        lambda *a, **k: None)
    monkeypatch.setattr(auto_control_mouse, "screen_size", lambda: (1920, 1080))
    return calls


@pytest.mark.parametrize("platform", ["win32", "cygwin", "linux", BSD])
def test_a_button_press_reaches_the_backend_on_a_bsd_too(mouse_env, monkeypatch,
                                                         platform):
    """The same missing-branch hole, in ``press_mouse`` and ``release_mouse``."""
    monkeypatch.setattr(sys, "platform", platform)

    auto_control_mouse.press_mouse("mouse_left", 10, 20)
    auto_control_mouse.release_mouse("mouse_left", 10, 20)

    assert mouse_env == [("press", 1), ("release", 1)]


def test_macos_keeps_its_xy_first_button_order(mouse_env, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")

    auto_control_mouse.press_mouse("mouse_left", 10, 20)

    assert mouse_env == [("press", 10, 20, 1)]


def test_an_unreportable_cursor_raises_the_documented_exception(mouse_env,
                                                                monkeypatch):
    """Regression: ``None`` from the backend was unpacked, raising TypeError.

    A backend that cannot report the cursor answers ``None``. That went
    straight into ``now_x, now_y = ...``, so the caller got a ``TypeError``
    from outside the ``AutoControlException`` family every containment
    boundary catches — instead of the exception this API documents.
    """
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(auto_control_mouse, "get_mouse_position", lambda: None)

    with pytest.raises(AutoControlMouseException):
        auto_control_mouse.press_mouse("mouse_left")

    assert mouse_env == []


def test_scrolling_survives_an_unreportable_cursor(mouse_env, monkeypatch):
    """One coordinate given and no cursor to fill the other: scroll anyway.

    Skipping the pre-move is the graceful degradation ``_scroll_to`` already
    documented for backends that cannot report the cursor; it used to reach
    the same unpacking and raise ``TypeError`` out of the whole call.
    """
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(auto_control_mouse, "special_mouse_keys_table",
                        {"scroll_down": 5})
    monkeypatch.setattr(auto_control_mouse, "get_mouse_position", lambda: None)

    auto_control_mouse.mouse_scroll(3, x=100)

    assert mouse_env == [("scroll", 3, 5)]


def test_scrolling_reads_no_axis_table_where_there_is_none(mouse_env,
                                                           monkeypatch):
    """Windows and macOS have one wheel axis and publish no axis table."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(auto_control_mouse, "special_mouse_keys_table", None)

    assert auto_control_mouse.mouse_scroll(-2) == (-2, "scroll_down")
    assert mouse_env == [("scroll", -2)]


def test_stop_record_returns_a_list_when_the_recorder_fails(monkeypatch):
    """Regression: it returned ``None`` while its signature promised a list."""
    def _explode():
        raise RuntimeError("no session")

    monkeypatch.setattr(auto_control_record, "recorder",
                        types.SimpleNamespace(stop_record=_explode))
    monkeypatch.setattr(auto_control_record, "record_action_to_list",
                        lambda *a, **k: None)

    assert auto_control_record.stop_record() == []
