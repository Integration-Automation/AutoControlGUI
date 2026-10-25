"""Recovery Actions explicitly review and create read-only renewal through the existing request editor."""
import json

import pytest


@pytest.mark.parametrize(('action', 'operation'), [
    ('agent_completion_authorization_review', 'review_completion_authorization'),
    ('agent_completion_authorization_create', 'create_authorized_completion'),
])
def test_readonly_renewal_actions_use_the_shared_recovery_protocol(monkeypatch, action, operation):
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.agent_tasks_tab import AgentTasksTab
    import shiboken6
    app = QApplication.instance() or QApplication([])
    tab = AgentTasksTab()
    try:
        requests = []
        monkeypatch.setattr(tab, '_dispatch', lambda name, data: requests.append((name, data)))
        tab._task_id.setText('original-workflow')
        tab._present_remainder({'source_task': 'original-workflow', 'snapshot': 'a' * 64,
            'verification_spec': {'actions': []}, 'authorization_review': 'b' * 64})
        request = json.loads(tab._remainder_request.toPlainText())
        request['note'] = 'Reviewed this current read-only scope'
        tab._remainder_request.setPlainText(json.dumps(request))
        actions = dict(tab.menu_actions())
        assert action in actions
        actions[action]()
        assert requests[0][0] == 'recovery' and requests[0][1]['operation'] == operation
        expected = {'task_id': 'original-workflow'} if operation.startswith('review') else request
        assert requests[0][1]['request'] == expected
    finally:
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()
