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


# --- process id ------------------------------------------------------------

def test_window_process_id_asks_the_backend_for_the_match(wm, monkeypatch):
    monkeypatch.setattr(wm, "get_window_process_id", lambda h: 4242)
    assert w.window_process_id("Editor") == 4242


def test_window_process_id_is_none_when_nothing_matches(wm):
    assert w.window_process_id("no such window") is None


def test_foreground_window_process_id_follows_the_foreground_hwnd(
        wm, monkeypatch):
    seen = []
    monkeypatch.setattr(wm, "get_window_process_id",
                        lambda h: seen.append(h) or 99)
    assert w.foreground_window_process_id() == 99
    assert seen == [13]          # the hwnd get_foreground_window reported


def test_process_id_zero_reads_as_unknown_not_as_pid_zero(wm, monkeypatch):
    """0 is the backend's "could not tell", and it is never a real user pid.

    Returning it verbatim would let a caller compare `pid == 0` against a
    process list and match the System Idle Process.
    """
    monkeypatch.setattr(wm, "get_window_process_id", lambda h: 0)
    assert w.foreground_window_process_id() is None
    assert w.window_process_id("Editor") is None


def test_real_foreground_window_process_id_is_a_live_pid():
    """No stubs: the ctypes prototype has to survive a real call."""
    pid = w.foreground_window_process_id()
    assert pid is None or (isinstance(pid, int) and pid > 0)


# --- posting input without focus -------------------------------------------

def test_post_key_targets_the_focused_control_not_the_frame(wm, monkeypatch):
    """The whole point of the fix.

    Keyboard messages are delivered to the control that has focus. Measured on
    Character Map: posting to the top-level frame typed nothing, posting to the
    focused edit typed the character — so a "background typing" feature that
    posts to the frame silently does nothing in any app with child controls.
    """
    posted = []
    monkeypatch.setattr(wm, "get_focused_control", lambda hwnd: 999)
    monkeypatch.setattr(wm, "post_key",
                        lambda hwnd, code, char="": posted.append(
                            (hwnd, code, char)) or True)
    assert w.post_key_to_window("Editor", "a") is True
    assert posted == [(11, 65, "a")]          # hwnd of the matched window


def test_post_key_sends_a_character_for_printable_keys_only():
    assert w._resolve_key("a") == (65, "a")   # WM_CHAR carries the text
    assert w._resolve_key("f5")[1] == ""      # a function key has no character
    assert w._resolve_key(65) == (65, "")


def test_post_key_rejects_an_unknown_key_name():
    from je_auto_control.utils.exception.exceptions import (
        AutoControlActionException,
    )
    with pytest.raises(AutoControlActionException):
        w._resolve_key("wingdings")


def test_post_click_accepts_both_button_spellings(wm, monkeypatch):
    seen = []
    monkeypatch.setattr(wm, "post_click",
                        lambda hwnd, button, x, y: seen.append(
                            (hwnd, button, x, y)) or True)
    assert w.post_click_to_window("Editor", "mouse_right", 5, 6) is True
    assert w.post_click_to_window("Editor", "LEFT", 1, 2) is True
    assert seen == [(11, "right", 5, 6), (11, "left", 1, 2)]


def test_posting_to_a_missing_window_is_false_not_an_exception(wm):
    assert w.post_key_to_window("no such window", "a") is False
    assert w.post_click_to_window("no such window") is False


def test_post_click_rejects_unknown_buttons():
    from je_auto_control.windows.window import windows_window_manage as module
    with pytest.raises(ValueError):
        module.post_click(0, "scroll", 0, 0)


def test_focused_control_falls_back_to_the_window_itself():
    """A window whose thread reports no focus must still be a usable target."""
    from je_auto_control.windows.window import windows_window_manage as module
    assert module.get_focused_control(0) == 0


# --- windows by owning process ---------------------------------------------

def test_windows_for_process_id_filters_by_owner(wm, monkeypatch):
    monkeypatch.setattr(wm, "get_window_process_id",
                        lambda hwnd: {11: 4242, 12: 7, 13: 4242}.get(hwnd, 0))
    assert w.windows_for_process_id(4242) == [(11, "Editor"), (13, "Browser")]


def test_windows_for_process_id_can_keep_untitled_windows(wm, monkeypatch):
    """A browser's helper windows are often untitled — and still worth acting on."""
    monkeypatch.setattr(wm, "get_window_process_id", lambda hwnd: 4242)
    assert len(w.windows_for_process_id(4242)) == 3
    assert len(w.windows_for_process_id(4242, titled_only=True)) == 2


def test_minimize_windows_for_process_counts_only_what_it_minimised(
        wm, monkeypatch):
    monkeypatch.setattr(wm, "get_window_process_id", lambda hwnd: 4242)
    monkeypatch.setattr(wm, "minimize_window", lambda hwnd: hwnd != 12)
    assert w.minimize_windows_for_process(4242) == 2


# --- the deprecated pair now delegates instead of doing nothing -------------

def test_deprecated_key_sender_warns_and_delegates(wm, monkeypatch):
    """It used to post to the frame and silently do nothing while reporting success."""
    from je_auto_control.wrapper import auto_control_keyboard as k

    posted = []
    monkeypatch.setattr(wm, "get_focused_control", lambda hwnd: hwnd)
    monkeypatch.setattr(wm, "post_key",
                        lambda hwnd, code, char="": posted.append(
                            (hwnd, code, char)) or True)
    with pytest.warns(DeprecationWarning):
        k.send_key_event_to_window("Editor", "a")
    assert posted == [(11, 65, "a")]          # resolved by title substring


def test_deprecated_mouse_sender_accepts_an_hwnd_and_a_title(wm, monkeypatch):
    """The old signature took an hwnd; keep that working while fixing the target."""
    from je_auto_control.wrapper import auto_control_mouse as m

    seen = []
    monkeypatch.setattr(wm, "post_click",
                        lambda hwnd, button, x, y: seen.append(
                            (hwnd, button, x, y)) or True)
    with pytest.warns(DeprecationWarning):
        m.send_mouse_event_to_window(11, "mouse_right", 5, 6)
    with pytest.warns(DeprecationWarning):
        m.send_mouse_event_to_window("Editor", "mouse_left", 1, 2)
    assert seen == [(11, "right", 5, 6), (11, "left", 1, 2)]


def test_deprecated_mouse_sender_maps_raw_keycodes_back_to_a_button():
    from je_auto_control.wrapper.auto_control_mouse import _button_name_for_post
    from je_auto_control.wrapper.platform_wrapper import mouse_keys_table

    assert _button_name_for_post("mouse_middle") == "middle"
    assert _button_name_for_post(mouse_keys_table["mouse_right"]) == "right"
    assert _button_name_for_post(object()) == "left"      # unknown → safe default
