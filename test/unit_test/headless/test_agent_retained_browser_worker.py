"""Actual worker/target transitions with an external SDK double; never start a browser or input."""
import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from headless.test_agent_browser_target import FakeSession, spec
from je_auto_control.utils.agent_runtime.browser_target import BrowserTarget
from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.native_worker import NativeWorker

PROOF = {"contract": 1, "input_supported": False, "network_retired": True, "context_id": "a" * 32}


class ControlledSession(FakeSession):
    """Only replace the external SDK; worker/target dispatch and scope checks stay real."""

    readonly_contract_version = 1

    def __init__(self):
        super().__init__()
        self.context_id = "a" * 32
        self.description = dict(PROOF)
        self.freeze_error = None

    def freeze_readonly(self):
        if self.freeze_error:
            raise self.freeze_error
        return self

    def capabilities(self):
        return dict(self.description)


@pytest.fixture
def configured(monkeypatch, request):
    session = ControlledSession()
    monkeypatch.setattr("je_auto_control.utils.agent_runtime.browser_target._open_session",
                        lambda *_args, **_kwargs: session)
    target = BrowserTarget()
    definition = spec(**getattr(request, "param", {}))
    with operation_scope(TaskOperation(definition, lambda: None, None)):
        assert target.ready(definition) == (True, "")
    worker = NativeWorker(io.BytesIO(), io.BytesIO(), target=target)
    worker._spec, worker._profile_kind = definition, "browser"
    try:
        yield SimpleNamespace(session=session, target=target, worker=worker, spec=definition)
    finally:
        target.cleanup()


def test_worker_freezes_actual_original_target_before_readonly_proof(configured):
    before = configured.target.observe()["identity"]
    reply = configured.worker._dispatch("retire_browser", {})
    assert reply == PROOF
    assert configured.worker._dispatch("readonly_capabilities", {}) == PROOF
    assert configured.worker._dispatch("observe", {})["identity"] == before
    assert configured.session.closed is False
    configured.session.label = "independent updated DOM"
    assert configured.worker._dispatch("observe", {})["text"] == "independent updated DOM"


@pytest.mark.parametrize("operation,payload", [
    ("perform", {"tool": "AC_browser_fill", "arguments": {"selector": "#field", "value": "forbidden"}}),
    ("configure", {"spec": {}}), ("probe_browser", {"transfer": False}),
    ("unknown", {}), ("retire_browser", {"replace": True}),
])
def test_retired_worker_refuses_executable_reconfiguration_paths(configured, operation, payload):
    configured.worker._dispatch("retire_browser", {})
    with pytest.raises(AgentTaskError, match="read.only|retired"):
        configured.worker._dispatch(operation, payload)
    assert configured.session.actions == []
    with pytest.raises(AgentTaskError, match="read.only|retired"):
        configured.target.perform("AC_browser_fill", {"selector": "#field", "value": "forbidden"})


def test_retired_worker_refuses_native_ack_without_writing_an_event(configured):
    configured.worker._dispatch("retire_browser", {})
    with pytest.raises(AgentTaskError, match="read.only|retired"):
        configured.worker._input({"kind": "mouse_press", "keycode": 1})
    assert configured.worker._sink.getvalue() == b""


@pytest.mark.parametrize("marker", [None, False, True, 0, 2, "1"])
def test_unsupported_sdk_does_not_forge_proof_or_break_normal_cleanup(configured, marker):
    configured.session.readonly_contract_version = marker
    assert configured.worker._dispatch("retire_browser", {}) == {"supported": False}
    configured.target.cleanup()
    assert configured.session.closed


def test_freeze_failure_never_restores_worker_input_or_returns_reader(configured):
    configured.session.freeze_error = RuntimeError("PRIVATE_INPUT")
    with pytest.raises(AgentTaskError, match="retirement.*unconfirmed") as failure:
        configured.worker._dispatch("retire_browser", {})
    assert "PRIVATE_INPUT" not in str(failure.value)
    for operation in ("perform", "configure", "readonly_capabilities", "retire_browser"):
        with pytest.raises(AgentTaskError):
            configured.worker._dispatch(operation, {})
    assert configured.session.actions == []


@pytest.mark.parametrize("changes", [
    {"contract": True}, {"input_supported": True}, {"network_retired": False},
    {"context_id": "another-context"}, {"extra": "unreviewed"},
])
def test_sdk_description_must_match_actual_context_and_closed_contract(configured, changes):
    configured.session.description.update(changes)
    with pytest.raises(AgentTaskError, match="retirement.*unconfirmed"):
        configured.worker._dispatch("retire_browser", {})
    with pytest.raises(AgentTaskError):
        configured.worker._dispatch("readonly_capabilities", {})
    assert configured.session.actions == []


def test_frozen_cleanup_never_calls_native_release_functions(configured, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Read-only browser cleanup cannot inject native releases")

    monkeypatch.setattr("je_auto_control.wrapper.auto_control_keyboard.release_keyboard_key", forbidden)
    monkeypatch.setattr("je_auto_control.wrapper.auto_control_mouse.release_mouse", forbidden)
    configured.worker._dispatch("retire_browser", {})
    assert configured.worker._dispatch("cleanup", {"keys": [], "buttons": []}) == {"cleaned": True}
    assert configured.session.closed


def test_frozen_cleanup_refuses_unowned_input_and_reconfiguration(configured):
    configured.worker._dispatch("retire_browser", {})
    with pytest.raises(AgentTaskError, match="read.only"):
        configured.worker._dispatch("cleanup", {"keys": [{"keycode": 65}], "buttons": []})
    with pytest.raises(AgentTaskError, match="read.only|retired"):
        configured.target.ready(configured.spec)
    assert not configured.session.closed


def test_lost_live_sdk_proof_stays_unavailable_after_apparent_restoration(configured):
    configured.worker._dispatch("retire_browser", {})
    configured.session.description["network_retired"] = False
    with pytest.raises(AgentTaskError):
        configured.worker._dispatch("readonly_capabilities", {})
    configured.session.description = dict(PROOF)
    with pytest.raises(AgentTaskError):
        configured.worker._dispatch("readonly_capabilities", {})
    assert configured.session.actions == []


def test_missing_original_sdk_context_identity_cannot_accept_an_arbitrary_view(configured):
    configured.session.context_id = None
    with pytest.raises(AgentTaskError, match="retirement.*unconfirmed"):
        configured.worker._dispatch("retire_browser", {})
    assert configured.session.actions == []


def test_frozen_sdk_cleanup_cannot_dispatch_nested_tools(configured, monkeypatch):
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.tool_use_schema import run_tool_call
    clipboard = Mock(side_effect=AssertionError("A read-only cleanup reached an external clipboard"))
    monkeypatch.setitem(executor.event_dict, "AC_clipboard_get", clipboard)
    configured.worker._dispatch("retire_browser", {})
    original_close = configured.session.close
    monkeypatch.setattr(configured.session, "close", lambda: run_tool_call("AC_clipboard_get", {}))
    try:
        with pytest.raises(AgentTaskError):
            configured.worker._dispatch("cleanup", {"keys": [], "buttons": []})
        clipboard.assert_not_called()
    finally:
        monkeypatch.setattr(configured.session, "close", original_close)


def reader_spec(configured):
    value = configured.spec.to_dict()
    value.update(goal="Reviewed completion: " + value["goal"], mode="external", actions=[])
    return value


def test_reader_scope_bind_does_not_reconfigure_original_input_or_change_context(configured):
    configured.worker._dispatch("retire_browser", {})
    original = configured.worker._spec
    assert configured.worker._dispatch("bind_browser_reader", {"spec": reader_spec(configured)}) == PROOF
    assert configured.worker._spec is original
    assert configured.worker._dispatch("observe", {})["identity"] == configured.target.observe()["identity"]
    with pytest.raises(AgentTaskError):
        configured.worker._dispatch("configure", {"spec": reader_spec(configured)})


@pytest.mark.parametrize("changed", [
    {"actions": [{"tool": "AC_browser_fill", "arguments": {"selector": "#field", "value": "forbidden"}}]},
    {"mode": "skill"}, {"roots": ["D:/"]}, {"allowed_tools": ["AC_click_mouse"]},
    {"options": {"allowed_origins": ["https://unreviewed.test"]}},
    {"options": {"allowed_origins": ["https://allowed.test"], "dag_batch": {"private": True}}},
    {"options": {"allowed_origins": ["https://allowed.test"], "skill_pin": {"private": True}}},
    {"success_criteria": [{"kind": "actions_complete"}, {"kind": "file_exists", "path": "D:/private"}]},
])
def test_readonly_scope_bind_cannot_broaden_original_permissions_or_change_evidence(configured, changed):
    configured.worker._dispatch("retire_browser", {})
    with pytest.raises(AgentTaskError):
        configured.worker._dispatch("bind_browser_reader", {"spec": {**reader_spec(configured), **changed}})
    assert configured.session.actions == []


@pytest.mark.parametrize("configured", [{"inputs": {"flag": 1}}], indirect=True)
def test_readonly_scope_bind_preserves_original_json_input_types(configured):
    configured.worker._dispatch("retire_browser", {})
    changed = {**reader_spec(configured), "inputs": {"flag": True}}
    with pytest.raises(AgentTaskError, match="original|scope"):
        configured.worker._dispatch("bind_browser_reader", {"spec": changed})
    assert configured.session.actions == []


def test_sdk_retirement_cannot_dispatch_nested_tools_or_ambient_reads(configured, monkeypatch):
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.tool_use_schema import run_tool_call
    clipboard = Mock(return_value=None)
    monkeypatch.setitem(executor.event_dict, "AC_clipboard_get", clipboard)
    monkeypatch.setattr(configured.session, "freeze_readonly", lambda: run_tool_call("AC_clipboard_get", {}))
    with pytest.raises(AgentTaskError, match="retirement.*unconfirmed"):
        configured.worker._dispatch("retire_browser", {})
    clipboard.assert_not_called()
    assert configured.session.actions == []


def test_sdk_retirement_refuses_native_notification_before_any_ack(configured, monkeypatch):
    from je_auto_control.wrapper._input_observer import input_event

    def freeze():
        input_event("key_press", keycode=65)
        return configured.session

    monkeypatch.setattr(configured.session, "freeze_readonly", freeze)
    with pytest.raises(AgentTaskError, match="retirement.*unconfirmed"):
        configured.worker._dispatch("retire_browser", {})
    assert configured.worker._sink.getvalue() == b""
    assert configured.session.actions == []


@pytest.mark.parametrize("mechanism", ["tool", "native"])
def test_live_sdk_capability_probe_cannot_escape_closed_worker_scope(configured, monkeypatch, mechanism):
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.tool_use_schema import run_tool_call
    from je_auto_control.wrapper._input_observer import input_event
    configured.worker._dispatch("retire_browser", {})
    clipboard = Mock(return_value=None)
    monkeypatch.setitem(executor.event_dict, "AC_clipboard_get", clipboard)

    def capability():
        if mechanism == "tool":
            run_tool_call("AC_clipboard_get", {})
        else:
            input_event("key_press", keycode=65)
        return dict(PROOF)

    monkeypatch.setattr(configured.session, "capabilities", capability)
    with pytest.raises(AgentTaskError, match="retirement.*unconfirmed"):
        configured.worker._dispatch("readonly_capabilities", {})
    clipboard.assert_not_called()
    assert configured.worker._sink.getvalue() == b""
