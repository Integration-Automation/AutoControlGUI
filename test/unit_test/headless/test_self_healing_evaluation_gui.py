"""Self-Healing comparison and revision menus delegate to the same headless APIs."""
import json
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
from PySide6.QtWidgets import QApplication


@pytest.fixture
def panel():
    from je_auto_control.gui.self_healing_evaluation import SelfHealingEvaluationPanel
    app = QApplication.instance() or QApplication([])
    widget = SelfHealingEvaluationPanel(lambda: 'baseline.png')
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def test_compare_menu_preserves_selected_versions_and_dataset(panel, monkeypatch):
    from je_auto_control.gui import self_healing_evaluation as gui
    calls = []
    monkeypatch.setattr(gui, 'compare_healing_versions', lambda dataset_path, versions, report_path:
                        calls.append((dataset_path, versions, report_path)) or {'sample_count': 1})
    monkeypatch.setattr(panel, '_submit', lambda function: panel._show_result(gui.prepare_preview(function())))
    panel.dataset.setText('dataset.json')
    panel.versions.setPlainText('{"v2":{"template_path":"candidate.png"}}')
    dict(panel.menu_actions())['heal_eval_compare']()
    assert calls == [('dataset.json', '{"v2":{"template_path":"candidate.png"}}', None)]
    assert json.loads(panel.results.toPlainText()) == {'sample_count': 1}
    assert panel.results.isReadOnly()


def test_preview_is_read_only_and_accept_is_a_separate_menu_action(panel, monkeypatch):
    from je_auto_control.gui import self_healing_evaluation as gui
    calls = []
    monkeypatch.setattr(gui, 'preview_template_candidate', lambda store_path, revision_id:
                        calls.append(('preview', store_path, revision_id)) or {'revision_id': revision_id})
    monkeypatch.setattr(gui, 'accept_template_candidate', lambda *args: pytest.fail('preview accepted a candidate'))
    monkeypatch.setattr(panel, '_submit', lambda function: panel._show_result(gui.prepare_preview(function())))
    panel.store.setText('revisions')
    panel.revision.setText('a' * 32)
    actions = dict(panel.menu_actions())
    assert 'heal_eval_accept' in actions and 'heal_eval_revert' in actions
    actions['heal_eval_preview']()
    assert calls == [('preview', 'revisions', 'a' * 32)]
