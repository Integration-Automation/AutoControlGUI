"""Tests for the high-level ``run_computer_use`` wrapper."""
import pytest

from je_auto_control.utils.agent.agent_loop import (
    AgentResult, AgentStep, FakeAgentBackend,
)
from je_auto_control.utils.agent.computer_use import (
    result_to_dict, run_computer_use, steps_to_dicts,
)
from je_auto_control.utils.agent import computer_use as cu_mod


def _stub_screenshot(monkeypatch) -> None:
    monkeypatch.setattr(cu_mod, "_resolve_display", lambda: (640, 480))


def test_run_computer_use_rejects_blank_goal():
    with pytest.raises(ValueError):
        run_computer_use("   ")


def test_run_computer_use_drives_backend_through_loop(monkeypatch):
    """Pass a FakeAgentBackend with no tool calls so the loop stops on the first
    decision and we don't have to mock the executor's tool dispatch.
    """
    _stub_screenshot(monkeypatch)
    fake = FakeAgentBackend([{"stop": True, "message": "done"}])
    result = run_computer_use("look at the screen", backend=fake,
                              max_steps=3, wall_seconds=5.0)
    assert isinstance(result, AgentResult)
    assert result.succeeded is True
    assert result.final_message == "done"


def test_run_computer_use_passes_budget(monkeypatch):
    _stub_screenshot(monkeypatch)
    fake = FakeAgentBackend([{"stop": True, "message": "ok"}])
    result = run_computer_use("x", backend=fake,
                              max_steps=7, wall_seconds=15.0)
    assert result.succeeded


def test_result_to_dict_renders_steps_and_metadata():
    result = AgentResult(
        succeeded=True, final_message="done", elapsed_s=1.25,
        steps=[
            AgentStep(index=0, tool="AC_screenshot",
                      arguments={"file_path": "x"},
                      result={"saved": "x"}),
            AgentStep(index=1, tool=None, arguments=None,
                      stop_reason="done"),
        ],
    )
    data = result_to_dict(result)
    assert data["succeeded"] is True
    assert data["final_message"] == "done"
    assert data["elapsed_s"] == 1.25
    assert len(data["steps"]) == 2
    assert data["steps"][0]["tool"] == "AC_screenshot"


def test_steps_to_dicts_collapses_non_json_results():
    step = AgentStep(index=0, tool="AC_screenshot", arguments={},
                     result=object())
    dicts = steps_to_dicts([step])
    assert isinstance(dicts[0]["result"], str)


def test_executor_registers_computer_use():
    from je_auto_control.utils.executor.action_executor import executor
    assert "AC_computer_use" in executor.known_commands()


def test_mcp_factory_registers_computer_use_tool():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert "ac_computer_use" in names


def test_facade_exports_run_computer_use():
    import je_auto_control as ac
    assert hasattr(ac, "run_computer_use")
    assert hasattr(ac, "computer_use_result_to_dict")


def test_executor_adapter_returns_dict(monkeypatch):
    """``AC_computer_use`` should pass through to the wrapper and return a dict."""
    _stub_screenshot(monkeypatch)
    fake = FakeAgentBackend([{"stop": True, "message": "ok"}])
    monkeypatch.setattr(
        cu_mod, "ComputerUseAgentBackend",
        lambda **_kwargs: fake,
    )
    from je_auto_control.utils.executor.action_executor import executor
    handler = executor.event_dict["AC_computer_use"]
    result = handler(goal="x", display_width_px=10, display_height_px=10,
                     max_steps=2, wall_seconds=2.0)
    assert isinstance(result, dict)
    assert result["succeeded"] is True
