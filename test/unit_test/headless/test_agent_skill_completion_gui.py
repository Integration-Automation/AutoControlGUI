"""The skill completion example prepares an explicit review request without submitting or publishing."""
import json

import pytest


def test_gui_prepares_separate_trial_and_completion_fields_without_dispatch(monkeypatch):
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.agent_tasks_tab import AgentTasksTab
    import shiboken6
    app = QApplication.instance() or QApplication([])
    tab = AgentTasksTab()
    monkeypatch.setattr(tab, '_dispatch', lambda *_args: pytest.fail('Preparing review must not dispatch'))
    try:
        tab._task_id.setText('reviewed-completion')
        dict(tab.menu_actions())['agent_skill_completion_example']()
        request = json.loads(tab._skill_request.toPlainText())
        assert tab._skill_operation.currentData() == 'accept'
        assert request == {'candidate_id': '<candidate-id>', 'task_id': '<original-validation-task-id>',
                           'completion_task_id': 'reviewed-completion', 'expected_version': 0, 'note': ''}
        assert tab._pages.currentIndex() == tab._page_keys.index('agent_page_skills')
    finally:
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()
