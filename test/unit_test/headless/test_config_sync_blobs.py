"""Assets can travel through the sync server itself, not only a shared folder.

``DirectoryAssetTransport`` needs a folder both machines can reach -- the one
thing two machines that only share a sync server do not have. The signaling
server now keeps content-addressed blobs per account at ``/blobs``, under the
rules ``/config`` already follows (the shared secret, account isolation, a
size cap checked before the body is read) plus a total quota per account, and
``HttpAssetTransport`` is the client side.
"""
import hashlib
import json
import socket
import threading
import time
from unittest.mock import patch

import pytest

from je_auto_control.utils.config_sync import (
    AssetManifest, AssetSyncError, BlobStore, ConfigSyncError, HttpAssetTransport,
    publish_assets, sync_assets,
)
from je_auto_control.utils.config_sync.blobs import (
    BlobCapacityError, BlobDigestError, BlobQuotaError, BlobStoreError, BlobTooLargeError,
)
from je_auto_control.utils.exception.exceptions import AutoControlException

_SECRET = {"X-Signaling-Secret": "s3cret"}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


# --- the store --------------------------------------------------------------------

def test_a_blob_round_trips_and_is_stored_once(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    data = b"template image bytes"
    assert store.put("alice", _sha(data), data) is True
    assert store.put("alice", _sha(data), data) is False, "already held: nothing written"
    assert store.get("alice", _sha(data)) == data and store.has("alice", _sha(data))
    usage = store.usage("alice")
    assert (usage["used"], usage["count"]) == (len(data), 1)
    assert usage["blobs"] == [{"sha256": _sha(data), "size": len(data)}]


def test_building_a_store_creates_nothing(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    assert store.get("alice", _sha(b"x")) is None and not store.has("alice", _sha(b"x"))
    assert store.usage("alice")["used"] == 0
    assert not (tmp_path / "blobs").exists()


def test_content_is_only_ever_stored_under_its_own_digest(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    with pytest.raises(BlobDigestError):
        store.put("alice", _sha(b"one thing"), b"another")
    for bad in ("", "abc", "g" * 64, "../" + "a" * 61, 7, None):
        with pytest.raises(BlobDigestError):
            store.put("alice", bad, b"x")
        with pytest.raises(BlobDigestError):
            store.get("alice", bad)
    assert not (tmp_path / "blobs").exists()


def test_accounts_cannot_read_each_other(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    data = b"alice's"
    store.put("alice", _sha(data), data)
    assert store.get("bob", _sha(data)) is None and not store.has("bob", _sha(data))
    # An account id is never a path: this one would climb out if it were.
    store.put("../../evil", _sha(data), data)
    assert all(tmp_path / "blobs" in path.parents for path in (tmp_path / "blobs").rglob("*"))
    assert not (tmp_path / "evil").exists()
    with pytest.raises(BlobStoreError):
        store.put("", _sha(data), data)


def test_the_per_blob_cap_and_the_account_quota(tmp_path):
    store = BlobStore(tmp_path / "blobs", max_blob_bytes=10, quota_bytes=25)
    with pytest.raises(BlobTooLargeError):
        store.put("alice", _sha(b"x" * 11), b"x" * 11)
    for fill in (b"a" * 10, b"b" * 10):
        store.put("alice", _sha(fill), fill)
    with pytest.raises(BlobQuotaError):
        store.put("alice", _sha(b"c" * 10), b"c" * 10)
    assert store.usage("alice")["used"] == 20, "the refused blob left nothing behind"
    # The quota is per account ...
    assert store.put("bob", _sha(b"c" * 10), b"c" * 10) is True
    # ... and deleting gives the room back.
    assert store.delete("alice", _sha(b"a" * 10)) is True
    assert store.delete("alice", _sha(b"a" * 10)) is False
    assert store.put("alice", _sha(b"c" * 10), b"c" * 10) is True


def test_the_number_of_accounts_is_bounded(tmp_path):
    store = BlobStore(tmp_path / "blobs", max_users=2)
    for user in ("a", "b"):
        store.put(user, _sha(b"x"), b"x")
    with pytest.raises(BlobCapacityError):
        store.put("c", _sha(b"x"), b"x")
    assert store.put("a", _sha(b"y"), b"y") is True, "an existing account is not shut out"


def test_the_errors_are_framework_errors():
    for error in (BlobCapacityError, BlobDigestError, BlobQuotaError, BlobTooLargeError):
        assert issubclass(error, BlobStoreError)
    assert issubclass(BlobStoreError, ConfigSyncError)
    assert issubclass(BlobStoreError, AutoControlException)


# --- the server -------------------------------------------------------------------

@pytest.fixture
def app_options(tmp_path):
    return {"shared_secret": "s3cret", "serve_web_viewer": False,
            "config_store_path": tmp_path / "buckets.sqlite3"}


def _test_client(**options):
    pytest.importorskip("fastapi")
    testclient = pytest.importorskip("fastapi.testclient")
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    return testclient.TestClient(create_app(**options))


def _put(client, user, data, digest=None, headers=_SECRET):
    return client.put(f"/blobs/{user}/{digest or _sha(data)}", content=data, headers=headers)


def test_put_get_head_and_delete(app_options):
    client = _test_client(**app_options)
    data = bytes(range(256)) * 4            # not text: it must come back byte for byte
    first = _put(client, "alice", data)
    assert first.status_code == 201 and first.json() == {
        "ok": True, "sha256": _sha(data), "size": len(data), "stored": True}
    again = _put(client, "alice", data)
    assert again.status_code == 200 and again.json()["stored"] is False
    got = client.get(f"/blobs/alice/{_sha(data)}", headers=_SECRET)
    assert got.status_code == 200 and got.content == data
    assert got.headers["content-type"] == "application/octet-stream"
    assert client.head(f"/blobs/alice/{_sha(data)}", headers=_SECRET).status_code == 200
    listing = client.get("/blobs/alice", headers=_SECRET).json()
    assert listing["used"] == len(data) and listing["count"] == 1
    assert client.delete(f"/blobs/alice/{_sha(data)}", headers=_SECRET).json() == {"deleted": True}
    assert client.get(f"/blobs/alice/{_sha(data)}", headers=_SECRET).status_code == 404
    assert client.head(f"/blobs/alice/{_sha(data)}", headers=_SECRET).status_code == 404


def test_the_blobs_live_beside_the_config_database_by_default(app_options, tmp_path):
    client = _test_client(**app_options)
    assert not (tmp_path / "buckets.sqlite3.blobs").exists(), "nothing until the first blob"
    _put(client, "alice", b"x")
    assert (tmp_path / "buckets.sqlite3.blobs").is_dir()
    other = tmp_path / "elsewhere"
    _put(_test_client(**app_options, blob_store_path=other), "alice", b"y")
    assert other.is_dir()


def test_blob_routes_need_the_secret(app_options):
    client = _test_client(**app_options)
    data = b"x"
    assert _put(client, "alice", data, headers={}).status_code == 401
    assert _put(client, "alice", data, headers={"X-Signaling-Secret": "wrong"}).status_code == 401
    _put(client, "alice", data)
    for method in (client.get, client.head, client.delete):
        assert method(f"/blobs/alice/{_sha(data)}").status_code == 401
    assert client.get("/blobs/alice").status_code == 401


def test_accounts_are_isolated_on_the_wire(app_options):
    client = _test_client(**app_options)
    data = b"alice's template"
    _put(client, "alice", data)
    assert client.get(f"/blobs/bob/{_sha(data)}", headers=_SECRET).status_code == 404
    assert client.get("/blobs/bob", headers=_SECRET).json()["count"] == 0
    assert client.delete(f"/blobs/bob/{_sha(data)}", headers=_SECRET).json() == {"deleted": False}
    assert client.get(f"/blobs/alice/{_sha(data)}", headers=_SECRET).content == data


def test_an_oversized_blob_is_refused_before_it_is_read(app_options):
    client = _test_client(**app_options, max_blob_bytes=64)
    big = b"x" * 65
    assert _put(client, "alice", big).status_code == 413
    assert client.put(f"/blobs/alice/{_sha(big)}", content=iter([big]),
                      headers=_SECRET).status_code == 411, "no Content-Length: not buffered"
    assert _put(client, "alice", b"x" * 64).status_code == 201


def test_the_quota_and_bad_digests_have_their_own_statuses(app_options):
    client = _test_client(**app_options, max_blob_bytes=10, blob_quota_bytes=15)
    assert _put(client, "alice", b"a" * 10).status_code == 201
    over = _put(client, "alice", b"b" * 10)
    assert over.status_code == 507 and "quota" in over.json()["detail"]
    assert _put(client, "alice", b"abc", digest=_sha(b"other")).status_code == 400
    assert _put(client, "alice", b"abc", digest="not-a-digest").status_code == 400
    assert client.get("/blobs/alice/not-a-digest", headers=_SECRET).status_code == 400
    assert _put(client, "a/b", b"abc").status_code in (400, 404)
    assert client.get("/blobs/alice", headers=_SECRET).json()["used"] == 10


def test_config_routes_are_untouched_and_the_wire_version_is_still_two(app_options):
    pytest.importorskip("fastapi")
    from je_auto_control.utils.config_sync import WIRE_VERSION
    from je_auto_control.utils.remote_desktop.signaling_server import CONFIG_WIRE_VERSION
    assert WIRE_VERSION == CONFIG_WIRE_VERSION == 2
    client = _test_client(**app_options)
    body = {"version": 2, "base_revision": 0, "operation_id": "op-1",
            "bucket": {"user_id": "alice", "sections": {}}}
    assert client.put("/config/alice", json=body, headers=_SECRET).json()["revision"] == 1
    # The config cap is still the config cap, whatever the blob cap is.
    huge = json.dumps({**body, "operation_id": "op-2", "pad": "x" * (1024 * 1024)})
    assert client.put("/config/alice", content=huge, headers={
        **_SECRET, "Content-Type": "application/json"}).status_code == 413


# --- the transport ----------------------------------------------------------------

def _reply(status, content=b"", text=""):
    return {"status": status, "content": content, "text": text}


def _transport():
    return HttpAssetTransport("https://sync.invalid/", user_id="alice", secret="s3cret")


def test_the_transport_speaks_the_blob_routes():
    calls = []
    data = b"\x00\xff binary"

    def perform(call):
        calls.append(call)
        return {"PUT": _reply(201), "GET": _reply(200, data), "HEAD": _reply(200)}[call["method"]]

    with patch("je_auto_control.utils.http_client.http_client.perform_call", new=perform):
        transport = _transport()
        transport.store(_sha(data), data)
        assert transport.fetch(_sha(data)) == data
        assert transport.has(_sha(data)) is True
    put, get, head = calls
    assert put["url"] == f"https://sync.invalid/blobs/alice/{_sha(data)}" == get["url"]
    assert put["body"] == data and put["headers"]["X-Signaling-Secret"] == "s3cret"
    assert put["headers"]["Content-Type"] == "application/octet-stream"
    assert all(call["follow_redirects"] is False for call in calls)
    assert get["want_bytes"] is True and head["method"] == "HEAD"


@pytest.mark.parametrize("status, words", [
    (413, "larger"), (507, "quota"), (401, "secret"), (404, "does not serve"),
    (405, "does not serve"), (500, "HTTP 500")])
def test_a_refused_store_says_why(status, words):
    with patch("je_auto_control.utils.http_client.http_client.perform_call",
               return_value=_reply(status)):
        with pytest.raises(AssetSyncError, match=words):
            _transport().store(_sha(b"x"), b"x")


def test_fetch_and_has_report_absence_and_trouble_differently():
    with patch("je_auto_control.utils.http_client.http_client.perform_call",
               return_value=_reply(404)):
        assert _transport().has(_sha(b"x")) is False
        with pytest.raises(AssetSyncError, match="not on the server"):
            _transport().fetch(_sha(b"x"))
    with patch("je_auto_control.utils.http_client.http_client.perform_call",
               side_effect=OSError("connection refused")):
        with pytest.raises(AssetSyncError, match="connection refused"):
            _transport().has(_sha(b"x"))
    with pytest.raises(AssetSyncError):
        _transport().fetch("not-a-digest")
    with pytest.raises(ConfigSyncError):
        HttpAssetTransport("", user_id="alice")


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def live_server(tmp_path):
    pytest.importorskip("fastapi")
    uvicorn = pytest.importorskip("uvicorn")
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    port = _free_port()
    app = create_app(shared_secret="s3cret", serve_web_viewer=False,
                     config_store_path=tmp_path / "buckets.sqlite3", max_blob_bytes=200_000)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=15)


def test_assets_travel_between_two_folders_through_a_real_server(live_server, tmp_path):
    source, target = tmp_path / "laptop", tmp_path / "desktop"
    (source / "img").mkdir(parents=True)
    picture = bytes(range(256)) * 300
    (source / "img" / "logo.png").write_bytes(picture)
    (source / "notes.txt").write_bytes(b"small")
    transport = HttpAssetTransport(live_server, user_id="alice", secret="s3cret")
    manifest = AssetManifest.from_directory(source)

    published = publish_assets(manifest, transport)
    assert sorted(published.transferred) == ["img/logo.png", "notes.txt"] and not published.failed
    assert publish_assets(manifest, transport).unchanged == ["img/logo.png", "notes.txt"]

    received = sync_assets(AssetManifest(root=target, assets=manifest.assets), transport)
    assert not received.failed
    assert (target / "img" / "logo.png").read_bytes() == picture

    # Another account, or a wrong secret, gets nothing.
    stranger = HttpAssetTransport(live_server, user_id="bob", secret="s3cret")
    assert stranger.has(_sha(picture)) is False
    with pytest.raises(AssetSyncError, match="secret"):
        HttpAssetTransport(live_server, user_id="alice", secret="nope").has(_sha(picture))
    # Larger than the server takes: reported per file, the rest still goes.
    (source / "huge.bin").write_bytes(b"z" * 200_001)
    again = publish_assets(AssetManifest.from_directory(source), transport)
    assert list(again.failed) == ["huge.bin"] and "larger" in again.failed["huge.bin"]


def test_config_sync_run_can_use_the_server_for_assets(tmp_path):
    from je_auto_control.utils.config_sync import session
    seen = {}

    def fake_run_sync(client, outbox, adapters, **options):
        seen.update(options)
        return session.SyncRunReport()

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    common = {"device_id": "laptop", "sections": "scripts", "scripts_dir": str(scripts),
              "outbox_path": str(tmp_path / "o.sqlite3"), "secret": "s3cret"}
    with patch.object(session, "run_sync", new=fake_run_sync):
        session.config_sync_run("https://sync.invalid", "alice", assets_server=True, **common)
        assert isinstance(seen["asset_transport"], HttpAssetTransport)
        session.config_sync_run("https://sync.invalid", "alice", **common)
        assert seen["asset_transport"] is None
        with pytest.raises(ConfigSyncError, match="assets_dir"):
            session.config_sync_run("https://sync.invalid", "alice", assets_server=True,
                                    assets_dir=str(tmp_path), **common)
