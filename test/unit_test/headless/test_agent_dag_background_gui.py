"""DAG Actions accept service work explicitly; retiring the view leaves accepted service work alive."""
import json
import threading
from unittest.mock import Mock

import pytest

from .test_agent_dag_background import until, read, finished
from .test_agent_dag_batch_loopback import service as service
from .test_agent_dag_batches import graph


def test_background_worker_forwards_initial_and_explicit_approved_continuation(monkeypatch):
    pytest.importorskip("PySide6")
    from je_auto_control.gui.dag_tab import _DagWorker
    call = Mock(return_value={"approval_id": "approval"})
    monkeypatch.setattr("je_auto_control.gui.dag_tab.manage_agent_dag", call)
    _DagWorker(graph(), 2, threading.Event(), batch_id="batch", batch_operation="run_background")._execute()
    assert call.call_args.args == ("run_background", {
        "batch_id": "batch", "definition": graph(), "max_parallel": 2})
    request = {"snapshot": "review", "decisions": [], "note": "reviewed"}
    _DagWorker(graph(), 2, threading.Event(), batch_id="batch", batch_operation={
        "operation": "continue_background", "request": request})._execute()
    assert call.call_args_list[-2].args == ("approve_continuation", {
        **request, "batch_id": "batch", "definition": graph()})
    assert call.call_args.args[1]["approval_id"] == "approval"


def test_closing_the_view_does_not_stop_a_batch_already_accepted_by_the_service(service, monkeypatch):
    pytest.importorskip("PySide6")
    import shiboken6
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.dag_tab import DagTab
    client, instance, target = service
    app = QApplication.instance() or QApplication([])
    batch = client.call("dag", {"operation": "register", "request": {"definition": graph()}})
    proceed = threading.Event()
    original = instance._dag_jobs._execute

    def delayed(worker):
        assert proceed.wait(5)
        return original(worker)

    monkeypatch.setattr(instance._dag_jobs, "_execute", delayed)
    tab = DagTab()
    try:
        tab._editor.setPlainText(json.dumps(graph()))
        tab._batch_id.setText(batch["batch_id"])
        dict(tab.menu_actions())["dag_background_run_btn"]()

        def accepted_and_view_worker_finished():
            app.processEvents()
            accepted = read(instance, batch)["background"] is not None
            return accepted and (tab._thread is None or not tab._thread.isRunning())

        until(accepted_and_view_worker_finished)
        tab.close()
        proceed.set()
        result = until(lambda: finished(instance, batch))
        assert result["state"] == "succeeded" and target.count == 2
    finally:
        proceed.set()
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()
