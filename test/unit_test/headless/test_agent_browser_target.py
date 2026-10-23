"""Managed WebRunner binding uses fake SDK sessions and never starts browsers or native input."""
import io
import json
import sys
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTargetProfile, AgentTaskSpec, AgentTaskError
from je_auto_control.utils.agent_runtime.browser_commands import BROWSER_TOOLS, browser_fill, browser_read
from je_auto_control.utils.agent_runtime.browser_target import BrowserTarget
from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
from je_auto_control.utils.agent_runtime.errors import AgentHumanReview, AgentObservationStale
from je_auto_control.utils.agent_runtime.runner import run_task


def profile(**changes):
    return AgentTargetProfile.from_dict({"name": "reviewed-browser", "kind": "browser",
        "allowed_tools": sorted(BROWSER_TOOLS), "settings": {"allowed_origins": ["https://allowed.test"]}, **changes})


def spec(**changes):
    return AgentTaskSpec.from_dict({"goal": "fill and verify", "target": "reviewed-browser", "mode": "skill",
        "allowed_tools": sorted(BROWSER_TOOLS), "options": {"allowed_origins": ["https://allowed.test"]},
        "actions": [{"tool": "AC_browser_fill", "arguments": {"selector": "#field", "value": "reviewed"}},
                    {"tool": "AC_browser_read", "arguments": {"operation": "value", "selector": "#field"},
                     "expect_result": "reviewed"}], "success_criteria": [{"kind": "actions_complete"}], **changes})


class FakeSession:
    def __init__(self):
        self.closed = False
        self.value = ""
        self.actions = []
        self.failure = None
        self.label = "Field"
        self.url = "https://allowed.test/form"
        self.policy = SimpleNamespace(require=Mock())

    def set_timeout(self, value):
        self.timeout = value

    def observe(self):
        return {"url": "https://allowed.test/form", "title": "Form", "text": self.label,
                "elements": [{"selector": "#field", "text": self.label, "tag": "input",
                              "is_visible": True, "is_enabled": True}],
                "frames": [{"selector": "#frame", "elements": [{"selector": "#save", "text": "Save",
                            "tag": "button", "is_visible": True, "is_enabled": True}]}]}

    def perform(self, action):
        self.actions.append(action)
        if self.failure:
            raise self.failure
        if action.kind == "fill":
            self.value = action.value

    def read_value(self, _selector, _frame=""):
        return self.value

    def text(self, _selector, _frame=""):
        return "visible text"

    def visible(self, _selector, _frame=""):
        return True

    def close(self):
        self.closed = True


@pytest.fixture
def fake_sdk(monkeypatch):
    class Action(SimpleNamespace):
        def __init__(self, kind, **values):
            super().__init__(kind=kind, **values)

    monkeypatch.setitem(sys.modules, "je_web_runner.api.ai", SimpleNamespace(AgentAction=Action))
    session = FakeSession()
    opener = Mock(return_value=session)
    monkeypatch.setattr("je_auto_control.utils.agent_runtime.browser_target._open_session", opener)
    return session, opener


def test_profile_is_inert_narrows_origins_and_refuses_unreviewed_settings(fake_sdk):
    session, opener = fake_sdk
    configuration = profile()
    configuration.check(spec())
    assert configuration.settings["allowed_origins"] == ("https://allowed.test:443",)
    with pytest.raises(AgentTaskError, match="network origins"):
        configuration.check(spec(options={"allowed_origins": ["https://outside.test"]}))
    for settings in ({"allowed_origins": []}, {"allowed_origins": ["https://allowed.test/path"]},
                     {"allowed_origins": ["https://allowed.test"], "argv": ["external"]}):
        with pytest.raises(AgentTaskError):
            profile(settings=settings)
    opener.assert_not_called()
    assert not session.closed


@pytest.mark.parametrize("changes", [{"apps": ["browser"]}, {"allowed_tools": ["AC_write"]}])
def test_browser_profile_cannot_grant_desktop_control(fake_sdk, changes):
    with pytest.raises(AgentTaskError):
        profile(**changes)
    fake_sdk[1].assert_not_called()


def test_browser_factory_uses_owned_helper_without_desktop_lock(fake_sdk, monkeypatch):
    from je_auto_control.utils.agent_runtime.target_factory import build_target
    monkeypatch.setattr("je_auto_control.utils.agent_runtime.native_target._desktop_lock_path",
                        lambda: pytest.fail("browser touched shared desktop ownership"))
    target = build_target(profile())
    assert target._resource_path.name == "browser-" + profile().digest + ".lock"
    assert target._channel is None
    fake_sdk[1].assert_not_called()


def test_fake_session_uses_common_runtime_actions_and_readback(fake_sdk, tmp_path):
    session, opener = fake_sdk
    target = BrowserTarget()
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": target})) as runtime:
        handle = runtime.submit(spec())
        result = run_task(runtime, handle.task_id)
        assert result.state == "succeeded"
        receipts = runtime.store.actions(handle.task_id)
        assert [item["status"] for item in receipts] == ["confirmed", "confirmed"]
        assert receipts[-1]["result"] == "reviewed"
        assert len(session.actions) == 1
        assert session.actions[0].kind == "fill"
    assert session.closed
    opener.assert_called_once_with(("https://allowed.test",))


def test_dom_reference_resolves_frame_and_changed_observation_refuses_dispatch(fake_sdk, tmp_path):
    session, _opener = fake_sdk
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        handle = runtime.submit(spec(mode="external", actions=[]))
        observed = runtime.observe(handle.task_id)
        assert observed.data["elements"][1]["frame"] == "#frame"
        result = runtime.act(handle.task_id, {"tool": "AC_browser_click", "arguments": {},
                             "reference": {"element_index": 1}, "observation_id": observed.observation_id})
        assert result.result is True
        assert session.actions[-1].selector == "#save"
        assert session.actions[-1].frame == "#frame"
        observed = runtime.observe(handle.task_id)
        session.label = "Changed"
        with pytest.raises(AgentObservationStale):
            runtime.act(handle.task_id, {"tool": "AC_browser_click", "arguments": {},
                        "reference": {"element_index": 0}, "observation_id": observed.observation_id})
        assert len(session.actions) == 1


def test_failed_browser_effect_is_uncertain_and_never_replayed(fake_sdk, tmp_path):
    session, _opener = fake_sdk
    session.failure = RuntimeError("raw browser exception includes SECRET")
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"reviewed-browser": BrowserTarget()})) as runtime:
        handle = runtime.submit(spec())
        assert run_task(runtime, handle.task_id).state == "waiting_user"
        assert len(session.actions) == 1
        receipt = runtime.store.actions(handle.task_id)[0]
        assert receipt["status"] == "uncertain"
        assert "SECRET" not in json.dumps(receipt)
        with pytest.raises(AgentTaskError, match="reconciliation"):
            runtime.resume(handle.task_id)


def test_unbound_or_widened_commands_cannot_call_sdk(fake_sdk):
    session, _opener = fake_sdk
    with pytest.raises(AgentTaskError, match="managed WebRunner session"):
        browser_fill("#field", "secret")
    from je_auto_control.utils.agent_runtime.browser_commands import browser_session_scope
    restricted = spec(allowed_tools=["AC_browser_read"], actions=[])
    with operation_scope(TaskOperation(restricted, lambda: None, None)), browser_session_scope(session):
        with pytest.raises(AgentTaskError, match="not allowed"):
            browser_fill("#field", "secret")
        assert browser_read("text", "body") == "visible text"
    assert session.actions == []


def test_browser_worker_uses_profile_pin_without_native_activity(fake_sdk, monkeypatch):
    from je_auto_control.utils.agent_runtime.native_worker import NativeWorker
    from je_auto_control.utils.agent_runtime import activity
    monkeypatch.setattr(activity, "desktop_activity_gate", lambda *_args: pytest.fail("native activity probe"))
    worker = NativeWorker(io.BytesIO(), io.BytesIO())
    configuration = profile()
    task = spec(options={"allowed_origins": ["https://allowed.test"], "target_profile": {
        "name": configuration.name, "digest": configuration.digest}})
    ready = worker._dispatch("configure", {"profile": configuration.to_dict(), "spec": task.to_dict()})
    assert ready == {"ready": True, "reason": ""}
    assert isinstance(worker._target, BrowserTarget)
    assert worker._dispatch("configure", {"profile": configuration.to_dict(), "spec": task.to_dict()}) == ready
    fake_sdk[1].assert_called_once()
    assert worker._dispatch("observe", {})["elements"][0]["selector"] == "#field"
    assert worker._dispatch("cleanup", {"keys": [], "buttons": []}) == {"cleaned": True}
    assert fake_sdk[0].closed


def test_native_owner_requests_browser_cleanup_with_no_held_input(tmp_path):
    from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
    target = NativeDesktopTarget(profile=profile().to_dict(), resource_path=tmp_path / "owned.lock")
    channel = Mock(retired=False)
    target._channel = channel
    target.cleanup()
    assert channel.request.call_args.args == ("cleanup", {"keys": [], "buttons": []})
    channel.close.assert_called_once()
    assert target._channel is None


def test_sdk_dialog_keeps_typed_human_review_boundary(fake_sdk):
    from je_auto_control.utils.agent_runtime.browser_commands import browser_session_scope
    session, _opener = fake_sdk

    class DialogError(RuntimeError):
        reason = "human_review_required"

    session.failure = DialogError("hidden dialog content")
    with operation_scope(TaskOperation(spec(), lambda: None, None)), browser_session_scope(session):
        with pytest.raises(AgentHumanReview, match="human review"):
            browser_fill("#field", "reviewed")


def test_model_schemas_offer_dom_indexes_without_changing_command_signature():
    from je_auto_control.utils.agent_runtime.model_tools import offered_tools, referenced_proposal
    tool = offered_tools(["AC_browser_fill"])[0]["function"]
    parameters = tool["parameters"]
    assert "selector" not in parameters["required"]
    assert parameters["properties"]["observed_target"]["required"] == ["element_index"]
    assert parameters["properties"]["value"]["maxLength"] == 8000
    read = offered_tools(["AC_browser_read"])[0]["function"]["parameters"]
    assert read["properties"]["operation"]["enum"] == ["text", "value", "visible"]
    proposal = referenced_proposal("AC_browser_fill", {"value": "x", "observed_target": {"element_index": 1}})
    assert proposal["reference"] == {"element_index": 1}
    with pytest.raises(AgentTaskError, match="DOM element"):
        referenced_proposal("AC_browser_fill", {"value": "x", "observed_target": {"image_point": [1, 2]}})


def test_read_reference_accepts_disabled_visible_field_but_effects_refuse_it():
    from je_auto_control.utils.agent_runtime.observation_refs import resolve_action
    data = {"elements": [{"index": 0, "selector": "#field", "frame": "", "enabled": False, "visible": True}]}
    arguments, evidence = resolve_action("AC_browser_read", {"operation": "value"}, {"element_index": 0}, data)
    assert arguments == {"operation": "value", "selector": "#field", "frame": ""}
    assert evidence["element"]["enabled"] is False
    with pytest.raises(AgentTaskError, match="not actionable"):
        resolve_action("AC_browser_click", {}, {"element_index": 0}, data)


@pytest.mark.parametrize("version", [None, True, 0, 2, "1", 1.0])
def test_sdk_contract_marker_is_checked_before_policy_or_browser_start(monkeypatch, version):
    from je_auto_control.utils.agent_runtime.browser_target import _open_session
    origin_policy = Mock()
    sdk = SimpleNamespace(contract_version=version, open=Mock())
    monkeypatch.setitem(sys.modules, "je_web_runner.api.ai",
                        SimpleNamespace(BrowserOriginPolicy=origin_policy, ManagedBrowserSession=sdk))
    with pytest.raises(AgentTaskError, match="contract version 1"):
        _open_session(("https://allowed.test",))
    sdk.open.assert_not_called()
    origin_policy.assert_not_called()


@pytest.mark.parametrize("value", ["😀" * 4001, "invalid\ud800"], ids=["overlimit", "invalid-unicode"])
def test_browser_fill_rejects_incompatible_unicode_before_sdk_effect(fake_sdk, value):
    from je_auto_control.utils.agent_runtime.browser_commands import browser_session_scope
    session = fake_sdk[0]
    with operation_scope(TaskOperation(spec(), lambda: None, None)), browser_session_scope(session):
        with pytest.raises(AgentTaskError):
            browser_fill("#field", value)
    assert session.actions == []


def test_readiness_keeps_actionable_trusted_sdk_compatibility_failure(fake_sdk):
    session, opener = fake_sdk
    opener.side_effect = AgentTaskError("managed browser contract version 1 is required before startup")
    with pytest.raises(AgentTaskError, match="contract version 1"):
        BrowserTarget().ready(spec())
    assert session.actions == []
