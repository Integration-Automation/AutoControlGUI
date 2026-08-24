"""Which window backend a platform gets, and what the others refuse.

Window management was Windows-only for the project's whole life -- the facade
branched on `sys.platform` and raised `NotImplementedError` everywhere else,
leaving 23 `AC_*` commands dead on macOS and Linux. This package is the seam
that replaced that branch, and the seam itself was covered by nothing: the
selector only ever ran its own platform's arm, and every square skipped the
other two.

Three things here are worth stating in a test:

* **A platform without a working backend gets a refusal that says why.** Not
  an ImportError at start-up and not a backend that answers falsely -- a null
  backend carrying the reason, so `AC_list_window` on a Wayland session says
  "Wayland does not expose other windows to a client" rather than failing
  with a stack trace about Xlib.
* **Selection is cached, because probing costs a connection.** It opens an X
  display or runs a Quartz query, and the answer cannot change inside a
  process.
* **"Cannot" and "did not work this time" are different answers.** The base
  class raises for the first and every backend returns a falsy value for the
  second; a caller that cannot tell them apart retries forever.

Both stubbed platforms are driven from every square, so this file tests all
three arms wherever it runs -- which is the point, since the coverage floor
is the lowest square.
"""
from __future__ import annotations

import sys
import types

import pytest

from headless import _pyobjc_stub as objc_stub
from headless import _xlib_stub
from je_auto_control.utils.exception.exceptions import (
    AutoControlUnsupportedOperationException,
)
from je_auto_control.wrapper import window_backends
from je_auto_control.wrapper.window_backends import (
    NullWindowBackend, WindowManageBackend, get_backend, reset_backend_cache,
)
from je_auto_control.wrapper.window_backends.windows_backend import (
    WindowsWindowBackend,
)


@pytest.fixture(autouse=True)
def clean_cache():
    """The selector caches; a test that leaves one behind poisons the next."""
    reset_backend_cache()
    yield
    reset_backend_cache()


@pytest.fixture
def on_platform(monkeypatch):
    def _set(name: str):
        monkeypatch.setattr(window_backends.sys, "platform", name)
    return _set


# --- selection ----------------------------------------------------------------

@pytest.mark.parametrize("platform", ["win32", "cygwin", "msys"])
def test_every_windows_spelling_selects_the_win32_backend(on_platform,
                                                          platform):
    on_platform(platform)
    assert isinstance(get_backend(), WindowsWindowBackend)


def test_a_mac_with_pyobjc_selects_the_quartz_backend(on_platform, monkeypatch):
    on_platform("darwin")
    objc_stub.install(monkeypatch, objc_stub.World())
    assert get_backend().name == "macos-quartz-ax"


def test_a_mac_without_pyobjc_gets_a_refusal_naming_it(on_platform,
                                                       monkeypatch):
    on_platform("darwin")
    objc_stub.install_missing(monkeypatch, "Quartz")
    backend = get_backend()
    assert isinstance(backend, NullWindowBackend)
    assert "pyobjc" in backend.reason


@pytest.mark.parametrize("platform", ["linux", "linux2"])
def test_a_linux_session_with_x_selects_the_ewmh_backend(on_platform,
                                                         monkeypatch,
                                                         platform):
    on_platform(platform)
    _xlib_stub.install(monkeypatch)
    assert get_backend().name == "x11-ewmh"


def test_a_session_with_no_x_display_gets_a_refusal_naming_wayland(
        on_platform, monkeypatch):
    # Wayland deliberately does not let a client enumerate or move other
    # applications' windows. That is a protocol decision, so the message has
    # to point at XWayland rather than read as a missing dependency.
    on_platform("linux")
    _xlib_stub.install_failing(monkeypatch, RuntimeError("no DISPLAY"))
    backend = get_backend()
    assert isinstance(backend, NullWindowBackend)
    assert "Wayland" in backend.reason
    assert "XWayland" in backend.reason


def test_an_unknown_platform_gets_a_refusal_naming_it(on_platform):
    on_platform("sunos5")
    backend = get_backend()
    assert isinstance(backend, NullWindowBackend)
    assert "sunos5" in backend.reason


def test_the_choice_is_made_once_and_cached(on_platform):
    # Probing opens an X connection or runs a Quartz query; the answer cannot
    # change inside a process, so paying for it twice is pure cost.
    on_platform("win32")
    assert get_backend() is get_backend()


def test_resetting_the_cache_re_detects(on_platform):
    on_platform("win32")
    first = get_backend()
    reset_backend_cache()
    assert get_backend() is not first


# --- the null backend ---------------------------------------------------------

def test_the_null_backend_lists_nothing_rather_than_refusing():
    # "There are no windows I can see" is a truthful answer a caller can
    # iterate; raising here would make every listing a special case.
    assert NullWindowBackend().list_windows() == []


def test_the_null_backend_carries_its_reason_in_its_name():
    backend = NullWindowBackend("no X display")
    assert backend.reason == "no X display"
    assert "no X display" in backend.name
    assert backend.available is False


def test_a_null_backend_with_no_reason_still_says_something():
    assert NullWindowBackend().reason


@pytest.mark.parametrize("call", [
    lambda b: b.foreground_window(),
    lambda b: b.window_rect(1),
    lambda b: b.window_process_id(1),
    lambda b: b.is_minimized(1),
    lambda b: b.set_foreground(1),
    lambda b: b.restore(1),
    lambda b: b.show(1, 9),
    lambda b: b.close(1),
    lambda b: b.minimize(1),
    lambda b: b.move(1, 0, 0, 1, 1),
    lambda b: b.post_key(1, 38),
    lambda b: b.post_click(1, "left", 0, 0),
])
def test_every_action_on_a_null_backend_refuses_loudly(call):
    with pytest.raises(AutoControlUnsupportedOperationException):
        call(NullWindowBackend("no X display"))


# --- the abstract base --------------------------------------------------------

def test_the_base_class_has_no_listing_of_its_own():
    # Every backend must answer this one; there is no sensible default, so
    # the base leaves it abstract rather than returning an empty list.
    with pytest.raises(NotImplementedError):
        WindowManageBackend().list_windows()


def test_a_refusal_names_the_operation_and_the_backend():
    backend = WindowManageBackend()
    with pytest.raises(AutoControlUnsupportedOperationException) as caught:
        backend.restore(1)
    assert "restore" in str(caught.value)
    assert "abstract" in str(caught.value)


# --- the Windows backend's delegation ------------------------------------------

class _WinManager(types.ModuleType):
    """The Win32 module, which stays the single home of the real calls."""

    SW_RESTORE = 9

    def __init__(self) -> None:
        super().__init__("je_auto_control.windows.window.windows_window_manage")
        self.calls = []

    def _record(self, name, *args):
        self.calls.append((name, args))
        return f"{name}-result"

    def get_all_window_hwnd(self):
        return self._record("get_all_window_hwnd")

    def get_foreground_window(self):
        return self._record("get_foreground_window")

    def get_window_rect(self, window_id):
        return self._record("get_window_rect", window_id)

    def get_window_process_id(self, window_id):
        return self._record("get_window_process_id", window_id)

    def is_window_minimized(self, window_id):
        return self._record("is_window_minimized", window_id)

    def set_foreground_window(self, window_id):
        return self._record("set_foreground_window", window_id)

    def show_window(self, window_id, cmd_show):
        return self._record("show_window", window_id, cmd_show)

    def close_window(self, window_id):
        return self._record("close_window", window_id)

    def minimize_window(self, window_id):
        return self._record("minimize_window", window_id)

    def move_window(self, window_id, x, y, width, height):
        return self._record("move_window", window_id, x, y, width, height)

    def post_key(self, window_id, keycode, character):
        return self._record("post_key", window_id, keycode, character)

    def post_click(self, window_id, button, x, y):
        return self._record("post_click", window_id, button, x, y)


@pytest.fixture
def win_manager(monkeypatch):
    """Stand in for the Win32 module, on every platform including Windows.

    The backend reaches it with `from je_auto_control.windows.window import
    windows_window_manage`, and `from package import name` resolves by
    *attribute* on the package before it looks in `sys.modules` -- so putting
    the double under its own dotted name is not enough on a machine where the
    real one is importable. The package it is read off is replaced instead.
    """
    module = _WinManager()
    package = types.ModuleType("je_auto_control.windows.window")
    package.windows_window_manage = module
    monkeypatch.setitem(sys.modules, "je_auto_control.windows.window", package)
    monkeypatch.setitem(
        sys.modules, "je_auto_control.windows.window.windows_window_manage",
        module)
    return module


@pytest.mark.parametrize("call,expected", [
    (lambda b: b.list_windows(), ("get_all_window_hwnd", ())),
    (lambda b: b.foreground_window(), ("get_foreground_window", ())),
    (lambda b: b.window_rect(5), ("get_window_rect", (5,))),
    (lambda b: b.window_process_id(5), ("get_window_process_id", (5,))),
    (lambda b: b.is_minimized(5), ("is_window_minimized", (5,))),
    (lambda b: b.set_foreground(5), ("set_foreground_window", (5,))),
    (lambda b: b.show(5, 3), ("show_window", (5, 3))),
    (lambda b: b.close(5), ("close_window", (5,))),
    (lambda b: b.minimize(5), ("minimize_window", (5,))),
    (lambda b: b.move(5, 1, 2, 3, 4), ("move_window", (5, 1, 2, 3, 4))),
    (lambda b: b.post_key(5, 38, "a"), ("post_key", (5, 38, "a"))),
    (lambda b: b.post_click(5, "left", 1, 2), ("post_click",
                                               (5, "left", 1, 2))),
])
def test_the_windows_backend_forwards_to_the_win32_module(win_manager, call,
                                                          expected):
    call(WindowsWindowBackend())
    assert win_manager.calls == [expected]


def test_restoring_goes_through_the_win32_show_state_constant(win_manager):
    # `restore` is deliberately not "show it however": it un-minimises
    # without un-maximising, which is what SW_RESTORE means.
    WindowsWindowBackend().restore(5)
    assert win_manager.calls == [("show_window", (5, _WinManager.SW_RESTORE))]


def test_a_show_code_is_passed_through_as_an_int(win_manager):
    WindowsWindowBackend().show(5, "3")
    assert win_manager.calls == [("show_window", (5, 3))]


@pytest.mark.parametrize("platform,available", [
    ("win32", True), ("cygwin", True), ("msys", True),
    ("linux", False), ("darwin", False),
])
def test_the_windows_backend_knows_where_it_can_run(monkeypatch, platform,
                                                    available):
    from je_auto_control.wrapper.window_backends import windows_backend
    monkeypatch.setattr(windows_backend.sys, "platform", platform)
    assert WindowsWindowBackend().available is available
