"""The calls from before version vectors are causal too, and announce their device.

``bucket.upsert(...)`` / ``bucket.remove(...)`` without ``origin=`` wrote the
flat ``last_modified`` entry, so every program written against the first API
kept merging by "the later clock wins" after the causal merge shipped. And a
device that only ever called ``client.sync(bucket)`` was never recorded under
``peers``: tombstones did not wait for it, so an entry deleted elsewhere could
come back from it.
"""
from unittest.mock import patch

import pytest

from je_auto_control.utils.config_sync import (
    ConfigBucket, ConfigSyncClient, ConfigSyncConflict, ConfigSyncError, FullResyncRequired,
    PeerState, SyncEntry, default_device_id, merge_buckets,
)


class _Server:
    """The revision-checked bucket endpoint, in memory."""

    def __init__(self):
        self.body = None
        self.revision = 0
        self.puts = []

    def request(self, method, body=None):
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


def _client(device=None):
    return ConfigSyncClient("https://sync.invalid", user_id="alice", device_id=device)


# --- upsert / remove -----------------------------------------------------------

def test_upsert_without_origin_is_versioned_by_this_device():
    bucket = ConfigBucket(user_id="alice")
    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+a"})
    entry = bucket.get_entry("hotkeys", "hk1")
    assert entry is not None
    assert entry.origin == default_device_id()
    assert entry.vector == {default_device_id(): 1}
    assert bucket.values("hotkeys") == {"hk1": {"combo": "ctrl+a"}}


def test_a_second_upsert_is_an_edit_on_top_of_the_first():
    bucket = ConfigBucket(user_id="alice")
    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+a"})
    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+b"})
    assert bucket.get_entry("hotkeys", "hk1").vector == {default_device_id(): 2}


def test_the_callers_last_modified_is_the_display_stamp_not_part_of_the_value():
    bucket = ConfigBucket(user_id="alice")
    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+a", "last_modified": 1700.0})
    entry = bucket.get_entry("hotkeys", "hk1")
    assert entry.value == {"combo": "ctrl+a"}
    assert entry.modified_at == pytest.approx(1700.0)


def test_two_devices_using_the_old_calls_no_longer_let_the_clock_decide():
    base = ConfigBucket(user_id="alice")
    base.upsert("hotkeys", "hk1", {"combo": "ctrl+a"}, origin="laptop")
    laptop = ConfigBucket.from_dict(base.to_dict())
    desktop = ConfigBucket.from_dict(base.to_dict())
    with patch("je_auto_control.utils.config_sync.device.default_device_id",
               return_value="laptop"):
        laptop.upsert("hotkeys", "hk1", {"combo": "ctrl+l", "last_modified": 9_999_999_999.0})
    with patch("je_auto_control.utils.config_sync.device.default_device_id",
               return_value="desktop"):
        desktop.upsert("hotkeys", "hk1", {"combo": "ctrl+d", "last_modified": 5.0})
    merged, conflicts = merge_buckets(laptop, desktop)
    # Made apart: both are kept. "Later wins" would have dropped the desktop's.
    assert [conflict.unresolved for conflict in conflicts] == [True]
    assert merged.get_entry("hotkeys", "hk1").in_conflict


def test_remove_without_origin_leaves_a_versioned_tombstone():
    bucket = ConfigBucket(user_id="alice")
    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+a"}, origin="laptop")
    assert bucket.remove("hotkeys", "hk1") is True          # used to raise: "needs origin="
    entry = bucket.get_entry("hotkeys", "hk1")
    assert entry.deleted and entry.vector == {"laptop": 1, default_device_id(): 1}
    assert bucket.remove("hotkeys", "hk1") is False


def test_removing_a_flat_entry_supersedes_every_flat_copy():
    bucket = ConfigBucket(user_id="alice")
    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+a", "last_modified": 100.0}, versioned=False)
    assert bucket.remove("hotkeys", "hk1") is True
    assert bucket.get_entry("hotkeys", "hk1").deleted
    other = ConfigBucket(user_id="alice")
    # A flat copy stamped far in the future does not bring it back.
    other.upsert("hotkeys", "hk1", {"combo": "ctrl+a", "last_modified": 9e12}, versioned=False)
    merged, _conflicts = merge_buckets(bucket, other)
    assert merged.entries("hotkeys") == {}


def test_the_flat_format_is_still_available_on_request():
    bucket = ConfigBucket(user_id="alice")
    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+a", "last_modified": 100.0}, versioned=False)
    assert bucket.sections["hotkeys"]["hk1"] == {"combo": "ctrl+a", "last_modified": 100.0}
    assert bucket.remove("hotkeys", "hk1", versioned=False) is True
    assert bucket.sections["hotkeys"]["hk1"]["deleted"] is True
    assert "vector" not in bucket.sections["hotkeys"]["hk1"]


def test_versioned_false_refuses_what_it_cannot_express():
    bucket = ConfigBucket(user_id="alice")
    with pytest.raises(ConfigSyncError):
        bucket.upsert("hotkeys", "hk1", {"combo": "x"}, origin="laptop", versioned=False)
    bucket.upsert("hotkeys", "hk1", {"combo": "x"}, origin="laptop")
    with pytest.raises(ConfigSyncError):
        bucket.remove("hotkeys", "hk1", versioned=False)


# --- sync() ---------------------------------------------------------------------

def test_the_old_sync_records_this_device_as_a_peer(server):
    local = ConfigBucket(user_id="alice")
    local.upsert("hotkeys", "hk1", {"combo": "ctrl+a"}, origin="laptop")
    merged, _conflicts = _client("laptop").sync(local)
    peer = PeerState.from_dict("laptop", server.body["peers"]["laptop"])
    assert peer.acked_revision == merged.revision == 1 and not peer.retired
    assert merged.peers == server.body["peers"]


def test_the_default_device_id_is_used_when_the_client_was_given_none(server):
    _client().sync(ConfigBucket(user_id="alice"))
    assert list(server.body["peers"]) == [default_device_id()]


def test_a_tombstone_waits_for_a_device_that_only_uses_the_old_sync(server):
    seed = ConfigBucket(user_id="alice")
    seed.upsert("hotkeys", "hk1", {"combo": "ctrl+a"}, origin="laptop")
    laptop, _ = _client("laptop").sync(seed)
    desktop, _ = _client("desktop").sync(ConfigBucket(user_id="alice"))   # the old call only
    assert "hk1" in desktop.values("hotkeys")
    # The laptop deletes; the desktop has not seen it yet, so it must be kept.
    laptop.remove("hotkeys", "hk1", origin="laptop")
    laptop, _ = _client("laptop").sync(laptop)
    assert SyncEntry.from_dict("hk1", server.body["sections"]["hotkeys"]["hk1"]).deleted
    # The desktop syncs its stale copy: the deletion wins instead of the entry returning.
    desktop, _ = _client("desktop").sync(desktop)
    assert desktop.values("hotkeys") == {}
    # Everyone has acknowledged it now, but it is held for the machines that
    # have not synced yet ...
    laptop, _ = _client("laptop").sync(laptop)
    assert SyncEntry.from_dict("hk1", server.body["sections"]["hotkeys"]["hk1"]).deleted
    # ... until the hold has passed; then the next commit drops it.
    stamp = server.body["sections"]["hotkeys"]["hk1"]["deleted_at"]
    laptop, _ = _client("laptop").sync(laptop, now=stamp + 31 * 24 * 3600.0)
    assert "hk1" not in server.body["sections"]["hotkeys"]


def test_a_retired_device_is_refused_by_the_old_sync_too(server):
    _client("laptop").sync(ConfigBucket(user_id="alice"))
    _client("desktop").sync(ConfigBucket(user_id="alice"))
    _client("laptop").retire_peer("desktop")
    with pytest.raises(FullResyncRequired):
        _client("desktop").sync(ConfigBucket(user_id="alice"))


def test_a_flat_bucket_file_after_its_first_sync_with_this_code(server):
    """Untouched flat entries stay as they were; what this device writes is versioned."""
    server.revision = 3
    server.body = {"user_id": "alice", "revision": 3, "sections": {"hotkeys": {
        "old": {"combo": "ctrl+o", "last_modified": 100.0},
        "edited": {"combo": "ctrl+e", "last_modified": 100.0}}}}
    local = _client("laptop").fetch()
    local.upsert("hotkeys", "edited", {"combo": "ctrl+E"}, origin="laptop")
    local.upsert("hotkeys", "new", {"combo": "ctrl+n"}, origin="laptop")
    merged, _conflicts = _client("laptop").sync(local)
    stored = server.body["sections"]["hotkeys"]
    assert stored["old"] == {"combo": "ctrl+o", "last_modified": 100.0}
    assert stored["edited"]["value"] == {"combo": "ctrl+E"} and stored["edited"]["vector"] == {"laptop": 1}
    assert stored["new"]["vector"] == {"laptop": 1}
    assert server.body["peers"]["laptop"]["acked_revision"] == 4
    assert merged.values("hotkeys") == {
        "old": {"combo": "ctrl+o", "last_modified": 100.0},
        "edited": {"combo": "ctrl+E"}, "new": {"combo": "ctrl+n"}}
