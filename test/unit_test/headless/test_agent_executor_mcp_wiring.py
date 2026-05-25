"""Wire-up tests for ``AC_run_agent`` + ``ac_run_agent``.

The closed-loop AgentLoop already has direct-API tests in
``test_agent_loop.py``. These tests cover the new executor + MCP
adapters: they verify both surfaces register, dispatch to AgentLoop,
and faithfully return the structured result. A ``FakeAgentBackend``
is patched in so the tests never hit a real LLM.
"""
from __future__ import annotations

from typing import Any, Dict, List

from je_auto_control.utils.agent import FakeAgentBackend


def _stub_backend_factory(decisions: List[Dict[str, Any]]):
    """Return an Anthropic-/OpenAI-backend stub that ignores tools kwargs."""
    def factory(*_args, **_kwargs):
        return FakeAgentBackend(decisions)
    return factory


def _patch_backends(monkeypatch, decisions):
    """Replace both production backends with the FakeAgentBackend stub."""
    factory = _stub_backend_factory(decisions)
    import je_auto_control.utils.agent.backends as backends_pkg
    monkeypatch.setattr(backends_pkg, "AnthropicAgentBackend", factory)
    monkeypatch.setattr(backends_pkg, "OpenAIAgentBackend", factory)
    # Disable the screenshot helper so the loop doesn't try to grab a
    # real frame on the CI runner.
    from je_auto_control.utils.agent import agent_loop as loop_mod
    monkeypatch.setattr(loop_mod, "_default_screenshot", lambda: None)


def test_executor_registers_ac_run_agent():
    from je_auto_control.utils.executor.action_executor import executor
    assert "AC_run_agent" in executor.known_commands()


def test_mcp_registry_exposes_ac_run_agent():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert "ac_run_agent" in names


def test_executor_path_runs_agent_loop(monkeypatch):
    _patch_backends(monkeypatch, [
        {"stop": True, "message": "done by stub"},
    ])
    # Stop AgentLoop from trying to dispatch a real AC_* tool.
    from je_auto_control.utils.executor.action_executor import _run_agent
    result = _run_agent(
        goal="probe", backend="anthropic",
        max_steps=2, wall_seconds=5.0,
    )
    assert result["succeeded"] is True
    assert result["final_message"] == "done by stub"
    assert len(result["steps"]) == 1


def test_mcp_handler_round_trips(monkeypatch):
    _patch_backends(monkeypatch, [
        {"stop": True, "message": "mcp-ok"},
    ])
    from je_auto_control.utils.mcp_server.tools._handlers import run_agent
    record = run_agent(
        goal="probe-mcp", backend="openai",
        max_steps=2, wall_seconds=5.0,
    )
    assert record["succeeded"] is True
    assert record["final_message"] == "mcp-ok"


def test_unknown_backend_raises():
    from je_auto_control.utils.executor.action_executor import _run_agent
    import pytest
    with pytest.raises(ValueError, match="unknown agent backend"):
        _run_agent(goal="x", backend="bogus")
