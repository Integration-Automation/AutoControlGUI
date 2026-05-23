"""Phase 7.9: Computer-Use Agent loop tests."""
import time

import pytest

from je_auto_control.utils.agent import (
    AgentBudget, AgentLoop, AgentStep, FakeAgentBackend, run_agent,
)


def _capture_runner():
    captured = []

    def runner(name, args):
        captured.append((name, dict(args)))
        return {"ok": True, "name": name}

    return runner, captured


# --- happy path ------------------------------------------------------

def test_loop_executes_decisions_until_stop():
    runner, captured = _capture_runner()
    backend = FakeAgentBackend([
        {"tool": "AC_click_mouse", "input": {"button": "left"}},
        {"tool": "AC_type_keyboard", "input": {"text": "hello"}},
        {"stop": True, "message": "goal reached"},
    ])
    result = AgentLoop(
        backend, tool_runner=runner, screenshot_fn=lambda: None,
    ).run(goal="say hello")
    assert result.succeeded is True
    assert result.final_message == "goal reached"
    assert len(result.steps) == 3
    assert captured == [
        ("AC_click_mouse", {"button": "left"}),
        ("AC_type_keyboard", {"text": "hello"}),
    ]


def test_convenience_wrapper_round_trip():
    backend = FakeAgentBackend([{"stop": True, "message": "ok"}])
    result = run_agent(
        "just stop", backend,
        tool_runner=lambda _n, _a: None,
        screenshot_fn=lambda: None,
    )
    assert result.succeeded is True


# --- budgets ---------------------------------------------------------

def test_max_steps_budget_exhausts_with_message():
    # Loop that asks to click forever and never stops.
    backend = FakeAgentBackend([
        {"tool": "AC_click_mouse", "input": {"button": "left"}}
        for _ in range(50)
    ])
    runner, _ = _capture_runner()
    result = AgentLoop(
        backend, tool_runner=runner, screenshot_fn=lambda: None,
        budget=AgentBudget(max_steps=3),
    ).run("loop forever")
    assert result.succeeded is False
    assert "max_steps" in result.final_message
    assert len(result.steps) == 3


def test_wall_seconds_budget_exhausts_with_message():
    class SlowBackend:
        def decide_next_action(self, *_args, **_kwargs):
            time.sleep(0.05)
            return {"tool": "AC_click_mouse", "input": {}}

    result = AgentLoop(
        SlowBackend(), tool_runner=lambda _n, _a: None,
        screenshot_fn=lambda: None,
        budget=AgentBudget(max_steps=1000, wall_seconds=0.1),
    ).run("burn time")
    assert result.succeeded is False
    assert "wall_seconds" in result.final_message


# --- error handling --------------------------------------------------

def test_tool_runner_error_is_surfaced_per_step():
    """Tool errors are recorded but the loop continues until stop or budget."""

    def runner(name, args):
        raise RuntimeError(f"{name} failed")

    backend = FakeAgentBackend([
        {"tool": "AC_click_mouse", "input": {}},
        {"stop": True, "message": "give up"},
    ])
    result = AgentLoop(
        backend, tool_runner=runner, screenshot_fn=lambda: None,
    ).run("any")
    assert result.succeeded is True
    failing = next(s for s in result.steps if s.tool == "AC_click_mouse")
    assert failing.error is not None
    assert "AC_click_mouse failed" in failing.error


def test_backend_missing_tool_aborts():
    """If the backend forgets the ``tool`` field, the loop stops cleanly."""
    backend = FakeAgentBackend([
        {"input": {"text": "no tool"}},  # malformed
        {"stop": True},  # would-be follow-up
    ])
    result = AgentLoop(
        backend, tool_runner=lambda _n, _a: None,
        screenshot_fn=lambda: None,
    ).run("any")
    assert result.succeeded is False
    assert "no tool" in result.final_message or \
           "returned no tool" in result.final_message


# --- observation handoff --------------------------------------------

def test_screenshot_fn_called_each_turn():
    calls = []

    def shot():
        calls.append(time.monotonic())
        return b"png-bytes"

    backend = FakeAgentBackend([
        {"tool": "AC_click_mouse", "input": {}},
        {"tool": "AC_click_mouse", "input": {}},
        {"stop": True},
    ])
    AgentLoop(
        backend, tool_runner=lambda _n, _a: None,
        screenshot_fn=shot,
    ).run("any")
    # One screenshot per loop iteration, including the final stop call.
    assert len(calls) == 3


def test_history_passed_to_backend_grows_each_turn():
    seen = []

    class Recording:
        def decide_next_action(self, goal, screenshot, history):
            seen.append(len(history))
            if len(history) >= 2:
                return {"stop": True, "message": "done"}
            return {"tool": "AC_click_mouse", "input": {}}

    AgentLoop(
        Recording(), tool_runner=lambda _n, _a: None,
        screenshot_fn=lambda: None,
    ).run("any")
    assert seen == [0, 1, 2]


def test_agent_step_structure():
    step = AgentStep(index=0, tool="AC_click_mouse", arguments={"x": 1})
    assert step.tool == "AC_click_mouse"
    assert step.error is None
