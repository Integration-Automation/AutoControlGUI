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
