"""Existing DAG Actions validate task JSON and expose recovery identity without native input."""
import json
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from headless.test_dag_managed_tasks import definition
from je_auto_control.gui.dag_tab import DagTab
from je_auto_control.utils.dag.runner import DagRunResult, NodeResult
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope, current_authorization


def test_existing_actions_validate_managed_nodes_and_show_recovery_task_id():
    app = QApplication.instance() or QApplication([])
    tab = DagTab()
    try:
        tab._editor.setPlainText(json.dumps(definition()))
        tab._on_validate()
        assert "2" in tab._status_label.text()
        result = DagRunResult(False, 0, {"one": NodeResult("one", "remote", status="failed",
            result={"outcome": "requires_review", "task_id": "retained-task-id"})})
        tab._on_worker_finished(result)
        assert tab._table.item(0, 3).text() == "retained-task-id"
        assert any(handler == tab._on_stop for _label, handler in tab.menu_actions())
    finally:
        tab.close()
        tab.deleteLater()
        app.processEvents()


def test_dag_gui_worker_does_not_borrow_ambient_admin_authority(monkeypatch):
    from je_auto_control.gui.dag_tab import _DagWorker
    from je_auto_control.utils.admin import admin_client

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(admin_client, "default_admin_console", lambda: pytest.fail("GUI borrowed host credentials"))
    with authorization_scope(AuthorizationContext("caller", "operator")):
        worker = _DagWorker(definition(host="remote"), 1, threading.Event())
    outcomes = []
    worker.finished.connect(outcomes.append)
    admin = AuthorizationContext("ambient", "admin")
    with authorization_scope(admin):
        worker.run()
        assert current_authorization() is admin
    assert len(outcomes) == 1 and not outcomes[0].succeeded
    assert "manage_hosts" in outcomes[0].nodes["one"].error
    worker.deleteLater()
    app.processEvents()


def test_dag_inspection_worker_calls_only_inspection(monkeypatch):
    from je_auto_control.gui import dag_tab

    app = QApplication.instance() or QApplication([])
    calls = []
    monkeypatch.setattr(dag_tab, "run_dag", lambda *_args, **_kwargs: pytest.fail("inspection submitted tasks"))
    monkeypatch.setattr(dag_tab, "inspect_agent_dag", lambda graph: calls.append(graph) or {"inspection_only": True})
    graph = definition()
    worker = dag_tab._DagWorker(graph, 1, threading.Event(), inspect_only=True)
    results = []
    worker.finished.connect(results.append)
    worker.run()
    assert calls == [graph] and results == [{"inspection_only": True}]
    worker.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("changed", [False, True])
def test_inspection_view_does_not_replace_a_changed_graph(changed):
    app = QApplication.instance() or QApplication([])
    tab = DagTab()
    try:
        tab._editor.setPlainText(json.dumps(definition()))
        tab._inspection_source = tab._editor.toPlainText()
        if changed:
            tab._editor.setPlainText('{"nodes": []}')
        snapshot = {"inspection_only": True, "resume_permitted": False,
                    "nodes": [{"id": "one", "host": "remote", "task_state": "waiting_user",
                               "task_id": "accepted-id", "request_match": "unverified"}]}
        tab._on_inspection_finished(snapshot)
        assert tab._table.rowCount() == (0 if changed else 1)
        if not changed:
            assert tab._table.item(0, 3).text() == "accepted-id"
            assert "unverified" in tab._inspection_output.toPlainText()
        assert "dag_inspect_btn" in dict(tab.menu_actions())
    finally:
        tab.close()
        tab.deleteLater()
        app.processEvents()
