"""The Accessibility and A11y Audit tabs run their commands off the GUI thread (offscreen Qt, fakes only).

They were the last tabs still calling a backend from a slot: the Windows UIA
backend kept one COM object for whichever thread came first, so moving the call
was not safe until each thread had its own. Every backend call here is a fake;
nothing reads the real accessibility tree and nothing clicks.
"""
import os
import threading
import time
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from je_auto_control.gui import a11y_audit_tab, accessibility_tab  # noqa: E402
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper  # noqa: E402
from je_auto_control.utils.accessibility.element import (  # noqa: E402
    AccessibilityElement, AccessibilityNotAvailableError,
)
from headless._qt_settle import deleting, pump_until  # noqa: E402

_PROMPT_S = 5.0


def _t(key):
    return language_wrapper.translate(key, key)


@pytest.fixture(autouse=True)
def qapp(monkeypatch):
    app = QApplication.instance() or QApplication([])
    messages = []
    for box in ("warning", "information", "question", "critical"):
        monkeypatch.setattr(QMessageBox, box, lambda *args: messages.append(args[-1]))
    app.messages = messages
    return app


@pytest.fixture(autouse=True)
def _tabs_deleted():
    with deleting(accessibility_tab.AccessibilityTab, a11y_audit_tab.A11yAuditTab):
        yield


class _Backend:
    """Stands in for the three accessibility calls; each records its thread and can be held."""

    def __init__(self, monkeypatch):
        self.hold, self.threads, self.calls = threading.Event(), [], []
        self.hold.set()
        self.elements = [_element("OK"), _element("Cancel"), _element("ok again")]
        self.focused, self.clicked, self.error = _element("Field"), True, None
        monkeypatch.setattr(accessibility_tab, "list_accessibility_elements", self._list)
        monkeypatch.setattr(accessibility_tab, "focused_accessibility_element", self._focused)
        monkeypatch.setattr(accessibility_tab, "click_accessibility_element", self._click)

    def _enter(self, call, kwargs):
        self.threads.append(threading.current_thread())
        self.calls.append((call, kwargs))
        self.hold.wait(30.0)
        if self.error is not None:
            raise self.error

    def _list(self, **kwargs):
        self._enter("list", kwargs)
        return list(self.elements)

    def _focused(self, **kwargs):
        self._enter("focused", kwargs)
        return self.focused

    def _click(self, **kwargs):
        self._enter("click", kwargs)
        return self.clicked


def _element(name):
    return AccessibilityElement(name=name, role="ControlType_50000", bounds=(1, 2, 30, 40),
                                app_name="app.exe", process_id=7, native_id=name.lower())


@pytest.fixture
def backend(monkeypatch):
    fake = _Backend(monkeypatch)
    yield fake
    fake.hold.set()


def _timed(call):
    started = time.monotonic()
    call()
    return time.monotonic() - started


def _idle(tab):
    return pump_until(lambda: not tab._task.running)


def test_refresh_lists_on_a_worker_thread_and_fills_the_table_when_it_answers(backend):
    tab = accessibility_tab.AccessibilityTab()
    tab._app_filter.setText("app.exe")
    tab._window_filter.setText("Editor")
    tab._name_filter.setText("OK")
    backend.hold.clear()
    assert _timed(tab._refresh) < _PROMPT_S
    assert tab._status.text() == _t("task_running")
    assert tab._table.rowCount() == 0
    tab._refresh()                          # a second command while one runs starts nothing
    backend.hold.set()
    assert _idle(tab)
    assert backend.calls == [("list", {"app_name": "app.exe", "window_title": "Editor"})]
    assert backend.threads[0] is not threading.main_thread()
    assert [tab._table.item(row, 2).text() for row in range(tab._table.rowCount())] == ["OK", "ok again"]
    assert tab._status.text() == _t("a11y_count_label").replace("{n}", "2")


def test_a_listing_that_fails_says_why_and_empties_the_table(backend):
    tab = accessibility_tab.AccessibilityTab()
    tab._refresh()
    assert _idle(tab)
    assert tab._table.rowCount() == 3
    backend.error = AccessibilityNotAvailableError("install comtypes")
    tab._refresh()
    assert _idle(tab)
    assert tab._status.text() == "install comtypes"
    assert tab._table.rowCount() == 0


def test_show_focused_reads_off_thread_and_reports_nothing_focused(backend):
    tab = accessibility_tab.AccessibilityTab()
    tab._show_focused()
    assert _idle(tab)
    assert backend.threads[0] is not threading.main_thread()
    assert tab._table.rowCount() == 1
    assert tab._table.item(0, 2).text() == "Field"
    assert tab._status.text() == _t("a11y_count_label").replace("{n}", "1")
    backend.focused = None
    tab._show_focused()
    assert _idle(tab)
    assert tab._table.rowCount() == 0
    assert tab._status.text() == _t("a11y_no_focus")


def test_click_selected_clicks_off_thread_and_reports_a_miss_or_a_missing_backend(backend, qapp):
    tab = accessibility_tab.AccessibilityTab()
    tab._click_selected()
    assert tab._status.text() == _t("a11y_no_selection")
    assert backend.calls == []
    tab._refresh()
    assert _idle(tab)
    tab._table.setCurrentCell(1, 0)
    tab._click_selected()
    assert _idle(tab)
    assert backend.calls[-1] == ("click", {"name": "Cancel", "role": "ControlType_50000", "app_name": "app.exe"})
    assert backend.threads[-1] is not threading.main_thread()
    assert tab._status.text() == ""
    backend.clicked = False
    tab._click_selected()
    assert _idle(tab)
    assert tab._status.text() == _t("a11y_click_not_found")
    backend.error = AccessibilityNotAvailableError("no backend")
    tab._click_selected()
    assert _idle(tab)
    assert qapp.messages == ["no backend"]


def test_a_released_accessibility_tab_drops_the_answer_still_out(backend):
    tab = accessibility_tab.AccessibilityTab()
    backend.hold.clear()
    tab._refresh()
    tab.dispose()
    backend.hold.set()
    assert _idle(tab)
    pump_until(lambda: False, timeout=0.2)
    assert tab._table.rowCount() == 0
    tab.dispose()


def test_the_audit_runs_off_thread_and_renders_its_report(monkeypatch):
    hold, threads = threading.Event(), []

    def run_audit(app_name=None):
        threads.append((threading.current_thread(), app_name))
        hold.wait(30.0)
        report = {"issues": [{"kind": "missing_label", "severity": "error", "target": "Button", "message": "no name"}],
                  "error_count": 1, "warning_count": 0}
        return types.SimpleNamespace(to_dict=lambda: report)

    monkeypatch.setattr(a11y_audit_tab.ac, "run_audit", run_audit)
    tab = a11y_audit_tab.A11yAuditTab()
    tab._app.setText("app.exe")
    assert _timed(tab._on_run) < _PROMPT_S
    assert tab._summary.text() == _t("task_running")
    tab._on_run()                           # ignored while the first runs
    hold.set()
    assert _idle(tab)
    assert len(threads) == 1
    assert threads[0][0] is not threading.main_thread()
    assert threads[0][1] == "app.exe"
    assert tab._table.rowCount() == 1
    assert tab._table.item(0, 3).text() == "no name"
    assert tab._summary.text() == _t("audit_summary").replace("{errors}", "1").replace("{warnings}", "0")


def test_an_audit_that_fails_says_why(monkeypatch):
    def run_audit(app_name=None):
        raise AccessibilityNotAvailableError("no accessibility backend")

    monkeypatch.setattr(a11y_audit_tab.ac, "run_audit", run_audit)
    tab = a11y_audit_tab.A11yAuditTab()
    tab._on_run()
    assert _idle(tab)
    assert tab._summary.text() == "no accessibility backend"


def test_the_contrast_check_still_answers_at_once():
    tab = a11y_audit_tab.A11yAuditTab()
    tab._fg.setText("0, 0, 0")
    tab._bg.setText("255, 255, 255")
    tab._on_contrast()
    assert "21.00" in tab._summary.text()
    assert "PASS" in tab._summary.text()
