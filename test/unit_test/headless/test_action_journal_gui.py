"""Run History journal actions keep preview read-only and recording explicit."""
import json
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
from PySide6.QtWidgets import QApplication

from je_auto_control.gui import run_history_tab as gui
from je_auto_control.utils.run_history.history_store import HistoryStore


@pytest.fixture
def tab(monkeypatch):
    app = QApplication.instance() or QApplication([])
    store = HistoryStore(':memory:')
    monkeypatch.setattr(gui, 'default_history_store', store)
    widget = gui.RunHistoryTab()
    widget._timer.stop()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()
    store.close()


def test_preview_uses_selected_run_without_executing(tab, monkeypatch):
    calls = []
    monkeypatch.setattr(gui, 'list_journal_runs', lambda path: [{'run_id': 'selected'}])
    monkeypatch.setattr(gui, 'read_action_journal', lambda path, run_id: calls.append((path, run_id)) or [])
    monkeypatch.setattr(gui, 'execute_journaled', lambda *args, **kwargs: pytest.fail('preview executed actions'))
    monkeypatch.setattr(tab, '_start_journal_worker', lambda function: tab._journal_done(function()))
    tab._journal_path.setText('fixture.jsonl')
    tab._journal_run.setText('selected')
    dict(tab.menu_actions())['journal_preview']()
    assert calls == [('fixture.jsonl', 'selected')]
    assert json.loads(tab._journal_view.toPlainText())['events'] == []
    assert tab._journal_view.isReadOnly()


def test_record_uses_explicit_script_and_destination(tab, monkeypatch, tmp_path):
    script = tmp_path / 'actions.json'
    script.write_text(json.dumps([['AC_sleep', {'seconds': 0}]]), encoding='utf-8')
    calls = []
    monkeypatch.setattr(gui.QFileDialog, 'getOpenFileName', lambda *args: (str(script), ''))
    monkeypatch.setattr(gui, 'execute_journaled', lambda actions, path, run_id:
                        calls.append((actions, path, run_id)) or {'status': 'ok'})
    monkeypatch.setattr(tab, '_start_journal_worker', lambda function: tab._journal_done(function()))
    tab._journal_path.setText(str(tmp_path / 'record.jsonl'))
    tab._journal_run.setText('recorded')
    dict(tab.menu_actions())['journal_record']()
    assert calls == [([['AC_sleep', {'seconds': 0}]], str(tmp_path / 'record.jsonl'), 'recorded')]
