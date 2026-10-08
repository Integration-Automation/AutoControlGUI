"""The signaling server serves the config-sync bucket routes the client calls.

``config_sync`` documented ``GET`` / ``PUT /config/{user_id}`` on the
signaling server, but nothing served them, so every push and pull failed.
The revision check and persistence are in ``test_config_sync_persistence.py``.
"""
import socket
import threading
import time

import pytest

pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")

from je_auto_control.utils.remote_desktop.signaling_server import create_app  # noqa: E402

_SECRET = {"X-Signaling-Secret": "s3cret"}


@pytest.fixture
def client(tmp_path):
    return testclient.TestClient(create_app(shared_secret="s3cret", serve_web_viewer=False,
                                            config_store_path=tmp_path / "buckets.sqlite3"))


def _put(bucket, base=0, operation="op-1"):
    return {"version": 2, "base_revision": base, "operation_id": operation, "bucket": bucket}


def test_an_unknown_bucket_is_404(client):
    assert client.get("/config/alice", headers=_SECRET).status_code == 404


def test_a_bucket_round_trips(client):
    bucket = {"user_id": "alice", "revision": 3,
              "sections": {"hotkeys": {"hk1": {"combo": "ctrl+a", "last_modified": 1.0}}}}
    assert client.put("/config/alice", json=_put(bucket), headers=_SECRET).status_code == 200
    # The revision is the one the server committed, not the one the client sent.
    assert client.get("/config/alice", headers=_SECRET).json() == {
        **bucket, "revision": 1, "version": 2, "peers": {}}


def test_config_routes_need_the_secret(client):
    assert client.get("/config/alice").status_code == 401
    assert client.put("/config/alice", json={}).status_code == 401


def test_a_bucket_for_another_user_is_refused(client):
    response = client.put("/config/alice", json=_put({"user_id": "bob"}), headers=_SECRET)
    assert response.status_code == 400


def test_an_oversized_bucket_is_refused_before_it_is_read(client):
    body = b'{"x":"' + b"A" * (2 * 1024 * 1024) + b'"}'
    response = client.put("/config/alice", content=body,
                          headers={**_SECRET, "Content-Type": "application/json"})
    assert response.status_code == 413


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_the_real_client_syncs_through_the_server(tmp_path):
    uvicorn = pytest.importorskip("uvicorn")
    from je_auto_control.utils.config_sync import ConfigBucket, ConfigSyncClient
    port = _free_port()
    app = create_app(shared_secret="s3cret", serve_web_viewer=False,
                     config_store_path=tmp_path / "buckets.sqlite3")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        sync = ConfigSyncClient(f"http://127.0.0.1:{port}", user_id="alice", secret="s3cret")
        assert sync.fetch() is None
        assert sync.push(ConfigBucket(user_id="alice")) == 1
        fetched = sync.fetch()
        assert fetched.user_id == "alice" and fetched.revision == 1
        # A second machine that never saw revision 1 cannot overwrite it ...
        from je_auto_control.utils.config_sync.client import ConfigSyncConflict
        other = ConfigSyncClient(f"http://127.0.0.1:{port}", user_id="alice", secret="s3cret")
        stale = ConfigBucket(user_id="alice")
        stale.upsert("hotkeys", "hk1", {"combo": "ctrl+a"})
        with pytest.raises(ConfigSyncConflict) as raised:
            other.push(stale)
        assert raised.value.revision == 1
        # ... but syncing merges on top of it.
        merged, _conflicts = other.sync(stale)
        assert merged.revision == 2 and "hk1" in sync.fetch().entries("hotkeys")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
