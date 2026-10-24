"""Skill renewal uses the shared HTTP/CLI and thin GUI operation selectors."""
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
from .test_agent_skill_reauthorization import published as published
from .test_agent_skill_versions import Editor


def test_cli_exposes_explicit_skill_authorization_operations():
    parser = build_parser()
    for operation in ("review_authorization", "create_authorized"):
        parsed = parser.parse_args(["agent-task", "skill", operation, "review.json"])
        assert parsed.skill_operation == operation and parsed.request == "review.json"


def test_authenticated_http_can_review_and_create_without_executing_or_publishing(published, monkeypatch):
    runtime, parent, _old_id, current_id, _allowed, narrow = published
    owner = {"user_id": "alice", "role": "operator", "store_path": None}
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_skill_candidates SET owner=? WHERE id=?", (json.dumps(owner), parent["id"]))
    runtime.close()
    instance = AgentRuntimeService(Path(runtime.store.path).parent, targets={"editor": Editor()})
    try:
        instance.start()
        client = AgentRuntimeClient(instance.directory / "agent_runtime.json")
        start = Mock()
        monkeypatch.setattr(instance.runtime.background, "start", start)
        with origin_scope(current_id), authorization_scope(AuthorizationContext("alice", "operator")):
            view = client.call("skill", {"operation": "review_authorization",
                                         "request": {"candidate_id": parent["id"]}})
            assert view["spec"]["roots"] == [str(narrow)]
            request = {"candidate_id": parent["id"], "snapshot": view["snapshot"], "spec": view["spec"],
                       "authorization_review": view["authorization_review"], "note": "Reviewed report-root candidate"}
            child = client.call("skill", {"operation": "create_authorized", "request": request})
            assert child["state"] == "draft" and child["version"] == 0
            assert child["provenance"]["reauthorization"]["actor"] == "alice"
            start.assert_not_called()
        with origin_scope(current_id), authorization_scope(AuthorizationContext("bob", "operator")):
            with pytest.raises(AgentTaskError):
                client.call("skill", {"operation": "review_authorization", "request": {"candidate_id": parent["id"]}})
    finally:
        instance.close()


def test_gui_skill_selector_dispatches_review_and_creation_only_on_explicit_actions(monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    import shiboken6
    from je_auto_control.gui.agent_tasks_tab import AgentTasksTab
    app = QApplication.instance() or QApplication([])
    tab = AgentTasksTab()
    calls = []
    monkeypatch.setattr(tab, "_dispatch", lambda *args: calls.append(args))
    try:
        for operation in ("review_authorization", "create_authorized"):
            index = tab._skill_operation.findData(operation)
            assert index >= 0
            tab._skill_operation.setCurrentIndex(index)
            tab._skill_request.setPlainText('{"candidate_id":"reviewed-source"}')
            assert calls == []
            dict(tab.menu_actions())["agent_skill_apply"]()
            assert calls.pop() == ("skill", {"operation": operation,
                                             "request": {"candidate_id": "reviewed-source"}})
        tab.retranslate()
    finally:
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()
