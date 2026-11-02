"""Durable trigger snapshots and request keys never replay duplicate events or widen authority."""
import time

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope


def spec(**updates):
    return {"goal": "fixture", "target": "fixture", "allowed_tools": ["AC_fixture"],
            "success_criteria": [{"kind": "result_equals", "key": "ok", "value": True}], **updates}


@pytest.fixture
def runtime(tmp_path):
    instance = AgentRuntime(tmp_path / "runtime.sqlite", targets={"fixture": object()})
    yield instance
    instance.close()


def register(runtime, kind="event", **updates):
    return runtime.triggers.control("register", {"kind": kind, "spec": spec(), **updates})["trigger_id"]


def fire(runtime, trigger_id, event_key="one", **updates):
    return runtime.triggers.control("fire", {"trigger_id": trigger_id, "event_key": event_key, **updates})


def test_request_key_is_atomic_owner_scoped_and_rejects_conflicting_specs(runtime):
    with authorization_scope(AuthorizationContext("alice", "operator")):
        first = runtime.submit(spec(), idempotency_key="request")
        assert runtime.submit(spec(), idempotency_key="request").task_id == first.task_id
        with pytest.raises(AgentTaskError, match="different task"):
            runtime.submit(spec(goal="different"), idempotency_key="request")
    with authorization_scope(AuthorizationContext("bob", "operator")):
        second = runtime.submit(spec(), idempotency_key="request")
    assert second.task_id != first.task_id
    assert len(runtime.store.list()) == 2


def test_duplicate_event_preserves_exact_task_and_original_payload(runtime):
    trigger_id = register(runtime)
    first = fire(runtime, trigger_id, payload={"row": 4})
    duplicate = fire(runtime, trigger_id, payload={"row": 4})
    assert first["task_id"] == duplicate["task_id"]
    assert duplicate["duplicate"] is True
    with pytest.raises(AgentTaskError, match="different payload"):
        fire(runtime, trigger_id, payload={"row": 5})
    assert len(runtime.store.list()) == 1
    snapshot = runtime.store.get(first["task_id"])["spec"]
    assert snapshot["allowed_tools"] == ["AC_fixture"]
    assert snapshot["inputs"]["event"]["payload"] == {"row": 4}


def test_pending_limit_defers_notifications_without_recording_an_unaccepted_event(runtime):
    trigger_id = register(runtime)
    first = fire(runtime, trigger_id)
    assert fire(runtime, trigger_id, "two")["deferred"] is True
    runtime.cancel(first["task_id"])
    second = fire(runtime, trigger_id, "two")
    assert second["task_id"] != first["task_id"]


def test_interval_trigger_reuses_existing_next_due_after_restart(tmp_path):
    path = tmp_path / "runtime.sqlite"
    runtime = AgentRuntime(path, targets={"fixture": object()})
    trigger_id = register(runtime, "interval", config={"seconds": 1})
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_triggers SET next_run=? WHERE id=?", (time.time() - 2, trigger_id))
    runtime.triggers.poll()
    task_id = runtime.store.list()[0]["id"]
    runtime.close()
    restored = AgentRuntime(path, targets={"fixture": object()})
    try:
        restored.triggers.poll()
        assert len(restored.store.list()) == 1
        assert restored.store.list()[0]["id"] == task_id
        assert restored.triggers.list()["triggers"][0]["enabled"]
    finally:
        restored.close()


def test_file_event_requires_a_stable_rooted_version_and_deduplicates(runtime, tmp_path, monkeypatch):
    source = tmp_path / "ready.csv"
    source.write_text("name\nAda\n", encoding="utf-8")
    specification = spec(roots=[str(tmp_path)])
    trigger_id = runtime.triggers.control("register", {"kind": "file", "spec": specification,
                                "config": {"path": str(source), "stable_seconds": 1}})["trigger_id"]
    clock = [0.0]
    monkeypatch.setattr("je_auto_control.utils.agent_runtime.task_triggers.monotonic", lambda: clock[0])
    runtime.triggers.poll()
    assert runtime.store.list() == []
    clock[0] = 2
    runtime.triggers.poll()
    runtime.triggers.poll()
    assert len(runtime.store.list()) == 1
    assert runtime.triggers._row(trigger_id)["last_event"]


def test_trigger_owner_cannot_inspect_or_disable_another_owner(runtime):
    with authorization_scope(AuthorizationContext("alice", "operator")):
        trigger_id = register(runtime)
    with authorization_scope(AuthorizationContext("bob", "operator")):
        assert runtime.triggers.list() == {"triggers": []}
        with pytest.raises(AgentTaskError, match="another"):
            runtime.triggers.control("disable", {"trigger_id": trigger_id})


def test_trigger_event_and_task_roll_back_together_on_missing_binding(runtime):
    specification = runtime._validated_spec(spec())
    with pytest.raises(AgentTaskError):
        runtime._create_task(specification, "binding", ("missing", "hash", "payload"))
    assert runtime.store.list() == []
    with runtime.store.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM agent_request_keys").fetchone()[0] == 0


def test_retained_event_tombstone_prevents_replay_after_task_retention(runtime):
    trigger_id = register(runtime)
    first = fire(runtime, trigger_id)
    runtime.cancel(first["task_id"])
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_tasks SET updated=? WHERE id=?",
                           (time.time() - 31 * 86400, first["task_id"]))
    runtime.prune()
    assert fire(runtime, trigger_id) == {"task_id": first["task_id"], "state": "expired", "duplicate": True}


def test_principals_from_different_authority_stores_do_not_share_task_ownership(runtime):
    task_id = runtime.store.create(spec(), {"user_id": "alice", "role": "operator", "store_path": "store-a"})
    with authorization_scope(AuthorizationContext("alice", "operator", store_path="store-b")):
        assert runtime.list() == []
        with pytest.raises(AgentTaskError, match="another"):
            runtime.get(task_id)


@pytest.mark.parametrize("change", ["viewer", "remove", "corrupt"])
def test_trigger_reauthorizes_its_owner_before_each_automatic_fire(runtime, tmp_path, change):
    from je_auto_control.utils.rbac.authorization import resolve_token
    from je_auto_control.utils.rbac.users import UserStore
    store = UserStore(tmp_path / "users.json")
    token = store.add_user(user_id="owner", display_name="Owner", role="operator")
    with authorization_scope(resolve_token(store, token)):
        trigger_id = register(runtime, "interval", config={"seconds": 1})
    if change == "remove":
        store.remove_user("owner")
    elif change == "viewer":
        store.set_role("owner", "viewer")
    else:
        store.path.write_text("not JSON", encoding="utf-8")
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_triggers SET next_run=0 WHERE id=?", (trigger_id,))
    runtime.triggers.poll()
    assert runtime.store.list() == []
    assert not runtime.triggers._row(trigger_id)["enabled"]


def test_emergency_stop_is_not_limited_to_the_task_list_page(runtime, monkeypatch):
    from je_auto_control.utils.agent_runtime.jobs import BackgroundTasks
    monkeypatch.setattr(runtime.evidence, "ensure", lambda _task_id: {})
    monkeypatch.setattr(runtime.evidence, "publish", lambda _task_id: None)
    for _index in range(1002):
        runtime.submit(spec())
    delivery = BackgroundTasks(runtime)
    restored = []
    monkeypatch.setattr(delivery, "start", restored.append)
    delivery.start_pending()
    assert len(restored) == 1002
    result = runtime.stop_all()
    assert result["requested"] == 1002
    assert result["cleanup_errors"] == []
    with runtime.store.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM agent_tasks WHERE state='cancelled'").fetchone()[0] == 1002


def test_queued_emergency_stop_reads_status_in_batches_instead_of_per_task(runtime, monkeypatch):
    from contextlib import contextmanager
    monkeypatch.setattr(runtime.evidence, "ensure", lambda _task_id: {})
    monkeypatch.setattr(runtime.evidence, "publish", lambda _task_id: None)
    for _index in range(5):
        runtime.submit(spec())
    connection = runtime.store.connection
    reads = []

    @contextmanager
    def counted(**kwargs):
        reads.append(kwargs)
        with connection(**kwargs) as opened:
            yield opened

    monkeypatch.setattr(runtime.store, "connection", counted)
    result = runtime.stop_all()
    assert len(reads) <= 6
    assert result["requested"] == 5 and all(item["state"] == "cancelled" for item in result["tasks"])


def test_canonical_root_replacement_requires_scope_review_before_target_acquisition(runtime, tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    task = runtime.submit(spec(roots=[str(root)]))
    root.rmdir()
    try:
        root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("filesystem does not allow a test-owned directory symlink")
    with pytest.raises(AgentTaskError, match="root changed"):
        runtime.observe(task.task_id)
    assert runtime.get(task.task_id).state == "paused"


def test_managed_operation_cannot_read_an_ambient_vault_through_variable_interpolation(runtime, monkeypatch):
    from je_auto_control.utils.script_vars.interpolate import interpolate_value
    from je_auto_control.utils.secrets import default_secret_manager
    calls = []
    monkeypatch.setattr(default_secret_manager, "get", lambda name: calls.append(name) or "private")
    task = runtime.submit(spec())
    row = runtime.store.get(task.task_id)
    with runtime._scope(row), pytest.raises(AgentTaskError, match="ambient secret vault"):
        interpolate_value("${secrets.PRIVATE}", {})
    assert calls == []
    assert interpolate_value("${secrets.PRIVATE}", {}) == "private"


def test_cron_uses_the_existing_parser_and_a_timezone_without_starting_a_task(runtime):
    trigger_id = register(runtime, "cron", config={"expression": "* * * * *", "timezone": "UTC"})
    assert runtime.triggers._row(trigger_id)["next_run"] > time.time()
    with pytest.raises(AgentTaskError):
        register(runtime, "cron", config={"expression": "invalid"})
    assert runtime.store.list() == []


def test_trigger_event_variable_is_scoped_through_owned_file_helper_and_completion(tmp_path):
    from je_auto_control.utils.agent_runtime.runner import run_task
    source = tmp_path / "report.txt"
    source.write_text("fixture", encoding="utf-8")
    runtime = AgentRuntime(tmp_path / "runtime.sqlite")
    try:
        manifest = str(tmp_path / "${event.key}.json")
        specification = {"goal": "archive manifest", "target": "local-files", "mode": "skill",
            "roots": [str(tmp_path)], "allowed_tools": ["AC_workflow_manifest"],
            "actions": [{"tool": "AC_workflow_manifest", "arguments": {"directory": str(tmp_path),
                "path": manifest, "names": [source.name]}}],
            "success_criteria": [{"kind": "file_exists", "path": manifest}]}
        trigger_id = runtime.triggers.control("register", {"kind": "event", "spec": specification})["trigger_id"]
        task = fire(runtime, trigger_id)
        assert run_task(runtime, task["task_id"]).state == "succeeded"
        key = runtime.store.get(task["task_id"])["spec"]["inputs"]["event"]["key"]
        assert (tmp_path / (key + ".json")).is_file()
    finally:
        runtime.close()
