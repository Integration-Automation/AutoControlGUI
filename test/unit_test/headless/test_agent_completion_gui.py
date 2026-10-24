"""Completion recovery stays a reviewed Actions-menu request, with no independent GUI execution logic."""
import json
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication  # noqa: E402  # reason: optional offscreen Qt after skip
from je_auto_control.gui.agent_tasks_tab import AgentTasksTab  # noqa: E402  # reason: optional Qt after skip


@pytest.mark.parametrize('source_owned', [False, True])
def test_actions_preserve_exact_completion_review_without_creating_an_executable_spec(monkeypatch, source_owned):
    import shiboken6
    app = QApplication.instance() or QApplication([])
    tab = AgentTasksTab()
    sent = []
    monkeypatch.setattr(tab, '_dispatch', lambda operation, body: sent.append((operation, body)))
    try:
        tab._task_id.setText('source-task')
        tab._owner_policy.setCurrentIndex(1 if source_owned else 0)
        actions = dict(tab.menu_actions())
        actions['agent_completion_preview']()
        request = {'task_id': 'source-task'} | ({'owner_policy': 'source_owner'} if source_owned else {})
        assert sent == [('recovery', {'operation': 'preview_completion', 'request': request})]
        response = {'source_task': 'source-task', 'snapshot': 'a' * 64, 'approval_required': True,
                    'verification_spec': {'goal': 'Review only', 'mode': 'external', 'actions': []}}
        if source_owned:
            response['ownership'] = {'review': 'b' * 64}
        tab._present_result(response)
        approved = json.loads(tab._remainder_request.toPlainText())
        assert approved['task_id'] == 'source-task' and approved['snapshot'] == 'a' * 64
        assert 'spec' not in approved and approved['note'] == ''
        approved['note'] = 'Reviewed independently'
        tab._remainder_request.setPlainText(json.dumps(approved))
        actions['agent_completion_create']()
        assert sent[-1] == ('recovery', {'operation': 'create_completion', 'request': approved})
    finally:
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()
