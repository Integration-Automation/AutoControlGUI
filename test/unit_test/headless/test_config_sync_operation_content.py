"""A repeated operation id only stands for the write it first named.

The store answered any repeat of an ``operation_id`` with the revision of the
first commit and wrote nothing. That is right for a resend -- and silently
wrong for a caller that reused an id for a *different* bucket: it was told its
write had been committed when the server had thrown it away.
"""
import json
import sqlite3
from unittest.mock import patch

import pytest

from je_auto_control.utils.config_sync import (
    ConfigBucket, ConfigStore, ConfigSyncClient, ConfigSyncConflict, ConfigSyncError,
    OperationMismatchError,
)
from je_auto_control.utils.exception.exceptions import AutoControlException

_SECRET = {"X-Signaling-Secret": "s3cret"}


def _bucket(combo="ctrl+a", user="alice"):
    bucket = ConfigBucket(user_id=user)
    bucket.upsert("hotkeys", "hk1", {"combo": combo, "last_modified": 100.0})
    return bucket


def _envelope(bucket, base=0, operation="op-1"):
    return {"version": 2, "base_revision": base, "operation_id": operation,
            "bucket": bucket.to_dict()}


@pytest.fixture
def db(tmp_path):
    return tmp_path / "buckets.sqlite3"


def test_the_same_id_with_other_content_is_refused_and_nothing_is_written(db):
    store = ConfigStore(db)
    first = store.commit("alice", _bucket("ctrl+a"), base_revision=0, operation_id="op-1")
    with pytest.raises(OperationMismatchError) as raised:
        store.commit("alice", _bucket("ctrl+b"), base_revision=0, operation_id="op-1")
    assert raised.value.operation_id == "op-1"
    assert raised.value.revision == first
    assert store.revision("alice") == first
    assert store.get("alice").sections["hotkeys"]["hk1"]["combo"] == "ctrl+a"


def test_the_error_is_a_framework_error_but_not_a_revision_conflict(db):
    # A revision conflict is retried by fetching again; this must not be.
    assert issubclass(OperationMismatchError, ConfigSyncError)
    assert issubclass(OperationMismatchError, AutoControlException)
    assert not issubclass(OperationMismatchError, ConfigSyncConflict)


def test_a_true_resend_is_still_answered_with_the_first_revision(db):
    store = ConfigStore(db)
    first = store.commit("alice", _bucket(), base_revision=0, operation_id="op-1")
    resent = _bucket()
    resent.revision = 41            # what the client believes; the server sets its own
    assert ConfigStore(db).commit("alice", resent, base_revision=0, operation_id="op-1") == first


def test_the_same_content_on_another_base_is_a_different_write(db):
    store = ConfigStore(db)
    store.commit("alice", _bucket(), base_revision=0, operation_id="op-1")
    with pytest.raises(OperationMismatchError):
        store.commit("alice", _bucket(), base_revision=1, operation_id="op-1")


def test_an_operation_recorded_before_the_hash_existed_is_still_a_resend(db):
    # A database written by the previous release: no content_hash column.
    connection = sqlite3.connect(db)
    connection.execute(
        "CREATE TABLE buckets (user_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,"
        " body TEXT NOT NULL, updated_at REAL NOT NULL)")
    connection.execute(
        "CREATE TABLE operations (seq INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,"
        " operation_id TEXT NOT NULL, revision INTEGER NOT NULL,"
        " UNIQUE (user_id, operation_id))")
    body = {**_bucket().to_dict(), "revision": 1}
    connection.execute("INSERT INTO buckets VALUES ('alice', 1, ?, 0)", (json.dumps(body),))
    connection.execute(
        "INSERT INTO operations (user_id, operation_id, revision) VALUES ('alice', 'old', 1)")
    connection.commit()
    connection.close()
    store = ConfigStore(db)
    # Nothing to compare against, so the old answer stands ...
    assert store.commit("alice", _bucket("ctrl+z"), base_revision=0, operation_id="old") == 1
    # ... and a write made from now on is recorded with its content.
    assert store.commit("alice", _bucket("ctrl+b"), base_revision=1, operation_id="new") == 2
    with pytest.raises(OperationMismatchError):
        store.commit("alice", _bucket("ctrl+c"), base_revision=1, operation_id="new")


# --- the server ----------------------------------------------------------------

def _app(db):
    pytest.importorskip("fastapi")
    testclient = pytest.importorskip("fastapi.testclient")
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    return testclient.TestClient(create_app(
        shared_secret="s3cret", serve_web_viewer=False, config_store_path=db))


def test_the_server_answers_409_naming_the_reason(db):
    client = _app(db)
    assert client.put("/config/alice", json=_envelope(_bucket("ctrl+a")),
                      headers=_SECRET).status_code == 200
    reply = client.put("/config/alice", json=_envelope(_bucket("ctrl+b")), headers=_SECRET)
    assert reply.status_code == 409
    assert reply.json()["code"] == "operation_mismatch"
    # The revision is there too: a version-2 client of today reads only that.
    assert reply.json()["revision"] == 1
    assert client.get("/config/alice", headers=_SECRET).json()[
        "sections"]["hotkeys"]["hk1"]["combo"] == "ctrl+a"


def test_a_resend_through_the_server_is_still_200(db):
    client = _app(db)
    first = client.put("/config/alice", json=_envelope(_bucket()), headers=_SECRET).json()
    again = client.put("/config/alice", json=_envelope(_bucket()), headers=_SECRET)
    assert again.status_code == 200 and again.json()["revision"] == first["revision"]


# --- the client ----------------------------------------------------------------

def _reply(status, body):
    return {"status": status, "text": json.dumps(body)}


def _push_against(reply):
    client = ConfigSyncClient("http://127.0.0.1:9", user_id="alice")
    with patch("je_auto_control.utils.http_client.http_client.perform_call",
               return_value=reply):
        return client.push(_bucket(), base_revision=0, operation_id="op-1")


def test_the_client_raises_the_typed_error():
    with pytest.raises(OperationMismatchError) as raised:
        _push_against(_reply(409, {"detail": "operation id reused with other content",
                                   "code": "operation_mismatch", "revision": 7}))
    assert raised.value.revision == 7 and raised.value.operation_id == "op-1"


def test_a_plain_409_is_still_a_revision_conflict():
    with pytest.raises(ConfigSyncConflict) as raised:
        _push_against(_reply(409, {"detail": "revision conflict", "revision": 3}))
    assert raised.value.revision == 3


def test_a_mismatch_is_not_retried_by_sync():
    calls = []

    def perform(call):
        calls.append(call["method"])
        if call["method"] == "GET":
            return {"status": 404, "text": ""}
        return _reply(409, {"code": "operation_mismatch", "revision": 1})

    client = ConfigSyncClient("http://127.0.0.1:9", user_id="alice")
    with patch("je_auto_control.utils.http_client.http_client.perform_call", new=perform):
        with pytest.raises(OperationMismatchError):
            client.sync(_bucket())
    assert calls == ["GET", "PUT"]
