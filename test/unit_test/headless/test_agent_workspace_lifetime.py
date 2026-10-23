"""Workspace bootstrap and launch containment tests use fake windows and an intercepted launcher."""
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime import AgentTaskSpec, AgentTaskError
from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
from je_auto_control.utils.agent_runtime.targets import DesktopTarget


def specification(tmp_path):
    document = tmp_path / "report.txt"
    document.write_text("report", encoding="utf-8")
    return AgentTaskSpec.from_dict({"goal": "prepare workspace", "apps": ["editor"], "roots": [str(tmp_path)],
        "allowed_tools": ["AC_workflow_open", "AC_focus_window", "AC_write"],
        "actions": [{"tool": "AC_focus_window", "arguments": {"title_substring": "report"}}],
        "options": {"approved_documents": [str(document.resolve())]},
        "success_criteria": [{"kind": "result_equals", "key": "ready", "value": True}]})


def test_document_launch_is_owned_outside_native_input_helper(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import document_launch
    from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
    spec = specification(tmp_path)
    adapter, calls = NativeDesktopTarget(), []
    monkeypatch.setattr(adapter, "_ensure", lambda: None)
    monkeypatch.setattr(adapter, "_request", lambda *a: pytest.fail("document entered disposable input helper"))
    monkeypatch.setattr(document_launch.subprocess, "run", lambda *a, **k: calls.append((a, k)))
    with operation_scope(TaskOperation(spec, lambda: None, None)):
        assert adapter.perform("AC_workflow_open", {"path": spec.options["approved_documents"][0]}) is True
    assert calls[0][0][0][2] == "je_auto_control.utils.agent_runtime.document_launch"
    assert calls[0][1]["timeout"] == spec.budget.action_seconds
    assert "shell" not in calls[0][1]


def test_document_handoff_failure_is_uncertain_and_not_retried(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import document_launch
    from je_auto_control.utils.agent_runtime.workflow_desktop import workflow_open
    calls = []

    def timeout(*args, **kwargs):
        calls.append(1)
        raise document_launch.subprocess.TimeoutExpired(args[0], 1)

    monkeypatch.setattr(document_launch.subprocess, "run", timeout)
    spec = specification(tmp_path)
    with operation_scope(TaskOperation(spec, lambda: None, None)):
        with pytest.raises(AgentTaskError, match="unconfirmed"):
            workflow_open(spec.options["approved_documents"][0])
    assert calls == [1]


def test_bootstrap_observation_does_not_disclose_foreign_foreground(tmp_path, monkeypatch):
    import je_auto_control.utils.session_guard as session_guard
    monkeypatch.setattr(session_guard, "ensure_interactive_session", lambda: None)
    target = DesktopTarget()

    def outside():
        raise AgentTaskError("foreground outside scope")

    monkeypatch.setattr(target, "_check_foreground", outside)
    assert target.ready(specification(tmp_path)) == (True, "")
    assert target.observe() == {"identity": "approved-window-bootstrap", "elements": [], "state": "waiting_for_window"}
    with pytest.raises(AgentTaskError, match="outside scope"):
        target.perform("AC_write", {"text": "must not type"})
    with pytest.raises(AgentTaskError, match="host outside"):
        target.perform("AC_workflow_open", {"path": "report.txt"})


def test_bootstrap_focus_waits_for_scoped_window_and_refuses_unapproved_title(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import workspace_scope, native_scope
    from je_auto_control.utils import tool_use_schema
    spec, probes, calls = specification(tmp_path), [], []

    def check(arguments, scope):
        probes.append(arguments)
        if len(probes) == 1:
            raise AgentTaskError("not ready yet")
        assert scope == spec

    monkeypatch.setattr(native_scope, "check_window_arguments", check)
    monkeypatch.setattr(tool_use_schema, "run_tool_call", lambda *args: calls.append(args) or 42)
    monkeypatch.setattr(workspace_scope, "time", SimpleNamespace(monotonic=lambda: 0, sleep=lambda _: None))
    with operation_scope(TaskOperation(spec, lambda: None, None)):
        assert workspace_scope.focus_approved(spec, {"title_substring": "report"}) == 42
        with pytest.raises(AgentTaskError, match="approved plan"):
            workspace_scope.focus_approved(spec, {"title_substring": "other"})
    assert len(probes) == 2 and len(calls) == 1
