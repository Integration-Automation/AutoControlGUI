"""Autonomous execution and local model contracts use fake targets and HTTP replies."""
import json
from unittest.mock import patch

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskSpec, AgentTaskError
from je_auto_control.utils.agent_runtime.ollama import OllamaTaskBackend
from je_auto_control.utils.agent_runtime.runner import run_task


class Target:
    """A deterministic target with no native dependencies."""

    def __init__(self):
        self.count = 0

    def ready(self, _spec):
        return True, ""

    def observe(self):
        return {"identity": "fixture", "count": self.count}

    def perform(self, _tool, _arguments):
        self.count += 1
        return {"value": self.count}

    def cleanup(self):
        return None


def task_spec(**extra):
    return AgentTaskSpec.from_dict({"goal": "increment", "target": "fixture", "mode": "skill",
                                    "allowed_tools": ["AC_increment"],
                                    "actions": [{"tool": "AC_increment"}],
                                    "success_criteria": [{"kind": "result_equals", "key": "value", "value": 1}],
                                    **extra})


def test_deterministic_skill_runs_through_the_same_verifier(tmp_path):
    target = Target()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": target})
    try:
        handle = runtime.submit(task_spec())
        assert run_task(runtime, handle.task_id).state == "succeeded"
        assert target.count == 1
    finally:
        runtime.close()


def test_untrusted_model_cannot_expand_task_scope(tmp_path):
    class Backend:
        def decide(self, *_args, **_kwargs):
            return {"tool": "AC_shell_command", "arguments": {"command": "no"}}

    target = Target()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": target})
    try:
        handle = runtime.submit(task_spec(mode="ollama"))
        assert run_task(runtime, handle.task_id, backend=Backend()).state == "waiting_user"
        assert target.count == 0
    finally:
        runtime.close()


def test_local_model_never_follows_redirects_and_only_receives_offered_tools():
    calls = []

    def transport(call):
        calls.append(call)
        if call["url"].endswith("/api/show"):
            data = {"capabilities": ["tools"]}
        else:
            data = {"message": {"tool_calls": [{"function": {"name": "AC_increment", "arguments": {}}}]}}
        return {"status": 200, "ok": True, "json": data}

    spec = task_spec(mode="ollama", options={"model": "installed-local-model"})
    with patch("je_auto_control.utils.agent_runtime.transport.urllib_transport", transport):
        with patch("je_auto_control.utils.tool_use_schema.export_openai_tools",
                   return_value=[{"type": "function", "function": {"name": "AC_increment"}}]):
            decision = OllamaTaskBackend(spec).decide({}, [], timeout=1, check=lambda: None)
    assert decision["tool"] == "AC_increment"
    assert all(call["follow_redirects"] is False for call in calls)
    payload = json.loads(calls[-1]["body"])
    assert [tool["function"]["name"] for tool in payload["tools"]] == ["AC_increment"]


@pytest.mark.parametrize("options", [{"model": "some-cloud-model"},
                                     {"model": "local", "endpoint": "https://example.org"}, {}])
def test_local_backend_rejects_remote_or_implicit_models(options):
    with pytest.raises(AgentTaskError):
        OllamaTaskBackend(task_spec(mode="ollama", options=options))
