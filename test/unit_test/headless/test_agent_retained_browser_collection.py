"""Task-bound retained process ownership; no SDK, browser, desktop or shared state is touched."""
from copy import deepcopy
from importlib import import_module
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError

PROOF = {"contract": 1, "input_supported": False, "network_retired": True, "context_id": "a" * 32}


class OwnedProcess:
    """External process seam; the actual collection must preserve and confirm its ownership."""

    def __init__(self, failure=False, confirmed=True):
        self.retired = False
        self.failure = failure
        self.confirmed = confirmed
        self.attempts = 0

    def close(self):
        self.attempts += 1
        if self.failure:
            raise AgentTaskError("controlled owned process has not retired")
        self.retired = self.confirmed


def collection(clock):
    try:
        module = import_module("je_auto_control.utils.agent_runtime.retained_browser")
    except ModuleNotFoundError as error:
        if error.name != "je_auto_control.utils.agent_runtime.retained_browser":
            raise
        pytest.fail("The effect-task-bound retained browser collection is missing")
    return module.RetainedBrowsers(clock=lambda: clock[0])


def source(identifier="first"):
    return {"id": identifier, "spec": {"target": "browser", "options": {"profile": "original"}},
            "owner": {"user_id": "reviewed-user", "role": "operator", "store_path": "owned.sqlite"}}


def retain(pool, row, process=None):
    process = OwnedProcess() if process is None else process
    with pool.reserve(row) as entry:
        assert entry is not None
        pool.commit(entry, process, PROOF)
    return entry


def test_distinct_effect_tasks_keep_their_own_process_on_one_profile():
    pool = collection([0])
    first, second = retain(pool, source()), retain(pool, source("second"))
    assert pool.require(source()) is first
    assert pool.require(source("second")) is second
    assert first.channel is not second.channel
    pool.discard("first")
    assert first.channel.retired and not second.channel.retired
    with pytest.raises(AgentTaskError, match="unavailable"):
        pool.require(source())
    pool.close()
    assert second.channel.retired


@pytest.mark.parametrize("field", ["owner", "spec"])
def test_source_binding_change_cannot_restore_historical_context(field):
    pool = collection([0])
    row = source()
    entry = retain(pool, row)
    changed = deepcopy(row)
    changed[field] = {"changed": True}
    with pytest.raises(AgentTaskError, match="unavailable"):
        pool.require(changed)
    assert entry.channel.retired
    with pytest.raises(AgentTaskError, match="unavailable"):
        pool.require(row)


def test_absolute_300_second_expiry_does_not_extend_on_borrow():
    clock = [10]
    pool = collection(clock)
    entry = retain(pool, source())
    clock[0] = 309.9
    assert pool.borrow(source()) is entry
    pool.release(entry)
    clock[0] = 310
    with pytest.raises(AgentTaskError, match="unavailable"):
        pool.borrow(source())
    assert entry.channel.retired


def test_only_one_borrower_and_no_use_of_pending_reservation():
    pool = collection([0])
    row = source()
    with pool.reserve(row) as entry:
        with pytest.raises(AgentTaskError, match="unavailable"):
            pool.require(row)
        pool.commit(entry, OwnedProcess(), PROOF)
    assert pool.borrow(row) is entry
    with pytest.raises(AgentTaskError, match="busy"):
        pool.borrow(row)
    pool.release(entry)
    assert pool.borrow(row) is entry
    pool.release(entry)
    pool.close()


def test_capacity_counts_pending_reservations_and_never_evicts_a_borrower():
    pool = collection([0])
    entries = [retain(pool, source(str(index))) for index in range(15)]
    borrowed = pool.borrow(source("0"))
    with pool.reserve(source("pending")) as pending:
        assert pending is not None and pool.full
        with pool.reserve(source("overflow")) as refused:
            assert refused is None
        assert not borrowed.channel.retired
    assert not pool.full
    assert all(not entry.channel.retired for entry in entries)
    pool.release(borrowed)
    pool.close()


@pytest.mark.parametrize("failure,confirmed", [(True, True), (False, False)])
def test_unconfirmed_reaping_stays_tracked_unavailable_and_counts_against_capacity(failure, confirmed):
    pool = collection([0])
    entry = retain(pool, source("failed"), OwnedProcess(failure, confirmed))
    for index in range(15):
        retain(pool, source(str(index)))
    with pytest.raises(AgentTaskError):
        pool.discard("failed")
    assert pool.full
    with pytest.raises(AgentTaskError):
        pool.require(source("failed"))
    entry.channel.failure = False
    entry.channel.confirmed = True
    pool.close()
    assert entry.channel.retired and not pool.full


def test_collection_close_invalidates_borrow_and_closes_other_owned_processes_after_a_failure():
    pool = collection([0])
    first = retain(pool, source("failed"), OwnedProcess(failure=True))
    second = retain(pool, source("borrowed"))
    borrowed = pool.borrow(source("borrowed"))
    with pytest.raises(AgentTaskError):
        pool.close()
    assert second.channel.retired
    with pytest.raises(AgentTaskError):
        pool.require(source("borrowed"))
    pool.release(borrowed)
    first.channel.failure = False
    pool.close()
    assert first.channel.retired


def test_invalid_proof_cannot_leave_an_orphaned_detached_process():
    pool = collection([0])
    process = OwnedProcess()
    with pytest.raises(AgentTaskError):
        with pool.reserve(source()) as entry:
            pool.commit(entry, process, {**PROOF, "input_supported": True})
    assert process.retired
    with pytest.raises(AgentTaskError):
        pool.require(source())


def test_lost_owned_process_never_launches_or_recreates_a_context():
    pool = collection([0])
    entry = retain(pool, source())
    entry.channel.close()
    with pytest.raises(AgentTaskError, match="unavailable"):
        pool.borrow(source())
    assert entry.channel.retired
    pool.close()


def test_closed_collection_cannot_create_new_context_reservations():
    pool = collection([0])
    pool.close()
    with pytest.raises(AgentTaskError, match="closed"):
        with pool.reserve(source("new")):
            pytest.fail("A closed owner cannot accept more retained process ownership")


def test_source_binding_preserves_json_value_types():
    pool = collection([0])
    row = source()
    row["spec"]["inputs"] = {"flag": 1}
    entry = retain(pool, row)
    changed = deepcopy(row)
    changed["spec"]["inputs"]["flag"] = True
    try:
        with pytest.raises(AgentTaskError, match="unavailable"):
            pool.borrow(changed)
        assert entry.channel.retired
    finally:
        pool.close()


def test_detachment_time_cannot_extend_the_absolute_retained_lifetime():
    clock = [0]
    pool = collection(clock)
    process = OwnedProcess()
    with pool.reserve(source()) as entry:
        clock[0] = 20
        pool.commit(entry, process, PROOF)
    clock[0] = 300
    try:
        with pytest.raises(AgentTaskError, match="unavailable"):
            pool.borrow(source())
        assert process.retired
    finally:
        pool.close()


def test_failed_detached_transfer_has_one_cleanup_owner_and_can_be_reaped_after_recovery():
    from je_auto_control.utils.agent_runtime.retained_browser_runtime import retire_target, maintain_retained
    pool = collection([0])
    row = source()
    process = OwnedProcess(failure=True)
    target = SimpleNamespace(_channel=None,
        detach_readonly=lambda: (process, {**PROOF, "contract": True}))
    runtime = SimpleNamespace(_retained_browsers=pool, _retained_source=lambda _identifier: row)
    try:
        with pytest.raises(AgentTaskError):
            retire_target(runtime, row, target, True)
        assert target._channel is None, "The collection already owns the detached process cleanup"
        assert pool.sources() == [row]
        process.failure = False
        maintain_retained(runtime)
        assert process.retired and pool.sources() == []
    finally:
        process.failure = False
        pool.close()
