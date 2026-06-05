"""GUI smoke tests for the QA tabs (assertions / data source / flakiness)."""
import os

import pytest

pytest.importorskip("PySide6.QtWidgets")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from je_auto_control.gui.assertions_tab import AssertionsTab  # noqa: E402
from je_auto_control.gui.data_source_tab import DataSourceTab  # noqa: E402
from je_auto_control.gui.flakiness_tab import FlakinessTab  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_flakiness_tab_refreshes(app):
    tab = FlakinessTab()
    tab._refresh()
    assert tab._status.text() != ""


def test_data_source_tab_loads_inline(app):
    tab = DataSourceTab()
    tab._kind.setCurrentText("inline")
    tab._inline.setPlainText('[{"u": "x"}, {"u": "y"}]')
    tab._on_load()
    assert tab._table.rowCount() == 2
    assert tab._table.columnCount() == 1


def test_data_source_tab_reports_error(app):
    tab = DataSourceTab()
    tab._kind.setCurrentText("csv")
    tab._path.setText("/no/such/file_zzz.csv")
    tab._on_load()
    assert "fail" in tab._status.text().lower() or tab._status.text()


def test_assertions_tab_window_check(app, monkeypatch):
    import je_auto_control.wrapper.auto_control_window as win
    monkeypatch.setattr(win, "list_windows", lambda: [(1, "Calculator")])
    tab = AssertionsTab()
    tab._kind.setCurrentIndex(3)  # window
    tab._target.setText("Calculator")
    tab._expect.setChecked(True)
    tab._on_run()
    assert "PASS" in tab._result.text() or "pass" in tab._result.text().lower()
