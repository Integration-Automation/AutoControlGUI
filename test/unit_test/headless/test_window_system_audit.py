"""Window and OS helpers at the edges the audit found (fakes; nothing is focused, typed or closed).

The file-dialog helper took a browser tab for the Open dialog and typed into
the active window; a watchdog key rule pressed its key in the active window;
psutil's and re's own errors escaped; empty needles matched everything; an
unregistered file type named the Open With picker; relative paths went into
file drops; the Window Manager tab acted on the first title match.
"""
import sys
import types

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.wrapper import window_backends


class _Backend:
    """Records what a helper asks of the window backend."""

    def __init__(self, windows, front_ok=True):
        self.windows, self.front_ok, self.fronted, self.closed = windows, front_ok, [], []

    def list_windows(self):
        return list(self.windows)

    def bring_to_front(self, window_id, settle_s=1.0):
        self.fronted.append(window_id)
        return self.front_ok

    def close(self, window_id):
        self.closed.append(window_id)
        return True


# --- file dialogs -----------------------------------------------------------------------------------

def test_a_title_containing_open_is_not_the_open_dialog(monkeypatch):
    from je_auto_control.utils.file_dialog.file_dialog import FileDialogDriver
    backend = _Backend([(1, "How to reopen closed tabs - Google Chrome")])
    monkeypatch.setattr(window_backends, "get_backend", lambda: backend)
    assert FileDialogDriver().wait_window("Open", 0) is False and backend.fronted == []


def test_the_dialog_is_brought_to_the_front_before_anything_is_typed(monkeypatch):
    from je_auto_control.utils.file_dialog.file_dialog import FileDialogDriver, handle_file_dialog
    backend = _Backend([(1, "Save Aspect Ratio.txt - Notepad"), (2, "Save As")], front_ok=False)
    monkeypatch.setattr(window_backends, "get_backend", lambda: backend)
    typed = []
    driver = FileDialogDriver()
    driver.type_path = typed.append
    driver.confirm = typed.append
    outcome = handle_file_dialog(r"C:\secret\payroll.xlsx", action="save", timeout_s=0, driver=driver)
    assert backend.fronted == [2] and outcome["handled"] is False and typed == []


# --- watchdog ---------------------------------------------------------------------------------------

def test_a_watchdog_key_is_not_pressed_when_the_popup_cannot_be_fronted(monkeypatch):
    from je_auto_control.utils.watchdog import popup_watchdog
    from je_auto_control.wrapper import auto_control_keyboard, auto_control_window
    pressed = []
    monkeypatch.setattr(auto_control_keyboard, "type_keyboard", pressed.append)
    monkeypatch.setattr(auto_control_window, "find_window", lambda *a, **k: (9, "Session expiring"))
    monkeypatch.setattr(window_backends, "get_backend", lambda: _Backend([], front_ok=False))
    with pytest.raises(AutoControlActionException):
        popup_watchdog._window_action("Session expiring", "enter", False)()  # noqa: SLF001
    assert pressed == []


def test_an_infinite_watchdog_interval_is_bounded():
    import math

    from je_auto_control.utils.watchdog.popup_watchdog import PopupWatchdog
    assert math.isfinite(PopupWatchdog(poll_interval_s=float("inf"))._poll)  # noqa: SLF001


# --- errors and empty needles -------------------------------------------------------------------------

def test_an_access_denied_kill_is_an_action_error(monkeypatch):
    from je_auto_control.utils.mcp_server.tools._handlers_system import kill_process

    class Error(Exception):
        pass

    class AccessDenied(Error):
        pass

    class _Process:
        def __init__(self, pid):
            self.pid = pid

        def terminate(self):
            raise AccessDenied("pid 4")

    fake = types.SimpleNamespace(Error=Error, AccessDenied=AccessDenied, NoSuchProcess=type("NSP", (Error,), {}),
                                 TimeoutExpired=type("TE", (Error,), {}), Process=_Process)
    monkeypatch.setitem(sys.modules, "psutil", fake)
    with pytest.raises(AutoControlActionException, match="pid 4"):
        kill_process(4)


def test_a_bad_title_pattern_is_a_value_error():
    from je_auto_control.utils.smart_waits.waits import wait_until_window_title
    with pytest.raises(ValueError, match="pattern"):
        wait_until_window_title("Report (draft", title_lister=lambda: [], timeout_s=0.1)


@pytest.mark.parametrize("call", [
    lambda: __import__("je_auto_control.utils.smart_waits.waits", fromlist=["x"]).wait_until_window_title(
        "", regex=False, title_lister=lambda: ["anything"], timeout_s=0.1),
    lambda: __import__("je_auto_control.utils.smart_waits.waits", fromlist=["x"]).wait_until_process(
        "", lister=lambda name: ["anything"], timeout_s=0.1),
])
def test_an_empty_needle_is_refused(call):
    with pytest.raises(ValueError, match="non-empty"):
        call()


def test_an_empty_process_name_is_refused():
    pytest.importorskip("psutil")
    from je_auto_control.utils.assertion.assertions import _running_process_names
    with pytest.raises(ValueError, match="non-empty"):
        _running_process_names("")


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows shell association API")
def test_an_unregistered_file_type_has_no_application():
    from je_auto_control.utils.file_assoc.file_assoc import file_association
    info = file_association(".nonexistentext123")
    assert info["exe"] is None and info["friendly"] is None


# --- file drops ---------------------------------------------------------------------------------------

def test_a_relative_drop_path_is_made_absolute(tmp_path, monkeypatch):
    from je_auto_control.utils.clipboard_files.clipboard_files import parse_dropfiles
    from je_auto_control.utils.file_drop.file_drop import drop_files
    monkeypatch.chdir(tmp_path)
    sent = []
    drop_files(1, ["report.pdf"], driver=lambda hwnd, blob, point: sent.append(blob) or True)
    assert parse_dropfiles(sent[0])["paths"] == [str(tmp_path / "report.pdf")]


# --- the Window Manager tab ---------------------------------------------------------------------------

def test_the_window_manager_acts_on_the_selected_window(monkeypatch):
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QTableWidgetItem
    _app = QApplication.instance() or QApplication([])
    from je_auto_control.gui import window_tab
    monkeypatch.setattr(window_tab, "list_windows", lambda: [])
    backend = _Backend([])
    monkeypatch.setattr(window_tab, "get_backend", lambda: backend)
    tab = window_tab.WindowManagerTab()
    table = tab._table  # noqa: SLF001
    table.setRowCount(2)
    for row, (window_id, title) in enumerate([(100, "*notes.txt - Notepad"), (200, "notes.txt - Notepad")]):
        table.setItem(row, 0, QTableWidgetItem(str(window_id)))
        table.setItem(row, 1, QTableWidgetItem(title))
    table.setCurrentCell(1, 0)
    tab._on_focus()  # noqa: SLF001
    tab._on_close()  # noqa: SLF001   (refreshes the table)
    assert backend.closed == [200] and backend.fronted == [200]
    tab.deleteLater()
