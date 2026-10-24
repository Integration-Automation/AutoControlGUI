"""Trigger authorization remains passive until explicit creation across HTTP/CLI/GUI."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from je_auto_control.cli import build_parser
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.origin_policy import origin_scope
from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from .test_agent_origin_policy import origin_directory as origin_directory
from .test_agent_trigger_reauthorization import retired_trigger as retired_trigger


def test_cli_exposes_review_and_explicit_creation():
    for operation in ("review_authorization", "create_authorized"):
        parsed = build_parser().parse_args(["agent-task", "trigger", operation, "review.json"])
        assert parsed.trigger_operation == operation and parsed.request == "review.json"


def test_authenticated_http_preserves_owner_and_does_not_dispatch_inherited_queued_tasks(retired_trigger, monkeypatch):
    runtime, source, old_task, _old_id, current_id, _allowed, _narrow = retired_trigger
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_triggers SET owner=? WHERE id=?",
                           (json.dumps({"user_id": "alice", "role": "operator", "store_path": None}), source))
    runtime.close()
    instance = AgentRuntimeService(Path(runtime.store.path).parent, targets={"fixture": object()})
    start = Mock()
    monkeypatch.setattr(instance.runtime.background, "start", start)
    try:
        instance.start()
        start.reset_mock()
        client = AgentRuntimeClient(instance.directory / "agent_runtime.json")
        with origin_scope(current_id), authorization_scope(AuthorizationContext("alice", "operator")):
            view = client.call("trigger", {"operation": "review_authorization", "request": {"trigger_id": source}})
            request = {"trigger_id": source, "snapshot": view["snapshot"], "spec": view["spec"],
                       "authorization_review": view["authorization_review"], "note": "Reviewed future report events"}
            child = client.call("trigger", {"operation": "create_authorized", "request": request})["trigger_id"]
            start.assert_not_called()
            duplicate = client.call("trigger", {"operation": "fire", "request": {"trigger_id": child,
                "event_key": "old-event", "payload": {"row": 1}}})
            assert duplicate["duplicate"] and duplicate["task_id"] == old_task
            start.assert_not_called()
            proof = client.call("trigger", {"operation": "get", "request": {"trigger_id": child}})
            assert proof["trigger"]["reauthorization"]["actor"] == "alice"
        with origin_scope(current_id), authorization_scope(AuthorizationContext("bob", "operator")):
            with pytest.raises(AgentTaskError):
                client.call("trigger", {"operation": "review_authorization", "request": {"trigger_id": child}})
    finally:
        instance.close()


def test_gui_review_prepares_separate_explicit_request_and_refuses_wrong_selection(monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    import shiboken6
    from je_auto_control.gui.agent_tasks_tab import AgentTasksTab
    from je_auto_control.gui.task_controller import TaskOutcome
    app = QApplication.instance() or QApplication([])
    tab = AgentTasksTab()
    calls = []
    monkeypatch.setattr(tab, "_dispatch", lambda *args: calls.append(args))
    try:
        tab._trigger_id.setText("source-a")
        original_scope = tab._scope.toPlainText()
        tab._trigger_operation.setCurrentIndex(tab._trigger_operation.findData("review_authorization"))
        dict(tab.menu_actions())["agent_trigger_apply"]()
        assert calls.pop() == ("trigger", {"operation": "review_authorization", "request": {"trigger_id": "source-a"}})
        tab._present_result({"trigger_id": "source-a", "snapshot": "a" * 64,
            "authorization_review": "b" * 64, "spec": {"goal": "future only"}, "approval_required": True})
        request = json.loads(tab._trigger_config.toPlainText())
        assert request["note"] == "" and request["authorization_review"] == "b" * 64
        assert tab._scope.toPlainText() == original_scope and calls == []
        tab._trigger_operation.setCurrentIndex(tab._trigger_operation.findData("create_authorized"))
        dict(tab.menu_actions())["agent_trigger_apply"]()
        assert calls.pop() == ("trigger", {"operation": "create_authorized", "request": request})
        tab._trigger_id.setText("source-b")
        dict(tab.menu_actions())["agent_trigger_apply"]()
        assert calls == [] and "selected registration" in tab._status.text()
        tab._view_task = "trigger:source-a"
        tab._handle = None
        tab._completed(TaskOutcome(100, "ok", {"trigger_id": "late-created"}))
        assert tab._trigger_id.text() == "source-b"
        tab._present_result({"trigger_id": "source-a", "spec": None, "approval_required": True})
        assert tab._trigger_id.text() == "source-b"
        tab._present_result({"trigger_id": "source-b", "spec": None, "approval_required": True})
        assert tab._trigger_config.toPlainText() == "{}"
        tab.retranslate()
    finally:
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()
