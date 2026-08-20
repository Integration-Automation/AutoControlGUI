"""Headless tests for the window-management backend seam. No Qt.

The old window tests are Windows-only, because the facade was: it branched on
``sys.platform`` and raised everywhere else, so there was nothing to test on
another platform. Now that the platform detail sits behind a backend, the
facade's own logic — substring matching, ordering, "move without restating the
size", waiting — is platform-neutral and can be checked anywhere, which is
what these do by driving a fake backend.
"""
import sys

import pytest

from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException, AutoControlException,
    AutoControlUnsupportedOperationException,
)
from je_auto_control.wrapper import auto_control_window as w
from je_auto_control.wrapper.window_backends import (
    NullWindowBackend, WindowManageBackend, get_backend, reset_backend_cache,
)


class FakeBackend(WindowManageBackend):
    """A backend that records what it was asked and answers predictably."""

    name = "fake"

    def __init__(self):
        self.available = True
        self.calls = []
        self.windows = [(11, "Editor"), (12, "   "), (13, "Browser")]
        self.rect = (10, 20, 110, 220)
        self.minimized = False

    def list_windows(self):
        return list(self.windows)

    def foreground_window(self):
        return 13

    def window_rect(self, window_id):
        self.calls.append(("window_rect", window_id))
        return self.rect

    def window_process_id(self, window_id):
        return {11: 111, 12: 112, 13: 113}.get(window_id, 0)

    def is_minimized(self, window_id):
        return self.minimized

    def set_foreground(self, window_id):
        self.calls.append(("set_foreground", window_id))

    def restore(self, window_id):
        self.calls.append(("restore", window_id))

    def show(self, window_id, cmd_show):
        self.calls.append(("show", window_id, cmd_show))

    def close(self, window_id):
        self.calls.append(("close", window_id))
        return True

    def minimize(self, window_id):
        self.calls.append(("minimize", window_id))
        return True

    def move(self, window_id, x, y, width, height):
        self.calls.append(("move", window_id, x, y, width, height))
        return True

    def post_key(self, window_id, keycode, character=""):
        self.calls.append(("post_key", window_id, keycode, character))
        return True

    def post_click(self, window_id, button, x, y):
        self.calls.append(("post_click", window_id, button, x, y))
        return True


@pytest.fixture()
def backend(monkeypatch):
    """Point the facade at a fake backend, on every platform."""
    fake = FakeBackend()
    monkeypatch.setattr(w, "get_backend", lambda: fake)
    return fake


# --- the refusal contract --------------------------------------------------


def test_unsupported_is_catchable_as_both_families():
    """A bare NotImplementedError escaped every containment boundary.

    The GUI tabs and the REST handler catch ``NotImplementedError`` to say
    "not on this platform", so that has to keep working. The executor and the
    background loops catch ``AutoControlException``, and a bare
    ``NotImplementedError`` slipped straight past them — aborting a whole
    script where one action should have been reported as failed.
    """
    assert issubclass(AutoControlUnsupportedOperationException,
                      NotImplementedError)
    assert issubclass(AutoControlUnsupportedOperationException,
                      AutoControlException)


def test_base_backend_refuses_by_name():
    base = WindowManageBackend()
    with pytest.raises(AutoControlUnsupportedOperationException) as caught:
        base.close(1)
    assert "close" in str(caught.value)
    assert "abstract" in str(caught.value)


def test_null_backend_lists_nothing_but_refuses_actions():
    """Listing is answerable without a backend; acting is not.

    "There are no windows I can see" lets a caller iterate and move on. A
    silent False from ``close`` would read as "the window refused", which is
    a different thing and would have callers retrying forever.
    """
    null = NullWindowBackend("no display here")
    assert null.list_windows() == []
    assert not null.available
    assert "no display here" in null.name
    with pytest.raises(AutoControlUnsupportedOperationException):
        null.close(1)


def test_selection_is_cached_and_resettable():
    reset_backend_cache()
    first = get_backend()
    assert get_backend() is first
    reset_backend_cache()
    assert get_backend() is not first


def test_every_platform_gets_a_backend_that_imports():
    """No platform may fail to import, whatever it can or cannot do."""
    reset_backend_cache()
    chosen = get_backend()
    assert isinstance(chosen, WindowManageBackend)
    assert chosen.name


@pytest.mark.skipif(sys.platform not in ("win32", "cygwin", "msys"),
                    reason="the Win32 backend only builds on Windows")
def test_windows_selects_the_win32_backend():
    reset_backend_cache()
    assert get_backend().name == "win32"


# --- the facade's platform-neutral logic -----------------------------------


def test_list_windows_can_drop_the_untitled(backend):
    assert w.list_windows() == backend.windows
    assert w.list_windows(titled_only=True) == [(11, "Editor"), (13, "Browser")]


def test_find_window_matches_case_insensitively_by_default(backend):
    assert w.find_window("edit") == (11, "Editor")
    assert w.find_window("EDIT") == (11, "Editor")
    assert w.find_window("EDIT", case_sensitive=True) is None
    assert w.find_window("nothing") is None


def test_focus_window_restores_only_when_minimised(backend):
    """SW_RESTORE on a maximised window un-maximises it.

    So focusing must not restore unconditionally: that would shrink a
    maximised window as a side effect of being asked to focus it.
    """
    w.focus_window("Editor")
    assert ("restore", 11) not in backend.calls
    assert ("set_foreground", 11) in backend.calls

    backend.calls.clear()
    backend.minimized = True
    w.focus_window("Editor")
    assert ("restore", 11) in backend.calls


def test_focus_window_reports_a_missing_window_as_an_action_failure(backend):
    with pytest.raises(AutoControlActionException):
        w.focus_window("nothing matches this")


def test_move_without_a_size_keeps_the_current_size(backend):
    """Otherwise a plain reposition has to restate dimensions it must look up."""
    assert w.move_window_by_title("Editor", 5, 6)
    assert ("move", 11, 5, 6, 100, 200) in backend.calls


def test_move_with_a_size_passes_it_through(backend):
    assert w.move_window_by_title("Editor", 5, 6, 70, 80)
    assert ("move", 11, 5, 6, 70, 80) in backend.calls


def test_close_and_minimize_report_no_match_as_false(backend):
    assert w.close_window_by_title("nothing") is False
    assert w.minimize_window_by_title("nothing") is False
    assert backend.calls == []


def test_windows_for_process_id_filters_by_owner(backend):
    assert w.windows_for_process_id(111) == [(11, "Editor")]
    assert w.windows_for_process_id(999) == []


def test_minimize_windows_for_process_counts_what_it_minimised(backend):
    assert w.minimize_windows_for_process(113) == 1
    assert ("minimize", 13) in backend.calls


def test_foreground_window_pairs_the_id_with_its_title(backend):
    assert w.foreground_window() == (13, "Browser")
    assert w.foreground_window_process_id() == 113


def test_wait_for_window_returns_as_soon_as_it_appears(backend):
    assert w.wait_for_window("Browser", timeout=1.0, poll=0.05) == 13


def test_wait_for_window_times_out_as_an_action_failure(backend):
    with pytest.raises(AutoControlActionException):
        w.wait_for_window("never", timeout=0.2, poll=0.05)
