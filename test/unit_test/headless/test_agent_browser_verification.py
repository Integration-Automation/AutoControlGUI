"""External/local agents finish only after pinned browser state is freshly and exactly verified."""
from contextlib import closing
from concurrent.futures import CancelledError
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.browser_target import BrowserTarget
from je_auto_control.utils.agent_runtime.policy import TaskPolicy
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.agent_runtime.verification import verify
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.agent_runtime.errors import AgentHumanReview
from .test_agent_browser_target import fake_sdk, spec  # noqa: F401 - shared SDK-free fixture


def criterion(operation="value", value="complete", **changes):
    result = {"kind": "browser", "operation": operation, "value": value}
    if operation != "url":
        result["selector"] = "#field"
    return {**result, **changes}


def task(clause=None, **changes):
    return spec(**{"mode": "external", "actions": [], "success_criteria": [clause or criterion()], **changes})


def test_finish_reads_current_value_instead_of_reusing_confirmed_receipt(fake_sdk, tmp_path):
    session = fake_sdk[0]
    session.value = "complete"
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        handle = runtime.submit(task())
        observed = runtime.observe(handle.task_id)
        runtime.act(handle.task_id, {"tool": "AC_browser_read", "arguments": {"operation": "value", "selector": "#field"},
                                    "observation_id": observed.observation_id})
        session.value = "changed after receipt"
        result = runtime.finish(handle.task_id)
        assert result.state == "waiting_user"
        assert result.verification[0]["status"] == "failed"
        assert session.actions == []


@pytest.mark.parametrize("clause,setup", [
    (criterion(), "value"), (criterion("text", "complete"), "text"),
    (criterion("visible", True), "visible"),
    (criterion("url", "https://allowed.test/form#complete"), "url"),
])
def test_independent_readback_can_complete_external_task_without_a_pinned_action_plan(fake_sdk, tmp_path, clause, setup):
    session = fake_sdk[0]
    session.value = "complete"
    session.text = Mock(return_value="complete")
    if setup == "url":
        session.url = clause["value"]
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        handle = runtime.submit(task(clause))
        result = runtime.finish(handle.task_id)
        assert result.state == "succeeded", result.reason
        assert result.verification[0]["status"] == "passed"
        assert runtime.store.actions(handle.task_id) == []
    assert session.closed


def test_blank_page_is_not_negative_visibility_completion_evidence(fake_sdk, tmp_path):
    session = fake_sdk[0]
    session.url = "about:blank"
    session.visible = Mock(return_value=False)
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        handle = runtime.submit(task(criterion("visible", False)))
        result = runtime.finish(handle.task_id)
        assert result.state == "waiting_user"
        assert result.verification[0]["status"] == "unknown"
    session.visible.assert_not_called()


def test_preview_text_cannot_substitute_for_an_unavailable_browser_verifier(tmp_path):
    target = SimpleNamespace(ready=lambda _spec: (True, ""), cleanup=lambda: None,
                             observe=lambda: {"identity": "preview", "text": "complete", "elements": []})
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": target})) as runtime:
        handle = runtime.submit(task())
        result = runtime.finish(handle.task_id)
        assert result.state == "waiting_user"
        assert result.verification[0]["status"] == "unknown"


def test_overlimit_readback_is_unknown_instead_of_accepting_an_equal_prefix(fake_sdk, tmp_path):
    session = fake_sdk[0]
    session.value = "x" * 8000 + "changed suffix"
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        handle = runtime.submit(task(criterion(value="x" * 8000)))
        result = runtime.finish(handle.task_id)
        assert result.state == "waiting_user"
        assert result.verification[0]["status"] == "unknown"


def test_page_change_during_readback_cannot_complete_the_old_page(fake_sdk, tmp_path):
    session = fake_sdk[0]
    def changed(_selector, _frame=""):
        session.url = "https://allowed.test/another-page"
        return "complete"
    session.read_value = changed
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        handle = runtime.submit(task())
        result = runtime.finish(handle.task_id)
        assert result.state == "waiting_user"
        assert result.verification[0]["status"] == "unknown"


@pytest.mark.parametrize("clause", [
    {"kind": "browser", "operation": "script", "value": "complete"},
    criterion(script="unreviewed"), criterion("visible", "true"), criterion(selector=""),
    criterion("url", "https://outside.test/form"), criterion("url", "https://allowed.test:0/form"),
    criterion("url", "https://allowed.test:bad/form"),
])
def test_invalid_or_ungranted_checks_are_rejected_before_sdk_start(fake_sdk, tmp_path, clause):
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        with pytest.raises(AgentTaskError):
            runtime.submit(task(clause))
    fake_sdk[1].assert_not_called()


def test_read_permission_is_not_implicitly_added_by_a_completion_clause(fake_sdk, tmp_path):
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        with pytest.raises(AgentTaskError, match="explicit browser-read"):
            runtime.submit(task(allowed_tools=["AC_browser_fill"]))
    fake_sdk[1].assert_not_called()


def test_local_model_stop_cannot_override_failed_browser_state(fake_sdk, tmp_path):
    session = fake_sdk[0]
    session.value = "not complete"
    backend = SimpleNamespace(decide=lambda *_args, **_kwargs: {"stop": True})
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        specification = task(mode="ollama", options={"model": "installed-local-model",
                                                     "allowed_origins": ["https://allowed.test"]})
        handle = runtime.submit(specification)
        assert run_task(runtime, handle.task_id, backend=backend).state == "waiting_user"
        assert session.actions == []


def test_local_model_can_fill_then_finish_only_after_independent_browser_readback(fake_sdk, tmp_path):
    class Backend:
        def decide(self, _observation, receipts, **_kwargs):
            return {"stop": True} if receipts else {
                "tool": "AC_browser_fill", "arguments": {"selector": "#field", "value": "complete"}}

    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        specification = task(mode="ollama", options={"model": "installed-local-model",
                                                     "allowed_origins": ["https://allowed.test"]})
        handle = runtime.submit(specification)
        assert run_task(runtime, handle.task_id, backend=Backend()).state == "succeeded"
        assert len(runtime.store.actions(handle.task_id)) == 1
        assert len(fake_sdk[0].actions) == 1


@pytest.mark.parametrize("failure", [CancelledError(), AuthorizationError("revoked"), AgentHumanReview("dialog")],
                         ids=["cancelled", "revoked", "human-review"])
def test_verifier_preserves_control_failures_instead_of_reporting_unknown(failure):
    specification = task()
    def failed(_clause):
        raise failure
    with pytest.raises(type(failure)):
        verify(TaskPolicy(specification), [], {}, browser_read=failed)


@pytest.mark.parametrize("value", ["passed", 1, {"passed": True}])
def test_invalid_verifier_response_is_unknown(value):
    reports = verify(TaskPolicy(task()), [], {}, browser_read=lambda _clause: value)
    assert reports[0]["status"] == "unknown"


def test_helper_verifier_refuses_a_clause_not_pinned_in_its_task(fake_sdk):
    from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
    target = BrowserTarget()
    specification = task()
    try:
        with operation_scope(TaskOperation(specification, lambda: None, None)):
            target.ready(specification)
            with pytest.raises(AgentTaskError, match="outside the owned task"):
                target.verify_browser(criterion(value="different"))
    finally:
        target.cleanup()
    assert fake_sdk[0].actions == []
