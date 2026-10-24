"""Fresh read-only helpers cannot acknowledge input, upgrade authority or clear unknown resource witnesses."""
import io
import json
import sys
from unittest.mock import Mock

import pytest

from je_auto_control.utils.agent_runtime import AgentTaskError, AgentTaskSpec
from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
from je_auto_control.utils.agent_runtime.input_journal import InputJournal
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.agent_runtime.readonly_target import CompletionReader, ReadOnlyNativeTarget
from je_auto_control.utils.agent_runtime.readonly_worker import ReadOnlyWorker


def spec(tmp_path):
    return AgentTaskSpec.from_dict({"goal": "fresh completion observation", "target": "local-files",
        "roots": [str(tmp_path)], "allowed_tools": ["AC_workflow_manifest"],
        "success_criteria": [{"kind": "file_exists", "path": str(tmp_path / "result.txt")}],
        "budget": {"action_seconds": 5}})


def test_standard_file_reader_is_fresh_scope_bound_and_retires_without_calling_original_target(tmp_path, monkeypatch):
    definition = spec(tmp_path)
    source = NativeDesktopTarget(resource_path=tmp_path / "input.lock")
    monkeypatch.setattr(source, "observe", Mock(side_effect=AssertionError("old observation reused")))
    monkeypatch.setattr(source, "perform", Mock(side_effect=AssertionError("source input called")))
    parent = TaskOperation(definition, lambda: None, None)
    with operation_scope(parent):
        with source.completion_reader(definition) as reader:
            assert reader.observe()["identity"] == "local-files" and not reader.retired
            with operation_scope(TaskOperation(definition, lambda: None, None)), pytest.raises(AgentTaskError):
                reader.observe()
        assert reader.retired
        with pytest.raises(AgentTaskError, match="closed"):
            reader.observe()
    assert source._channel is None and source._resource is None
    witness = InputJournal(tmp_path / "input.lock").read()
    assert witness["owner"] is None and witness["held"] == {} and witness["in_flight"] is None
    source.observe.assert_not_called()
    source.perform.assert_not_called()


def test_unknown_input_journal_is_never_cleared_by_opening_a_reader(tmp_path):
    path = tmp_path / "input.lock"
    journal = InputJournal(path)
    journal.acquire()
    before = journal.path.read_bytes()
    source = NativeDesktopTarget(resource_path=path)
    definition = spec(tmp_path)
    with (operation_scope(TaskOperation(definition, lambda: None, None)),
          pytest.raises(AgentTaskError, match="recovery")):
        with source.completion_reader(definition):
            pytest.fail("unknown witness was accepted")
    assert journal.path.read_bytes() == before


@pytest.mark.parametrize("operation", ["perform", "configure_readwrite", "probe_browser"])
def test_worker_refuses_execution_and_upgrade_before_calling_a_target(tmp_path, operation):
    target = Mock()
    worker = ReadOnlyWorker(io.BytesIO(), io.BytesIO(), target=target)
    with pytest.raises(AgentTaskError, match="read-only"):
        worker._dispatch(operation, {"tool": "AC_click_mouse", "arguments": {}})
    target.perform.assert_not_called()


def test_worker_refuses_native_ack_and_nonempty_cleanup_without_any_target_call():
    target, sink = Mock(), io.BytesIO()
    worker = ReadOnlyWorker(io.BytesIO(), sink, target=target)
    with pytest.raises(AgentTaskError, match="acknowledge"):
        worker._input({"kind": "mouse_press", "x": 1, "y": 2})
    with pytest.raises(AgentTaskError, match="cleanup input"):
        worker._dispatch("cleanup", {"keys": [{"keycode": 65}], "buttons": []})
    assert sink.getvalue() == b"" and not target.method_calls


HELPER = '''
import json,sys
for line in sys.stdin:
    request=json.loads(line)
    op=request['operation']
    if op=='bootstrap': result={'protocol':1}
    elif op=='readonly_capabilities': result={'contract':1,'input_supported':False}
    elif op=='configure': result={'ready':True}
    elif op=='observe':
        print(json.dumps({'id':request['id'],'event':{'kind':'key_press','keycode':65,'is_shift':False}}),flush=True)
        sys.stdin.readline()
        break
    print(json.dumps({'id':request['id'],'result':result}),flush=True)
'''


def test_unexpected_input_from_a_helper_is_not_acked_and_retains_quarantine(tmp_path):
    definition = spec(tmp_path)
    path = tmp_path / "input.lock"
    adapter = ReadOnlyNativeTarget(argv=[sys.executable, "-u", "-c", HELPER], resource_path=path)
    with operation_scope(TaskOperation(definition, lambda: None, None)):
        reader = CompletionReader(adapter, definition)
        with pytest.raises(AgentTaskError):
            with reader.session():
                reader.observe()
        assert not reader.retired
        with pytest.raises(AgentTaskError, match="closed"):
            reader.observe()
    witness = InputJournal(path).read()
    assert witness["owner"] and witness["in_flight"] == "readonly_input_violation"
    assert json.loads(path.with_suffix(".lock.journal").read_text())["owner"]


@pytest.mark.parametrize("reply", [{"contract": True, "input_supported": False},
                                   {"contract": 1, "input_supported": 0},
                                   {"contract": 1, "input_supported": False, "upgrade": True}])
def test_reader_refuses_nonexact_capabilities_before_any_configuration(tmp_path, reply):
    adapter = Mock()
    adapter._request.return_value = reply
    definition = spec(tmp_path)
    with operation_scope(TaskOperation(definition, lambda: None, None)):
        reader = CompletionReader(adapter, definition)
        with pytest.raises(AgentTaskError, match="contract"):
            with reader.session():
                pytest.fail("bad capability accepted")
    adapter.ready.assert_not_called()
    adapter.cleanup.assert_called_once()


def test_normal_worker_and_active_source_are_not_used_as_readonly_fallbacks(tmp_path):
    source = NativeDesktopTarget(argv=[sys.executable, "-u", "-c", "raise AssertionError('launched')"],
                                 resource_path=tmp_path / "input.lock")
    definition = spec(tmp_path)
    with (operation_scope(TaskOperation(definition, lambda: None, None)),
          pytest.raises(AgentTaskError, match="declared")):
        source.completion_reader(definition)
    assert not InputJournal(tmp_path / "input.lock").path.exists()


def test_nested_executor_calls_from_observation_are_denied_before_clipboard_access(tmp_path, monkeypatch):
    from je_auto_control.utils.tool_use_schema import run_tool_call
    from je_auto_control.utils.executor.action_executor import executor
    clipboard = Mock(side_effect=AssertionError("clipboard accessed"))
    monkeypatch.setitem(executor.event_dict, "AC_clipboard_get", clipboard)

    class Target:
        def ready(self, _spec):
            return True, ""

        def observe(self):
            return run_tool_call("AC_clipboard_get", {})

    worker = ReadOnlyWorker(io.BytesIO(), io.BytesIO(), target=Target())
    worker._dispatch("configure", {"spec": spec(tmp_path).to_dict(), "owner": {}})
    with pytest.raises(AgentTaskError, match="read-only"):
        worker._dispatch("observe", {})
    clipboard.assert_not_called()


def test_passive_target_diagnostics_never_invoke_custom_capability_descriptors(tmp_path):
    from je_auto_control.utils.agent_runtime import AgentRuntime

    class Target:
        @property
        def supports_readonly_completion(self):
            pytest.fail("passive diagnostics invoked a custom descriptor")

    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={"injected": Target()})
    try:
        report = runtime.target_profiles.describe()["targets"][0]
        assert report["readonly_completion"] == {"status": "not_supported"}
        assert report["readiness"] == "not_probed" and report["native_evidence"] == "not_recorded"
    finally:
        runtime.close()


@pytest.mark.parametrize("tool", ["AC_workflow_open", "AC_workflow_download", "AC_click_mouse"])
def test_host_proxy_refuses_tools_before_local_workflow_or_helper_startup(tmp_path, tool):
    adapter = ReadOnlyNativeTarget(resource_path=tmp_path / "input.lock")
    with pytest.raises(AgentTaskError, match="read-only"):
        adapter.perform(tool, {})
    with pytest.raises(AgentTaskError, match="read-only"):
        adapter.recover("must not clear a witness", actor="fixture")
    assert not InputJournal(tmp_path / "input.lock").path.exists()


def test_worker_configuration_cannot_be_replaced_or_upgraded(tmp_path):
    target = Mock()
    target.ready.return_value = (True, "")
    worker = ReadOnlyWorker(io.BytesIO(), io.BytesIO(), target=target)
    payload = {"spec": spec(tmp_path).to_dict(), "owner": {}}
    worker._dispatch("configure", payload)
    with pytest.raises(AgentTaskError, match="replace"):
        worker._dispatch("configure", payload)
    assert target.ready.call_count == 1


def test_browser_configuration_never_starts_a_fresh_browser():
    target = Mock()
    worker = ReadOnlyWorker(io.BytesIO(), io.BytesIO(), target=target)
    worker._profile_kind = "browser"
    assert worker._operation("configure", {})["ready"] is False
    target.ready.assert_not_called()


def test_file_reader_refuses_unpinned_browser_criteria_before_transport(tmp_path):
    adapter = Mock()
    definition = spec(tmp_path)
    with operation_scope(TaskOperation(definition, lambda: None, None)):
        reader = CompletionReader(adapter, definition)
        with pytest.raises(AgentTaskError, match="not pinned"):
            reader.verify_browser({"kind": "browser", "check": "title_equals", "value": "unreviewed"})
    adapter._request.assert_not_called()


def test_revocation_during_an_active_reader_prevents_further_reads_and_still_retires(tmp_path):
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
    from je_auto_control.utils.rbac.users import UserStore
    users = UserStore(tmp_path / "users.json")
    users.add_user(user_id="owner", display_name="Owner", role="operator")
    owner = AuthorizationContext("owner", "operator", store_path=str(users.path))
    definition = spec(tmp_path)
    source = NativeDesktopTarget(resource_path=tmp_path / "input.lock")
    with authorization_scope(owner), operation_scope(TaskOperation(definition, lambda: None, owner)):
        with source.completion_reader(definition) as reader:
            reader.observe()
            users.set_role("owner", "viewer")
            with pytest.raises(AuthorizationError):
                reader.observe()
        assert reader.retired


def test_reader_cannot_be_borrowed_under_another_owner_even_in_the_same_operation(tmp_path):
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
    owner, other = AuthorizationContext("owner", "operator"), AuthorizationContext("other", "admin")
    definition = spec(tmp_path)
    source = NativeDesktopTarget(resource_path=tmp_path / "input.lock")
    with authorization_scope(owner), operation_scope(TaskOperation(definition, lambda: None, owner)):
        with source.completion_reader(definition) as reader:
            with authorization_scope(other), pytest.raises(AgentTaskError, match="another owner"):
                reader.observe()
        assert reader.retired


def test_direct_readonly_proxy_uses_only_the_readonly_worker_and_refuses_unscoped_startup(tmp_path):
    adapter = ReadOnlyNativeTarget(resource_path=tmp_path / "input.lock")
    assert adapter._argv[-1] == "je_auto_control.utils.agent_runtime.readonly_worker"
    with pytest.raises(AgentTaskError, match="scope"):
        adapter.ready(spec(tmp_path))
    assert not InputJournal(tmp_path / "input.lock").path.exists()


def test_revocation_after_a_reply_prevents_publication_of_the_observation(tmp_path):
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
    from je_auto_control.utils.rbac.users import UserStore
    users = UserStore(tmp_path / "users.json")
    users.add_user(user_id="owner", display_name="Owner", role="operator")
    owner = AuthorizationContext("owner", "operator", store_path=str(users.path))
    definition, adapter = spec(tmp_path), Mock()

    def revoked(_operation, _payload):
        users.set_role("owner", "viewer")
        return {"identity": "must not be published"}

    adapter._request.side_effect = revoked
    with authorization_scope(owner), operation_scope(TaskOperation(definition, lambda: None, owner)):
        reader = CompletionReader(adapter, definition)
        with pytest.raises(AuthorizationError):
            reader.observe()
