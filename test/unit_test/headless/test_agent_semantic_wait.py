"""Semantic readiness polling uses fake readers and a deterministic clock."""
from concurrent.futures import CancelledError
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


@pytest.fixture
def polling(monkeypatch):
    from je_auto_control.utils.agent_runtime import workflow_wait as public_wait
    import importlib
    module = importlib.import_module("je_auto_control.utils.agent_runtime.workflow_wait")
    now, samples = [0.0], []
    policy = SimpleNamespace(spec=SimpleNamespace(budget=SimpleNamespace(action_seconds=2)))
    monkeypatch.setattr(module, "task_policy", lambda: policy)
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(module.time, "sleep", lambda seconds: (samples.append(seconds), now.__setitem__(0, now[0]+seconds)))
    return module, public_wait, samples, now


def test_wait_only_polls_reads_after_a_delayed_update(polling, monkeypatch):
    _module, wait, sleeps, _now = polling
    values, calls = iter(["pending", "pending", "saved"]), []

    def read(operation, selector):
        calls.append((operation, selector))
        return next(values)

    monkeypatch.setattr("je_auto_control.utils.agent_runtime.workflow_desktop.workflow_control", read)
    assert wait({"name": "Receipt"}, "saved") == "saved"
    assert calls == [("get", {"name": "Receipt"})] * 3
    assert sleeps == [0.05, 0.05]


def test_wait_never_sleeps_past_its_budget(polling, monkeypatch):
    _module, wait, sleeps, now = polling
    monkeypatch.setattr("je_auto_control.utils.agent_runtime.workflow_desktop.workflow_control", lambda *_args: "old")
    with pytest.raises(AgentTaskError, match="deadline"):
        wait({"name": "Receipt"}, "saved", timeout_seconds=0.12)
    assert now[0] == pytest.approx(0.12)
    assert all(0 < sample <= 0.05 for sample in sleeps)


def test_cancellation_interrupts_polling_without_another_read(polling, monkeypatch):
    module, wait, _sleeps, _now = polling
    reads, checks = [], []
    original = module.task_policy

    def policy():
        checks.append(True)
        if len(checks) == 3:
            raise CancelledError()
        return original()

    monkeypatch.setattr(module, "task_policy", policy)
    monkeypatch.setattr("je_auto_control.utils.agent_runtime.workflow_desktop.workflow_control",
                        lambda *args: reads.append(args) or "old")
    with pytest.raises(CancelledError):
        wait({"name": "Receipt"}, "saved")
    assert len(reads) == 1


def test_readback_arriving_after_the_requested_deadline_is_not_success(polling, monkeypatch):
    _module, wait, _sleeps, now = polling

    def late_read(*_args):
        now[0] = 1.1
        return "saved"

    monkeypatch.setattr("je_auto_control.utils.agent_runtime.workflow_desktop.workflow_control", late_read)
    with pytest.raises(AgentTaskError, match="deadline"):
        wait({"name": "Receipt"}, "saved", timeout_seconds=1)


@pytest.mark.parametrize("timeout", [True, 0, -1, float("nan"), 61])
def test_invalid_wait_budgets_fail_before_reading(polling, monkeypatch, timeout):
    _module, wait, _sleeps, _now = polling
    monkeypatch.setattr("je_auto_control.utils.agent_runtime.workflow_desktop.workflow_control",
                        lambda *_args: pytest.fail("invalid wait attempted a read"))
    with pytest.raises(AgentTaskError):
        wait({"name": "Receipt"}, "saved", timeout_seconds=timeout)
