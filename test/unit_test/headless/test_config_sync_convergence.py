"""Config sync converges without trusting clocks, across restarts and deletions.

The first merge picked the later ``last_modified``: a machine whose clock ran
ahead won every disagreement, two machines editing one entry while apart lost
an edit silently, a change made offline lived only in memory, and a tombstone
was dropped after thirty days whether or not every machine had seen it.
"""
import threading
from dataclasses import replace
from unittest.mock import patch

import pytest

from je_auto_control.utils.config_sync import (
    ConfigBucket, ConfigSyncClient, ConfigSyncConflict, ConfigSyncError, FullResyncRequired,
    PeerState, SyncEntry, SyncOperation, SyncOutbox, collect_tombstones, compare_vectors,
    merge_buckets, merge_collections, merge_entries,
)


class _Server:
    """The revision-checked bucket endpoint, in memory."""

    def __init__(self):
        self.body = None
        self.revision = 0
        self.offline = False
        self.puts = []

    def request(self, method, body=None):
        if self.offline:
            raise ConfigSyncError("config sync: connection refused")
        if method == "GET":
            return self.body
        self.puts.append(body)
        if body["base_revision"] != self.revision:
            raise ConfigSyncConflict("behind", self.revision)
        self.revision += 1
        self.body = {**body["bucket"], "revision": self.revision}
        return {"ok": True, "revision": self.revision}


@pytest.fixture
def server():
    endpoint = _Server()
    with patch.object(ConfigSyncClient, "_request",
                      new=lambda _client, method, body=None: endpoint.request(method, body)):
        yield endpoint


def _client():
    return ConfigSyncClient("https://sync.invalid", user_id="alice")


def _op(entry, section="hotkeys"):
    return SyncOperation(section=section, entry=entry)


# --- merge_entries ---------------------------------------------------------

def test_parallel_edits_preserve_conflict():
    base = SyncEntry.create("hk1", {"combo": "ctrl+a"}, "laptop")
    left = base.edited({"combo": "ctrl+l"}, "laptop")
    right = base.edited({"combo": "ctrl+r"}, "desktop")
    decision = merge_entries(left, right)
    conflict = decision.conflict
    assert conflict.local == left and conflict.remote == right
    siblings = decision.entry.siblings
    assert decision.entry.in_conflict and len(siblings) == 2
    assert left in siblings and right in siblings
    # Both machines compute the same conflicted entry, so they still converge.
    assert merge_entries(right, left).entry == decision.entry


def test_clock_skew_does_not_choose_winner():
    base = SyncEntry.create("hk1", {"combo": "ctrl+a"}, "laptop", modified_at=1_000.0)
    newer = base.edited({"combo": "ctrl+b"}, "laptop", modified_at=5.0)   # clock far behind
    stale = replace(base, modified_at=9_999_999_999.0)                    # clock far ahead
    assert merge_entries(stale, newer).entry == newer
    assert merge_entries(newer, stale).entry == newer

    skewed = merge_entries(base.edited({"combo": "l"}, "laptop", modified_at=1.0),
                           base.edited({"combo": "r"}, "desktop", modified_at=9e12))
    wall_clock_does_not_change_merge = skewed.conflict is not None and skewed.entry.in_conflict
    assert wall_clock_does_not_change_merge is True


def test_a_change_made_knowing_the_other_supersedes_it_and_reports_nothing():
    base = SyncEntry.create("hk1", {"combo": "ctrl+a"}, "laptop")
    edited = base.edited({"combo": "ctrl+b"}, "desktop")
    assert merge_entries(base, edited).entry == edited
    assert merge_entries(edited, base).conflict is None
    assert compare_vectors(base.vector, edited.vector) == "before"


def test_an_edit_made_apart_from_a_delete_is_a_conflict_not_a_silent_loss():
    base = SyncEntry.create("hk1", {"combo": "ctrl+a"}, "laptop")
    tombstone = base.removed("laptop")
    assert tombstone.is_deleted is True
    decision = merge_entries(tombstone, base.edited({"combo": "ctrl+z"}, "desktop"))
    assert decision.conflict is not None
    # A delete made after seeing the value just wins.
    assert merge_entries(base, tombstone).entry == tombstone


def test_the_same_value_made_apart_is_not_a_conflict():
    """Two machines that each already had the entry agree; nothing to choose."""
    left = SyncEntry.create("hk1", {"combo": "ctrl+a"}, "laptop")
    right = SyncEntry.create("hk1", {"combo": "ctrl+a"}, "desktop")
    decision = merge_entries(left, right)
    assert decision.conflict is None and not decision.entry.in_conflict
    assert decision.entry.value == {"combo": "ctrl+a"}
    assert decision.entry.vector == {"laptop": 1, "desktop": 1}
    assert merge_entries(right, left).entry == decision.entry
    for side in (left, right):
        assert merge_entries(side, decision.entry).entry == decision.entry


def test_resolving_a_conflict_supersedes_every_sibling():
    base = SyncEntry.create("hk1", {"combo": "a"}, "laptop")
    left, right = base.edited({"combo": "l"}, "laptop"), base.edited({"combo": "r"}, "desktop")
    conflicted = merge_entries(left, right).entry
    chosen = conflicted.resolved({"combo": "r"}, "laptop")
    assert not chosen.in_conflict
    for other in (left, right, conflicted):
        assert merge_entries(other, chosen).entry == chosen


def test_changes_to_different_keys_merge_without_conflict():
    one = SyncEntry.create("hk1", {"combo": "a"}, "laptop")
    two = SyncEntry.create("hk2", {"combo": "b"}, "desktop")
    merged, conflicts = merge_collections({"hk1": one}, {"hk2": two})
    assert merged == {"hk1": one, "hk2": two} and conflicts == []


def test_an_entry_round_trips_through_its_bucket_shape():
    base = SyncEntry.create("hk1", {"combo": "a"}, "laptop")
    conflicted = merge_entries(base.edited({"combo": "l"}, "laptop"),
                               base.removed("desktop")).entry
    assert SyncEntry.from_dict("hk1", conflicted.to_dict()) == conflicted
    with pytest.raises(ConfigSyncError):
        SyncEntry.from_dict("hk1", {"value": {}, "vector": {"laptop": -1}})
    with pytest.raises(ConfigSyncError):
        SyncEntry.from_dict("hk1", {"combo": "flat entry"})


# --- buckets ---------------------------------------------------------------

def test_a_bucket_written_with_a_device_id_merges_by_causality():
    laptop = ConfigBucket(user_id="alice")
    laptop.upsert("hotkeys", "hk1", {"combo": "ctrl+a"}, origin="laptop")
    desktop = ConfigBucket.from_dict(laptop.to_dict())
    laptop.upsert("hotkeys", "hk1", {"combo": "ctrl+l"}, origin="laptop")
    desktop.upsert("hotkeys", "hk1", {"combo": "ctrl+r"}, origin="desktop")

    merged, conflicts = merge_buckets(laptop, desktop)
    assert len(conflicts) == 1 and conflicts[0].unresolved is True
    assert merged.values("hotkeys") == {}
    [(section, entry)] = merged.conflicts()
    assert section == "hotkeys"
    assert {sibling.value["combo"] for sibling in entry.siblings} == {"ctrl+l", "ctrl+r"}


def test_a_versioned_tombstone_is_not_dropped_by_age():
    bucket = ConfigBucket(user_id="alice")
    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+a"}, origin="laptop")
    assert bucket.remove("hotkeys", "hk1", origin="laptop") is True
    merged, _conflicts = merge_buckets(bucket, ConfigBucket(user_id="alice"), now=9e12)
    assert merged.get_entry("hotkeys", "hk1").is_deleted is True
    with pytest.raises(ConfigSyncError):
        other = ConfigBucket(user_id="alice")
        other.upsert("hotkeys", "hk1", {"combo": "ctrl+a"}, origin="laptop")
        other.remove("hotkeys", "hk1", versioned=False)   # a flat tombstone cannot delete it


# --- tombstone collection --------------------------------------------------

def test_a_tombstone_waits_for_every_active_peer():
    tombstone = replace(SyncEntry.create("hk1", {"c": 1}, "laptop").removed("laptop"),
                        deleted_revision=5)
    entries = {"hk1": tombstone}
    behind = [PeerState("laptop", acked_revision=6), PeerState("desktop", acked_revision=4)]
    assert collect_tombstones(entries, behind) == entries
    caught_up = [PeerState("laptop", acked_revision=6), PeerState("desktop", acked_revision=5)]
    assert collect_tombstones(entries, caught_up) == {}
    retired = [PeerState("laptop", acked_revision=6),
               PeerState("desktop", acked_revision=4, retired=True)]
    assert collect_tombstones(entries, retired) == {}
    assert collect_tombstones(entries, []) == entries


def test_a_deletion_reaches_an_offline_machine_however_long_it_was_away(server):
    client = _client()
    entry = SyncEntry.create("hk1", {"combo": "ctrl+a"}, "laptop")
    client.push_operations([_op(entry)], device_id="laptop", now=0.0)
    client.push_operations([], device_id="desktop", now=0.0)

    client.push_operations([_op(entry.removed("laptop"))], device_id="laptop", now=1.0)
    # Years pass on the laptop's clock; the desktop has not been back.
    for year in range(1, 4):
        result = client.push_operations([], device_id="laptop", now=year * 3.2e7)
        assert result.bucket.get_entry("hotkeys", "hk1").is_deleted is True

    seen = client.push_operations([], device_id="desktop", now=1e9)
    assert seen.bucket.values("hotkeys") == {}
    # Now that every peer has acknowledged it, the tombstone can go.
    final = client.push_operations([], device_id="laptop", now=1e9)
    assert final.bucket.sections["hotkeys"] == {}
    # ... and nobody keeps pushing acknowledgements at each other afterwards.
    puts = len(server.puts)
    client.push_operations([], device_id="desktop", now=1e9)
    client.push_operations([], device_id="laptop", now=1e9)
    assert len(server.puts) == puts


def test_retired_peer_requires_full_sync(server):
    client = _client()
    entry = SyncEntry.create("hk1", {"combo": "ctrl+a"}, "laptop")
    client.push_operations([_op(entry)], device_id="laptop")
    client.push_operations([], device_id="desktop")
    stale_edit = entry.edited({"combo": "made while away"}, "desktop")

    client.retire_peer("desktop")
    client.push_operations([_op(entry.removed("laptop"))], device_id="laptop")
    # With the desktop retired the laptop alone confirms, and the tombstone is collected.
    collected = client.push_operations([], device_id="laptop")
    assert collected.bucket.sections["hotkeys"] == {}

    before = server.revision
    with pytest.raises(FullResyncRequired):
        client.push_operations([_op(stale_edit)], device_id="desktop")
    assert server.revision == before, "a retired device must not write"

    adopted = client.full_resync(device_id="desktop")
    assert adopted.values("hotkeys") == {}, "the deleted entry did not come back"
    assert adopted.peer_states()["desktop"].retired is False
    assert client.push_operations([], device_id="desktop").bucket.values("hotkeys") == {}


def test_peers_unseen_for_too_long_are_retired_when_asked(server):
    client = _client()
    client.push_operations([], device_id="desktop", now=0.0)
    entry = SyncEntry.create("hk1", {"combo": "a"}, "laptop")
    client.push_operations([_op(entry)], device_id="laptop", now=100.0, max_offline_s=50.0)
    assert server.body["peers"]["desktop"]["retired"] is True
    assert server.body["peers"]["laptop"]["retired"] is False


def test_two_devices_pushing_at_once_lose_nothing(server):
    client = _client()
    mine = SyncEntry.create("mine", {"combo": "m"}, "laptop")
    theirs = SyncEntry.create("theirs", {"combo": "t"}, "desktop")
    real = server.request
    raced = []

    def racing(method, body=None):
        if method == "PUT" and not raced:
            raced.append(True)
            # The desktop's push lands between the laptop's fetch and its push.
            ConfigSyncClient("https://sync.invalid", user_id="alice").push_operations(
                [_op(theirs)], device_id="desktop")
        return real(method, body)

    server.request = racing
    result = client.push_operations([_op(mine)], device_id="laptop")
    assert set(result.bucket.values("hotkeys")) == {"mine", "theirs"}
    assert result.revision == 2


def test_resending_a_batch_changes_nothing(server):
    client = _client()
    operations = [_op(SyncEntry.create("hk1", {"combo": "a"}, "laptop"))]
    first = client.push_operations(operations, device_id="laptop")
    again = client.push_operations(operations, device_id="laptop")
    assert first.pushed is True and again.pushed is False
    assert again.revision == first.revision == 1


# --- the outbox ------------------------------------------------------------

def _outbox(tmp_path, **options):
    return SyncOutbox(tmp_path / "outbox.sqlite3", account="alice",
                      endpoint="https://sync.invalid", **options)


def test_restart_retries_outbox(tmp_path, server):
    entry = SyncEntry.create("hk1", {"combo": "ctrl+a"}, "laptop")
    server.offline = True
    first_run = _outbox(tmp_path, base_delay_s=0.0)
    first_run.enqueue(_op(entry))
    report = first_run.drain(
        lambda batch: _client().push_operations(batch, device_id="laptop"), max_attempts=2)
    assert report.offline is True and report.pending == 1 and report.attempts == 2

    # The program restarts; the server comes back.
    server.offline = False
    second_run = _outbox(tmp_path, base_delay_s=0.0)
    queued = second_run.pending()
    assert [operation.operation_id for operation in queued] == [entry.operation_id]
    report = second_run.drain(
        lambda batch: _client().push_operations(batch, device_id="laptop"))
    assert report.sent == 1 and report.pending == 0 and report.offline is False
    assert server.body["sections"]["hotkeys"]["hk1"]["operation_id"] == entry.operation_id


def test_an_uncertain_send_is_resent_under_the_same_operation_id(tmp_path, server):
    """The push arrived but its reply did not: the resend must not double-apply."""
    entry = SyncEntry.create("hk1", {"combo": "ctrl+a"}, "laptop")
    outbox = _outbox(tmp_path, base_delay_s=0.0)
    outbox.enqueue(_op(entry))
    outbox.enqueue(_op(entry))   # queued twice by mistake: still one operation
    lost = []

    def send(batch):
        _client().push_operations(batch, device_id="laptop")
        if not lost:
            lost.append(True)
            raise ConfigSyncError("config sync PUT failed: timed out")

    report = outbox.drain(send)
    assert report.sent == 1 and report.attempts == 2
    assert server.revision == 1, "the resend found its change already there"


def test_backoff_is_bounded_and_the_queue_waits_for_it(tmp_path):
    outbox = _outbox(tmp_path, base_delay_s=2.0, max_delay_s=30.0)
    assert [outbox.retry_delay(n) for n in (0, 1, 2, 3, 4, 5, 6, 60)] == [
        0.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]
    entry = SyncEntry.create("hk1", {"combo": "a"}, "laptop")
    outbox.enqueue(_op(entry))
    outbox.record_failure([entry.operation_id], now=100.0, error="offline")
    assert outbox.seconds_until_due(100.0) == pytest.approx(2.0)
    calls = []
    report = outbox.drain(calls.append, wait=False, clock=lambda: 100.5)
    assert calls == [] and report.pending == 1 and report.offline is True


def test_a_drain_waiting_to_retry_can_be_cancelled(tmp_path):
    outbox = _outbox(tmp_path, base_delay_s=3600.0, max_delay_s=3600.0)
    outbox.enqueue(_op(SyncEntry.create("hk1", {"combo": "a"}, "laptop")))
    cancel = threading.Event()
    attempts = []

    def send(batch):
        attempts.append(batch)
        cancel.set()          # cancelled while the hour-long back-off is pending
        raise ConfigSyncError("offline")

    report = outbox.drain(send, cancel=cancel, max_attempts=10)
    assert report.cancelled is True and len(attempts) == 1 and report.pending == 1


def test_outboxes_are_isolated_by_account_and_endpoint(tmp_path):
    path = tmp_path / "outbox.sqlite3"
    alice = SyncOutbox(path, account="alice", endpoint="https://one.invalid")
    bob = SyncOutbox(path, account="bob", endpoint="https://one.invalid")
    elsewhere = SyncOutbox(path, account="alice", endpoint="https://two.invalid")
    alice.enqueue(_op(SyncEntry.create("hk1", {"combo": "a"}, "laptop")))
    alice.save_baseline(ConfigBucket(user_id="alice", revision=7))
    assert len(alice.pending()) == 1
    assert bob.pending() == [] and elsewhere.pending() == []
    assert bob.load_baseline() is None and elsewhere.load_baseline() is None
    assert SyncOutbox(path, account="alice",
                      endpoint="https://one.invalid/").load_baseline().revision == 7


def test_a_full_resync_is_not_retried_by_the_outbox(tmp_path):
    outbox = _outbox(tmp_path, base_delay_s=0.0)
    outbox.enqueue(_op(SyncEntry.create("hk1", {"combo": "a"}, "laptop")))

    def send(_batch):
        raise FullResyncRequired("retired")

    with pytest.raises(FullResyncRequired):
        outbox.drain(send)
    assert [operation.entry.key for operation in outbox.clear()] == ["hk1"]
    assert outbox.pending() == []
