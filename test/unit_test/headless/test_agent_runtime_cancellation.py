"""A cancelled client operation must stop its separately owned host operation."""
from concurrent.futures import CancelledError
from unittest.mock import patch

import pytest

from je_auto_control.utils.agent_runtime.api import act_agent_task
from je_auto_control.utils.exception.cancellation import CancellationToken, cancellation_scope, current_cancellation_token


def test_cancelled_action_requests_host_pause_with_cancellation_suspended():
    calls = []

    class Client:
        def call(self, operation, _body, **_kwargs):
            calls.append(operation)
            if operation == "act":
                raise CancelledError()
            assert current_cancellation_token() is None
            return {"state": "pausing"}

    with patch("je_auto_control.utils.agent_runtime.api.AgentRuntimeClient", Client):
        with cancellation_scope(CancellationToken(1)), pytest.raises(CancelledError):
            act_agent_task("task", {"tool": "AC_click_mouse", "observation_id": "observation"})
    assert calls == ["act", "pause"]


def test_loopback_cancel_reaches_host_and_retires_active_operation(tmp_path):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
    from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
    from je_auto_control.utils.exception.cancellation import cancellation_checkpoint

    entered, cleaned = threading.Event(), threading.Event()

    class Target:
        def ready(self, _spec):
            return True, ""

        def observe(self):
            return {"identity": "fixture"}

        def perform(self, _name, _arguments):
            entered.set()
            while True:
                cancellation_checkpoint()
                time.sleep(0.01)

        def cleanup(self):
            cleaned.set()

    service = AgentRuntimeService(tmp_path, targets={"fixture": Target()})
    service.start()
    client = AgentRuntimeClient(tmp_path / "agent_runtime.json")
    token = CancellationToken(3)
    try:
        task = client.call("submit", {"spec": {"goal": "fixture", "target": "fixture",
                           "allowed_tools": ["AC_fixture"],
                           "success_criteria": [{"kind": "result_equals", "key": "ok", "value": True}]}})
        task_id = task["task_id"]
        frame = client.call("observe", {"task_id": task_id})

        def action():
            with cancellation_scope(token):
                return act_agent_task(task_id, {"tool": "AC_fixture", "observation_id": frame["observation_id"]})

        with patch("je_auto_control.utils.agent_runtime.api.AgentRuntimeClient", return_value=client):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(action)
                assert entered.wait(3)
                token.cancel()
                with pytest.raises(CancelledError):
                    future.result(timeout=4)
        assert cleaned.wait(3)
        deadline = time.monotonic() + 3
        while service.runtime.get(task_id).state == "pausing" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert service.runtime.get(task_id).state == "paused"
        assert not service.runtime._leases
    finally:
        service.close()
