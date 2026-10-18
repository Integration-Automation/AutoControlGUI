"""DAG node diagnostics stay masked after a local runner returns or raises."""
import io
import json
import logging

import pytest

from je_auto_control.utils.dag.runner import run_dag
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.logging.secret_scope import current_secret_scope, secret_log_scope
from je_auto_control.utils.secrets import default_secret_manager

FAKE = "fake-dag-node-private-value"


@pytest.mark.parametrize("mode", ["default", "enclosing", "custom"])
def test_worker_diagnostic_uses_the_owner_mask_while_error_results_remain_intact(mode, monkeypatch):
    def fail(value):
        raise ValueError("controlled failure: " + value)
    monkeypatch.setattr(default_secret_manager, "get", lambda _name: FAKE)
    monkeypatch.setitem(executor.event_dict, "AC_dag_diagnostic_probe", fail)
    actions = [["AC_dag_diagnostic_probe", {"value": "${secrets.LOGIN}"}]]
    definition = {"nodes": [{"id": "probe", "actions": actions}]}
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    autocontrol_logger.addHandler(handler)
    def custom(node, _definition):
        return executor.execute_action(node.actions, raise_on_error=True)
    try:
        if mode == "enclosing":
            with secret_log_scope():
                owner = current_secret_scope()
                report = run_dag(definition)
                assert current_secret_scope() is owner
        else:
            report = run_dag(definition, local_runner=custom if mode == "custom" else None)
    finally:
        autocontrol_logger.removeHandler(handler)
        handler.close()
    assert current_secret_scope() is None
    assert FAKE in json.dumps(report.to_dict())
    assert FAKE not in stream.getvalue()
    assert "DAG node 'probe' failed: ValueError: controlled failure: ***" in stream.getvalue()
