"""Runtime maintenance owns failed read-only process cleanup without manufacturing retirement."""
import pytest
from types import SimpleNamespace

from headless.test_agent_browser_target import profile, spec
from headless.test_agent_retained_browser_collection import OwnedProcess, PROOF
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError


def retained(runtime, process):
    runtime.target_profiles.control("register", profile().to_dict())
    definition = spec(mode="external", actions=[], success_criteria=[
        {"kind": "browser", "operation": "value", "selector": "#field", "value": "complete"}])
    task = runtime.submit(definition).task_id
    runtime.store.update(task, "waiting_user")
    row = runtime.store.get(task)
    with runtime._retained_browsers.reserve(row) as entry:
        runtime._retained_browsers.commit(entry, process, PROOF)
    return task


def test_expiry_maintenance_does_not_retry_unconfirmed_reaping_in_the_same_sweep(tmp_path, monkeypatch):
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={})
    process = OwnedProcess(failure=True)
    task = retained(runtime, process)
    monkeypatch.setattr(runtime._retained_browsers, "_clock", lambda: float("inf"))
    try:
        with pytest.raises(AgentTaskError):
            runtime.maintain()
        assert process.attempts == 1
        assert runtime._retained_browsers.sources()[0]["id"] == task
    finally:
        process.failure = False
        runtime.close()


def test_failed_retained_reaping_keeps_runtime_open_and_service_ownership_until_confirmed(tmp_path):
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={})
    process = OwnedProcess(failure=True)
    retained(runtime, process)
    try:
        with pytest.raises(AgentTaskError):
            runtime.close()
        assert runtime._closed is False and not process.retired
    finally:
        process.failure = False
        runtime.close()
    assert runtime._closed is True and process.retired


def test_nonbrowser_input_retirement_survives_unreadable_action_evidence(tmp_path, monkeypatch):
    cleaned = []
    target = SimpleNamespace(ready=lambda _spec: (True, ""), observe=lambda: {"identity": "owned"},
                             cleanup=lambda: cleaned.append(True))
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={"fixture": target})
    try:
        task = runtime.submit({"goal": "Retire input independently of unavailable business evidence",
            "target": "fixture", "allowed_tools": ["AC_click_mouse"],
            "success_criteria": [{"kind": "result_equals", "key": "saved", "value": True}]}).task_id
        runtime.observe(task)

        def unavailable(_identifier):
            raise AgentTaskError("controlled action evidence is unavailable")

        with monkeypatch.context() as patch:
            patch.setattr(runtime.store, "actions", unavailable)
            with pytest.raises(AgentTaskError, match="action evidence"):
                runtime.pause(task)
            assert cleaned == [True], "Input cleanup cannot depend on business receipt availability"
            assert task not in runtime._leases
            assert runtime.store.get(task)["state"] != "succeeded"
    finally:
        runtime.close()
