"""Persistent target profiles remain inert, immutable and narrower than host policy."""
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope


def profile(tmp_path, **updates):
    return {"name": "archive", "kind": "files", "roots": [str(tmp_path)], "apps": [],
            "allowed_tools": ["AC_workflow_manifest"], "settings": {}, **updates}


def task(tmp_path, **updates):
    return {"goal": "archive", "target": "archive", "roots": [str(tmp_path)],
            "allowed_tools": ["AC_workflow_manifest"],
            "success_criteria": [{"kind": "result_equals", "key": "value", "value": 1}], **updates}


@pytest.fixture
def configured(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import target_profiles
    calls, instances = [], []

    def factory(configuration):
        calls.append(configuration.to_dict())
        adapter = SimpleNamespace(ready=lambda _spec: (True, ""), observe=lambda: {"identity": "archive"},
                                  perform=lambda *_args: {"value": 1}, cleanup=lambda: None)
        instances.append(adapter)
        return adapter

    monkeypatch.setattr(target_profiles, "build_target", factory)
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={})
    yield runtime, calls, instances
    runtime.close()


def test_registration_is_inert_and_pins_a_detached_host_scope(configured, tmp_path):
    runtime, calls, _instances = configured
    config = profile(tmp_path)
    registered = runtime.target_profiles.control("register", config)
    config["roots"].append(str(tmp_path.parent))
    handle = runtime.submit(task(tmp_path))
    pinned = runtime.store.get(handle.task_id)["spec"]["options"]["target_profile"]
    assert pinned == {"name": "archive", "digest": registered["digest"]}
    assert calls[0]["roots"] == [str(tmp_path.resolve())]
    assert runtime.get(handle.task_id).state == "queued"
    assert runtime.target_profiles.describe()["targets"][0]["readiness"] == "not_probed"


def test_target_names_are_immutable_even_when_disabled(configured, tmp_path):
    runtime, _calls, _instances = configured
    runtime.target_profiles.control("register", profile(tmp_path))
    runtime.target_profiles.control("disable", {"name": "archive"})
    with pytest.raises(AgentTaskError, match="already|immutable"):
        runtime.target_profiles.control("register", profile(tmp_path, roots=[str(tmp_path.parent)]))


@pytest.mark.parametrize("updates", [
    {"roots": []}, {"allowed_tools": ["AC_write"]}, {"settings": {"argv": ["unreviewed"]}},
    {"kind": "unreviewed"}, {"name": "../elsewhere"}, {"name": "local-files"},
])
def test_invalid_profiles_cannot_publish_an_adapter(configured, tmp_path, updates):
    runtime, calls, _instances = configured
    with pytest.raises(AgentTaskError):
        runtime.target_profiles.control("register", profile(tmp_path, **updates))
    assert calls == []


def test_task_cannot_expand_profile_tools_roots_or_apps(configured, tmp_path):
    runtime, _calls, _instances = configured
    runtime.target_profiles.control("register", profile(tmp_path))
    for updates in ({"roots": [str(tmp_path.parent)]}, {"apps": ["other"]}, {"allowed_tools": ["AC_write"]}):
        with pytest.raises(AgentTaskError):
            runtime.submit(task(tmp_path, **updates))


def test_profile_change_controls_require_host_authority(configured, tmp_path):
    runtime, calls, _instances = configured
    with authorization_scope(AuthorizationContext("operator", "operator")):
        with pytest.raises(AgentTaskError):
            runtime.target_profiles.control("register", profile(tmp_path))
    assert calls == []


def test_disable_retires_active_input_and_enable_requires_explicit_resume(configured, tmp_path):
    runtime, _calls, _instances = configured
    runtime.target_profiles.control("register", profile(tmp_path))
    handle = runtime.submit(task(tmp_path))
    runtime.observe(handle.task_id)
    assert runtime._leases
    runtime.target_profiles.control("disable", {"name": "archive"})
    assert runtime.get(handle.task_id).state == "paused"
    assert not runtime._leases
    with pytest.raises(AgentTaskError):
        runtime.observe(handle.task_id)
    runtime.target_profiles.control("enable", {"name": "archive"})
    assert runtime.get(handle.task_id).state == "paused"
    runtime.resume(handle.task_id)
    assert runtime.observe(handle.task_id).observation_id


def test_restart_preserves_profile_scope_and_disabled_state(configured, tmp_path):
    runtime, calls, _instances = configured
    runtime.target_profiles.control("register", profile(tmp_path))
    runtime.target_profiles.control("disable", {"name": "archive"})
    runtime.close()
    restored = AgentRuntime(tmp_path / "runtime.sqlite", targets={})
    try:
        assert len(calls) == 2
        assert restored.target_profiles.describe()["targets"][0]["enabled"] is False
        with pytest.raises(AgentTaskError):
            restored.submit(task(tmp_path))
    finally:
        restored.close()


def test_anonymous_mcp_context_cannot_reuse_local_host_authority(monkeypatch):
    from je_auto_control.utils.mcp_server.context import ToolCallContext
    from je_auto_control.utils.mcp_server.tools._agent_tasks import _handler
    from je_auto_control.utils.agent_runtime.commands import CATALOG
    calls = []
    original = CATALOG["AC_agent_target"]
    monkeypatch.setitem(CATALOG, "AC_agent_target", (lambda **kwargs: calls.append(kwargs), *original[1:]))
    with pytest.raises(AgentTaskError, match="administrator"):
        _handler("AC_agent_target")(ctx=ToolCallContext(1, session_id="anonymous"), operation="register", request={})
    assert calls == []


def test_anonymous_mcp_legacy_wrapper_cannot_expand_to_host_configuration(monkeypatch):
    from je_auto_control.utils.mcp_server.context import ToolCallContext
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.utils.rbac.authorization import AuthorizationError
    from je_auto_control.utils.executor.action_executor import executor
    calls = []
    monkeypatch.setitem(executor.event_dict, "AC_agent_target", lambda **kwargs: calls.append(kwargs))
    tool = next(item for item in build_default_tool_registry() if item.name == "ac_execute_actions")
    with pytest.raises(AuthorizationError):
        tool.invoke({"actions": [["AC_agent_target", {"operation": "get", "request": {"name": "archive"}}]]},
                    ctx=ToolCallContext(1, session_id="anonymous"))
    assert calls == []


def test_desktop_profile_platform_is_checked_before_native_resource_acquisition(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import target_config
    from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
    from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
    from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
    config = profile(tmp_path, kind="desktop", apps=["editor"], allowed_tools=["AC_write"],
                     settings={"platform": "macos"})
    adapter = NativeDesktopTarget(profile=config)
    monkeypatch.setattr(target_config, "desktop_platform", lambda: "windows")
    monkeypatch.setattr(adapter, "_ensure", lambda: pytest.fail("wrong platform acquired native input"))
    spec = AgentTaskSpec.from_dict(task(tmp_path, allowed_tools=["AC_write"], apps=["editor"]))
    with operation_scope(TaskOperation(spec, lambda: None, None)):
        with pytest.raises(AgentTaskError, match="platform"):
            adapter.ready(spec)


def test_named_file_profile_uses_the_real_owned_file_helper(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import target_profiles
    from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
    from je_auto_control.utils.agent_runtime.runner import run_task
    monkeypatch.setattr(target_profiles, "build_target", lambda configuration: NativeDesktopTarget(
        resource_path=tmp_path / "files.lock", recovery_probe=lambda: None, profile=configuration.to_dict()))
    source = tmp_path / "report.txt"
    source.write_text("fixture", encoding="utf-8")
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={})
    try:
        runtime.target_profiles.control("register", profile(tmp_path))
        handle = runtime.submit(task(tmp_path, mode="skill", actions=[{"tool": "AC_workflow_manifest", "arguments": {
            "directory": str(tmp_path), "path": str(tmp_path / "manifest.json"), "names": [source.name]}}],
            success_criteria=[{"kind": "actions_complete"}]))
        result = run_task(runtime, handle.task_id)
        assert result.state == "succeeded", result.reason
        assert (tmp_path / "manifest.json").is_file()
    finally:
        runtime.close()


def test_profile_lifecycle_and_sensitive_configuration_are_protected_over_http(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import target_profiles
    from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
    from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
    monkeypatch.setattr(target_profiles, "build_target", lambda _profile: SimpleNamespace(cleanup=lambda: None))
    service = AgentRuntimeService(tmp_path, targets={})
    try:
        service.start()
        client = AgentRuntimeClient(tmp_path / "agent_runtime.json")
        with authorization_scope(AuthorizationContext("operator", "operator")):
            with pytest.raises(AgentTaskError):
                client.call("target", {"operation": "register", "request": profile(tmp_path)})
        with authorization_scope(AuthorizationContext("admin", "admin")):
            result = client.call("target", {"operation": "register", "request": profile(tmp_path)})
            assert result["profile"]["roots"] == [str(tmp_path.resolve())]
        with authorization_scope(AuthorizationContext("operator", "operator")):
            targets = client.call("targets")["targets"]
            assert targets[0]["name"] == "archive"
            assert "profile" not in targets[0]
            with pytest.raises(AgentTaskError):
                client.call("target", {"operation": "get", "request": {"name": "archive"}})
    finally:
        service.close()
