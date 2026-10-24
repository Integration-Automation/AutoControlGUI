"""Continuation review prepares a separate blank-note request and execution stays explicit."""
import json
import threading
from unittest.mock import Mock

import pytest

from .test_agent_dag_batches import graph


def test_review_and_run_actions_preserve_source_selection_and_do_not_auto_execute(monkeypatch):
    pytest.importorskip("PySide6")
    import shiboken6
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.dag_tab import DagTab, _DagWorker
    app = QApplication.instance() or QApplication([])
    tab = DagTab()
    dispatched = []
    monkeypatch.setattr(tab, "_spawn_worker", lambda *args, **kwargs: dispatched.append((args, kwargs)))
    try:
        tab._editor.setPlainText(json.dumps(graph()))
        tab._batch_id.setText("batch-a")
        ordinary = tab._editor.toPlainText()
        actions = dict(tab.menu_actions())
        actions["dag_continuation_review_btn"]()
        assert dispatched.pop()[1] == {"inspect_only": True, "batch_operation": "review_continuation"}
        tab._inspection_source = ordinary
        tab.setProperty("dag_batch_source", "batch-a")
        tab._on_batch_finished({"batch_id": "batch-a", "definition": graph(), "snapshot": "a" * 64,
                                "decisions": [{"node_id": "a", "action": "wait"}], "nodes": []})
        request = json.loads(tab._continuation_request.toPlainText())
        assert request["note"] == "" and tab._editor.toPlainText() == ordinary and dispatched == []
        actions["dag_continuation_run_btn"]()
        assert dispatched.pop()[1] == {"inspect_only": False, "batch_operation": "run_continuation"}
        tab._batch_id.setText("batch-b")
        actions["dag_continuation_run_btn"]()
        assert dispatched == []
        tab.retranslate()
        call = Mock(return_value={})
        monkeypatch.setattr("je_auto_control.gui.dag_tab.manage_agent_dag", call)
        _DagWorker(graph(), 4, threading.Event(), batch_id="batch-a", batch_operation={
            "operation": "review_continuation", "request": request})._execute()
        assert call.call_args.args == ("review_continuation", {
            "batch_id": "batch-a", "definition": graph(), "decisions": request["decisions"]})
        runner = Mock()
        monkeypatch.setattr("je_auto_control.gui.dag_tab.run_dag", runner)
        _DagWorker(graph(), 4, threading.Event(), batch_id="batch-a", batch_operation={
            "operation": "run_continuation", "request": request})._execute()
        assert runner.call_args.kwargs["recovery"] == request
    finally:
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()


def test_executor_and_mcp_forward_the_same_reviewed_recovery_body(monkeypatch):
    from je_auto_control.utils import dag
    from je_auto_control.utils.dag.runner import DagRunResult
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import _handlers_operations
    runner = Mock(return_value=DagRunResult(True, 0))
    monkeypatch.setattr(dag, "run_dag", runner)
    request = {"snapshot": "a" * 64, "decisions": [], "note": "reviewed"}
    result = executor.execute_one("AC_run_dag", {
        "definition": graph(), "batch_id": "registered", "recovery": request})
    assert result["succeeded"]
    assert runner.call_args.kwargs["recovery"] == request
    _handlers_operations.run_dag(graph(), batch_id="registered", recovery=request)
    assert runner.call_args.kwargs["recovery"] == request
