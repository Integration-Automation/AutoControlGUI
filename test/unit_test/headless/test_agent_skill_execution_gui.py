"""GUI examples prepare explicit full-chain review and acceptance without executing either."""
import json

import pytest


@pytest.mark.parametrize('operation,key', [
    ('review_execution', 'agent_skill_execution_review_example'),
    ('accept', 'agent_skill_execution_accept_example'),
])
def test_gui_prepares_original_trial_and_separate_execution_without_dispatch(monkeypatch, operation, key):
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.agent_tasks_tab import AgentTasksTab
    import shiboken6
    app = QApplication.instance() or QApplication([])
    tab = AgentTasksTab()
    monkeypatch.setattr(tab, '_dispatch', lambda *_args: pytest.fail('Preparing a request must not dispatch'))
    try:
        tab._task_id.setText('actual-final-executable-successor')
        dict(tab.menu_actions())[key]()
        request = json.loads(tab._skill_request.toPlainText())
        expected = {'candidate_id': '<candidate-id>', 'task_id': '<original-validation-task-id>',
                    'execution_task_id': 'actual-final-executable-successor'}
        if operation == 'accept':
            expected.update(execution_review='<review-token>', expected_version=0, note='')
        assert request == expected and tab._skill_operation.currentData() == operation
        assert tab._pages.currentIndex() == tab._page_keys.index('agent_page_skills')
    finally:
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()
