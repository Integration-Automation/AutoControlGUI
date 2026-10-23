"""Browser form/transfer drafts verify real state changes through a fake owned SDK session."""
from contextlib import closing
from unittest.mock import Mock

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError, draft_agent_workflow
from je_auto_control.utils.agent_runtime.browser_commands import browser_session_scope, browser_wait
from je_auto_control.utils.agent_runtime.browser_target import BrowserTarget
from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.runner import run_task
from .test_agent_browser_target import fake_sdk, spec  # noqa: F401 - shared optional-SDK-free fixture


@pytest.fixture
def browser(fake_sdk):
    session, _opener = fake_sdk
    session.values = {"#source": "  Ada  "}
    session.confirmation = "ready"
    session.submissions = 0
    session.wrong = False

    def perform(action):
        session.actions.append(action)
        if action.kind == "fill":
            session.values[action.selector] = action.value
        if action.kind == "click" and action.selector == "#new":
            session.confirmation = "ready"
        if action.kind == "click" and action.selector == "#save":
            session.submissions += 1
            session.confirmation = "saved"

    session.perform = perform
    session.read_value = lambda selector, _frame="": "wrong" if session.wrong else session.values.get(selector, "")
    session.text = lambda _selector, _frame="": session.confirmation
    return session


def form_config(tmp_path, **changes):
    source = tmp_path / "rows.csv"
    source.write_text("name\nAda\nGrace\n", encoding="utf-8")
    return {"backend": "browser", "roots": [str(tmp_path)], "source": str(source),
        "target": "reviewed-browser", "allowed_origins": ["https://allowed.test"], "url": "https://allowed.test/form",
        "fields": [{"column": "name", "selector": "#field"}], "new_record_selector": "#new",
        "submit_selector": "#save", "confirmation_selector": "#confirmation", "confirmation_value": "saved",
        "wait_seconds": .5, **changes}


def transfer_config(**changes):
    return {"backend": "browser", "allowed_origins": ["https://allowed.test", "https://other.test"],
        "source_url": "https://allowed.test/source", "destination_url": "https://other.test/destination",
        "fields": [{"source": "#source", "destination": "#destination", "transform": "strip"}],
        "submit_selector": "#save", "confirmation_selector": "#confirmation", "confirmation_value": "saved",
        "wait_seconds": .5, **changes}


def test_csv_browser_flow_reads_each_field_and_each_fresh_submission(browser, tmp_path):
    draft = draft_agent_workflow("batch_form", form_config(tmp_path))
    assert all(action["tool"].startswith("AC_browser_") for action in draft["actions"])
    assert draft["apps"] == []
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        task = runtime.submit(draft)
        result = run_task(runtime, task.task_id)
        assert result.state == "succeeded", result.reason
        assert browser.submissions == 2
        assert browser.values["#field"] == "Grace"
        assert runtime.receipts(task.task_id)["rows"] == [
            {"row": "1", "status": "success"}, {"row": "2", "status": "success"}]


def test_stale_browser_confirmation_refuses_submit_and_resume_does_not_duplicate(browser, tmp_path):
    browser.confirmation = "saved"
    draft = draft_agent_workflow("batch_form", form_config(tmp_path, new_record_selector=""))
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        task = runtime.submit(draft)
        assert run_task(runtime, task.task_id).state == "waiting_user"
        assert browser.submissions == 0
        runtime.resume(task.task_id)
        assert run_task(runtime, task.task_id).state == "waiting_user"
        assert browser.submissions == 0


def test_mismatched_browser_value_stops_before_submission(browser, tmp_path):
    browser.wrong = True
    draft = draft_agent_workflow("batch_form", form_config(tmp_path))
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        task = runtime.submit(draft)
        assert run_task(runtime, task.task_id).state == "waiting_user"
        assert browser.submissions == 0
        assert sum(action.kind == "fill" for action in browser.actions) == 1


def test_browser_transfer_captures_transforms_and_reads_back_before_save(browser, tmp_path):
    draft = draft_agent_workflow("transfer", transfer_config())
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        task = runtime.submit(draft)
        assert run_task(runtime, task.task_id).state == "succeeded"
        assert browser.values["#destination"] == "Ada"
        assert browser.submissions == 1
        navigations = [action.value for action in browser.actions if action.kind == "navigate"]
        assert navigations == ["https://allowed.test/source", "https://other.test/destination"]


@pytest.mark.parametrize("changes", [
    {"url": "https://outside.test/form"}, {"apps": ["browser"]}, {"allowed_origins": []},
    {"backend": "unknown"}, {"backend": []}, {"wait_seconds": True}, {"confirmation_value": ""},
    {"fields": [{"column": "missing", "selector": "#field"}]},
    {"fields": [{"column": "name", "selector": "#field", "script": "unreviewed"}]},
    {"confirmation_column": "missing"}, {"submit_selector": ""},
])
def test_invalid_browser_drafts_have_no_session_or_action_effects(fake_sdk, tmp_path, changes):
    with pytest.raises(AgentTaskError):
        draft_agent_workflow("batch_form", form_config(tmp_path, **changes))
    fake_sdk[1].assert_not_called()
    assert fake_sdk[0].actions == []


def test_browser_backend_never_falls_back_to_desktop_workspace(fake_sdk):
    with pytest.raises(AgentTaskError):
        draft_agent_workflow("workspace", {"backend": "browser", "allowed_origins": ["https://allowed.test"]})
    fake_sdk[1].assert_not_called()


def test_browser_wait_polls_reads_only_and_rejects_late_matching_result(fake_sdk, monkeypatch):
    from je_auto_control.utils.agent_runtime import browser_commands
    session = fake_sdk[0]
    session.text = Mock(side_effect=["pending", "saved"])
    scoped = spec(allowed_tools=["AC_browser_wait"], actions=[])
    with operation_scope(TaskOperation(scoped, lambda: None, None)), browser_session_scope(session):
        assert browser_wait("text", "#confirmation", "saved", timeout_seconds=1) == "saved"
    assert session.text.call_count == 2
    assert session.actions == []
    session.text = Mock(return_value="saved")
    times = iter([10, 10, 12])
    monkeypatch.setattr(browser_commands.time, "monotonic", lambda: next(times))
    with operation_scope(TaskOperation(scoped, lambda: None, None)), browser_session_scope(session):
        with pytest.raises(AgentTaskError, match="deadline"):
            browser_wait("text", "#confirmation", "saved", timeout_seconds=1)
    assert session.actions == []
    session.text.assert_called_once()


def test_browser_wait_allows_newly_appearing_element_without_reading_absent_control(fake_sdk):
    session = fake_sdk[0]
    session.visible = Mock(side_effect=[False, True])
    session.text = Mock(return_value="saved")
    scoped = spec(allowed_tools=["AC_browser_wait"], actions=[])
    with operation_scope(TaskOperation(scoped, lambda: None, None)), browser_session_scope(session):
        assert browser_wait("text", "#confirmation", "saved", timeout_seconds=1) == "saved"
    session.text.assert_called_once()
    assert session.visible.call_count == 2
    assert session.timeout < 1
    assert session.actions == []


def test_browser_draft_rejects_overlimit_unicode_before_session_or_effect(fake_sdk, tmp_path):
    config = form_config(tmp_path)
    from pathlib import Path
    Path(config["source"]).write_text("name\n" + "😀" * 4001 + "\n", encoding="utf-8")
    with pytest.raises(AgentTaskError):
        draft_agent_workflow("batch_form", config)
    fake_sdk[1].assert_not_called()
    assert fake_sdk[0].actions == []
