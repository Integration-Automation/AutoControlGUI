"""Phase 7.4: config sync client + merge tests."""
import json
from unittest.mock import patch

import pytest

from je_auto_control.utils.config_sync import (
    ConfigBucket, ConfigSyncClient, ConfigSyncError, merge_buckets,
)


# --- ConfigBucket ----------------------------------------------------

def test_upsert_stamps_last_modified():
    bucket = ConfigBucket(user_id="alice")
    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+a"})
    entry = bucket.sections["hotkeys"]["hk1"]
    assert "last_modified" in entry
    assert isinstance(entry["last_modified"], float)


def test_upsert_preserves_explicit_timestamp():
    bucket = ConfigBucket(user_id="alice")
    bucket.upsert("hotkeys", "hk1",
                  {"combo": "ctrl+a", "last_modified": 1700.0})
    assert bucket.sections["hotkeys"]["hk1"]["last_modified"] == pytest.approx(1700.0)


def test_remove_returns_false_when_absent():
    bucket = ConfigBucket(user_id="alice")
    assert bucket.remove("hotkeys", "hk-missing") is False
    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+a"})
    assert bucket.remove("hotkeys", "hk1") is True
    assert bucket.remove("hotkeys", "hk1") is False


def test_from_dict_round_trip():
    bucket = ConfigBucket(user_id="alice")
    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+a"})
    body = bucket.to_dict()
    parsed = ConfigBucket.from_dict(body)
    assert parsed.user_id == "alice"
    assert "hk1" in parsed.sections["hotkeys"]


def test_from_dict_rejects_invalid_input():
    with pytest.raises(ConfigSyncError):
        ConfigBucket.from_dict("not-a-mapping")  # type: ignore[arg-type]  # NOSONAR python:S5655  # reason: intentional bad-type negative test
    with pytest.raises(ConfigSyncError):
        ConfigBucket.from_dict({"sections": {}})  # missing user_id
    with pytest.raises(ConfigSyncError):
        ConfigBucket.from_dict({"user_id": "a", "sections": "bad"})


# --- merge_buckets ---------------------------------------------------

def test_merge_takes_newer_entry_per_section():
    local = ConfigBucket(user_id="u")
    local.upsert("hotkeys", "hk1",
                 {"combo": "ctrl+a", "last_modified": 100.0})
    remote = ConfigBucket(user_id="u")
    remote.upsert("hotkeys", "hk1",
                  {"combo": "ctrl+b", "last_modified": 200.0})
    merged, conflicts = merge_buckets(local, remote)
    assert merged.sections["hotkeys"]["hk1"]["combo"] == "ctrl+b"
    assert len(conflicts) == 1
    assert conflicts[0].dropped["combo"] == "ctrl+a"


def test_merge_keeps_local_when_local_is_newer():
    local = ConfigBucket(user_id="u")
    local.upsert("hotkeys", "hk1",
                 {"combo": "ctrl+a", "last_modified": 300.0})
    remote = ConfigBucket(user_id="u")
    remote.upsert("hotkeys", "hk1",
                  {"combo": "ctrl+b", "last_modified": 100.0})
    merged, conflicts = merge_buckets(local, remote)
    assert merged.sections["hotkeys"]["hk1"]["combo"] == "ctrl+a"
    assert len(conflicts) == 1


def test_merge_handles_disjoint_entries():
    local = ConfigBucket(user_id="u")
    local.upsert("hotkeys", "hk1", {"combo": "ctrl+a"})
    remote = ConfigBucket(user_id="u")
    remote.upsert("triggers", "tr1", {"kind": "webhook"})
    merged, conflicts = merge_buckets(local, remote)
    assert "hk1" in merged.sections["hotkeys"]
    assert "tr1" in merged.sections["triggers"]
    assert conflicts == []


def test_merge_tie_breaks_in_favour_of_local():
    """Identical timestamps shouldn't ping-pong — local wins by convention."""
    local = ConfigBucket(user_id="u")
    local.upsert("hotkeys", "hk1",
                 {"combo": "ctrl+local", "last_modified": 100.0})
    remote = ConfigBucket(user_id="u")
    remote.upsert("hotkeys", "hk1",
                  {"combo": "ctrl+remote", "last_modified": 100.0})
    merged, conflicts = merge_buckets(local, remote)
    assert merged.sections["hotkeys"]["hk1"]["combo"] == "ctrl+local"
    assert conflicts == []  # tie not counted as a conflict


def test_merge_rejects_user_id_mismatch():
    a = ConfigBucket(user_id="alice")
    b = ConfigBucket(user_id="bob")
    with pytest.raises(ConfigSyncError, match="user_id mismatch"):
        merge_buckets(a, b)


def test_merge_bumps_revision():
    local = ConfigBucket(user_id="u", revision=4)
    remote = ConfigBucket(user_id="u", revision=7)
    merged, _ = merge_buckets(local, remote)
    assert merged.revision == 8


# --- ConfigSyncClient HTTP layer ----------------------------------

def test_client_requires_server_url_and_user_id():
    with pytest.raises(ConfigSyncError):
        ConfigSyncClient("", user_id="u")
    with pytest.raises(ConfigSyncError):
        ConfigSyncClient("https://signaling.example", user_id="")


def test_push_rejects_user_id_mismatch():
    client = ConfigSyncClient(
        "https://signaling.example", user_id="alice",
    )
    bucket = ConfigBucket(user_id="bob")
    with pytest.raises(ConfigSyncError, match="user_id"):
        client.push(bucket)


def _patch_request(reply, *, calls=None):
    """Patch ConfigSyncClient._request with a stub that records calls."""

    def stub(self, method, body=None):
        if calls is not None:
            calls.append((method, body))
        return reply

    return patch.object(ConfigSyncClient, "_request", new=stub)


def test_fetch_returns_none_when_server_404():
    client = ConfigSyncClient("https://x", user_id="alice")
    with _patch_request(None):
        assert client.fetch() is None


def test_fetch_returns_bucket_from_server_body():
    client = ConfigSyncClient("https://x", user_id="alice")
    reply = {
        "user_id": "alice", "revision": 5,
        "sections": {"hotkeys": {
            "hk1": {"combo": "ctrl+a", "last_modified": 100.0},
        }},
    }
    with _patch_request(reply):
        bucket = client.fetch()
    assert bucket is not None
    assert bucket.revision == 5
    assert "hk1" in bucket.sections["hotkeys"]


def test_push_round_trip_uses_put():
    client = ConfigSyncClient("https://x", user_id="alice")
    calls: list = []
    local = ConfigBucket(user_id="alice")
    local.upsert("hotkeys", "hk1", {"combo": "ctrl+a"})
    with _patch_request({}, calls=calls):
        client.push(local)
    assert len(calls) == 1
    method, body = calls[0]
    assert method == "PUT"
    assert body["user_id"] == "alice"
    assert "hk1" in body["sections"]["hotkeys"]


def test_sync_merges_remote_into_local_and_pushes_result():
    """End-to-end: pull → merge → push, all stubbed."""
    client = ConfigSyncClient("https://x", user_id="alice")
    local = ConfigBucket(user_id="alice")
    local.upsert("hotkeys", "hk1",
                 {"combo": "ctrl+a", "last_modified": 100.0})
    remote_body = {
        "user_id": "alice", "revision": 0,
        "sections": {"hotkeys": {
            "hk1": {"combo": "ctrl+b", "last_modified": 200.0},
        }},
    }

    fetched: list = []

    def fake_request(self, method, body=None):
        fetched.append(method)
        return remote_body if method == "GET" else {}

    with patch.object(ConfigSyncClient, "_request", new=fake_request):
        merged, conflicts = client.sync(local)
    # Verify the merge picked the newer remote entry.
    assert merged.sections["hotkeys"]["hk1"]["combo"] == "ctrl+b"
    assert len(conflicts) == 1
    assert fetched == ["GET", "PUT"]
