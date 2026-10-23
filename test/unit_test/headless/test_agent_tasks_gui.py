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
        assert {"agent_submit", "agent_pause", "agent_resume", "agent_cancel"} <= set(actions)
        tab.retranslate()
        assert calls == []
    finally:
        import shiboken6
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()
    assert calls == []


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
