"""Waiting out a retry delay is not the same thing as being offline.

After a failed send the outbox waits 2 s, 4 s ... up to 300 s before it tries
again. A sync asked for inside that window did not contact the server at all
and reported ``state="offline"`` -- so pressing "Sync now" the moment the
network came back looked exactly like a server that was still down.
"""
from unittest.mock import patch

import pytest

from je_auto_control.utils.config_sync import (
    ConfigSyncClient, ConfigSyncConflict, ConfigSyncError, SyncAdapter, SyncEntry,
    SyncOperation, SyncOutbox, config_sync_run, config_sync_status, run_sync, sync_status,
)

_URL = "https://sync.invalid"


class _Server:
    def __init__(self):
        self.body = None
        self.revision = 0
        self.offline = False
        self.requests = 0

    def request(self, method, body=None):
        self.requests += 1
        if self.offline:
            raise ConfigSyncError("config sync: connection refused")
        if method == "GET":
            return self.body
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


@pytest.fixture
def machine(tmp_path):
    outbox = SyncOutbox(tmp_path / "outbox.sqlite3", account="alice", endpoint=_URL,
                        base_delay_s=120.0)
    adapters = [_DictAdapter("laptop", {"a": {"v": 1}})]

    def sync(**options):
        return run_sync(ConfigSyncClient(_URL, user_id="alice"), outbox, adapters,
                        device_id="laptop", max_attempts=1, **options)
    sync.outbox = outbox
    return sync


def _op(key="a"):
    return SyncOperation("custom", SyncEntry.create(key, {"v": 1}, "laptop"))


# --- the outbox ------------------------------------------------------------------

def test_a_drain_inside_the_delay_says_it_is_backing_off(tmp_path):
    outbox = SyncOutbox(tmp_path / "o.sqlite3", account="a", endpoint=_URL, base_delay_s=60.0)
    outbox.enqueue(_op())
    outbox.record_failure([outbox.pending()[0].operation_id], now=1000.0, error="refused")
    sent = []
    report = outbox.drain(sent.append, wait=False, clock=lambda: 1010.0)
    assert sent == []
    # offline stays true for callers that only ask "did the queue get out?".
    assert report.backing_off
    assert report.offline
    assert not report.cancelled
    assert report.retry_in_s == pytest.approx(50.0)
    assert report.error == "refused", "the reason for the wait is the failure that caused it"
    assert report.pending == 1
    assert report.attempts == 0


def test_force_skips_the_wait_once(tmp_path):
    outbox = SyncOutbox(tmp_path / "o.sqlite3", account="a", endpoint=_URL, base_delay_s=60.0)
    outbox.enqueue(_op())
    outbox.record_failure([outbox.pending()[0].operation_id], now=1000.0, error="refused")
    attempts = []

    def still_down(batch):
        attempts.append(len(batch))
        raise ConfigSyncError("refused again")

    report = outbox.drain(still_down, wait=False, force=True, max_attempts=5,
                          clock=lambda: 1010.0)
    # One forced attempt -- not five: the delay it earned is waited out as usual.
    assert attempts == [1]
    assert report.offline
    assert not report.backing_off
    assert report.error == "refused again"
    assert report.retry_in_s == pytest.approx(120.0)


def test_a_failure_in_this_drain_is_offline_and_names_the_next_attempt(tmp_path):
    outbox = SyncOutbox(tmp_path / "o.sqlite3", account="a", endpoint=_URL, base_delay_s=8.0)
    outbox.enqueue(_op())

    def down(_batch):
        raise ConfigSyncError("refused")

    report = outbox.drain(down, wait=False, clock=lambda: 500.0)
    assert report.offline
    assert not report.backing_off
    assert report.retry_in_s == pytest.approx(8.0)


# --- run_sync / status -----------------------------------------------------------

def test_a_sync_inside_the_delay_reports_backing_off_not_offline(machine, server):
    server.offline = True
    first = machine()
    assert first.state == "offline"
    assert first.retry_in_s > 0
    requests = server.requests

    server.offline = False                      # the network is back ...
    second = machine()                          # ... but this run is inside the delay
    assert second.state == "backing_off"
    assert 0 < second.retry_in_s <= 120.0
    assert second.error == first.error
    assert server.requests == requests, "a run that is waiting does not contact the server"
    assert second.pending == 1
    assert second.to_dict()["retry_in_s"] == second.retry_in_s

    status = sync_status(machine.outbox)
    assert status["state"] == "backing_off"
    assert 0 < status["retry_in_s"] <= 120.0


def test_an_explicit_sync_skips_the_wait_once(machine, server):
    server.offline = True
    machine()
    server.offline = False
    report = machine(force=True)
    assert (report.state, report.pending) == ("synced", 0)
    assert not report.retry_in_s
    assert server.revision == 1


def test_forcing_while_the_server_is_still_down_is_offline_again(machine, server):
    server.offline = True
    machine()
    requests = server.requests
    report = machine(force=True)
    assert report.state == "offline", "the delay doubled"
    assert report.retry_in_s > 120.0, "the delay doubled"
    assert server.requests > requests


def test_the_status_turns_to_pending_once_the_delay_has_passed(machine, server):
    server.offline = True
    machine()
    machine()
    assert sync_status(machine.outbox)["state"] == "backing_off"
    with patch("je_auto_control.utils.config_sync.session.time.time",
               return_value=4_000_000_000.0):
        status = sync_status(machine.outbox)
    assert status["state"] == "pending"
    assert not status["retry_in_s"]


def test_the_one_call_entry_points_carry_the_state(tmp_path, server):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "a.json").write_text("[]", encoding="utf-8")
    options = {"device_id": "laptop", "sections": "scripts", "scripts_dir": str(scripts),
               "outbox_path": str(tmp_path / "outbox.sqlite3"), "max_attempts": 1}
    server.offline = True
    assert config_sync_run(_URL, "alice", **options)["state"] == "offline"
    waiting = config_sync_run(_URL, "alice", **options)
    assert waiting["state"] == "backing_off"
    assert waiting["retry_in_s"] > 0
    assert config_sync_status(_URL, "alice", options["outbox_path"])["state"] == "backing_off"
    server.offline = False
    assert config_sync_run(_URL, "alice", force=True, **options)["state"] == "synced"


def test_never_synced_reports_no_retry(tmp_path):
    status = config_sync_status(_URL, "alice", str(tmp_path / "absent.sqlite3"))
    assert status["state"] == "never"
    assert not status["retry_in_s"]


def test_the_surfaces_accept_force():
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    tools = {tool.name: tool
             for tool in build_default_tool_registry(read_only=False, aliases=False)}
    assert "force" in tools["ac_config_sync_run"].input_schema["properties"]
    run = next(spec for spec in _build_specs() if spec.command == "AC_config_sync_run")
    assert "force" in {field.name for field in run.fields}
