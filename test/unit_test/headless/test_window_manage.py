"""Headless tests for window management. No Qt.

The wrapper imports ``windows_window_manage`` inside each function, so patching
attributes on that module intercepts the Win32 layer and keeps these tests off
the real desktop.
"""
import sys

import pytest

from je_auto_control.wrapper import auto_control_window as w

_WINDOWS = sys.platform in ("win32", "cygwin", "msys")
pytestmark = pytest.mark.skipif(not _WINDOWS,
                                reason="window management is Windows-only")


@pytest.fixture()
def wm(monkeypatch):
    """The Win32 backend module, with every call stubbed out."""
    from je_auto_control.windows.window import windows_window_manage as module
    calls = []
    monkeypatch.setattr(module, "get_all_window_hwnd",
                        lambda: [(11, "Editor"), (12, "  "), (13, "Browser")])
    monkeypatch.setattr(module, "get_window_rect", lambda h: (10, 20, 110, 220))
    monkeypatch.setattr(module, "get_foreground_window", lambda: 13)
    for name in ("close_window", "minimize_window"):
        monkeypatch.setattr(module, name,
                            lambda h, _n=name: calls.append((_n, h)) or True)
    monkeypatch.setattr(module, "move_window",
                        lambda h, x, y, cx, cy, *a: calls.append(
                            ("move", h, x, y, cx, cy)) or True)
    module.calls = calls
    return module


# --- hwnd type -------------------------------------------------------------

def test_enumerated_hwnds_are_plain_ints():
    """The whole point of the callback prototype fix.

    A ``POINTER(c_int)`` declaration handed back ``LP_c_long`` objects, and
    ``int(hwnd)`` on one raises ValueError — the list was unusable for any
    follow-up Win32 call.
    """
    for hwnd, _title in w.list_windows():
        assert isinstance(hwnd, int)
        assert int(hwnd) == hwnd


def test_real_foreground_window_is_int_or_none():
    hit = w.foreground_window()
    assert hit is None or isinstance(hit[0], int)


# --- listing ---------------------------------------------------------------

def test_titled_only_drops_blank_titles(wm):
    assert w.list_windows(titled_only=True) == [(11, "Editor"), (13, "Browser")]
    assert len(w.list_windows()) == 3


def test_find_window_is_case_insensitive_by_default(wm):
    assert w.find_window("editor") == (11, "Editor")
    assert w.find_window("editor", case_sensitive=True) is None


# --- close vs minimise -----------------------------------------------------

def test_close_and_minimize_reach_different_backend_calls(wm):
    """They were the same call, so 'close' silently only minimised."""
    assert w.close_window_by_title("Editor") is True
    assert w.minimize_window_by_title("Editor") is True
    assert wm.calls == [("close_window", 11), ("minimize_window", 11)]


def test_close_and_minimize_report_a_miss(wm):
    assert w.close_window_by_title("nothing here") is False
    assert w.minimize_window_by_title("nothing here") is False
    assert wm.calls == []


# --- geometry --------------------------------------------------------------

def test_window_rect_returns_the_backend_rect(wm):
    assert w.window_rect("Browser") == (10, 20, 110, 220)
    assert w.window_rect("nothing here") is None


def test_move_keeps_current_size_when_width_height_omitted(wm):
    assert w.move_window_by_title("Editor", 5, 6) is True
    # rect (10, 20, 110, 220) -> 100 x 200, carried over rather than zeroed.
    assert wm.calls == [("move", 11, 5, 6, 100, 200)]


def test_move_uses_explicit_size_when_given(wm):
    w.move_window_by_title("Editor", 5, 6, width=42, height=43)
    assert wm.calls == [("move", 11, 5, 6, 42, 43)]


def test_foreground_window_pairs_hwnd_with_title(wm):
    assert w.foreground_window() == (13, "Browser")


def test_foreground_window_is_none_when_backend_reports_zero(wm, monkeypatch):
    monkeypatch.setattr(wm, "get_foreground_window", lambda: 0)
    assert w.foreground_window() is None


# --- show_window -----------------------------------------------------------

def test_hiding_a_window_does_not_pull_it_to_the_foreground(monkeypatch):
    """Hide-then-foreground is self-contradicting, and it used to do both."""
    from je_auto_control.windows.window import windows_window_manage as module
    seen = []

    class _FakeUser32:
        def ShowWindow(self, hwnd, cmd):  # noqa: N802  # Win32 name
            seen.append(("show", hwnd, cmd))

        def SetForegroundWindow(self, hwnd):  # noqa: N802  # Win32 name
            seen.append(("front", hwnd))

    monkeypatch.setattr(module, "_user32", _FakeUser32())
    module.show_window(7, 0)                      # SW_HIDE
    assert seen == [("show", 7, 0)]
    seen.clear()
    module.show_window(7, 3)                      # SW_MAXIMIZE
    assert seen == [("show", 7, 3), ("front", 7)]
