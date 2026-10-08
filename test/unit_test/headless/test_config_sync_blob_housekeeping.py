"""An upload that is too large says so, and blobs nobody refers to can be collected.

Three gaps around the sync server's ``/blobs``:

* The server refuses an oversized ``PUT`` from its declared length and closes.
  A client still sending the body could see the connection reset first (it did
  on the Windows CI runner), so the per-file reason read as a connection error.
  ``HttpAssetTransport`` now reads the limit from the listing and refuses
  locally.
* Nothing deleted a blob, ever: every script removed or replaced kept counting
  against the account's quota.
* The quota was one process's lock; two server processes sharing a folder
  could each admit a blob the other had not counted.
"""
import hashlib
import json
import os
import threading
import time
from unittest.mock import patch

import pytest

import je_auto_control as ac
from je_auto_control.utils.config_sync import (
    AssetSyncError, BlobStore, ConfigBucket, ConfigSyncClient, ConfigSyncError,
    HttpAssetTransport, SyncEntry, SyncOperation, SyncOutbox, collect_unreferenced_blobs,
    config_sync_collect_blobs, referenced_blob_digests,
)
from je_auto_control.utils.config_sync.blobs import BlobQuotaError, BlobStoreBusyError

_PERFORM = "je_auto_control.utils.http_client.http_client.perform_call"
_DAY = 24 * 3600.0


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _reply(status, body=None):
    return {"status": status, "content": b"", "text": "" if body is None else json.dumps(body)}


def _transport():
    return HttpAssetTransport("https://sync.invalid/", user_id="alice", secret="s3cret")


class _Wire:
    """A scripted ``perform_call``: what the listing says, and what a PUT does."""

    def __init__(self, listing=None, put=None):
        self.listing = listing
        self.put = put if put is not None else _reply(201)
        self.calls = []
        self.deleted = []

    def __call__(self, call):
        method, url = call["method"], call["url"]
        self.calls.append((method, url.rsplit("/", 1)[-1]))
        if url.endswith("/blobs/alice"):
            return self._listing()
        if method == "PUT":
            if isinstance(self.put, BaseException):
                raise self.put
            return self.put
        if method == "DELETE":
            self.deleted.append(url.rsplit("/", 1)[-1])
            return _reply(200, {"deleted": True})
        return _reply(404)

    def _listing(self):
        listing = self.listing.pop(0) if isinstance(self.listing, list) else self.listing
        if isinstance(listing, BaseException):
            raise listing
        return _reply(404) if listing is None else _reply(200, listing)

    def methods(self):
        return [method for method, _name in self.calls]


# --- an upload over the server's limit ---------------------------------------------

def test_a_file_over_the_limit_is_refused_without_being_sent():
    wire = _Wire(listing={"max_blob_bytes": 10, "blobs": []})
    data = b"x" * 11
    with patch(_PERFORM, new=wire):
        with pytest.raises(AssetSyncError, match="larger") as refused:
            _transport().store(_sha(data), data)
    assert "11 bytes; the limit is 10" in str(refused.value)
    assert wire.methods() == ["GET"], "the body never left this machine"


def test_the_limit_is_asked_for_once():
    wire = _Wire(listing={"max_blob_bytes": 10, "blobs": []})
    with patch(_PERFORM, new=wire):
        transport = _transport()
        for data in (b"a", b"b", b"c"):
            transport.store(_sha(data), data)
        assert transport.max_blob_bytes() == 10
    assert wire.methods() == ["GET", "PUT", "PUT", "PUT"]


def test_a_file_at_the_limit_is_sent():
    wire = _Wire(listing={"max_blob_bytes": 10, "blobs": []})
    with patch(_PERFORM, new=wire):
        _transport().store(_sha(b"x" * 10), b"x" * 10)
    assert wire.methods() == ["GET", "PUT"]


@pytest.mark.parametrize("listing", [
    None,                                   # a server that does not serve the listing
    {"used": 0, "blobs": []},               # ... or one that does not say its limit
    {"max_blob_bytes": "big"}, {"max_blob_bytes": True}, {"max_blob_bytes": 0},
    OSError("unreachable"),
])
def test_a_server_that_does_not_say_its_limit_is_simply_sent_the_file(listing):
    wire = _Wire(listing=listing, put=_reply(413))
    with patch(_PERFORM, new=wire):
        transport = _transport()
        assert transport.max_blob_bytes() is None
        with pytest.raises(AssetSyncError, match="larger"):
            transport.store(_sha(b"x" * 11), b"x" * 11)     # the server's own 413
    assert "PUT" in wire.methods()


def test_a_reset_during_an_oversized_upload_is_reported_as_too_large():
    """The limit was not known beforehand; the reset alone would say nothing."""
    wire = _Wire(listing=[OSError("timed out"), {"max_blob_bytes": 10, "blobs": []}],
                 put=ConnectionResetError(10054, "connection reset by peer"))
    data = b"x" * 11
    with patch(_PERFORM, new=wire):
        with pytest.raises(AssetSyncError, match="larger") as refused:
            _transport().store(_sha(data), data)
    assert "the limit is 10" in str(refused.value)
    assert isinstance(refused.value.__cause__, AssetSyncError), "the reset is kept as the cause"
    assert wire.methods() == ["GET", "PUT", "GET"]


def test_a_reset_during_an_upload_that_fits_is_still_a_connection_error():
    wire = _Wire(listing={"max_blob_bytes": 10, "blobs": []},
                 put=ConnectionResetError(10054, "connection reset by peer"))
    with patch(_PERFORM, new=wire):
        with pytest.raises(AssetSyncError, match="connection reset") as failed:
            _transport().store(_sha(b"x"), b"x")
    assert "larger" not in str(failed.value)


def test_a_limit_lowered_since_it_was_read_is_noticed_when_the_upload_is_cut_off():
    wire = _Wire(listing=[{"max_blob_bytes": 100}, {"max_blob_bytes": 10}],
                 put=ConnectionResetError(10054, "reset"))
    with patch(_PERFORM, new=wire):
        with pytest.raises(AssetSyncError, match="the limit is 10"):
            _transport().store(_sha(b"x" * 50), b"x" * 50)


def test_a_bad_digest_is_refused_before_anything_is_asked():
    wire = _Wire(listing={"max_blob_bytes": 10})
    with patch(_PERFORM, new=wire):
        with pytest.raises(AssetSyncError, match="SHA-256"):
            _transport().store("not-a-digest", b"x")
    assert wire.calls == []


def test_the_listing_and_delete_calls():
    listing = {"used": 3, "quota": 100, "count": 1, "max_blob_bytes": 10,
               "blobs": [{"sha256": _sha(b"abc"), "size": 3, "age_s": 5.0}]}
    wire = _Wire(listing=listing)
    with patch(_PERFORM, new=wire):
        transport = _transport()
        assert transport.usage() == listing
        assert transport.delete(_sha(b"abc")) is True
    assert wire.deleted == [_sha(b"abc")]
    with patch(_PERFORM, return_value=_reply(404)):
        assert _transport().delete(_sha(b"abc")) is False
        with pytest.raises(AssetSyncError, match="does not serve"):
            _transport().usage()
    with patch(_PERFORM, return_value={"status": 200, "text": "<html>"}):
        with pytest.raises(AssetSyncError, match="not JSON"):
            _transport().usage()
    with patch(_PERFORM, return_value=_reply(401)):
        with pytest.raises(AssetSyncError, match="secret"):
            _transport().delete(_sha(b"abc"))


# --- collecting what nothing refers to ------------------------------------------------

def _row(data, age_s=None):
    row = {"sha256": _sha(data), "size": len(data)}
    if age_s is not None:
        row["age_s"] = age_s
    return row


def test_only_old_unreferenced_blobs_are_deleted():
    wire = _Wire(listing={"blobs": [
        _row(b"in use", 9 * _DAY), _row(b"orphan", 2 * _DAY), _row(b"just uploaded", 60.0),
        {"sha256": "not a digest", "size": 1, "age_s": 9 * _DAY}, "junk"]})
    with patch(_PERFORM, new=wire):
        result = collect_unreferenced_blobs(_transport(), [_sha(b"in use").upper()])
    assert result == {"deleted": [_sha(b"orphan")], "freed": 6, "kept": 1,
                      "recent": [_sha(b"just uploaded")], "failed": {}, "dry_run": False}
    assert wire.deleted == [_sha(b"orphan")]


def test_a_dry_run_deletes_nothing_and_says_what_would_go():
    wire = _Wire(listing={"blobs": [_row(b"orphan", 2 * _DAY)]})
    with patch(_PERFORM, new=wire):
        result = collect_unreferenced_blobs(_transport(), [], dry_run=True)
    assert result["deleted"] == [_sha(b"orphan")] and result["dry_run"] is True
    assert wire.deleted == [] and "DELETE" not in wire.methods()


def test_a_server_that_reports_no_ages_has_nothing_collected_unless_asked():
    listing = {"blobs": [_row(b"orphan")]}
    with patch(_PERFORM, new=_Wire(listing=listing)) as wire:
        assert collect_unreferenced_blobs(_transport(), [])["recent"] == [_sha(b"orphan")]
        assert wire.deleted == []
        assert collect_unreferenced_blobs(
            _transport(), [], min_age_s=0)["deleted"] == [_sha(b"orphan")]


def test_one_blob_that_cannot_be_deleted_does_not_stop_the_others():
    listing = {"blobs": [_row(b"one", _DAY * 2), _row(b"two", _DAY * 2)]}

    def perform(call):
        if call["method"] == "GET":
            return _reply(200, listing)
        return _reply(503) if call["url"].endswith(_sha(b"one")) else _reply(200, {"deleted": True})

    with patch(_PERFORM, new=perform):
        result = collect_unreferenced_blobs(_transport(), [])
    assert result["deleted"] == [_sha(b"two")] and list(result["failed"]) == [_sha(b"one")]


@pytest.mark.parametrize("bad", [-1, "soon", True, float("nan"), None])
def test_a_grace_period_that_is_not_one_is_refused(bad):
    with patch(_PERFORM, new=_Wire(listing={"blobs": []})) as wire:
        with pytest.raises(AssetSyncError, match="min_age_s"):
            collect_unreferenced_blobs(_transport(), [], min_age_s=bad)
    assert wire.calls == []


def test_a_reference_that_is_not_a_digest_is_refused_before_anything_is_deleted():
    with patch(_PERFORM, new=_Wire(listing={"blobs": [_row(b"x", _DAY * 2)]})) as wire:
        with pytest.raises(AssetSyncError):
            collect_unreferenced_blobs(_transport(), ["nope"])
    assert wire.calls == []


def test_referenced_digests_cover_every_section_conflict_candidates_and_the_queue():
    large = {"sha256": _sha(b"large script"), "size": 99_999}
    bucket = ConfigBucket(user_id="alice")
    bucket.put_entry("scripts", SyncEntry.create("a.json", large, "laptop"))
    base = SyncEntry.create("b.json", {"sha256": _sha(b"v0"), "size": 1}, "laptop")
    left = base.edited({"sha256": _sha(b"left"), "size": 1}, "laptop")
    right = base.edited({"sha256": _sha(b"right"), "size": 1}, "desktop")
    bucket.put_entry("scripts", ac.merge_entries(left, right).entry)
    gone = SyncEntry.create("c.json", {"sha256": _sha(b"gone"), "size": 1}, "laptop")
    bucket.put_entry("scripts", gone.removed("laptop"))
    bucket.put_entry("custom", SyncEntry.create("k", {"nested": [{"sha256": _sha(b"deep")}]},
                                                "laptop"))
    queued = SyncOperation("scripts", SyncEntry.create(
        "d.json", {"sha256": _sha(b"queued"), "size": 1}, "laptop"))
    assert referenced_blob_digests(bucket, None, operations=[queued]) == {
        _sha(b"large script"), _sha(b"left"), _sha(b"right"), _sha(b"deep"), _sha(b"queued")}
    assert referenced_blob_digests() == set()


def _server_bucket(*contents):
    bucket = ConfigBucket(user_id="alice", revision=3)
    for index, data in enumerate(contents):
        bucket.put_entry("scripts", SyncEntry.create(
            f"s{index}.json", {"sha256": _sha(data), "size": len(data)}, "desktop"))
    return bucket


def test_config_sync_collect_blobs_keeps_what_the_bucket_this_machine_and_keep_name(tmp_path):
    outbox_path = tmp_path / "outbox.sqlite3"
    outbox = SyncOutbox(outbox_path, account="alice", endpoint="https://sync.invalid")
    outbox.save_baseline(_server_bucket(b"merged here"))
    outbox.enqueue(SyncOperation("scripts", SyncEntry.create(
        "new.json", {"sha256": _sha(b"not sent yet"), "size": 1}, "laptop")))
    names = (b"on the server", b"merged here", b"not sent yet", b"published by hand", b"orphan")
    wire = _Wire(listing={"blobs": [_row(data, 3 * _DAY) for data in names]})
    with patch(_PERFORM, new=wire), patch.object(
            ConfigSyncClient, "fetch", return_value=_server_bucket(b"on the server")):
        result = config_sync_collect_blobs(
            "https://sync.invalid/", "alice", keep=_sha(b"published by hand"),
            outbox_path=str(outbox_path), secret="s3cret")
    assert result["deleted"] == [_sha(b"orphan")] and result["kept"] == 4
    assert result["referenced"] == 4 and wire.deleted == [_sha(b"orphan")]


def test_collecting_for_an_account_that_never_synced_here_creates_no_outbox(tmp_path):
    outbox_path = tmp_path / "outbox.sqlite3"
    wire = _Wire(listing={"blobs": [_row(b"orphan", 3 * _DAY)]})
    with patch(_PERFORM, new=wire), patch.object(ConfigSyncClient, "fetch", return_value=None):
        result = config_sync_collect_blobs("https://sync.invalid", "alice", dry_run=True,
                                           outbox_path=str(outbox_path))
    assert result["deleted"] == [_sha(b"orphan")] and result["dry_run"] is True
    assert not outbox_path.exists() and wire.deleted == []


def test_an_unreachable_server_deletes_nothing(tmp_path):
    wire = _Wire(listing={"blobs": [_row(b"orphan", 3 * _DAY)]})
    with patch(_PERFORM, new=wire), patch.object(
            ConfigSyncClient, "fetch", side_effect=ConfigSyncError("offline")):
        with pytest.raises(ConfigSyncError, match="offline"):
            config_sync_collect_blobs("https://sync.invalid", "alice",
                                      outbox_path=str(tmp_path / "o.sqlite3"))
    assert wire.calls == []
    with pytest.raises(ConfigSyncError, match="unknown config sync option"):
        config_sync_collect_blobs("https://sync.invalid", "alice", nonsense=1)


# --- the store: ages, and one quota for every process ---------------------------------

def test_the_listing_reports_each_blobs_age_and_storing_again_renews_it(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    data = b"template"
    store.put("alice", _sha(data), data)
    blob = next((tmp_path / "blobs").rglob(_sha(data)))
    then = time.time() - 5 * _DAY
    os.utime(blob, (then, then))
    (listed,) = store.usage("alice")["blobs"]
    assert listed["age_s"] == pytest.approx(5 * _DAY, abs=600)
    assert store.put("alice", _sha(data), data) is False, "held already: nothing written"
    assert store.usage("alice")["blobs"][0]["age_s"] < 600, "but it counts as stored now"


def test_two_stores_on_one_folder_share_the_quota(tmp_path):
    """Two server processes, as two stores: each has its own in-process lock."""
    stores = [BlobStore(tmp_path / "blobs", max_blob_bytes=10, quota_bytes=30) for _ in range(2)]
    refused = []

    def fill(store, offset):
        for number in range(8):
            data = bytes([offset + number]) * 10
            try:
                store.put("alice", _sha(data), data)
            except BlobQuotaError:
                refused.append(number)

    threads = [threading.Thread(target=fill, args=(store, index * 100))
               for index, store in enumerate(stores)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads)
    usage = stores[0].usage("alice")
    assert usage["used"] == 30 and usage["count"] == 3 and len(refused) == 13
    assert not (tmp_path / "blobs" / "store.lock").exists(), "the lock is released"
    assert stores[1].usage("alice")["count"] == 3, "the lock file is not listed as a blob"


def test_a_store_locked_by_another_process_refuses_instead_of_overshooting(tmp_path, monkeypatch):
    from je_auto_control.utils.json_store import json_store
    monkeypatch.setattr(json_store, "_LOCK_WAIT_S", 0.2)
    store = BlobStore(tmp_path / "blobs")
    (tmp_path / "blobs").mkdir()
    (tmp_path / "blobs" / "store.lock").write_bytes(b"")     # held by "another process"
    with pytest.raises(BlobStoreBusyError, match="locked by another process"):
        store.put("alice", _sha(b"x"), b"x")
    assert store.usage("alice")["count"] == 0
    (tmp_path / "blobs" / "store.lock").unlink()
    assert store.put("alice", _sha(b"x"), b"x") is True


# --- the delivery surfaces ----------------------------------------------------------------

def test_the_command_the_tool_and_the_facade_reach_the_same_function():
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert ac.config_sync_collect_blobs is config_sync_collect_blobs
    assert ac.collect_unreferenced_blobs is collect_unreferenced_blobs
    assert ac.referenced_blob_digests is referenced_blob_digests
    for name in ("config_sync_collect_blobs", "collect_unreferenced_blobs",
                 "referenced_blob_digests"):
        assert name in ac.__all__
    assert executor.event_dict["AC_config_sync_collect_blobs"] is config_sync_collect_blobs
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    tool = tools["ac_config_sync_collect_blobs"]
    assert tool.handler is config_sync_collect_blobs
    assert {"keep", "min_age_s", "dry_run", "secret"} <= set(tool.input_schema["properties"])


def test_the_command_runs_from_an_action_list(tmp_path):
    wire = _Wire(listing={"blobs": [_row(b"orphan", 3 * _DAY)]})
    with patch(_PERFORM, new=wire), patch.object(ConfigSyncClient, "fetch", return_value=None):
        record = ac.execute_action([["AC_config_sync_collect_blobs", {
            "server_url": "https://sync.invalid", "user_id": "alice", "dry_run": True,
            "outbox_path": str(tmp_path / "o.sqlite3")}]])
    (result,) = record.values()
    assert result["deleted"] == [_sha(b"orphan")] and result["dry_run"] is True


# --- against the real server (needs the [signaling] extra; skipped without it) ------------

def test_the_server_listing_carries_the_limit_and_the_ages(tmp_path):
    pytest.importorskip("fastapi")
    testclient = pytest.importorskip("fastapi.testclient")
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    client = testclient.TestClient(create_app(
        shared_secret="s3cret", serve_web_viewer=False, max_blob_bytes=64,
        config_store_path=tmp_path / "buckets.sqlite3"))
    headers = {"X-Signaling-Secret": "s3cret"}
    data = b"template"
    assert client.put(f"/blobs/alice/{_sha(data)}", content=data,
                      headers=headers).status_code == 201
    listing = client.get("/blobs/alice", headers=headers).json()
    assert listing["max_blob_bytes"] == 64 and listing["count"] == 1
    (row,) = listing["blobs"]
    assert row["sha256"] == _sha(data) and row["size"] == len(data)
    assert isinstance(row["age_s"], float) and 0.0 <= row["age_s"] < 3600.0
