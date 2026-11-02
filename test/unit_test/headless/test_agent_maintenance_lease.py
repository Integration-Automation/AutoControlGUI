"""Lease maintenance cannot mutate a source after its actual input owner has retired."""
import threading

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore
from .test_agent_runtime import FakeTarget, specification


@pytest.fixture
def owned(tmp_path):
    users = UserStore(tmp_path / "users.json")
    users.add_user(user_id="owner", display_name="Owner", role="operator")
    owner = AuthorizationContext("owner", "operator", store_path=str(users.path))
    target = FakeTarget()
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={"fixture": target})
    try:
        with authorization_scope(owner):
            task = runtime.submit(specification()).task_id
            runtime.observe(task)
        yield runtime, target, users, owner, task
    finally:
        runtime.close()


@pytest.mark.parametrize("cause", ["expired", "revoked"])
def test_stale_maintenance_does_not_change_an_already_retired_source(owned, monkeypatch, cause):
    runtime, target, users, owner, task = owned
    entered, proceed = threading.Event(), threading.Event()
    failures = []
    remaining = runtime.clock.remaining

    def delayed(row):
        value = remaining(row)
        if threading.current_thread().name == "OwnedStaleLeaseWatch":
            entered.set()
            assert proceed.wait(5)
            return 0 if cause == "expired" else value
        return value

    def maintain():
        try:
            runtime.maintain()
        except Exception as error:  # reason: propagate owned background failures to the parent test
            failures.append(error)

    monkeypatch.setattr(runtime.clock, "remaining", delayed)
    watcher = threading.Thread(target=maintain, name="OwnedStaleLeaseWatch", daemon=True)
    watcher.start()
    try:
        assert entered.wait(5)
        with authorization_scope(owner):
            assert runtime.pause(task).state == "paused"
        assert task not in runtime._leases
        before = runtime.store.get(task)
        if cause == "revoked":
            users.set_role("owner", "viewer")
        proceed.set()
        watcher.join(5)
        assert not watcher.is_alive() and not failures
        assert runtime.store.get(task) == before, "A stale watcher cannot rewrite retired recovery evidence"
        assert target.calls == []
    finally:
        proceed.set()
        watcher.join(5)


@pytest.mark.parametrize("cause", ["expired", "revoked"])
def test_current_input_owner_still_retires_on_expiry_or_revocation(owned, monkeypatch, cause):
    runtime, target, users, _owner, task = owned
    if cause == "expired":
        monkeypatch.setattr(runtime.clock, "remaining", lambda _row: 0)
    else:
        users.set_role("owner", "viewer")
    runtime.maintain()
    assert runtime.store.get(task)["state"] == ("timed_out" if cause == "expired" else "cancelled")
    assert task not in runtime._leases and target.calls == []


@pytest.mark.parametrize("reacquire", [False, True])
def test_maintenance_rechecks_the_actual_lease_at_stop_publication(owned, monkeypatch, reacquire):
    runtime, target, _users, owner, task = owned
    remaining, request_stop = runtime.clock.remaining, runtime.store.request_stop
    first = [True]
    snapshots = []

    def expired_once(row):
        if first:
            first.pop()
            return 0
        return remaining(row)

    def changed(identifier, state, **options):
        if state == "cancelling" and not snapshots:
            with authorization_scope(owner):
                assert runtime.pause(task).state == "paused"
                if reacquire:
                    runtime.resume(task)
                    runtime.observe(task)
            snapshots.append(runtime.store.get(task))
        return request_stop(identifier, state, **options)

    monkeypatch.setattr(runtime.clock, "remaining", expired_once)
    monkeypatch.setattr(runtime.store, "request_stop", changed)
    runtime.maintain()
    assert snapshots and runtime.store.get(task) == snapshots[0]
    if reacquire:
        assert task in runtime._leases and not runtime._token(task).is_cancelled
    else:
        assert task not in runtime._leases
    assert target.calls == []


def test_maintenance_publishes_final_state_before_a_worker_can_settle(owned, monkeypatch):
    runtime, _target, _users, _owner, task = owned
    request_stop = runtime.store.request_stop

    def settle_immediately(identifier, state, **options):
        accepted = request_stop(identifier, state, **options)
        if accepted and state == "cancelling":
            runtime._settle_control(identifier)
        return accepted

    monkeypatch.setattr(runtime.clock, "remaining", lambda _row: 0)
    monkeypatch.setattr(runtime.store, "request_stop", settle_immediately)
    runtime.maintain()
    assert runtime.store.get(task)["state"] == "timed_out"
    assert task not in runtime._leases


def test_concurrent_retirement_cannot_validate_an_already_released_lease(owned, monkeypatch):
    runtime, _target, _users, _owner, task = owned
    released, proceed = threading.Event(), threading.Event()
    release = runtime.broker.release
    results, failures = [], []

    def delayed(lease, cleanup):
        accepted = release(lease, cleanup)
        if accepted and threading.current_thread().name == "OwnedRetirement":
            released.set()
            assert proceed.wait(5)
        return accepted

    def pause():
        try:
            results.append(runtime.pause(task))
        except Exception as error:  # reason: propagate owned retirement errors to the parent test
            failures.append(error)

    monkeypatch.setattr(runtime.broker, "release", delayed)
    worker = threading.Thread(target=pause, name="OwnedRetirement", daemon=True)
    worker.start()
    try:
        assert released.wait(5)
        assert runtime._retire(task) is False, "Concurrent retirement must remain pending for its actual owner"
    finally:
        proceed.set()
        worker.join(5)
    assert not worker.is_alive() and not failures
    assert results[0].state == "paused" and task not in runtime._leases


def test_revocation_reason_is_final_when_cancellation_is_published(owned, monkeypatch):
    runtime, _target, users, _owner, task = owned
    transition = runtime.store.transition
    published = []

    def capture(identifier, expected, state, **options):
        accepted = transition(identifier, expected, state, **options)
        if accepted and state == "cancelled":
            published.append(runtime.store.get(identifier))
        return accepted

    monkeypatch.setattr(runtime.store, "transition", capture)
    users.set_role("owner", "viewer")
    runtime.maintain()
    assert published and published[0]["reason"] == "owner authorization or origin scope requires review"
    assert runtime.store.get(task) == published[0], "Terminal publication must leave a stable recovery snapshot"
