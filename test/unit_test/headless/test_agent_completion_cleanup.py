"""Completion never publishes success before cleanup and cancellation settle."""
import json
import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from headless.test_agent_runtime import FakeTarget, specification


@pytest.mark.parametrize("failure", ["exception", "busy"])
def test_failed_retirement_keeps_verified_task_out_of_success(tmp_path, monkeypatch, failure):
    target = FakeTarget()
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={"fixture": target})
    task = runtime.submit(specification())
    frame = runtime.observe(task.task_id)
    runtime.act(task.task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})
    original = runtime.broker.release

    def failed(*_args):
        if failure == "exception":
            raise AgentTaskError("owned cleanup was not confirmed")
        return False

    monkeypatch.setattr(runtime.broker, "release", failed)
    try:
        if failure == "exception":
            with pytest.raises(AgentTaskError):
                runtime.finish(task.task_id)
        else:
            assert runtime.finish(task.task_id).state != "succeeded"
        result = runtime.get(task.task_id)
        assert result.state == "waiting_user"
        assert result.verification[0]["status"] == "passed"
        assert result.metadata["input_released"] is False
        assert result.metadata["completion_contract"] == 0
        assert task.task_id in runtime._leases
    finally:
        monkeypatch.setattr(runtime.broker, "release", original)
        runtime.close()


def test_cancel_during_cleanup_cannot_be_overwritten_by_success(tmp_path, monkeypatch):
    target = FakeTarget()
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={"fixture": target})
    task = runtime.submit(specification())
    frame = runtime.observe(task.task_id)
    runtime.act(task.task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})
    original = runtime.broker.release

    def release(lease, cleanup):
        # Control calls do not wait for the task's execution lock.
        runtime.cancel(task.task_id)
        return original(lease, cleanup)

    monkeypatch.setattr(runtime.broker, "release", release)
    try:
        result = runtime.finish(task.task_id)
        assert result.state in {"cancelling", "cancelled"}
        assert runtime.get(task.task_id).state == "cancelled"
        assert result.metadata["input_released"] is True
        report = json.loads((runtime.evidence.directory(task.task_id) / "report.json").read_text())
        assert report["state"] == "cancelled"
        assert not runtime._leases
    finally:
        monkeypatch.setattr(runtime.broker, "release", original)
        runtime.close()


def test_crash_before_cleanup_confirmation_requires_recovery(tmp_path, monkeypatch):
    path = tmp_path / "runtime.sqlite"
    runtime = AgentRuntime(path, targets={"fixture": FakeTarget()})
    task = runtime.submit(specification())
    frame = runtime.observe(task.task_id)
    runtime.act(task.task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})
    original = runtime.broker.release

    def crash(*_args):
        raise SystemExit("fixture host exit during cleanup")

    monkeypatch.setattr(runtime.broker, "release", crash)
    try:
        with pytest.raises(SystemExit):
            runtime.finish(task.task_id)
        assert runtime.get(task.task_id).state == "verifying"
    finally:
        monkeypatch.setattr(runtime.broker, "release", original)
        runtime.close()
    replacement = AgentRuntime(path, targets={"fixture": FakeTarget()})
    try:
        assert replacement.get(task.task_id).state == "recovering"
    finally:
        replacement.close()


def test_success_has_confirmed_input_retirement(tmp_path):
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={"fixture": FakeTarget()})
    try:
        task = runtime.submit(specification())
        frame = runtime.observe(task.task_id)
        runtime.act(task.task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})
        result = runtime.finish(task.task_id)
        assert result.state == "succeeded"
        assert result.metadata["input_released"] is True
        assert result.metadata["completion_contract"] == 1
        report = json.loads((runtime.evidence.directory(task.task_id) / "report.json").read_text())
        assert report["state"] == "succeeded"
    finally:
        runtime.close()


def test_completion_contract_survives_restart_and_does_not_certify_legacy_success(tmp_path):
    path = tmp_path / "runtime.sqlite"
    runtime = AgentRuntime(path, targets={"fixture": FakeTarget()})
    task = runtime.submit(specification())
    legacy = runtime.submit(specification())
    try:
        frame = runtime.observe(task.task_id)
        runtime.act(task.task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})
        runtime.finish(task.task_id)
        runtime.store.update(legacy.task_id, "succeeded")
    finally:
        runtime.close()
    replacement = AgentRuntime(path, targets={"fixture": FakeTarget()})
    try:
        assert replacement.get(task.task_id).metadata["completion_contract"] == 1
        assert replacement.get(legacy.task_id).metadata["completion_contract"] == 0
    finally:
        replacement.close()
