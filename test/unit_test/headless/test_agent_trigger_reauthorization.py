"""Renewed bindings retain accepted event identities and never dispatch inherited work."""
from unittest.mock import Mock
import json
import time

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.origin_policy import origin_scope
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
from .test_agent_origin_policy import origin_directory as origin_directory
from .test_agent_task_triggers import spec


@pytest.fixture
def retired_trigger(tmp_path, origin_directory, request):
    allowed = tmp_path / "allowed"
    narrow = allowed / "reports"
    narrow.mkdir(parents=True)
    old, current = PathPolicy([allowed]), PathPolicy([narrow])
    old_id, current_id = old.managed_origin(), current.managed_origin()
    runtime = AgentRuntime(tmp_path / "agent_runtime.sqlite", targets={"fixture": object()})
    try:
        with origin_scope(old_id):
            kind = getattr(request, "param", "event")
            config = {}
            if kind == "interval":
                config = {"seconds": 60}
            elif kind == "file":
                path = narrow / "ready.csv"
                path.write_text("row\n1\n")
                config = {"path": str(path), "stable_seconds": 1}
            source = runtime.triggers.control("register", {"kind": kind, "config": config,
                                                           "spec": spec(roots=[str(allowed)])})
            task = runtime.triggers.control("fire", {"trigger_id": source["trigger_id"], "event_key": "old-event",
                                                      "payload": {"row": 1}})
        old.revoke_managed_origin()
        yield runtime, source["trigger_id"], task["task_id"], old_id, current_id, allowed, narrow
    finally:
        runtime.close()


def approval(runtime, source):
    view = runtime.triggers.control("review_authorization", {"trigger_id": source})
    return {"trigger_id": source, "snapshot": view["snapshot"], "authorization_review": view["authorization_review"],
            "spec": view["spec"], "note": "Reviewed future report events and retained old event identities"}


def fire(runtime, trigger_id, key, payload=None):
    return runtime.triggers.control("fire", {"trigger_id": trigger_id, "event_key": key, "payload": payload or {}})


def test_renewal_preserves_event_dedup_and_pending_limit_without_dispatching_old_task(retired_trigger):
    runtime, source, old_task, _old_id, current_id, allowed, narrow = retired_trigger
    original = runtime.triggers._row(source)
    start = Mock()
    runtime.background = Mock(start=start)
    with origin_scope(current_id):
        request = approval(runtime, source)
        assert request["spec"]["roots"] == [str(narrow)]
        start.assert_not_called()
        child = runtime.triggers.control("create_authorized", request)["trigger_id"]
        assert child != source
        start.assert_not_called()
        assert runtime.triggers.control("create_authorized", request)["trigger_id"] == child
        duplicate = fire(runtime, child, "old-event", {"row": 1})
        assert duplicate["duplicate"] and duplicate["task_id"] == old_task
        start.assert_not_called()
        with pytest.raises(AgentTaskError, match="different payload"):
            fire(runtime, child, "old-event", {"row": 2})
        assert fire(runtime, child, "future-event")["deferred"]
        runtime.cancel(old_task)
        fresh = fire(runtime, child, "future-event")
        assert fresh["task_id"] != old_task
        start.assert_called_once_with(fresh["task_id"])
        assert fire(runtime, child, "future-event")["duplicate"]
        assert start.call_count == 2 and start.call_args.args == (fresh["task_id"],)
        assert runtime.store.get(fresh["task_id"])["spec"]["roots"] == [str(narrow)]
        with pytest.raises(AgentTaskError, match="replacement"):
            runtime.triggers.control("enable", {"trigger_id": source})
    after = runtime.triggers._row(source)
    assert not after["enabled"]
    assert after["spec"] == original["spec"] and after["spec"]["roots"] == [str(allowed)]


@pytest.mark.parametrize("change", ["root", "actions", "tools", "criteria", "options", "snapshot", "digest"])
def test_forged_or_widened_renewal_is_rejected_atomically(retired_trigger, change):
    runtime, source, _old_task, _old_id, current_id, allowed, _narrow = retired_trigger
    with origin_scope(current_id):
        request = approval(runtime, source)
        if change == "root":
            request["spec"]["roots"] = [str(allowed.parent)]
        elif change == "actions":
            request["spec"]["actions"] = [{"tool": "AC_fixture"}]
        elif change == "tools":
            request["spec"]["allowed_tools"].append("AC_other")
        elif change == "criteria":
            request["spec"]["success_criteria"][0]["value"] = False
        elif change == "options":
            request["spec"]["options"]["model"] = "different"
        else:
            request["snapshot" if change == "snapshot" else "authorization_review"] = "0" * 64
        with pytest.raises(AgentTaskError):
            runtime.triggers.control("create_authorized", request)
    assert len(runtime.triggers.list()["triggers"]) == 1
    assert runtime.triggers._row(source)["enabled"]


def test_normal_enable_does_not_replace_an_expired_source_policy(retired_trigger):
    runtime, source, _old_task, _old_id, current_id, _allowed, _narrow = retired_trigger
    runtime.triggers.control("disable", {"trigger_id": source})
    with origin_scope(current_id), pytest.raises(AgentTaskError, match="managed origin"):
        runtime.triggers.control("enable", {"trigger_id": source})


def test_lineage_survives_ancestor_removal_restart_and_task_retention(retired_trigger):
    runtime, source, old_task, _old_id, current_id, _allowed, _narrow = retired_trigger
    with origin_scope(current_id):
        request = approval(runtime, source)
        child = runtime.triggers.control("create_authorized", request)["trigger_id"]
        runtime.triggers.control("remove", {"trigger_id": source})
        runtime.cancel(old_task)
        with runtime.store.connection(write=True) as connection:
            connection.execute("UPDATE agent_tasks SET updated=? WHERE id=?", (time.time() - 32 * 86400, old_task))
        assert runtime.prune()["deleted"] == [old_task]
    runtime.close()
    restored = AgentRuntime(runtime.store.path, targets={"fixture": object()})
    try:
        with origin_scope(current_id):
            duplicate = fire(restored, child, "old-event", {"row": 1})
            assert duplicate == {"task_id": old_task, "state": "expired", "duplicate": True}
            proof = restored.triggers.control("get", {"trigger_id": child})["trigger"]["reauthorization"]
            assert proof["source_trigger"] == source
            restored.triggers.control("remove", {"trigger_id": child})
        with restored.store.connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM agent_trigger_event_history").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM agent_trigger_authorizations").fetchone()[0] == 0
    finally:
        restored.close()


def test_three_generations_share_dedup_pending_and_do_not_resurrect_a_removed_child(retired_trigger):
    runtime, source, old_task, _old_id, current_id, _allowed, _narrow = retired_trigger
    with origin_scope(current_id):
        first = approval(runtime, source)
        child = runtime.triggers.control("create_authorized", first)["trigger_id"]
        second = approval(runtime, child)
        grandchild = runtime.triggers.control("create_authorized", second)["trigger_id"]
        assert fire(runtime, grandchild, "old-event", {"row": 1})["task_id"] == old_task
        assert fire(runtime, grandchild, "future-event")["deferred"]
        runtime.triggers.control("remove", {"trigger_id": grandchild})
        repeat = runtime.triggers.control("create_authorized", second)
        assert repeat["trigger_id"] == grandchild and repeat["retired"] and not repeat["enabled"]
        assert runtime.triggers.control("review_authorization", {"trigger_id": child})["spec"] is None
        with pytest.raises(AgentTaskError, match="replacement"):
            runtime.triggers.control("enable", {"trigger_id": child})


def test_atomic_failure_leaves_source_and_event_namespace_unchanged(retired_trigger):
    runtime, source, _old_task, _old_id, current_id, _allowed, _narrow = retired_trigger
    with runtime.store.connection(write=True) as connection:
        connection.execute("CREATE TRIGGER fail_renew BEFORE INSERT ON agent_trigger_authorizations "
                           "BEGIN SELECT RAISE(ABORT, 'fixture rollback'); END")
    with origin_scope(current_id):
        request = approval(runtime, source)
        with pytest.raises(AgentTaskError, match="database operation failed"):
            runtime.triggers.control("create_authorized", request)
        assert runtime.triggers._row(source)["enabled"]
        assert len(runtime.triggers.list()["triggers"]) == 1
        with runtime.store.connection(write=True) as connection:
            assert connection.execute("SELECT COUNT(*) FROM agent_trigger_event_history").fetchone()[0] == 0
            connection.execute("DROP TRIGGER fail_renew")
        assert runtime.triggers.control("create_authorized", request)["enabled"]


@pytest.mark.parametrize("change", ["state", "event", "context", "current_revoked"])
def test_snapshot_and_current_authority_changes_require_another_review(retired_trigger, change):
    from je_auto_control.utils.agent_runtime import origin_policy
    runtime, source, _old_task, _old_id, current_id, allowed, _narrow = retired_trigger
    with origin_scope(current_id):
        request = approval(runtime, source)
        if change == "state":
            runtime.triggers.control("disable", {"trigger_id": source})
        elif change == "event":
            with runtime.store.connection(write=True) as connection:
                connection.execute("UPDATE agent_trigger_events SET payload_hash='changed' WHERE trigger_id=?",
                                   (source,))
        else:
            path = origin_policy._path(current_id)
            data = json.loads(path.read_text())
            if change == "context":
                data["roots"] = [str(allowed)]
            else:
                data["active"] = False
            path.write_text(json.dumps(data))
        with pytest.raises(AgentTaskError):
            runtime.triggers.control("create_authorized", request)


def test_direct_review_requires_owner_and_drive_authority(retired_trigger):
    runtime, source, _old_task, _old_id, current_id, _allowed, _narrow = retired_trigger
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_triggers SET owner=? WHERE id=?",
                           (json.dumps({"user_id": "alice", "role": "operator", "store_path": None}), source))
    with origin_scope(current_id), authorization_scope(AuthorizationContext("bob", "operator")):
        with pytest.raises(AgentTaskError, match="another caller"):
            approval(runtime, source)
    with origin_scope(current_id), authorization_scope(AuthorizationContext("alice", "viewer")):
        with pytest.raises(AuthorizationError):
            approval(runtime, source)


@pytest.mark.parametrize("retired_trigger", ["interval"], indirect=True)
def test_schedule_renewal_starts_in_the_future_without_replaying_missed_slots(retired_trigger):
    runtime, source, _old_task, _old_id, current_id, _allowed, _narrow = retired_trigger
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_triggers SET next_run=1 WHERE id=?", (source,))
    with origin_scope(current_id):
        child = runtime.triggers.control("create_authorized", approval(runtime, source))["trigger_id"]
    row = runtime.triggers._row(child)
    assert row["next_run"] > time.time() + 50 and row["config"] == {"seconds": 60}
    runtime.triggers.poll()
    assert len(runtime.store.list()) == 1


@pytest.mark.parametrize("retired_trigger", ["file"], indirect=True)
def test_file_checkpoint_and_config_are_preserved_and_outside_watch_scope_is_blocked(retired_trigger):
    runtime, source, _old_task, _old_id, current_id, _allowed, narrow = retired_trigger
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_triggers SET last_event='observed-version' WHERE id=?", (source,))
    with origin_scope(current_id):
        request = approval(runtime, source)
        outside = narrow / "other-subtree"
        outside.mkdir()
        request["spec"]["roots"] = [str(outside)]
        with pytest.raises(AgentTaskError, match="outside"):
            runtime.triggers.control("create_authorized", request)
        child = runtime.triggers.control("create_authorized", approval(runtime, source))["trigger_id"]
        assert runtime.triggers._row(child)["last_event"] == "observed-version"
        assert runtime.triggers._row(child)["config"] == runtime.triggers._row(source)["config"]


def test_concurrent_identical_approvals_reuse_one_registration(retired_trigger):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    runtime, source, _old_task, _old_id, current_id, _allowed, _narrow = retired_trigger
    with origin_scope(current_id):
        request = approval(runtime, source)
    barrier = Barrier(2)

    def create(_index):
        with origin_scope(current_id):
            barrier.wait(timeout=10)
            return runtime.triggers.control("create_authorized", request)["trigger_id"]

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(create, (0, 1)))
    assert results[0] == results[1] and len(runtime.triggers.list()["triggers"]) == 2


def test_new_event_history_failure_rolls_back_task_and_local_event_together(retired_trigger):
    runtime, source, old_task, _old_id, current_id, _allowed, _narrow = retired_trigger
    with origin_scope(current_id):
        child = runtime.triggers.control("create_authorized", approval(runtime, source))["trigger_id"]
        runtime.cancel(old_task)
        with runtime.store.connection(write=True) as connection:
            connection.execute("CREATE TRIGGER fail_history BEFORE INSERT ON agent_trigger_event_history "
                               "BEGIN SELECT RAISE(ABORT, 'fixture rollback'); END")
        with pytest.raises(AgentTaskError, match="database operation failed"):
            fire(runtime, child, "future-event")
        assert len(runtime.store.list()) == 1
        with runtime.store.connection(write=True) as connection:
            assert connection.execute("SELECT COUNT(*) FROM agent_trigger_events WHERE trigger_id=?",
                                      (child,)).fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM agent_trigger_event_history").fetchone()[0] == 1
            connection.execute("DROP TRIGGER fail_history")
        assert not fire(runtime, child, "future-event")["duplicate"]


@pytest.mark.parametrize("retired_trigger", ["file"], indirect=True)
def test_unavailable_fixed_watch_path_withholds_runnable_review(retired_trigger):
    from je_auto_control.utils.agent_runtime import origin_policy
    runtime, source, _old_task, _old_id, current_id, _allowed, narrow = retired_trigger
    other = narrow / "other"
    other.mkdir()
    path = origin_policy._path(current_id)
    data = json.loads(path.read_text())
    data["roots"] = [str(other)]
    path.write_text(json.dumps(data))
    with origin_scope(current_id):
        view = runtime.triggers.control("review_authorization", {"trigger_id": source})
        assert view["spec"] is None and view["issues"] == ["authorization_scope_unavailable"]
