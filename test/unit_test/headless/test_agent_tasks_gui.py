"""The managed task view never owns a running service or native task."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402  # reason: optional Qt import after skip

from je_auto_control.gui.agent_tasks_tab import AgentTasksTab  # noqa: E402  # reason: optional Qt import


def test_task_workspace_is_idle_and_uses_actions(monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []
    monkeypatch.setattr("je_auto_control.gui.agent_tasks_tab._request", lambda *args: calls.append(args))
    tab = AgentTasksTab()
    try:
        assert tab.findChildren(QPushButton) == []
        actions = dict(tab.menu_actions())
        assert {"agent_submit", "agent_pause", "agent_resume", "agent_cancel", "agent_skill_apply",
                "agent_skill_list"} <= set(actions)
        tab.retranslate()
        assert calls == []
    finally:
        import shiboken6
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()
    assert calls == []


def test_unavailable_remainder_draft_clears_approval_without_filling_the_task_form():
    import shiboken6
    app = QApplication.instance() or QApplication([])
    tab = AgentTasksTab()
    try:
        tab._task_id.setText("source-task")
        original_scope = tab._scope.toPlainText()
        tab._remainder_request.setPlainText('{"task_id":"stale-source"}')
        tab._present_result({"source_task": "source-task", "snapshot": "a" * 64,
                             "draft": None, "issues": ["unknown_source_effects"]})
        assert tab._remainder_request.toPlainText() == "{}"
        assert tab._scope.toPlainText() == original_scope
    finally:
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()


@pytest.mark.parametrize("change", ["none", "key", "task"])
def test_lookup_action_is_inspection_only_and_discards_stale_view_results(monkeypatch, change):
    from types import SimpleNamespace
    from je_auto_control.gui.task_controller import TaskOutcome

    app = QApplication.instance() or QApplication([])
    tab = AgentTasksTab()
    requests = []
    signal = SimpleNamespace(connect=lambda _slot: None)
    try:
        tab._request_key.setText("original-key")
        tab._task_id.setText("")
        handle = SimpleNamespace(task_id=42, outcome=None, finished=signal)
        monkeypatch.setattr(tab._controller, "submit", lambda request, **_kwargs: requests.append(request) or handle)
        dict(tab.menu_actions())["agent_lookup"]()
        assert requests[0].args == ("lookup", {"idempotency_key": "original-key"})
        if change == "key":
            tab._request_key.setText("another-key")
        elif change == "task":
            tab._task_id.setText("another-task")
        tab._completed(TaskOutcome(42, "ok", {"found": True, "task": {"task_id": "accepted-task"}}))
        expected = {"none": "accepted-task", "key": "", "task": "another-task"}[change]
        assert tab._task_id.text() == expected
        assert len(requests) == 1
    finally:
        import shiboken6
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()


def test_emergency_action_remains_available_during_an_active_view_request(monkeypatch):
    from types import SimpleNamespace
    app = QApplication.instance() or QApplication([])
    cancelled, submitted = [], []
    tab = AgentTasksTab()
    signal = SimpleNamespace(connect=lambda _slot: None)
    try:
        tab._handle = SimpleNamespace(outcome=None, cancel=lambda: cancelled.append(True))
        tab._task_id.setText("fixture-task")
        monkeypatch.setattr(tab._controller, "submit", lambda request, **_kwargs: (
            submitted.append(request) or SimpleNamespace(finished=signal, outcome=None)))
        tab._dispatch("cancel")
        assert cancelled == [True]
        assert submitted[0].args == ("cancel", {"task_id": "fixture-task"})
    finally:
        import shiboken6
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()


def test_view_request_cancellation_only_detaches_from_service_work(monkeypatch):
    from concurrent.futures import CancelledError
    from je_auto_control.gui.agent_tasks_tab import _request
    from je_auto_control.utils.exception.cancellation import CancellationToken
    calls = []

    class Client:
        def call(self, operation, *_args, **_kwargs):
            calls.append(operation)
            raise CancelledError()

    monkeypatch.setattr("je_auto_control.gui.agent_tasks_tab.AgentRuntimeClient", Client)
    monkeypatch.setattr("je_auto_control.utils.agent_runtime.api.AgentRuntimeClient", Client)
    with pytest.raises(CancelledError):
        _request("observe", {"task_id": "fixture"}, CancellationToken(1))
    assert calls == ["observe"]


@pytest.mark.parametrize("change_task", [False, True])
def test_remainder_preview_is_passive_bound_to_selected_task_and_requires_explicit_create(monkeypatch, change_task):
    import json
    import shiboken6
    from types import SimpleNamespace
    from je_auto_control.gui.task_controller import TaskOutcome
    app = QApplication.instance() or QApplication([])
    tab, requests = AgentTasksTab(), []
    signal = SimpleNamespace(connect=lambda _slot: None)
    handle = SimpleNamespace(task_id=42, outcome=None, finished=signal)
    try:
        monkeypatch.setattr(tab._controller, "submit", lambda request, **_kwargs: requests.append(request) or handle)
        tab._task_id.setText("source-task")
        original_scope = tab._scope.toPlainText()
        dict(tab.menu_actions())["agent_remainder_preview"]()
        assert requests[0].args == ("recovery", {"operation": "preview", "request": {"task_id": "source-task"}})
        if change_task:
            tab._task_id.setText("other-task")
        tab._completed(TaskOutcome(42, "ok", {"source_task": "source-task", "snapshot": "a" * 64,
                                             "draft": {"goal": "review remaining actions"}}))
        assert len(requests) == 1 and tab._scope.toPlainText() == original_scope
        review = json.loads(tab._remainder_request.toPlainText())
        if change_task:
            assert review == {}
            return
        assert review["task_id"] == "source-task" and review["note"] == ""
        handle.outcome = "finished"
        review["note"] = "Reviewed remaining actions in the new context"
        tab._remainder_request.setPlainText(json.dumps(review))
        dict(tab.menu_actions())["agent_remainder_create"]()
        assert requests[1].args == ("recovery", {"operation": "create", "request": review})
        tab._task_id.setText("different-task")
        assert tab._remainder_request.toPlainText() == "{}"
    finally:
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()


def test_dynamic_review_template_requires_manual_goal_and_note_without_submitting(monkeypatch):
    import json
    import shiboken6
    app = QApplication.instance() or QApplication([])
    tab = AgentTasksTab()
    submitted = []
    try:
        monkeypatch.setattr(tab, "_dispatch", lambda *args: submitted.append(args))
        tab._task_id.setText("source-task")
        original_scope = tab._scope.toPlainText()
        template = {"goal": "", "mode": "ollama", "options": {"model": "fixture-tools"}, "actions": []}
        tab._present_result({"source_task": "source-task", "source_mode": "ollama", "snapshot": "a" * 64,
            "draft": None, "review_template": template, "issues": ["new_plan_required"]})
        assert submitted == [] and tab._scope.toPlainText() == original_scope
        request = json.loads(tab._remainder_request.toPlainText())
        assert request["spec"]["goal"] == "" and request["note"] == ""
        request["spec"]["goal"] = "Read only the remaining field"
        request["note"] = "Reviewed the new plan"
        tab._remainder_request.setPlainText(json.dumps(request))
        dict(tab.menu_actions())["agent_remainder_create"]()
        assert submitted == [("recovery", {"operation": "create", "request": request})]
    finally:
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()
