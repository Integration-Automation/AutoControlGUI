"""Joining a bucket that already has content commits no revision.

A device's first sync against a non-empty bucket used to write a revision
that carried nothing but the device's own name under ``peers``: that listing
was what made later deletions wait for the device. Acknowledged tombstones
are now held for ``TOMBSTONE_HOLD_S``, which covers a device the bucket does
not list, so the join-only commit is gone. A device is listed by its first
real change.

What that costs is pinned here too: once the hold has run out, an *edit* made
on a device that only ever pulled re-creates a deleted entry without a
conflict (``test_past_the_hold_an_edit_from_a_device_that_only_pulled_...``).
An untouched copy is still removed, because the device's own baseline says
the entry was deleted elsewhere.

Hold expiry is simulated with ``tombstone_hold_s=0`` (the tombstone goes as
soon as the listed devices acknowledged it) or with ``now=``; no test waits.
"""
from unittest.mock import patch

import pytest

from je_auto_control.utils.config_sync import (
    ConfigBucket, ConfigSyncClient, ConfigSyncConflict, SyncAdapter, SyncEntry, SyncOperation,
    SyncOutbox, run_sync,
)
from je_auto_control.utils.config_sync.merge import awaits_ack
from je_auto_control.utils.config_sync.versions import TOMBSTONE_HOLD_S

_URL = "https://sync.invalid"
_T0 = 1_700_000_000.0


class _Server:
    """The revision-checked bucket endpoint, in memory."""

    def __init__(self):
        self.body = None
        self.revision = 0
        self.puts = 0

    def request(self, method, body=None):
        if method == "GET":
            return self.body
        self.puts += 1
        if body["base_revision"] != self.revision:
            raise ConfigSyncConflict("behind", self.revision)
        self.revision += 1
        self.body = {**body["bucket"], "revision": self.revision}
        return {"ok": True, "revision": self.revision}

    def bucket(self):
        return ConfigBucket.from_dict(self.body)


@pytest.fixture
def server():
    endpoint = _Server()
    with patch.object(ConfigSyncClient, "_request",
                      new=lambda _client, method, body=None: endpoint.request(method, body)):
        yield endpoint


class _DictAdapter(SyncAdapter):
    section = "custom"

    def __init__(self, origin, store):
        super().__init__(origin)
        self.store = store

    def read_local(self):
        return {key: dict(value) for key, value in self.store.items()}

    def write_local(self, key, value, existing):
        self.store[key] = dict(value)

    def delete_local(self, key):
        self.store.pop(key, None)


class _Device:
    """One machine: its local store and its durable outbox."""

    def __init__(self, tmp_path, name, store=None, hold_s=TOMBSTONE_HOLD_S):
        self.name = name
        self.store = {} if store is None else store
        self._outbox = SyncOutbox(tmp_path / f"{name}.sqlite3", account="alice",
                                  endpoint=_URL, base_delay_s=0.0)
        self._client = ConfigSyncClient(_URL, user_id="alice", tombstone_hold_s=hold_s)

    def sync(self):
        return run_sync(self._client, self._outbox, [_DictAdapter(self.name, self.store)],
                        device_id=self.name)


def _op(entry):
    return SyncOperation(section="custom", entry=entry)


# --- the join itself -----------------------------------------------------------------

def test_a_join_with_nothing_to_send_commits_nothing(tmp_path, server):
    _Device(tmp_path, "laptop", {"a": {"v": 1}}).sync()
    assert (server.revision, server.puts) == (1, 1)
    desktop = _Device(tmp_path, "desktop")
    report = desktop.sync()
    assert desktop.store == {"a": {"v": 1}}, "it still receives the content"
    assert (report.state, report.revision, report.pending) == ("synced", 1, 0)
    assert (server.revision, server.puts) == (1, 1), "a revision was committed just for joining"
    assert list(server.body["peers"]) == ["laptop"]
    for _again in range(3):
        desktop.sync()
    assert (server.revision, server.puts) == (1, 1)


def test_push_operations_from_an_unlisted_device_with_no_change_does_not_push(server):
    client = ConfigSyncClient(_URL, user_id="alice")
    entry = SyncEntry.create("a", {"v": 1}, "laptop")
    client.push_operations([_op(entry)], device_id="laptop", now=_T0)
    result = client.push_operations([], device_id="desktop", now=_T0)
    assert result.pushed is False and result.revision == 1
    assert result.bucket.values("custom") == {"a": {"v": 1}}
    assert server.puts == 1
    assert awaits_ack(server.bucket(), "desktop") is False


def test_an_unlisted_device_owes_no_acknowledgement_for_a_waiting_tombstone(server):
    client = ConfigSyncClient(_URL, user_id="alice")
    entry = SyncEntry.create("a", {"v": 1}, "laptop")
    client.push_operations([_op(entry)], device_id="laptop", now=_T0)
    client.push_operations([_op(entry.removed("laptop"))], device_id="laptop", now=_T0)
    assert awaits_ack(server.bucket(), "desktop") is False
    assert client.push_operations([], device_id="desktop", now=_T0).pushed is False
    assert server.puts == 2


def test_the_first_real_change_lists_the_device_and_deletions_then_wait_for_it(tmp_path, server):
    laptop = _Device(tmp_path, "laptop", {"a": {"v": 1}}, hold_s=0)
    laptop.sync()
    desktop = _Device(tmp_path, "desktop", hold_s=0)
    desktop.sync()
    desktop.store["b"] = {"v": 2}
    desktop.sync()
    assert set(server.body["peers"]) == {"laptop", "desktop"}
    laptop.sync()
    del laptop.store["a"]
    laptop.sync()
    # No hold at all, and still kept: the desktop is listed and has not acknowledged.
    assert server.bucket().get_entry("custom", "a").deleted
    assert awaits_ack(server.bucket(), "desktop") is True
    desktop.sync()
    assert desktop.store == {"b": {"v": 2}}
    laptop.sync()
    assert server.bucket().get_entry("custom", "a") is None


# --- a deletion made while the device is unlisted, inside the hold ---------------------

def _pulled_then_deleted_elsewhere(tmp_path, hold_s=TOMBSTONE_HOLD_S):
    """laptop creates ``a``; desktop pulls it without committing; laptop deletes it."""
    laptop = _Device(tmp_path, "laptop", {"a": {"v": 1}}, hold_s=hold_s)
    laptop.sync()
    desktop = _Device(tmp_path, "desktop", hold_s=hold_s)
    desktop.sync()
    assert desktop.store == {"a": {"v": 1}}
    del laptop.store["a"]
    laptop.sync()
    return laptop, desktop


def test_inside_the_hold_the_deletion_reaches_an_unlisted_device_as_a_deletion(tmp_path, server):
    _laptop, desktop = _pulled_then_deleted_elsewhere(tmp_path)
    assert list(server.body["peers"]) == ["laptop"], "the desktop was never listed"
    assert server.bucket().get_entry("custom", "a").deleted, "held although the laptop acknowledged"
    puts = server.puts
    report = desktop.sync()
    assert desktop.store == {}
    assert report.applied["custom"]["removed"] == ["a"]
    assert (report.state, report.conflicts) == ("synced", [])
    assert server.puts == puts, "receiving a deletion is not a reason to commit either"


def test_inside_the_hold_an_edit_made_meanwhile_becomes_a_conflict(tmp_path, server):
    laptop, desktop = _pulled_then_deleted_elsewhere(tmp_path)
    desktop.store["a"] = {"v": "edited while away"}
    report = desktop.sync()
    assert (report.state, report.conflicts) == ("conflict", ["custom/a"])
    entry = server.bucket().get_entry("custom", "a")
    assert entry.in_conflict
    assert sorted(sibling.deleted for sibling in entry.siblings) == [False, True]
    assert server.bucket().values("custom") == {}, "nothing came back by itself"
    seen = laptop.sync()
    assert laptop.store == {} and seen.conflicts == ["custom/a"]


def test_the_conflict_is_the_same_by_the_clock_until_the_hold_runs_out(server):
    client = ConfigSyncClient(_URL, user_id="alice")
    created = SyncEntry.create("a", {"v": 1}, "laptop")
    client.push_operations([_op(created)], device_id="laptop", now=_T0)
    assert client.push_operations([], device_id="tablet", now=_T0).pushed is False
    client.push_operations([_op(created.removed("laptop"))], device_id="laptop", now=_T0)
    # Another commit just short of thirty days later keeps the tombstone ...
    client.push_operations([_op(SyncEntry.create("b", {"v": 2}, "laptop"))],
                           device_id="laptop", now=_T0 + TOMBSTONE_HOLD_S - 60)
    edit = created.edited({"v": "tablet"}, "tablet")
    result = client.push_operations([_op(edit)], device_id="tablet",
                                    now=_T0 + TOMBSTONE_HOLD_S - 30)
    assert [conflict.key for conflict in result.conflicts] == ["a"]
    assert server.bucket().get_entry("custom", "a").in_conflict


# --- past the hold: what still holds, and what no longer does -----------------------------

def test_past_the_hold_an_untouched_copy_is_still_removed(tmp_path, server):
    _laptop, desktop = _pulled_then_deleted_elsewhere(tmp_path, hold_s=0)
    assert server.bucket().get_entry("custom", "a") is None, "the tombstone is gone"
    puts = server.puts
    report = desktop.sync()
    assert desktop.store == {}, "its own baseline says the entry was deleted elsewhere"
    assert report.applied["custom"]["removed"] == ["a"]
    assert server.bucket().values("custom") == {} and server.puts == puts


def test_past_the_hold_an_edit_from_a_device_that_only_pulled_brings_the_entry_back(
        tmp_path, server):
    """The weaker guarantee: with the join-only commit this was a conflict.

    The desktop was never listed, so the tombstone did not wait for it; once
    the hold is over nothing in the bucket remembers the deletion and the
    desktop's edit is taken as a new entry.
    """
    laptop, desktop = _pulled_then_deleted_elsewhere(tmp_path, hold_s=0)
    desktop.store["a"] = {"v": "edited while away"}
    report = desktop.sync()
    assert (report.state, report.conflicts) == ("synced", [])
    assert server.bucket().values("custom") == {"a": {"v": "edited while away"}}
    laptop.sync()
    assert laptop.store == {"a": {"v": "edited while away"}}, "the deleted entry returned"


def test_past_the_hold_by_the_clock_the_edit_returns_without_a_conflict(server):
    client = ConfigSyncClient(_URL, user_id="alice")
    created = SyncEntry.create("a", {"v": 1}, "laptop")
    client.push_operations([_op(created)], device_id="laptop", now=_T0)
    assert client.push_operations([], device_id="tablet", now=_T0).pushed is False
    client.push_operations([_op(created.removed("laptop"))], device_id="laptop", now=_T0)
    client.push_operations([_op(SyncEntry.create("b", {"v": 2}, "laptop"))],
                           device_id="laptop", now=_T0 + TOMBSTONE_HOLD_S + 60)
    assert server.bucket().get_entry("custom", "a") is None
    result = client.push_operations([_op(created.edited({"v": "tablet"}, "tablet"))],
                                    device_id="tablet", now=_T0 + TOMBSTONE_HOLD_S + 120)
    assert result.conflicts == []
    assert server.bucket().values("custom") == {"a": {"v": "tablet"}, "b": {"v": 2}}
