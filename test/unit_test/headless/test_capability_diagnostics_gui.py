"""Diagnostics explicitly renders passive capabilities and retranslates cached metadata without active checks."""
# ruff: noqa: E402  # reason: optional Qt and offscreen setup must precede GUI imports
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
from PySide6.QtWidgets import QApplication

from je_auto_control.gui import diagnostics_tab
from je_auto_control.gui.language_wrapper.multi_language_wrapper import LanguageWrapper
from je_auto_control.utils.exception.control_signals import OperationCancelledError
from je_auto_control.wrapper.capabilities import BackendContext, probe_capabilities

_APP = None


@pytest.mark.parametrize('language', ['English', 'Traditional_Chinese', 'Simplified_Chinese', 'Japanese'])
def test_every_base_catalogue_defines_capability_labels_without_english_fallback(language):
    catalogue = LanguageWrapper()._registry[language]
    keys = {'diag_probe', 'diag_cap_title', 'diag_cap_idle', 'diag_cap_snapshot', 'diag_cap_name',
            'diag_cap_backend', 'diag_cap_state', 'diag_cap_input', 'diag_cap_capture',
            'diag_cap_scope_desktop', 'diag_cap_scope_limited'}
    states = {'available', 'unverified', 'needs_permission', 'needs_dependency',
              'unsupported', 'paused', 'revoked', 'failed'}
    keys.update('diag_cap_state_'+state for state in states)
    assert keys <= set(catalogue), 'a base catalogue would silently fall back to English'


@pytest.fixture
def panel(monkeypatch):
    global _APP  # reason: retain the process-wide Qt application beyond individual widget teardown
    _APP = QApplication.instance() or QApplication([])
    context = BackendContext('linux', {'WAYLAND_DISPLAY': 'w',
                                      'JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND': 'cli'}, frozenset({'grim'}))
    snapshot = probe_capabilities(context)
    calls = []

    def passive(candidate):
        assert candidate is context
        calls.append('passive')
        return snapshot

    def forbidden():
        pytest.fail('passive capability inspection invoked active diagnostics')

    monkeypatch.setattr(BackendContext, 'current', classmethod(lambda _cls: context))
    monkeypatch.setattr(diagnostics_tab, 'probe_capabilities', passive, raising=False)
    monkeypatch.setattr(diagnostics_tab, 'run_diagnostics', forbidden)
    widget = diagnostics_tab.DiagnosticsTab()
    try:
        yield widget, snapshot, calls
    finally:
        widget.deleteLater()


def test_capability_inspection_is_explicit_and_matches_the_headless_snapshot(panel):
    widget, snapshot, calls = panel
    assert calls == []
    dict(widget.menu_actions())['diag_probe']()
    assert calls == ['passive'] and widget._table.rowCount() == 0
    table = widget._capability_view._table
    assert table.rowCount() == 2
    assert table.item(0, 1).text() == snapshot.input.backend
    assert table.item(1, 1).text() == snapshot.capture.backend
    assert snapshot.input.recovery in table.item(0, 3).text()


@pytest.mark.parametrize('language', ['English', 'Traditional_Chinese', 'Simplified_Chinese', 'Japanese'])
def test_translating_a_passive_snapshot_never_reexecutes_the_probe(panel, monkeypatch, language):
    from je_auto_control.gui import diagnostics_capabilities
    widget, _snapshot, calls = panel
    wrapper = LanguageWrapper()
    monkeypatch.setattr(diagnostics_tab, 'language_wrapper', wrapper)
    monkeypatch.setattr(diagnostics_capabilities, 'language_wrapper', wrapper)
    dict(widget.menu_actions())['diag_probe']()
    wrapper.reset_language(language)
    widget.retranslate()
    table = widget._capability_view._table
    assert calls == ['passive']
    assert table.item(0, 2).text() == wrapper.translate('diag_cap_state_needs_dependency')
    assert table.item(1, 2).text() == wrapper.translate('diag_cap_state_unverified')


def test_passive_probe_cancellation_retains_the_original_control(panel, monkeypatch):
    widget, _snapshot, calls = panel
    original = OperationCancelledError('passive probe')

    def canceled(_context):
        raise original

    monkeypatch.setattr(diagnostics_tab, 'probe_capabilities', canceled)
    with pytest.raises(OperationCancelledError) as caught:
        dict(widget.menu_actions())['diag_probe']()
    assert caught.value is original and calls == [] and widget._table.rowCount() == 0
