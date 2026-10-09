"""A sync with nothing to send and nothing to protect commits no revision.

A device's first ``push_operations([])`` always pushed, to list the device
under ``peers``. Against an account with no entries that produced revision 1
of a bucket holding nothing but the device's own name -- a write, a row in
the server's database and a 409 for anyone pushing at the same moment, all
for no content. Joining a bucket that does hold entries is not worth a
revision either: the device is listed by the first change it commits, and
until then a deletion reaches it through the held tombstone
(``test_config_sync_join_without_commit.py``).
"""
from unittest.mock import patch

import pytest

from je_auto_control.utils.config_sync import (
    ConfigSyncClient, ConfigSyncConflict, SyncAdapter, SyncEntry, SyncOperation, SyncOutbox,
    run_sync, sync_status,
)

_URL = "https://sync.invalid"


class _Server:
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


def _run(tmp_path, name, store):
    outbox = SyncOutbox(tmp_path / f"{name}.sqlite3", account="alice", endpoint=_URL,
                        base_delay_s=0.0)
    report = run_sync(ConfigSyncClient(_URL, user_id="alice"), outbox,
                      [_DictAdapter(name, store)], device_id=name)
    return report, outbox


def test_the_first_sync_of_an_empty_account_writes_nothing(tmp_path, server):
    report, outbox = _run(tmp_path, "laptop", {})
    assert report.state == "synced"
    assert report.revision == 0
    assert server.puts == 0
    assert server.body is None
    assert sync_status(outbox)["state"] == "synced"
    # ... and it stays that way however often it is repeated.
    _run(tmp_path, "laptop", {})
    assert server.puts == 0


def test_push_operations_with_nothing_on_either_side_does_not_push(server):
    result = ConfigSyncClient(_URL, user_id="alice").push_operations([], device_id="laptop")
    assert (result.pushed, result.revision, server.puts) == (False, 0, 0)


def test_the_first_real_change_still_creates_the_bucket_and_lists_the_device(tmp_path, server):
    report, _outbox = _run(tmp_path, "laptop", {"a": {"v": 1}})
    assert report.revision == 1
    assert server.puts == 1
    assert list(server.body["peers"]) == ["laptop"]


def test_joining_a_bucket_that_holds_entries_commits_nothing_either(tmp_path, server):
    _run(tmp_path, "laptop", {"a": {"v": 1}})
    store = {}
    report, _outbox = _run(tmp_path, "desktop", store)
    assert store == {"a": {"v": 1}}
    assert report.state == "synced"
    assert report.revision == 1
    assert server.puts == 1
    assert list(server.body["peers"]) == ["laptop"]
    # The desktop's first real change is what lists it ...
    store["b"] = {"v": 2}
    report, _outbox = _run(tmp_path, "desktop", store)
    assert report.revision == 2
    assert set(server.body["peers"]) == {"laptop", "desktop"}
    # ... and once listed, a further sync with nothing new writes nothing.
    _run(tmp_path, "desktop", store)
    assert server.puts == 2


def test_a_bucket_emptied_of_entries_is_not_joined_either(server):
    # tombstone_hold_s=0: the bucket has to be empty for this, so the deletion
    # must not be held for the machines that have not synced yet.
    client = ConfigSyncClient(_URL, user_id="alice", tombstone_hold_s=0)
    entry = SyncEntry.create("a", {"v": 1}, "laptop")
    client.push_operations([SyncOperation("custom", entry)], device_id="laptop")
    client.push_operations([SyncOperation("custom", entry.removed("laptop"))], device_id="laptop")
    client.push_operations([], device_id="laptop")          # sole peer: the tombstone goes
    assert server.body["sections"]["custom"] == {}
    puts = server.puts
    result = client.push_operations([], device_id="desktop")
    assert not result.pushed
    assert server.puts == puts
