"""Opening or translating Diagnostics never starts active checks; its action remains explicit."""
# ruff: noqa: E402  # reason: optional Qt guard and offscreen setup must precede GUI imports
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)

from PySide6.QtWidgets import QApplication

from je_auto_control.gui import diagnostics_tab
from je_auto_control.gui.language_wrapper.multi_language_wrapper import LanguageWrapper
from je_auto_control.utils.diagnostics import diagnostics
from je_auto_control.utils.diagnostics.diagnostics import Check, DiagnosticsReport
from je_auto_control.utils.exception.control_signals import OperationCancelledError

_APP = None


@pytest.fixture
def tab(monkeypatch):
    global _APP  # reason: retain the process-wide Qt application after individual widgets retire
    _APP = QApplication.instance() or QApplication([])
    language = LanguageWrapper()
    monkeypatch.setattr(diagnostics_tab, 'language_wrapper', language)
    calls = []

    def run():
        calls.append('explicit run')
        return DiagnosticsReport([Check('controlled', False, 'error', 'controlled subsystem')])

    monkeypatch.setattr(diagnostics_tab, 'run_diagnostics', run)
    panel = diagnostics_tab.DiagnosticsTab()
    try:
        yield panel, language, calls
    finally:
        panel.deleteLater()


@pytest.mark.parametrize('language', ['English', 'Traditional_Chinese', 'Simplified_Chinese', 'Japanese'])
def test_opening_and_translating_diagnostics_keeps_an_honest_localized_idle_state(tab, language):
    panel, wrapper, calls = tab
    assert calls == [], 'merely opening Diagnostics started its active runner'
    wrapper.reset_language(language)
    panel.retranslate()
    assert calls == [] and panel._table.rowCount() == 0
    message = wrapper.translate('diag_summary_idle')
    assert message != 'diag_summary_idle' and panel._summary_label.text() == message
    assert panel._table.horizontalHeaderItem(3).text() == wrapper.translate('diag_col_detail')


def test_actions_menu_runs_the_existing_diagnostic_runner_once_and_displays_its_result(tab):
    panel, wrapper, calls = tab
    assert calls == []
    dict(panel.menu_actions())['diag_run']()
    assert calls == ['explicit run'] and panel._table.rowCount() == 1
    assert panel._table.item(0, 0).text() == 'controlled'
    assert panel._table.item(0, 3).text() == 'controlled subsystem'
    expected = wrapper.translate('diag_summary_failed').format(failed=1, count=1)
    assert panel._summary_label.text() == expected
    panel.retranslate()
    assert calls == ['explicit run'] and panel._summary_label.text() == expected


def test_explicit_cancellation_stays_original_and_allows_a_later_deliberate_retry(tab, monkeypatch):
    panel, wrapper, calls = tab
    assert calls == []
    original = OperationCancelledError('diagnostics action')

    def canceled():
        raise original

    action = dict(panel.menu_actions())['diag_run']
    monkeypatch.setattr(diagnostics_tab, 'run_diagnostics', canceled)
    with pytest.raises(OperationCancelledError) as caught:
        action()
    assert caught.value is original and calls == [] and panel._table.rowCount() == 0
    panel.retranslate()
    assert panel._summary_label.text() == wrapper.translate('diag_summary_idle')
    monkeypatch.setattr(diagnostics_tab, 'run_diagnostics', lambda: DiagnosticsReport([]))
    action()
    expected = wrapper.translate('diag_summary_ok').format(count=0)
    assert panel._summary_label.text() == expected


def test_a_real_check_cancellation_stops_the_gui_run_and_allows_an_explicit_retry(tab, monkeypatch):
    panel, wrapper, _calls = tab
    original = OperationCancelledError('real diagnostic check')
    events = []

    def cancelled():
        events.append('cancelled')
        raise original

    def later():
        events.append('later')
        return Check('later', True, 'info', 'controlled')

    monkeypatch.setattr(diagnostics, '_ALL_CHECKS', (cancelled, later))
    monkeypatch.setattr(diagnostics_tab, 'run_diagnostics', diagnostics.run_diagnostics)
    action = dict(panel.menu_actions())['diag_run']
    try:
        with pytest.raises(OperationCancelledError):
            action()
    finally:
        original.__traceback__ = None  # release GUI frames before queued widget destruction
    assert events == ['cancelled'] and panel._table.rowCount() == 0
    panel.retranslate()
    assert panel._summary_label.text() == wrapper.translate('diag_summary_idle')
    monkeypatch.setattr(diagnostics, '_ALL_CHECKS', (later,))
    action()
    assert events == ['cancelled', 'later'] and panel._table.rowCount() == 1
    assert panel._summary_label.text() == wrapper.translate('diag_summary_ok').format(count=1)
