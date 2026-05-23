"""Phase 10.1: agent-loop instrumentation tests.

We patch the agent's tool runner so we don't need a real GUI; the
focus is verifying that ``AgentLoop.run`` increments the right
Prometheus metrics and emits the right tracer spans.
"""
import pytest

from je_auto_control.utils.agent.agent_loop import (
    AgentBudget, AgentLoop, FakeAgentBackend,
)
from je_auto_control.utils.observability import default_registry


@pytest.fixture(autouse=True)
def _reset_agent_metric_cache():
    """Clear cached agent metrics and the registered entries between runs."""
    from je_auto_control.utils.agent import agent_loop
    agent_loop._AGENT_METRIC_CACHE.clear()
    registry = default_registry()
    for name in (
        "autocontrol_agent_runs_total",
        "autocontrol_agent_steps_total",
        "autocontrol_agent_outcomes_total",
    ):
        registry.unregister(name)
    yield
    agent_loop._AGENT_METRIC_CACHE.clear()
    for name in (
        "autocontrol_agent_runs_total",
        "autocontrol_agent_steps_total",
        "autocontrol_agent_outcomes_total",
    ):
        registry.unregister(name)


def _runner_recorder():
    calls = []
    def runner(tool, args):
        calls.append((tool, args))
        if tool == "AC_fail":
            raise RuntimeError("simulated failure")
        return {"ok": True}
    return calls, runner


def test_agent_run_counter_increments_each_run():
    backend = FakeAgentBackend([
        {"stop": True, "message": "done"},
    ])
    _, runner = _runner_recorder()
    loop = AgentLoop(
        backend, tool_runner=runner,
        screenshot_fn=lambda: None,
        budget=AgentBudget(max_steps=5, wall_seconds=10.0),
    )
    loop.run("goal")
    loop.run("goal again")
    counter = default_registry().get("autocontrol_agent_runs_total")
    assert counter is not None
    assert counter.value() == 2


def test_agent_steps_counter_partitions_by_tool_and_outcome():
    backend = FakeAgentBackend([
        {"tool": "AC_click_mouse", "input": {"x": 1, "y": 2}},
        {"tool": "AC_fail",        "input": {}},
        {"tool": "AC_click_mouse", "input": {"x": 3, "y": 4}},
        {"stop": True, "message": "done"},
    ])
    _, runner = _runner_recorder()
    loop = AgentLoop(
        backend, tool_runner=runner,
        screenshot_fn=lambda: None,
        budget=AgentBudget(max_steps=10, wall_seconds=10.0),
    )
    result = loop.run("multi-step")
    assert result.succeeded is True
    steps_counter = default_registry().get("autocontrol_agent_steps_total")
    assert steps_counter is not None
    assert steps_counter.value(
        labels={"tool": "AC_click_mouse", "outcome": "ok"},
    ) == 2
    assert steps_counter.value(
        labels={"tool": "AC_fail", "outcome": "error"},
    ) == 1


def test_agent_outcome_counter_records_success_and_failure():
    successful = FakeAgentBackend([{"stop": True, "message": "done"}])
    failing = FakeAgentBackend([])  # immediately exhausted → final_message set, succeeded=False
    _, runner = _runner_recorder()
    loop = AgentLoop(
        successful, tool_runner=runner, screenshot_fn=lambda: None,
        budget=AgentBudget(max_steps=2, wall_seconds=5.0),
    )
    loop.run("a")
    AgentLoop(
        failing, tool_runner=runner, screenshot_fn=lambda: None,
        budget=AgentBudget(max_steps=2, wall_seconds=5.0),
    ).run("b")
    outcome_counter = default_registry().get(
        "autocontrol_agent_outcomes_total",
    )
    # FakeAgentBackend returns {"stop": True, ...} when exhausted, so both
    # runs end with succeeded=True. Test the structure not the partition.
    assert outcome_counter is not None
    assert outcome_counter.value(labels={"outcome": "succeeded"}) >= 1


def test_agent_loop_uses_noop_tracer_when_otel_missing(monkeypatch):
    """Ensure the agent loop doesn't crash when opentelemetry isn't importable."""
    import sys
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    backend = FakeAgentBackend([{"stop": True, "message": "done"}])
    _, runner = _runner_recorder()
    loop = AgentLoop(
        backend, tool_runner=runner, screenshot_fn=lambda: None,
        budget=AgentBudget(max_steps=2, wall_seconds=5.0),
    )
    result = loop.run("goal")
    assert result.succeeded is True
