"""Candidate previews never import or execute actions without the separate menu."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
from PySide6.QtWidgets import QApplication


@pytest.fixture
def panel(tmp_path):
    from je_auto_control.gui.journal_candidate_panel import JournalCandidatePanel
    app = QApplication.instance() or QApplication([])
    imports = []
    widget = JournalCandidatePanel(lambda: [['AC_sleep', {'seconds': 0}]], imports.append)
    yield widget, imports
    widget.close()
    widget.deleteLater()
    app.processEvents()


def test_preview_diff_is_read_only_and_import_is_explicit(panel, monkeypatch, tmp_path):
    from je_auto_control.gui import journal_candidate_panel as gui
    from je_auto_control.utils.codegen.candidate_models import CandidateScript
    widget, imports = panel
    calls = []
    candidate = CandidateScript('# observed\n', {'journal_path': str(tmp_path / 'journal.jsonl')},
                                 ('observed path only',), True, [['AC_sleep', {'seconds': 1}]])
    monkeypatch.setattr(gui, 'generate_candidate_from_log',
                        lambda path, **kwargs: calls.append((path, kwargs)) or candidate)
    monkeypatch.setattr(widget, '_submit', lambda function: widget._show_result(function()))
    widget.journal.setText('journal.jsonl')
    widget.run_id.setText('selected')
    actions = dict(widget.menu_actions())
    actions['journal_candidate_preview']()
    assert calls[0][1]['run_id'] == 'selected'
    assert imports == []
    assert widget.preview.isReadOnly()
    assert '--- current' in widget.preview.toPlainText() and '+++ observed' in widget.preview.toPlainText()
    actions['journal_candidate_import']()
    assert imports == [candidate.actions]


def test_editor_and_builder_offer_same_candidate_menu_without_running(tmp_path, monkeypatch):
    from je_auto_control.gui.recording_editor_tab import RecordingEditorTab
    from je_auto_control.gui.script_builder.builder_tab import ScriptBuilderTab
    from je_auto_control.gui.script_builder.step_model import steps_to_actions
    app = QApplication.instance() or QApplication([])
    editor, builder = RecordingEditorTab(), ScriptBuilderTab()
    try:
        expected = {'journal_candidate_preview', 'journal_candidate_import', 'journal_candidate_export'}
        assert expected <= dict(editor.menu_actions()).keys()
        assert expected <= dict(builder.menu_actions()).keys()
        data = [['AC_sleep', {'seconds': 0}]]
        builder._import_candidate(data)
        assert steps_to_actions(builder._tree.root_steps()) == data
        editor._journal_candidate._set_actions(data)
        assert editor._actions == data
    finally:
        editor.close()
        builder.close()
        editor.deleteLater()
        builder.deleteLater()
        app.processEvents()
