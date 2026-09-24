"""Deletions survive a config sync.

``ConfigBucket.remove()`` dropped the entry from the local dict, and the merge
takes every entry only the remote side has -- so the next ``sync()`` fetched
the deleted entry straight back from the server. A removed entry now stays as
a tombstone that wins or loses the merge by its timestamp like any value.
"""
from unittest.mock import patch

import pytest

from je_auto_control.utils.config_sync import (
    ConfigBucket, ConfigSyncClient, ConfigSyncError, merge_buckets,
)
from je_auto_control.utils.config_sync.client import is_tombstone


class _Server:
    """A bucket store answering GET / PUT the way the sync endpoint does."""

    def __init__(self) -> None:
        self.body = None

    def request(self, method, body=None):
        if method == "PUT":
            self.body = body
            return {}
        return self.body


def _sync(bucket, server):
    client = ConfigSyncClient("https://sync.invalid", user_id=bucket.user_id)
    with patch.object(ConfigSyncClient, "_request",
                      new=lambda _client, method, body=None: server.request(method, body)):
        merged, _conflicts = client.sync(bucket)
    return merged


def _entry(bucket, entry_id="hk1", stamp=100.0):
    bucket.upsert("hotkeys", entry_id, {"combo": "ctrl+a", "last_modified": stamp})
    return bucket


def test_a_removed_entry_stays_removed_after_sync():
    server = _Server()
    local = _sync(_entry(ConfigBucket(user_id="alice")), server)
    assert local.remove("hotkeys", "hk1") is True
    merged = _sync(local, server)
    assert merged.entries("hotkeys") == {}
    assert is_tombstone(server.body["sections"]["hotkeys"]["hk1"])


def test_a_deletion_on_one_machine_reaches_the_other():
    server = _Server()
    laptop = _sync(_entry(ConfigBucket(user_id="alice")), server)
    desktop = _sync(ConfigBucket(user_id="alice"), server)
    assert "hk1" in desktop.entries("hotkeys")
    laptop.remove("hotkeys", "hk1")
    _sync(laptop, server)
    assert _sync(desktop, server).entries("hotkeys") == {}


def test_an_edit_newer_than_the_deletion_brings_the_entry_back():
    local = _entry(ConfigBucket(user_id="u"))
    local.remove("hotkeys", "hk1")
    deleted_at = local.sections["hotkeys"]["hk1"]["last_modified"]
    remote = ConfigBucket(user_id="u")
    remote.upsert("hotkeys", "hk1", {"combo": "ctrl+z", "last_modified": deleted_at + 5})
    merged, _ = merge_buckets(local, remote)
    assert merged.entries("hotkeys")["hk1"]["combo"] == "ctrl+z"


def test_a_deletion_is_never_stamped_before_the_value_it_removes():
    future = 32503680000.0     # a clock far ahead wrote the entry
    local = _entry(ConfigBucket(user_id="u"), stamp=future)
    local.remove("hotkeys", "hk1")
    remote = _entry(ConfigBucket(user_id="u"), stamp=future)
    merged, _ = merge_buckets(local, remote, now=future)
    assert merged.entries("hotkeys") == {}


def test_remove_reports_only_live_entries():
    bucket = _entry(ConfigBucket(user_id="u"))
    assert bucket.remove("hotkeys", "missing") is False
    assert bucket.remove("hotkeys", "hk1") is True
    assert bucket.remove("hotkeys", "hk1") is False


def test_old_tombstones_are_purged_at_merge():
    local = ConfigBucket(user_id="u")
    local.sections["hotkeys"] = {"old": {"deleted": True, "last_modified": 100.0},
                                 "new": {"deleted": True, "last_modified": 950.0}}
    merged, _ = merge_buckets(local, ConfigBucket(user_id="u"), now=1000.0,
                              tombstone_retention_s=100.0)
    assert set(merged.sections["hotkeys"]) == {"new"}


def test_upsert_over_a_tombstone_revives_the_entry():
    bucket = _entry(ConfigBucket(user_id="u"))
    bucket.remove("hotkeys", "hk1")
    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+q"})
    assert bucket.entries("hotkeys")["hk1"]["combo"] == "ctrl+q"


def test_a_non_boolean_deleted_flag_is_rejected():
    body = {"user_id": "u", "sections": {"hotkeys": {
        "hk1": {"deleted": "yes", "last_modified": 1.0}}}}
    with pytest.raises(ConfigSyncError, match="deleted"):
        ConfigBucket.from_dict(body)
