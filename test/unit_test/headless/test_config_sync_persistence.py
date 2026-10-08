"""Config-sync buckets survive a restart and refuse a write built on stale data.

The signaling server kept buckets in a dict and let every ``PUT`` replace the
previous one: a restart lost them all, and two machines pushing together
dropped one side's changes without either hearing about it.
"""
import threading

import pytest

from je_auto_control.utils.config_sync.client import ConfigBucket, ConfigSyncError
from je_auto_control.utils.config_sync.store import (
    ConfigStore, ConfigStoreError, RevisionConflictError, StoreCapacityError,
)

_SECRET = {"X-Signaling-Secret": "s3cret"}


def _bucket(user="alice", combo="ctrl+a"):
    bucket = ConfigBucket(user_id=user)
    bucket.upsert("hotkeys", "hk1", {"combo": combo, "last_modified": 100.0})
    return bucket


def _envelope(bucket, base, operation="op-1"):
    return {"version": 2, "base_revision": base, "operation_id": operation,
            "bucket": bucket.to_dict()}


@pytest.fixture
def db(tmp_path):
    return tmp_path / "sync" / "buckets.sqlite3"


def _client(db, **options):
    pytest.importorskip("fastapi")
    testclient = pytest.importorskip("fastapi.testclient")
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    return testclient.TestClient(create_app(
        shared_secret="s3cret", serve_web_viewer=False, config_store_path=db, **options))


# --- the store -------------------------------------------------------------

def test_reopen_preserves_bucket(db):
    user = "alice"
    committed_revision = ConfigStore(db).commit(
        user, _bucket(), base_revision=0, operation_id="op-1")
    reopened = ConfigStore(db)
    assert reopened.get(user).revision == committed_revision
    assert reopened.get(user).sections["hotkeys"]["hk1"]["combo"] == "ctrl+a"


def test_a_stale_base_revision_is_refused_and_nothing_is_written(db):
    store = ConfigStore(db)
    store.commit("alice", _bucket(combo="first"), base_revision=0, operation_id="a")
    with pytest.raises(RevisionConflictError) as raised:
        store.commit("alice", _bucket(combo="second"), base_revision=0, operation_id="b")
    assert raised.value.current_revision == 1
    assert store.get("alice").sections["hotkeys"]["hk1"]["combo"] == "first"


def test_operation_retry_is_idempotent(db):
    store = ConfigStore(db)
    original = store.commit("alice", _bucket(), base_revision=0, operation_id="op-1")
    # The retry still names base 0, which is stale by now -- it is the
    # operation id that tells the store this is the same write.
    store_after_restart = ConfigStore(db)
    repeated = store_after_restart.commit(
        "alice", _bucket(), base_revision=0, operation_id="op-1")
    assert repeated == original
    assert store_after_restart.revision("alice") == original


def test_operation_ids_are_per_user(db):
    store = ConfigStore(db)
    store.commit("alice", _bucket("alice"), base_revision=0, operation_id="op-1")
    assert store.commit("bob", _bucket("bob"), base_revision=0, operation_id="op-1") == 1
    assert store.get("bob").user_id == "bob"


def test_concurrent_commits_from_one_base_admit_exactly_one(db):
    store = ConfigStore(db)
    store.commit("alice", _bucket(), base_revision=0, operation_id="seed")
    outcomes = []
    start = threading.Barrier(8)

    def push(index):
        start.wait(timeout=10)
        try:
            outcomes.append(ConfigStore(db).commit(
                "alice", _bucket(combo=f"writer-{index}"),
                base_revision=1, operation_id=f"writer-{index}"))
        except RevisionConflictError:
            outcomes.append(None)

    threads = [threading.Thread(target=push, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(outcome for outcome in outcomes if outcome is not None) == [2]
    assert outcomes.count(None) == 7


def test_a_bucket_cannot_be_committed_under_another_user(db):
    with pytest.raises(ConfigStoreError):
        ConfigStore(db).commit("alice", _bucket("bob"), base_revision=0, operation_id="x")


def test_the_user_limit_is_enforced_inside_the_commit(db):
    store = ConfigStore(db, max_users=1)
    store.commit("alice", _bucket("alice"), base_revision=0, operation_id="a")
    with pytest.raises(StoreCapacityError):
        store.commit("bob", _bucket("bob"), base_revision=0, operation_id="b")
    assert store.commit("alice", _bucket("alice"), base_revision=1, operation_id="c") == 2


@pytest.mark.parametrize("base, operation", [(-1, "op"), (True, "op"), ("0", "op"), (0, ""),
                                             (0, "x" * 200), (0, None)])
def test_malformed_commit_arguments_are_refused(db, base, operation):
    with pytest.raises(ConfigStoreError):
        ConfigStore(db).commit("alice", _bucket(), base_revision=base, operation_id=operation)


def test_building_a_store_touches_nothing_until_first_use(db):
    store = ConfigStore(db)
    assert not db.parent.exists()
    assert store.get("alice") is None
    assert db.exists()


def test_the_default_path_is_resolved_at_call_time(tmp_path, monkeypatch):
    from pathlib import Path
    store = ConfigStore()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert store.path == tmp_path / ".je_auto_control" / "config_sync.sqlite3"


def test_a_database_failure_is_a_framework_error(tmp_path):
    not_a_database = tmp_path / "junk.sqlite3"
    not_a_database.write_bytes(b"this is not sqlite" * 64)
    with pytest.raises(ConfigSyncError):
        ConfigStore(not_a_database).get("alice")


# --- the server ------------------------------------------------------------

def test_stale_revision_conflicts(db):
    client = _client(db)
    first = client.put("/config/alice", json=_envelope(_bucket(combo="first"), 0, "a"),
                       headers=_SECRET)
    assert first.status_code == 200 and first.json()["revision"] == 1
    stale_response = client.put("/config/alice", json=_envelope(_bucket(combo="second"), 0, "b"),
                                headers=_SECRET)
    assert stale_response.status_code == 409
    assert stale_response.json()["revision"] == 1
    stored = client.get("/config/alice", headers=_SECRET).json()
    assert stored["sections"]["hotkeys"]["hk1"]["combo"] == "first"


def test_get_returns_the_committed_revision_not_the_one_the_client_sent(db):
    client = _client(db)
    bucket = _bucket()
    bucket.revision = 41
    client.put("/config/alice", json=_envelope(bucket, 0), headers=_SECRET)
    body = client.get("/config/alice", headers=_SECRET).json()
    assert body["revision"] == 1
    assert body["version"] == 2


def test_a_server_restart_keeps_the_bucket(db):
    _client(db).put("/config/alice", json=_envelope(_bucket(), 0), headers=_SECRET)
    body = _client(db).get("/config/alice", headers=_SECRET).json()
    assert body["revision"] == 1
    assert body["sections"]["hotkeys"]["hk1"]["combo"] == "ctrl+a"


def test_a_retried_put_gets_the_original_revision(db):
    client = _client(db)
    envelope = _envelope(_bucket(), 0, "retry-me")
    original = client.put("/config/alice", json=envelope, headers=_SECRET).json()
    repeated = client.put("/config/alice", json=envelope, headers=_SECRET)
    assert repeated.status_code == 200
    assert repeated.json()["revision"] == original["revision"] == 1


def test_a_blind_write_is_refused_unless_the_compatibility_setting_is_on(db):
    refused = _client(db).put("/config/alice", json=_bucket().to_dict(), headers=_SECRET)
    assert refused.status_code == 428
    assert _client(db).get("/config/alice", headers=_SECRET).status_code == 404

    compat = _client(db, allow_blind_config_writes=True)
    assert compat.put("/config/alice", json=_bucket(combo="one").to_dict(),
                      headers=_SECRET).status_code == 200
    reply = compat.put("/config/alice", json=_bucket(combo="two").to_dict(), headers=_SECRET)
    assert reply.status_code == 200 and reply.json()["revision"] == 2
    assert compat.get("/config/alice", headers=_SECRET).json()["revision"] == 2


def test_accounts_stay_isolated(db):
    client = _client(db)
    client.put("/config/alice", json=_envelope(_bucket("alice"), 0), headers=_SECRET)
    assert client.get("/config/bob", headers=_SECRET).status_code == 404
    crossed = client.put("/config/bob", json=_envelope(_bucket("alice"), 0), headers=_SECRET)
    assert crossed.status_code == 400


@pytest.mark.parametrize("envelope", [
    {"version": 2, "base_revision": "0", "operation_id": "a", "bucket": {"user_id": "alice"}},
    {"version": 2, "base_revision": 0, "operation_id": "", "bucket": {"user_id": "alice"}},
    {"version": 2, "base_revision": 0, "operation_id": "a", "bucket": []},
    {"version": 2, "base_revision": 0, "operation_id": "a",
     "bucket": {"user_id": "alice", "sections": {"hotkeys": []}}},
    {"version": 3, "base_revision": 0, "operation_id": "a", "bucket": {"user_id": "alice"}},
])
def test_a_malformed_envelope_is_a_400(db, envelope):
    assert _client(db).put("/config/alice", json=envelope, headers=_SECRET).status_code == 400


def test_the_secret_and_the_body_cap_still_apply(db):
    client = _client(db)
    assert client.put("/config/alice", json=_envelope(_bucket(), 0)).status_code == 401
    body = b'{"x":"' + b"A" * (2 * 1024 * 1024) + b'"}'
    oversized = client.put("/config/alice", content=body,
                           headers={**_SECRET, "Content-Type": "application/json"})
    assert oversized.status_code == 413
    assert not db.exists()


def test_creating_the_app_does_not_create_the_database(db):
    client = _client(db)
    assert client.get("/health").status_code == 200
    assert not db.parent.exists()
