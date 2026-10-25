"""Existing handoff Actions display the bounded renewed review without inferring or issuing consent."""
import json
from types import SimpleNamespace

import pytest


def test_existing_handoff_action_and_result_keep_the_renewed_review_explicit(monkeypatch):
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.agent_tasks_tab import AgentTasksTab
    import shiboken6
    app = QApplication.instance() or QApplication([])
    tab = AgentTasksTab()
    try:
        requests = []
        monkeypatch.setattr(tab, '_dispatch', lambda name, payload: requests.append((name, payload)))
        operation = 'review_handoff'
        request = {'task_id': 'renewed-reader', 'batch_id': 'original-batch', 'node_id': 'a'}
        tab._handoff_operation.setCurrentIndex(tab._handoff_operation.findData(operation))
        tab._handoff_request.setPlainText(json.dumps(request))
        dict(tab.menu_actions())['agent_handoff_apply']()
        payload = {'operation': operation, 'request': request}
        assert requests == [('recovery', payload)]
        tab._select_request_view('recovery', payload)
        result = {'handoff_review': 'a' * 64, 'approval_required': True, 'evidence': {
            'completion_authorization': {'completion_task': 'renewed-reader', 'review': 'b' * 64,
                                         'approved_root_count': 1, 'replaced_origins': ['expired-origin']}}}
        tab._completed(SimpleNamespace(task_id='review', status='ok', value=result))
        assert json.loads(tab._output.toPlainText()) == result
        assert json.loads(tab._handoff_request.toPlainText()) == request and len(requests) == 1
    finally:
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()
