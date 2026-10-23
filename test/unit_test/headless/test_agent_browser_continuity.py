"""A discarded browser context cannot reuse verified form history to submit a fresh empty form."""
from contextlib import closing

from je_auto_control.utils.agent_runtime import AgentRuntime
from je_auto_control.utils.agent_runtime.browser_target import BrowserTarget
from je_auto_control.utils.agent_runtime.runner import run_task
from .test_agent_browser_target import fake_sdk as _fake_sdk, spec

fake_sdk = _fake_sdk


def form():
    return spec(actions=[{"tool": "AC_browser_fill", "arguments": {"selector": "#field", "value": "reviewed"},
                          "expect_result": True},
                         {"tool": "AC_browser_click", "arguments": {"selector": "#save"}, "expect_result": True}])


def fill_first(runtime, task_id):
    observed = runtime.observe(task_id)
    runtime.act(task_id, {"tool": "AC_browser_fill", "arguments": {"selector": "#field", "value": "reviewed"},
                          "observation_id": observed.observation_id})


def test_pause_with_confirmed_fields_cannot_submit_a_new_empty_browser(fake_sdk, tmp_path):
    session, opener = fake_sdk
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        task = runtime.submit(form())
        fill_first(runtime, task.task_id)
        runtime.pause(task.task_id)
        session.value = ""  # The old draft is gone; a reopened SDK is not evidence of the old form state.
        runtime.resume(task.task_id)
        outcome = run_task(runtime, task.task_id)
        assert outcome.state == "waiting_user"
        assert "browser context" in outcome.reason
        assert [action.kind for action in session.actions] == ["fill"]
        assert len(runtime.store.actions(task.task_id)) == 1
        opener.assert_called_once()


def test_runtime_restart_cannot_turn_old_browser_receipts_into_live_form_state(fake_sdk, tmp_path):
    path = tmp_path / "runtime.sqlite"
    with closing(AgentRuntime(path, targets={"reviewed-browser": BrowserTarget()})) as original:
        task = original.submit(form())
        fill_first(original, task.task_id)
    with closing(AgentRuntime(path, targets={"reviewed-browser": BrowserTarget()})) as resumed:
        resumed.resume(task.task_id)
        outcome = run_task(resumed, task.task_id)
        assert outcome.state == "waiting_user"
        assert "browser context" in outcome.reason
        assert len(fake_sdk[0].actions) == 1
        fake_sdk[1].assert_called_once()


def test_pause_before_first_effect_and_uninterrupted_skill_remain_runnable(fake_sdk, tmp_path):
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        task = runtime.submit(form())
        runtime.pause(task.task_id)
        runtime.resume(task.task_id)
        assert run_task(runtime, task.task_id).state == "succeeded"
        assert [action.kind for action in fake_sdk[0].actions] == ["fill", "click"]
        fake_sdk[1].assert_called_once()


def test_external_browser_owner_can_reobserve_a_fresh_context_after_pause(fake_sdk, tmp_path):
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        task = runtime.submit(spec(mode="external", actions=[]))
        old = runtime.observe(task.task_id)
        runtime.pause(task.task_id)
        runtime.resume(task.task_id)
        fresh = runtime.observe(task.task_id)
        assert old.data["identity"]["browser_session"] != fresh.data["identity"]["browser_session"]
        assert fake_sdk[1].call_count == 2


def test_only_reviewed_non_effects_allow_a_fresh_skill_context():
    from je_auto_control.utils.agent_runtime.browser_continuity import require_browser_continuity
    require_browser_continuity(form(), [{"status": "not_applied"}, {"status": "failed"}], False)
