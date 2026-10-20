"""Diagnostics Actions stay responsive, stop active checks, and reject late results after closing."""
# ruff: noqa: E402  # reason: optional Qt and offscreen setup precede GUI imports
import os
import threading
import time

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from je_auto_control.gui import diagnostics_tab
from je_auto_control.gui.language_wrapper.multi_language_wrapper import LanguageWrapper
from je_auto_control.utils.diagnostics import diagnostics
from je_auto_control.utils.exception.cancellation import current_cancellation_token
from je_auto_control.utils.exception.control_signals import OperationCancelledError

_APP = None


def _pump(app, predicate, timeout=3.0):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        threading.Event().wait(0.001)
    return predicate()


@pytest.fixture
def panel(monkeypatch):
    global _APP  # reason: keep the one Qt application alive across widget retirement
    _APP = QApplication.instance() or QApplication([])
    language = LanguageWrapper()
    monkeypatch.setattr(diagnostics_tab, 'language_wrapper', language)
    widget = diagnostics_tab.DiagnosticsTab()
    try:
        yield _APP, widget, language
    finally:
        if isValid(widget):
            widget.close()
            if hasattr(widget, '_task_controller'):
                assert _pump(_APP, lambda: widget._task_controller.active_count == 0)
            widget.deleteLater()


def test_active_actions_run_off_the_gui_thread_and_duplicate_run_is_ignored(panel, monkeypatch):
    app, widget, _language = panel
    entered, release = threading.Event(), threading.Event()
    threads, ticks = [], []

    def controlled():
        threads.append(threading.get_ident())
        entered.set()
        release.wait(2)
        return diagnostics.DiagnosticsReport([diagnostics.Check('controlled', True, 'info', 'done')])

    monkeypatch.setattr(diagnostics_tab, 'run_diagnostics', controlled)
    run = dict(widget.menu_actions())['diag_run']
    try:
        run()
        assert entered.wait(1)
        assert threads == [threads[0]] and threads[0] != threading.get_ident()
        run()
        QTimer.singleShot(0, lambda: ticks.append('tick'))
        assert _pump(app, lambda: ticks)
        assert len(threads) == 1 and widget._table.rowCount() == 0
    finally:
        release.set()
    assert _pump(app, lambda: widget._active_task is None and widget._table.rowCount() == 1)


def test_stop_reaches_the_active_check_and_allows_a_deliberate_retry(panel, monkeypatch):
    app, widget, language = panel
    entered = threading.Event()
    calls = []

    def waiting():
        token = current_cancellation_token()
        assert token is not None
        calls.append('waiting')
        entered.set()
        token.wait(3)
        token.checkpoint()
        return diagnostics.Check('waiting', True, 'info', 'unreachable')

    def later():
        calls.append('later')
        return diagnostics.Check('later', True, 'info', 'controlled')

    monkeypatch.setattr(diagnostics, '_ALL_CHECKS', (waiting, later))
    monkeypatch.setattr(diagnostics_tab, 'run_diagnostics', diagnostics.run_diagnostics)
    actions = dict(widget.menu_actions())
    assert 'diag_stop' in actions
    actions['diag_run']()
    assert entered.wait(1)
    actions['diag_stop']()
    assert _pump(app, lambda: widget._active_task is None)
    assert calls == ['waiting'] and widget._table.rowCount() == 0
    assert widget._summary_label.text() == language.translate('diag_summary_cancelled')
    monkeypatch.setattr(diagnostics, '_ALL_CHECKS', (later,))
    actions['diag_run']()
    assert _pump(app, lambda: widget._active_task is None and widget._table.rowCount() == 1)
    assert calls == ['waiting', 'later']
    assert widget._summary_label.text() == language.translate('diag_summary_ok').format(count=1)


def test_close_drops_a_late_success_instead_of_populating_a_closed_panel(panel, monkeypatch):
    app, widget, _language = panel
    entered, release = threading.Event(), threading.Event()

    def uncooperative():
        entered.set()
        release.wait(2)
        return diagnostics.DiagnosticsReport([diagnostics.Check('late', True, 'info', 'must be ignored')])

    monkeypatch.setattr(diagnostics_tab, 'run_diagnostics', uncooperative)
    try:
        dict(widget.menu_actions())['diag_run']()
        assert entered.wait(1)
        widget.close()
    finally:
        release.set()
    assert _pump(app, lambda: widget._task_controller.active_count == 0)
    assert widget._table.rowCount() == 0 and widget._active_task is None


@pytest.mark.parametrize('language', ['English', 'Traditional_Chinese', 'Simplified_Chinese', 'Japanese'])
def test_retranslation_of_running_and_stopping_states_never_restarts_checks(panel, monkeypatch, language):
    app, widget, wrapper = panel
    entered = threading.Event()
    calls = []

    def waiting():
        token = current_cancellation_token()
        assert token is not None
        calls.append('waiting')
        entered.set()
        token.wait(3)
        token.checkpoint()

    monkeypatch.setattr(diagnostics_tab, 'run_diagnostics', waiting)
    dict(widget.menu_actions())['diag_run']()
    assert entered.wait(1)
    wrapper.reset_language(language)
    widget.retranslate()
    assert calls == ['waiting']
    assert wrapper.translate('diag_summary_running') in widget._summary_label.text()
    dict(widget.menu_actions())['diag_stop']()
    widget.retranslate()
    assert calls == ['waiting']
    assert _pump(app, lambda: widget._active_task is None)
    assert widget._summary_label.text() == wrapper.translate('diag_summary_cancelled')


def test_destroying_the_widget_cancels_its_wait_without_touching_destroyed_controls(panel, monkeypatch):
    app, widget, _language = panel
    entered, cleaned = threading.Event(), threading.Event()

    def waiting():
        token = current_cancellation_token()
        assert token is not None
        entered.set()
        try:
            token.wait(3)
            token.checkpoint()
        finally:
            cleaned.set()

    monkeypatch.setattr(diagnostics_tab, 'run_diagnostics', waiting)
    dict(widget.menu_actions())['diag_run']()
    assert entered.wait(1)
    controller = widget._task_controller
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert _pump(app, lambda: cleaned.is_set() and controller.active_count == 0)
    assert not isValid(widget)


@pytest.mark.parametrize('language', ['English', 'Traditional_Chinese', 'Simplified_Chinese', 'Japanese'])
def test_all_base_catalogues_define_explicit_async_diagnostic_states(language):
    catalogue = LanguageWrapper()._registry[language]
    assert {'diag_stop', 'diag_summary_running', 'diag_summary_stopping', 'diag_summary_cancelled',
            'diag_summary_error', 'diag_progress'} <= set(catalogue)


def test_runner_error_is_displayed_as_plain_text_and_the_action_can_retry(panel, monkeypatch):
    app, widget, language = panel

    def broken():
        raise ValueError('<b>controlled error</b>')

    monkeypatch.setattr(diagnostics_tab, 'run_diagnostics', broken)
    run = dict(widget.menu_actions())['diag_run']
    run()
    assert _pump(app, lambda: widget._active_task is None)
    assert 'controlled error' in widget._summary_label.text() and widget._table.rowCount() == 0
    assert widget._summary_label.textFormat().name == 'PlainText'
    monkeypatch.setattr(diagnostics_tab, 'run_diagnostics', lambda: diagnostics.DiagnosticsReport([]))
    run()
    assert _pump(app, lambda: widget._active_task is None)
    assert widget._summary_label.text() == language.translate('diag_summary_ok').format(count=0)


def test_failed_submission_restores_an_error_state_without_a_phantom_active_task(panel, monkeypatch):
    _app, widget, _language = panel

    def failed_start(*_args, **_kwargs):
        raise RuntimeError('controlled startup failure')

    monkeypatch.setattr(widget._task_controller, 'submit', failed_start)
    dict(widget.menu_actions())['diag_run']()
    assert widget._active_task is None and 'controlled startup failure' in widget._summary_label.text()


def test_synchronous_submission_cancellation_keeps_the_original_control_and_restores_ui(panel, monkeypatch):
    _app, widget, language = panel
    original = OperationCancelledError('submit')

    def failed_start(*_args, **_kwargs):
        raise original

    monkeypatch.setattr(widget._task_controller, 'submit', failed_start)
    try:
        try:
            dict(widget.menu_actions())['diag_run']()
        except OperationCancelledError as caught:
            assert caught is original
        else:
            pytest.fail('submission cancellation was converted into an ordinary failure')
    finally:
        original.__traceback__ = None
    assert widget._active_task is None
    assert widget._summary_label.text() == language.translate('diag_summary_cancelled')
