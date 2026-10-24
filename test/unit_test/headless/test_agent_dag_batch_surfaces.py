"""Batch registration and bound execution use shared APIs and explicit thin GUI Actions."""
import json
import threading
from unittest.mock import Mock

import pytest

from je_auto_control.cli import build_parser
from je_auto_control.utils.agent_runtime.dag_batches import OPERATIONS
from .test_agent_dag_batches import graph


def test_new_registry_routes_cannot_change_the_fixed_task_method_dispatch():
    from types import SimpleNamespace
    from je_auto_control.utils.agent_runtime.routes import dispatch
    runtime = SimpleNamespace(observe=lambda identifier: SimpleNamespace(to_dict=lambda: {"task_id": identifier}))
    for operation in ("finish", "pause", "resume", "cancel"):
        setattr(runtime, operation, runtime.observe)
    for operation in ("observe", "finish", "pause", "resume", "cancel"):
        assert dispatch(runtime, operation, {"task_id": "requested"}) == {"task_id": "requested"}


def test_versioned_api_and_catalog_expose_the_same_managed_batch_protocol():
    import je_auto_control as root
    from je_auto_control import api
    from je_auto_control.api import core
    from je_auto_control.utils.agent_runtime.commands import CATALOG
    assert root.manage_agent_dag is api.manage_agent_dag is core.manage_agent_dag
    function, fields, required, _read_only, _host_management = CATALOG["AC_agent_dag"]
    assert function is root.manage_agent_dag and required == ("operation",)
    assert fields["operation"]["enum"] == list(OPERATIONS)
    for operation in OPERATIONS:
        parsed = build_parser().parse_args(["agent-task", "dag", operation, "request.json"])
        assert parsed.dag_operation == operation and parsed.request == "request.json"


def test_gui_registers_only_on_action_and_discards_graph_or_batch_selection_changes(monkeypatch):
    pytest.importorskip("PySide6")
    import shiboken6
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.dag_tab import DagTab, _DagWorker
    app = QApplication.instance() or QApplication([])
    tab = DagTab()
    requests = []
    monkeypatch.setattr(tab, "_spawn_worker", lambda *args, **kwargs: requests.append((args, kwargs)))
    try:
        tab._editor.setPlainText(json.dumps(graph()))
        assert requests == []
        dict(tab.menu_actions())["dag_batch_register_btn"]()
        assert requests[0][1] == {"inspect_only": True, "batch_operation": "register"}
        assert tab._batch_id.text() == ""
        tab._inspection_source = tab._editor.toPlainText()
        tab.setProperty("dag_batch_source", "")
        tab._on_batch_finished({"batch_id": "registered", "nodes": []})
        assert tab._batch_id.text() == "registered" and len(requests) == 1
        tab._batch_id.setText("other-batch")
        tab._on_batch_finished({"batch_id": "late-old", "nodes": []})
        assert tab._batch_id.text() == "other-batch"
        tab.retranslate()
        call = Mock(return_value={"batch_id": "registered"})
        monkeypatch.setattr("je_auto_control.gui.dag_tab.manage_agent_dag", call)
        worker = _DagWorker(graph(), 4, threading.Event(), batch_operation="register")
        assert worker._execute() == {"batch_id": "registered"}
        call.assert_called_once_with("register", {"definition": graph(), "max_parallel": 4})
        runner = Mock()
        monkeypatch.setattr("je_auto_control.gui.dag_tab.run_dag", runner)
        _DagWorker(graph(), 4, threading.Event(), batch_id="registered")._execute()
        assert runner.call_args.kwargs["batch_id"] == "registered"
    finally:
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()
