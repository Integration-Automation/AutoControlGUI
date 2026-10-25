"""Task-source handoff controls prepare explicit JSON and never infer or dispatch consent."""
import json

import pytest


@pytest.fixture
def tab(monkeypatch):
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.agent_tasks_tab import AgentTasksTab
    import shiboken6
    app = QApplication.instance() or QApplication([])
    widget = AgentTasksTab()
    calls = []
    monkeypatch.setattr(widget, '_dispatch', lambda name, payload: calls.append((name, payload)))
    try:
        yield widget, calls
    finally:
        widget.close()
        shiboken6.delete(widget)
        app.processEvents()


def test_explicit_task_source_mode_prepares_a_real_source_request_without_fabricating_dag_fields(tab, monkeypatch):
    from PySide6.QtWidgets import QComboBox
    widget, calls = tab
    mode = widget.findChild(QComboBox, 'agent_handoff_scope')
    assert mode is not None, 'Handoffs needs an explicit original-task source choice'
    mode.setCurrentIndex(mode.findData('task'))
    widget._task_id.setText('reviewed-reader')
    actions = dict(widget.menu_actions())
    actions['agent_handoff_example_review_handoff']()
    request = json.loads(widget._handoff_request.toPlainText())
    assert request == {'task_id': 'reviewed-reader', 'source_task': '<original-source-task-id>'}
    assert calls == []
    monkeypatch.setattr('je_auto_control.gui.agent_tasks_tab._translate', lambda key: 'translated:' + key)
    widget.retranslate()
    assert mode.currentData() == 'task' and mode.currentText().startswith('translated:')
    request['source_task'] = 'actual-original-task'
    widget._handoff_request.setPlainText(json.dumps(request))
    actions['agent_handoff_apply']()
    assert calls == [('recovery', {'operation': 'review_handoff', 'request': request})]


def test_skill_actions_prepare_selected_grant_adoption_without_issuing_or_publishing_it(tab):
    widget, calls = tab
    widget._task_id.setText('reviewed-evidence-task')
    actions = dict(widget.menu_actions())
    for name, operation, selected in (
        ('agent_skill_recording_handoff_example', 'record', 'completion_task_id'),
        ('agent_skill_publication_handoff_example', 'accept', 'completion_task_id'),
        ('agent_skill_execution_handoff_example', 'review_execution', 'execution_task_id'),
    ):
        assert name in actions, 'Existing skill Actions must expose explicit grant selection'
        actions[name]()
        request = json.loads(widget._skill_request.toPlainText())
        assert widget._skill_operation.currentData() == operation
        assert request['handoff_id'] == '<handoff-id>' and request[selected] == 'reviewed-evidence-task'
    assert calls == []
