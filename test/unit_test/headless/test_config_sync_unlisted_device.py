"""A deletion is still there when a machine the bucket never listed turns up.

A versioned tombstone is dropped once every device under ``peers`` has
acknowledged it. A machine that holds the entry but has never synced is not
under ``peers``: after the tombstone was gone, its first sync simply added the
entry again -- no conflict, no report. An acknowledged tombstone is now also
held for ``TOMBSTONE_HOLD_S`` from the commit that first carried it, so a
machine that joins inside that time meets the deletion.

Every time here is passed in (``now=``); no test reads the clock.
"""
from unittest.mock import patch

import pytest

from je_auto_control.utils.config_sync import (
    ConfigBucket, ConfigSyncClient, ConfigSyncConflict, PeerState, SyncEntry, SyncOperation,
    collect_tombstones,
)
from je_auto_control.utils.config_sync.merge import settle
from je_auto_control.utils.config_sync.versions import TOMBSTONE_HOLD_S

_DAY = 24 * 3600.0
_T0 = 1_700_000_000.0


class _Server:
    """The revision-checked bucket endpoint, in memory."""

    def __init__(self):
        self.body = None
        self.revision = 0

    def request(self, method, body=None):
        if method == "GET":
            return self.body
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


def _client(device, **options):
    return ConfigSyncClient("https://sync.invalid", user_id="alice", device_id=device, **options)


def _push(device, operations=(), *, now, **options):
    entries = [SyncOperation(section="hotkeys", entry=entry) for entry in operations]
    return _client(device, **options).push_operations(entries, device_id=device, now=now)


def _delete_on_both_listed_devices(now=_T0, **options):
    """laptop and desktop both know ``hk1``; laptop deletes it; both acknowledge."""
    created = SyncEntry.create("hk1", {"combo": "ctrl+a"}, "laptop")
    _push("laptop", [created], now=now, **options)
    _push("desktop", now=now, **options)                    # joins: it now holds hk1 too
    _push("laptop", [created.removed("laptop")], now=now, **options)
    _push("desktop", now=now, **options)                    # acknowledges the deletion
    _push("laptop", now=now, **options)
    return created


def test_a_machine_that_never_synced_meets_the_deletion_instead_of_undoing_it(server):
    _delete_on_both_listed_devices()
    assert server.bucket().values("hotkeys") == {}
    # The tablet has had hk1 all along and syncs for the first time a day later.
    result = _push("tablet", [SyncEntry.create("hk1", {"combo": "ctrl+a"}, "tablet")],
                   now=_T0 + _DAY)
    entry = server.bucket().get_entry("hotkeys", "hk1")
    assert entry.in_conflict, "the deletion and the tablet's copy are both kept"
    assert sorted(sibling.deleted for sibling in entry.siblings) == [False, True]
    assert [conflict.key for conflict in result.conflicts] == ["hk1"]
    assert server.bucket().values("hotkeys") == {}, "nothing came back by itself"


def test_every_machine_sees_the_same_conflict_and_one_choice_settles_it(server):
    _delete_on_both_listed_devices()
    _push("tablet", [SyncEntry.create("hk1", {"combo": "ctrl+a"}, "tablet")], now=_T0 + _DAY)
    seen = [_push(device, now=_T0 + _DAY).bucket.get_entry("hotkeys", "hk1")
            for device in ("laptop", "desktop", "tablet")]
    assert seen[0] == seen[1] == seen[2] and seen[0].in_conflict
    # A person on the desktop decides the deletion stands.
    _push("desktop", [seen[1].resolved(None, "desktop")], now=_T0 + _DAY)
    for device in ("laptop", "tablet", "desktop"):
        assert _push(device, now=_T0 + _DAY).bucket.values("hotkeys") == {}
    assert not server.bucket().conflicts()


def test_a_flat_copy_from_an_unlisted_machine_stays_deleted(server):
    """``client.sync`` with an entry in the flat shape from before version vectors."""
    _delete_on_both_listed_devices()
    local = ConfigBucket(user_id="alice")
    local.upsert("hotkeys", "hk1", {"combo": "ctrl+a", "last_modified": _T0 + 5},
                 versioned=False)
    merged, conflicts = _client("tablet").sync(local, now=_T0 + _DAY)
    assert merged.values("hotkeys") == {} and server.bucket().values("hotkeys") == {}
    assert [(record.entry_id, record.unresolved) for record in conflicts] == [("hk1", False)]


def test_the_tombstone_goes_once_it_is_acknowledged_and_the_hold_has_passed(server):
    _delete_on_both_listed_devices()
    assert server.bucket().get_entry("hotkeys", "hk1").deleted, "held, though both acknowledged"
    # Still inside the hold: a later commit keeps it.
    _push("laptop", [SyncEntry.create("hk2", {"combo": "b"}, "laptop")],
          now=_T0 + TOMBSTONE_HOLD_S - 60)
    assert server.bucket().get_entry("hotkeys", "hk1") is not None
    # Past it: the next commit drops it, so the bucket does not grow for ever.
    _push("laptop", [SyncEntry.create("hk3", {"combo": "c"}, "laptop")],
          now=_T0 + TOMBSTONE_HOLD_S + 60)
    assert server.bucket().get_entry("hotkeys", "hk1") is None
    assert sorted(server.bucket().values("hotkeys")) == ["hk2", "hk3"]


def test_a_held_tombstone_does_not_make_acknowledged_devices_commit_again(server):
    _delete_on_both_listed_devices()
    revision = server.revision
    for device in ("laptop", "desktop", "laptop"):
        assert _push(device, now=_T0 + _DAY).pushed is False
    assert server.revision == revision


def test_no_clock_drops_a_tombstone_a_listed_device_has_not_acknowledged(server):
    created = SyncEntry.create("hk1", {"combo": "ctrl+a"}, "laptop")
    _push("laptop", [created], now=_T0)
    _push("desktop", now=_T0)
    _push("laptop", [created.removed("laptop")], now=_T0)
    # The desktop has not acknowledged; the laptop's clock jumps ten years.
    _push("laptop", [SyncEntry.create("hk2", {"combo": "b"}, "laptop")], now=_T0 + 3650 * _DAY)
    assert server.bucket().get_entry("hotkeys", "hk1").deleted
    # ... and a clock far behind cannot shorten the wait for the desktop either.
    _push("laptop", [SyncEntry.create("hk3", {"combo": "c"}, "laptop")], now=1.0)
    assert server.bucket().get_entry("hotkeys", "hk1").deleted


def test_a_hold_of_zero_is_the_earlier_rule(server):
    _delete_on_both_listed_devices(tombstone_hold_s=0)
    assert server.bucket().get_entry("hotkeys", "hk1") is None
    # ... and that is the case the hold exists for: the entry simply returns.
    _push("tablet", [SyncEntry.create("hk1", {"combo": "ctrl+a"}, "tablet")],
          now=_T0 + _DAY, tombstone_hold_s=0)
    assert server.bucket().values("hotkeys") == {"hk1": {"combo": "ctrl+a"}}


def test_a_tombstone_stamped_by_an_older_client_is_collected_on_acknowledgement():
    """No ``deleted_at``: nothing to measure the hold from, so nothing is held."""
    base = SyncEntry.create("hk1", {"combo": "a"}, "laptop")
    body = {**base.removed("laptop").to_dict(), "deleted_revision": 3}
    assert "deleted_at" not in body
    old = SyncEntry.from_dict("hk1", body)
    assert old.deleted_at == pytest.approx(0.0)
    peers = [PeerState("laptop", acked_revision=3), PeerState("desktop", acked_revision=4)]
    assert collect_tombstones({"hk1": old}, peers, now=_T0) == {}


def test_collect_tombstones_without_a_time_goes_by_acknowledgement_alone():
    base = SyncEntry.create("hk1", {"combo": "a"}, "laptop")
    stamped = SyncEntry.from_dict("hk1", {
        **base.removed("laptop").to_dict(), "deleted_revision": 3, "deleted_at": _T0})
    peers = [PeerState("laptop", acked_revision=3)]
    assert collect_tombstones({"hk1": stamped}, peers) == {}
    assert collect_tombstones({"hk1": stamped}, peers, now=_T0 + 60) == {"hk1": stamped}
    assert collect_tombstones({"hk1": stamped}, peers, now=_T0 + 60, hold_s=0) == {}
    assert collect_tombstones({"hk1": stamped}, peers, now=_T0 + TOMBSTONE_HOLD_S) == {}
    behind = [PeerState("laptop", acked_revision=2)]
    assert collect_tombstones({"hk1": stamped}, behind, now=_T0 + 10 * TOMBSTONE_HOLD_S) == {
        "hk1": stamped}


def test_the_stamp_is_written_once_and_survives_the_bucket_shape():
    bucket = ConfigBucket(user_id="alice")
    base = SyncEntry.create("hk1", {"combo": "a"}, "laptop")
    bucket.put_entry("hotkeys", base.removed("laptop"))
    settle(bucket, "laptop", 5, _T0, None)
    stored = bucket.sections["hotkeys"]["hk1"]
    assert stored["deleted_revision"] == 5 and stored["deleted_at"] == pytest.approx(_T0)
    again = ConfigBucket.from_dict(bucket.to_dict())
    settle(again, "desktop", 6, _T0 + _DAY, None)
    kept = again.get_entry("hotkeys", "hk1")
    assert kept.deleted_revision == 5 and kept.deleted_at == pytest.approx(_T0)
    # A live entry carries neither field.
    assert "deleted_at" not in base.to_dict() and "deleted_revision" not in base.to_dict()
