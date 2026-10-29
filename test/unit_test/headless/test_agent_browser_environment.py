"""Host-reviewed browser interpreters and dependency probes never acquire input or start a browser."""
from contextlib import closing
import sys
from types import SimpleNamespace
import threading
from concurrent.futures import CancelledError
import io
from unittest.mock import Mock

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTargetProfile, AgentTaskError, AgentTaskSpec
from je_auto_control.utils.agent_runtime.target_factory import build_target
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope


def profile(**changes):
    return AgentTargetProfile(name="isolated-browser", kind="browser", allowed_tools=("AC_browser_read",),
        settings={"allowed_origins": ["https://allowed.test"], **changes})


def test_reviewed_helper_interpreter_selects_isolated_installed_modules():
    configuration = profile(helper_python=sys.executable)
    target = build_target(configuration)
    assert target._argv[0] == configuration.settings["helper_python"]
    assert "-I" in target._argv
    assert target._argv[-1] == "je_auto_control.utils.agent_runtime.native_worker"
    assert target._channel is None and target._resource is None


def test_target_probe_uses_existing_host_management_and_does_not_enable_target(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import target_profiles
    adapter = Mock()
    adapter.probe.return_value = {"status": "python_dependencies_ready", "browser_launch": "not_probed",
                                  "native_evidence": "not_recorded"}
    monkeypatch.setattr(target_profiles, "build_target", lambda _profile: adapter)
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={})) as runtime:
        configuration = profile()
        runtime.target_profiles.control("register", configuration.to_dict())
        runtime.target_profiles.control("disable", {"name": configuration.name})
        with authorization_scope(AuthorizationContext("operator", "operator")):
            with pytest.raises(AgentTaskError, match="host management"):
                runtime.target_profiles.control("probe", {"name": configuration.name})
        report = runtime.target_profiles.control("probe", {"name": configuration.name})
        assert report["probe"]["status"] == "python_dependencies_ready"
        assert report["enabled"] is False
        assert runtime.target_profiles.describe()["targets"][0]["last_probe"]["browser_launch"] == "not_probed"
        assert runtime._leases == {}
        adapter.probe.assert_called_once()


@pytest.mark.parametrize("value", [
    "python", "../python", "//server/share/python", "/tmp/../python", "bad\x00path", None,
])
def test_helper_selection_refuses_implicit_remote_and_traversing_paths(value):
    with pytest.raises(AgentTaskError, match="helper Python"):
        profile(helper_python=value)


def test_helper_interpreter_is_host_configuration_and_preserves_venv_symlinks(monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "resolve", Mock(side_effect=AssertionError("do not dereference virtualenv Python")))
    configuration = profile(helper_python=sys.executable)
    task = AgentTaskSpec.from_dict({"goal": "read", "target": configuration.name,
        "allowed_tools": ["AC_browser_read"], "options": {"allowed_origins": ["https://allowed.test"],
                                                           "helper_python": sys.executable},
        "success_criteria": [{"kind": "actions_complete"}]})
    with pytest.raises(AgentTaskError, match="host configuration"):
        configuration.check(task)


def test_worker_probe_imports_without_starting_sdk_or_playwright(monkeypatch):
    from je_auto_control.utils.agent_runtime.native_worker import NativeWorker
    sdk = SimpleNamespace(contract_version=1, transfer_contract_version=1, link=Mock(), open_download=Mock(),
                          upload=Mock(), open=Mock())
    runtime = Mock()
    require_runtime = Mock(return_value=runtime)
    monkeypatch.setitem(sys.modules, "je_web_runner.api.ai", SimpleNamespace(ManagedBrowserSession=sdk))
    monkeypatch.setitem(sys.modules, "je_web_runner.webdriver.playwright_wrapper",
                        SimpleNamespace(_require_playwright=require_runtime))
    worker = NativeWorker(io.BytesIO(), io.BytesIO())
    report = worker._dispatch("probe_browser", {"transfer": True})
    assert report["status"] == "python_dependencies_ready"
    assert report["browser_launch"] == "not_probed" and report["native_evidence"] == "not_recorded"
    assert worker._spec is None and worker._activity is None
    sdk.open.assert_not_called()
    require_runtime.assert_called_once()
    runtime.assert_not_called()


@pytest.mark.parametrize("value", [True, None, 0, 2, "1", 1.0])
def test_probe_does_not_accept_an_incompatible_sdk_marker(monkeypatch, value):
    from je_auto_control.utils.agent_runtime import browser_environment
    sdk = SimpleNamespace(contract_version=value, transfer_contract_version=1, link=Mock(), open_download=Mock(),
                          upload=Mock(), open=Mock())
    monkeypatch.setitem(sys.modules, "je_web_runner.api.ai", SimpleNamespace(ManagedBrowserSession=sdk))
    monkeypatch.setattr(browser_environment, "_runtime_available", lambda: True)
    assert browser_environment.inspect_browser_dependencies(True)["status"] == "incompatible"
    sdk.open.assert_not_called()


def test_worker_dependency_probe_cannot_run_inside_a_configured_input_scope(monkeypatch):
    from je_auto_control.utils.agent_runtime import browser_environment
    from je_auto_control.utils.agent_runtime.native_worker import NativeWorker
    inspect = Mock()
    monkeypatch.setattr(browser_environment, "inspect_browser_dependencies", inspect)
    worker = NativeWorker(io.BytesIO(), io.BytesIO())
    worker._spec = object()
    with pytest.raises(AgentTaskError, match="unconfigured"):
        worker._dispatch("probe_browser", {"transfer": False})
    inspect.assert_not_called()


def test_probe_protocol_never_configures_or_reuses_an_input_channel(monkeypatch):
    from je_auto_control.utils.agent_runtime import browser_environment, helper_environment
    report = browser_environment._report("3.14.4", (True, True, True, True), True)
    channel = SimpleNamespace(request=Mock(side_effect=[{"protocol": 1}, report]), close=Mock())
    factory = Mock(return_value=channel)
    monkeypatch.setattr(helper_environment, "owned_channel", factory)
    assert helper_environment.probe_browser_helper((sys.executable,), transfer=True) == report
    assert [call.args[0] for call in channel.request.call_args_list] == ["bootstrap", "probe_browser"]
    channel.close.assert_called_once()


def test_dependency_reply_cannot_claim_native_success_or_include_unknown_metadata(monkeypatch):
    from je_auto_control.utils.agent_runtime import browser_environment, helper_environment
    report = browser_environment._report("3.14.4", (True, True, True, True), True)
    report["native_evidence"] = "verified"
    channel = SimpleNamespace(request=Mock(side_effect=[{"protocol": 1}, report]), close=Mock())
    monkeypatch.setattr(helper_environment, "owned_channel", Mock(return_value=channel))
    result = helper_environment.probe_browser_helper((sys.executable,), transfer=True)
    assert result["status"] == "unknown" and result["native_evidence"] == "not_recorded"
    channel.close.assert_called_once()


def test_probe_preserves_cancellation_and_enforces_capacity_before_process_launch(monkeypatch):
    from je_auto_control.utils.agent_runtime import helper_environment
    channel = SimpleNamespace(request=Mock(side_effect=CancelledError()), close=Mock())
    factory = Mock(return_value=channel)
    monkeypatch.setattr(helper_environment, "owned_channel", factory)
    with pytest.raises(CancelledError):
        helper_environment.probe_browser_helper((sys.executable,), transfer=False)
    channel.close.assert_called_once()
    factory.reset_mock()
    monkeypatch.setattr(helper_environment, "_PROBES", threading.BoundedSemaphore(0))
    with pytest.raises(AgentTaskError, match="capacity"):
        helper_environment.probe_browser_helper((sys.executable,), transfer=False)
    factory.assert_not_called()


def test_default_environment_probe_does_not_acquire_target_input_or_start_a_browser():
    target = build_target(profile())
    result = target.probe()
    assert result["status"] in {"python_dependencies_ready", "dependency_missing", "incompatible"}
    assert result["native_evidence"] == "not_recorded" and result["browser_launch"] == "not_probed"
    assert target._channel is None and target._resource is None


def test_cli_and_command_schema_offer_the_same_host_probe_operation():
    from je_auto_control.cli import build_parser
    from je_auto_control.utils.agent_runtime.commands import CATALOG
    parser = build_parser()
    parsed = parser.parse_args(["agent-task", "target", "probe", "request.json"])
    assert parsed.target_operation == "probe"
    assert "probe" in CATALOG["AC_agent_target"][1]["operation"]["enum"]
