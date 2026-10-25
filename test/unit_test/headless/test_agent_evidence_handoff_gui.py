"""Handoff Actions prepare editable evidence-only consent requests without dispatch."""
import json

import pytest


@pytest.mark.parametrize('operation', ['review_handoff', 'create_handoff', 'revoke_handoff'])
def test_actions_only_prepare_explicit_handoff_requests(monkeypatch, operation):
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.agent_tasks_tab import AgentTasksTab
    import shiboken6
    app = QApplication.instance() or QApplication([])
    tab = AgentTasksTab()
    monkeypatch.setattr(tab, '_dispatch', lambda *_args: pytest.fail('Preparing consent cannot dispatch'))
    try:
        tab._task_id.setText('not-an-inferred-recipient-or-source')
        dict(tab.menu_actions())['agent_handoff_example_' + operation]()
        assert tab._handoff_operation.currentData() == operation
        request = json.loads(tab._handoff_request.toPlainText())
        if operation == 'revoke_handoff':
            assert request == {'handoff_id': '<handoff-id>'}
        else:
            assert request['task_id'] == '<final-evidence-task-id>'
            assert request['batch_id'] == '<original-batch-id>' and request['node_id'] == '<node-id>'
            if operation == 'create_handoff':
                assert request['review'] == '<handoff-review-token>' and request['note'] == ''
        assert tab._pages.currentIndex() == tab._page_keys.index('agent_page_handoffs')
    finally:
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()
