"""Actual SDK/worker/owned-channel completion with only the installed Chromium factory replaced."""
from concurrent.futures import CancelledError
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("je_web_runner", reason="source SDK proof runs in the existing reviewed WebRunner interpreter")

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTargetProfile, AgentTaskError  # noqa: E402
from je_auto_control.utils.agent_runtime import native_channel  # noqa: E402
from je_auto_control.utils.agent_runtime.runner import run_task  # noqa: E402


@pytest.fixture
def live(tmp_path, monkeypatch):
    original_launch = native_channel.subprocess.Popen
    controls, processes = [], []
    behavior = SimpleNamespace(legacy=False)

    def launch(argv, **options):
        if argv[-1] == "je_auto_control.utils.agent_runtime.readonly_worker":
            pytest.fail("Retained browser completion cannot launch a fresh read-only helper")
        if argv[-2:] == ["-m", "je_auto_control.utils.agent_runtime.native_worker"]:
            control = tmp_path / f"dom-{len(controls)}.txt"
            controls.append(control)
            script = (
                "import sys; sys.path.insert(0,sys.argv[1]); "
                "from headless.test_agent_browser_webrunner_contract import fake_runtime; "
                "from je_web_runner.webdriver import playwright_wrapper as sdk; "
                f"sdk._require_playwright=lambda:fake_runtime(readonly_state={str(control)!r}); "
                + ("from je_web_runner import ManagedBrowserSession; "
                   "ManagedBrowserSession.readonly_contract_version=None; " if behavior.legacy else "") +
                "from je_auto_control.utils.agent_runtime.native_worker import main; main()")
            argv = [argv[0], "-u", "-c", script, str(Path(__file__).parent.parent)]
            process = original_launch(argv, **options)
            processes.append(process)
            return process
        return original_launch(argv, **options)

    monkeypatch.setattr(native_channel.subprocess, "Popen", launch)
    profile = AgentTargetProfile(name="retained-browser", kind="browser",
        allowed_tools=("AC_browser_navigate", "AC_browser_fill", "AC_browser_read"),
        settings={"allowed_origins": ["https://allowed.test"]})
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={})
    runtime.target_profiles.control("register", profile.to_dict())
    definition = {"goal": "Confirm delayed DOM after input retirement", "target": profile.name, "mode": "skill",
        "allowed_tools": list(profile.allowed_tools), "options": {"allowed_origins": ["https://allowed.test"]},
        "actions": [{"tool": "AC_browser_navigate", "arguments": {"url": "https://allowed.test/form"}},
                    {"tool": "AC_browser_fill", "arguments": {"selector": "#field", "value": "reviewed"}}],
        "success_criteria": [{"kind": "actions_complete"},
                             {"kind": "browser", "operation": "value", "selector": "#field", "value": "complete"}]}
    try:
        yield SimpleNamespace(runtime=runtime, controls=controls, processes=processes,
                              definition=definition, behavior=behavior)
    finally:
        runtime.close()
    assert all(process.poll() is not None for process in processes)


def completion(runtime, source):
    review = runtime.recovery.control("preview_completion", {"task_id": source})
    assert review["source_completion_inherited"] is False
    return runtime.recovery.control("create_completion", {
        "task_id": source, "snapshot": review["snapshot"], "note": "Reviewed original effects and current criterion"})


def test_completion_keeps_real_original_sdk_context_without_new_helper_or_actions(live):
    runtime = live.runtime
    source = runtime.submit(live.definition).task_id
    assert run_task(runtime, source).state == "waiting_user"
    historical = runtime.store.actions(source)
    live.controls[0].write_text("complete", encoding="utf-8")
    child = completion(runtime, source)["task_id"]
    result = runtime.finish(child)
    assert result.state == "succeeded", result.reason
    assert result.metadata["input_released"] is True
    assert [item["status"] for item in result.verification] == ["passed", "passed"]
    assert len(live.processes) == 1
    assert runtime.store.actions(source) == historical
    assert runtime.store.actions(child) == []


def test_input_lease_releases_while_runtime_still_owns_the_original_readonly_process(live):
    source = live.runtime.submit(live.definition).task_id
    assert run_task(live.runtime, source).state == "waiting_user"
    assert source not in live.runtime._leases
    assert len(live.processes) == 1 and live.processes[0].poll() is None
    live.runtime.close()
    assert live.processes[0].poll() is not None


def test_another_task_on_same_profile_cannot_replace_the_first_effect_context(live):
    runtime = live.runtime
    first = runtime.submit(live.definition).task_id
    assert run_task(runtime, first).state == "waiting_user"
    second = runtime.submit({**live.definition, "goal": "Different effect task on the same profile"}).task_id
    assert run_task(runtime, second).state == "waiting_user"
    live.controls[0].write_text("complete", encoding="utf-8")
    live.controls[1].write_text("still incomplete", encoding="utf-8")
    assert runtime.finish(completion(runtime, first)["task_id"]).state == "succeeded"
    assert runtime.finish(completion(runtime, second)["task_id"]).state == "waiting_user"
    assert len(live.processes) == 2


def test_older_sdk_closes_normally_but_cannot_create_a_completion_context(live):
    live.behavior.legacy = True
    source = live.runtime.submit(live.definition).task_id
    assert run_task(live.runtime, source).state == "waiting_user"
    assert live.processes[0].poll() is not None
    with pytest.raises(AgentTaskError, match="context.*unavailable"):
        completion(live.runtime, source)
    assert len(live.processes) == 1 and source not in live.runtime._leases


def test_expired_context_is_reaped_without_replacement_or_historical_fallback(live, monkeypatch):
    source = live.runtime.submit(live.definition).task_id
    assert run_task(live.runtime, source).state == "waiting_user"
    monkeypatch.setattr(live.runtime._retained_browsers, "_clock", lambda: float("inf"))
    with pytest.raises(AgentTaskError, match="context.*unavailable"):
        completion(live.runtime, source)
    assert live.processes[0].poll() is not None and len(live.processes) == 1


def test_disabled_target_maintenance_retires_the_original_owned_context(live):
    source = live.runtime.submit(live.definition).task_id
    assert run_task(live.runtime, source).state == "waiting_user"
    live.runtime.target_profiles.control("disable", {"name": "retained-browser"})
    live.runtime.maintain()
    assert live.processes[0].poll() is not None
    with pytest.raises(AgentTaskError):
        completion(live.runtime, source)
    assert len(live.processes) == 1


def test_forged_live_capability_description_cannot_revive_a_reaped_context(live, monkeypatch):
    runtime = live.runtime
    source = runtime.submit(live.definition).task_id
    assert run_task(runtime, source).state == "waiting_user"
    entry = runtime._retained_browsers.require(runtime.store.get(source))
    original = entry.channel.request
    monkeypatch.setattr(entry.channel, "request", lambda *_args, **_kwargs: {**entry.proof, "context_id": "c" * 32})
    with pytest.raises(AgentTaskError, match="unconfirmed"):
        completion(runtime, source)
    monkeypatch.setattr(entry.channel, "request", original)
    with pytest.raises(AgentTaskError, match="unavailable"):
        completion(runtime, source)
    assert live.processes[0].poll() is not None and len(live.processes) == 1


def test_source_snapshot_change_during_live_read_cannot_publish_completion(live, monkeypatch):
    runtime = live.runtime
    source = runtime.submit(live.definition).task_id
    assert run_task(runtime, source).state == "waiting_user"
    live.controls[0].write_text("complete", encoding="utf-8")
    child = completion(runtime, source)["task_id"]
    entry = runtime._retained_browsers.require(runtime.store.get(source))
    original = entry.channel.request

    def changed(operation, payload, **options):
        result = original(operation, payload, **options)
        if operation == "observe":
            runtime.store.update(source, "waiting_user", reason="source changed during current DOM read")
        return result

    monkeypatch.setattr(entry.channel, "request", changed)
    with pytest.raises(AgentTaskError, match="snapshot"):
        runtime.finish(child)
    assert runtime.get(child).state != "succeeded"
    assert live.processes[0].poll() is not None


def test_cancelled_live_read_reaps_only_original_readonly_context(live, monkeypatch):
    runtime = live.runtime
    source = runtime.submit(live.definition).task_id
    assert run_task(runtime, source).state == "waiting_user"
    live.controls[0].write_text("complete", encoding="utf-8")
    child = completion(runtime, source)["task_id"]
    entry = runtime._retained_browsers.require(runtime.store.get(source))
    original = entry.channel.request

    def cancelled(operation, payload, **options):
        result = original(operation, payload, **options)
        if operation == "observe":
            runtime.cancel(child)
        return result

    monkeypatch.setattr(entry.channel, "request", cancelled)
    with pytest.raises(CancelledError):
        runtime.finish(child)
    assert runtime.get(child).state == "cancelled"
    assert live.processes[0].poll() is not None and len(live.processes) == 1


@pytest.fixture
def verified_skill(live):
    runtime = live.runtime
    source = runtime.submit(live.definition).task_id
    assert run_task(runtime, source).state == "waiting_user"
    live.controls[0].write_text("complete", encoding="utf-8")
    reader = completion(runtime, source)["task_id"]
    assert runtime.finish(reader).state == "succeeded"
    candidate = runtime.skills.control("record", {"task_id": source, "completion_task_id": reader,
                                                 "name": "Retained original browser workflow"})
    trial = runtime.skills.control("validate", {"candidate_id": candidate["id"]})["task_id"]
    assert run_task(runtime, trial).state == "waiting_user"
    live.controls[1].write_text("complete", encoding="utf-8")
    trial_reader = completion(runtime, trial)["task_id"]
    assert runtime.finish(trial_reader).state == "succeeded"
    return SimpleNamespace(live=live, source=source, reader=reader, candidate=candidate,
                           trial=trial, trial_reader=trial_reader)


def test_skill_recording_keeps_original_browser_actions_and_its_own_new_validation(verified_skill):
    value = verified_skill
    runtime = value.live.runtime
    assert value.candidate["spec"]["actions"] == value.live.definition["actions"]
    assert value.candidate["provenance"]["source_task"] == value.source
    assert value.candidate["provenance"]["completion_review"]["task_id"] == value.reader
    assert value.trial not in {value.source, value.reader, value.trial_reader}
    assert runtime.store.actions(value.trial_reader) == []
    with pytest.raises(AgentTaskError):
        runtime.skills.control("review_execution", {"candidate_id": value.candidate["id"], "task_id": value.trial,
                                                    "execution_task_id": value.trial_reader})
    assert len(value.live.processes) == 2


def test_skill_publication_uses_actual_trial_and_separate_same_context_completion(verified_skill):
    value = verified_skill
    runtime = value.live.runtime
    before = runtime.store.actions(value.trial)
    accepted = runtime.skills.control("accept", {
        "candidate_id": value.candidate["id"], "task_id": value.trial, "completion_task_id": value.trial_reader,
        "expected_version": 0, "note": "Reviewed actual new trial and original-context independent evidence"})
    assert accepted["version"] == 1 and accepted["state"] == "accepted"
    assert accepted["publication"]["task_id"] == value.trial
    assert accepted["publication"]["completion_review"]["task_id"] == value.trial_reader
    assert runtime.store.actions(value.trial) == before
    assert runtime.store.actions(value.trial_reader) == []
    assert len(value.live.processes) == 2


def test_revoked_actual_owner_maintenance_reaps_context_and_refuses_future_completion(live, tmp_path):
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
    from je_auto_control.utils.rbac.users import UserStore
    users = UserStore(tmp_path / "owned-users.json")
    users.add_user(user_id="owner", display_name="Owner", role="operator")
    owner = AuthorizationContext("owner", "operator", store_path=str(users.path))
    with authorization_scope(owner):
        source = live.runtime.submit(live.definition).task_id
        assert run_task(live.runtime, source).state == "waiting_user"
    users.remove_user("owner")
    live.runtime.maintain()
    assert live.processes[0].poll() is not None
    with pytest.raises((AgentTaskError, AuthorizationError)):
        completion(live.runtime, source)
    assert len(live.processes) == 1


def test_dead_source_helper_is_refused_by_actual_probe_without_new_process(live):
    source = live.runtime.submit(live.definition).task_id
    assert run_task(live.runtime, source).state == "waiting_user"
    live.processes[0].kill()
    live.processes[0].wait(timeout=3)
    with pytest.raises(AgentTaskError):
        completion(live.runtime, source)
    assert live.processes[0].poll() is not None and len(live.processes) == 1


def test_explicit_private_scope_renewal_reads_original_context_without_reviving_old_origin(live, tmp_path):
    from je_auto_control.utils.agent_runtime import origin_policy
    old = origin_policy.OriginWitness((tmp_path,))
    current = origin_policy.OriginWitness((tmp_path,))
    runtime = live.runtime
    try:
        with origin_policy.origin_scope(old.identifier):
            source = runtime.submit(live.definition).task_id
            assert run_task(runtime, source).state == "waiting_user"
        old.revoke()
        runtime.maintain()
        assert live.processes[0].poll() is None
        with origin_policy.origin_scope(current.identifier):
            with pytest.raises(AgentTaskError):
                completion(runtime, source)
            review = runtime.recovery.control("review_completion_authorization", {"task_id": source})
            child = runtime.recovery.control("create_authorized_completion", {
                "task_id": source, "snapshot": review["snapshot"],
                "authorization_review": review["authorization_review"],
                "note": "Reviewed fresh scope for original context; original input remains retired"})["task_id"]
            live.controls[0].write_text("complete", encoding="utf-8")
            assert runtime.finish(child).state == "succeeded"
        assert old.identifier in runtime.store.get(source)["spec"]["options"]["origin_policies"]
        assert len(live.processes) == 1
        with pytest.raises(AgentTaskError):
            origin_policy._read(old.identifier)
    finally:
        old.revoke()
        current.revoke()


def test_exact_creation_retry_returns_existing_task_after_context_retirement_without_new_authority(live):
    runtime = live.runtime
    source = runtime.submit(live.definition).task_id
    assert run_task(runtime, source).state == "waiting_user"
    review = runtime.recovery.control("preview_completion", {"task_id": source})
    request = {"task_id": source, "snapshot": review["snapshot"], "note": "Reviewed exact retained source"}
    child = runtime.recovery.control("create_completion", request)["task_id"]
    runtime._retained_browsers.discard(source)
    assert runtime.recovery.control("create_completion", request)["task_id"] == child
    assert runtime.get(child).state == "queued"
    assert len(live.processes) == 1 and live.processes[0].poll() is not None


def test_source_change_during_admission_probe_rolls_back_the_private_completion_task(live, monkeypatch):
    runtime = live.runtime
    source = runtime.submit(live.definition).task_id
    assert run_task(runtime, source).state == "waiting_user"
    review = runtime.recovery.control("preview_completion", {"task_id": source})
    entry = runtime._retained_browsers.require(runtime.store.get(source))
    original = entry.channel.request
    armed = [True]

    def changed(operation, payload, **options):
        result = original(operation, payload, **options)
        if operation == "readonly_capabilities" and armed[0]:
            armed[0] = False
            runtime.store.update(source, "waiting_user", reason="source changed during actual admission probe")
        return result

    monkeypatch.setattr(entry.channel, "request", changed)
    with pytest.raises(AgentTaskError, match="source|snapshot"):
        runtime.recovery.control("create_completion", {
            "task_id": source, "snapshot": review["snapshot"], "note": "Previously reviewed exact source"})
    assert len(runtime.store.list(100)) == 1
    assert runtime.store.actions(source)[-1]["status"] == "confirmed"


def test_public_surfaces_verify_the_actual_retained_browser_without_replaying_input(live, monkeypatch, tmp_path):
    import json
    import je_auto_control as ac
    from je_auto_control.cli import build_parser
    from je_auto_control.utils.agent_runtime.cli import run
    from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
    from je_auto_control.utils.rest_api.rest_server import RestApiServer
    from je_auto_control.utils.tool_use_schema import run_tool_call
    runtime = live.runtime
    source = runtime.submit(live.definition).task_id
    assert run_task(runtime, source).state == "waiting_user"
    original = runtime.store.actions(source)
    live.controls[0].write_text("complete", encoding="utf-8")
    server = RestApiServer(port=0, token="owned-retained-browser-surfaces", agent_runtime=runtime,
                           enable_audit=False, use_environment_users=False)
    server.start()
    try:
        connection = tmp_path / "connection.json"
        connection.write_text(json.dumps({"url": server.base_url, "token": server.token,
                                          "generation": "owned-retained-browser-surfaces"}), encoding="utf-8")
        monkeypatch.setattr("je_auto_control.utils.agent_runtime.client.default_connection_path", lambda: connection)
        review = ac.manage_agent_recovery("preview_completion", {"task_id": source})
        request = {"task_id": source, "snapshot": review["snapshot"], "note": "Reviewed real original browser effects"}
        approval = tmp_path / "approval.json"
        approval.write_text(json.dumps(request), encoding="utf-8")
        arguments = build_parser().parse_args(["agent-task", "recovery", "create_completion", str(approval)])
        child = run(arguments)["task_id"]
        assert run_tool_call("AC_agent_task_recovery", {
            "operation": "create_completion", "request": request})["task_id"] == child
        result = AgentRuntimeClient(connection).call("finish", {"task_id": child})
        assert result["state"] == "succeeded" and result["metadata"]["input_released"] is True
        assert result["metadata"]["completion_review"]["effect_task"] == source
        assert runtime.store.actions(source) == original and runtime.store.actions(child) == []
        assert len(live.processes) == 1
    finally:
        server.stop()
