"""Owned IPC tests prove local helper death cannot cancel work already running remotely."""
import json
import sys
import threading
from concurrent.futures import CancelledError
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
from je_auto_control.utils.agent_runtime import AgentRuntime
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.remote_journal import RemoteInputJournal, device_identity
from je_auto_control.utils.agent_runtime.remote_target import NativeRemoteTarget
from je_auto_control.utils.agent_runtime.runtime_lock import RuntimeLock

HELPER = '''
import json, sys, urllib.request
guard = None
def notify(request, kind):
    event = dict(kind=kind, controller=guard['controller'], device=guard['device'],
                 sequence=guard['next_sequence'], epoch='effect-epoch')
    print(json.dumps({'id': request['id'], 'event': event}), flush=True)
    if json.loads(sys.stdin.buffer.readline()) != {'ack': True}: raise SystemExit(2)
for line in sys.stdin.buffer:
    request = json.loads(line)
    operation, payload = request['operation'], request['payload']
    if operation == 'bootstrap': result = {'protocol': 1}
    elif operation == 'remote_capabilities': result = {'remote_effect_protocol': 1}
    elif operation == 'configure':
        guard = payload['remote_guard']
        result = {'ready': True}
    elif operation == 'observe': result = {'identity': 'device-fixture', 'value': 0}
    elif operation == 'perform':
        notify(request, 'remote_begin')
        # The host fsyncs before ACK. This read is after ACK but before remote dispatch.
        with open(sys.argv[1], encoding='utf-8') as stream: witness = json.load(stream)
        if witness['remote_effect']['sequence'] != guard['next_sequence']: raise SystemExit(3)
        if payload['arguments'].get('url'):
            with urllib.request.urlopen(payload['arguments']['url'], timeout=10) as response: response.read()
        if not payload['arguments'].get('omit_end'):
            notify(request, 'remote_end')
            guard['next_sequence'] += 1
        result = {'value': 1}
    print(json.dumps({'id': request['id'], 'result': result}), flush=True)
'''


@pytest.fixture
def scope():
    spec = AgentTaskSpec.from_dict({"goal": "remote fixture", "target": "fixture",
        "allowed_tools": ["AC_increment"], "budget": {"action_seconds": 0.3},
        "success_criteria": [{"kind": "result_equals", "key": "value", "value": 1}]})
    with operation_scope(TaskOperation(spec, lambda: None, None)):
        yield spec


def target(tmp_path, *, helper=HELPER, probe=None):
    return NativeRemoteTarget(argv=[sys.executable, "-u", "-c", helper, str(tmp_path / "device.lock.journal")],
        platform="android", physical_id="fixture-device", resource_path=tmp_path / "device.lock",
        recovery_probe=probe)


def test_settled_remote_actions_release_without_replacement_or_desktop_commands(tmp_path, scope):
    adapter = target(tmp_path)
    try:
        assert adapter.ready(scope) == (True, "")
        assert adapter.can_reobserve
        assert adapter.perform("AC_increment", {}) == {"value": 1}
        assert adapter.perform("AC_increment", {}) == {"value": 1}
        channel = adapter._channel
        adapter.cleanup()
        assert channel.retired
        assert adapter._resource is None
        assert json.loads((tmp_path / "device.lock.journal").read_text())["owner"] is None
    finally:
        adapter.cleanup()


@contextmanager
def remote_server():
    started, release, completed = threading.Event(), threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            started.set()
            release.wait(timeout=5)
            completed.set()
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", started, release, completed
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_killed_local_helper_does_not_stop_remote_effect_or_transfer_ownership(tmp_path, scope):
    epoch = ["after-writer-retired"]
    proof = lambda: {"device": device_identity("android", "fixture-device"),
                     "epoch": epoch[0], "writers_retired": True}
    adapter = target(tmp_path, probe=proof)
    other = target(tmp_path)
    try:
        adapter.ready(scope)
        with remote_server() as (url, started, release, completed):
            with pytest.raises(AgentTaskError, match="deadline"):
                adapter.perform("AC_increment", {"url": url})
            assert started.is_set()
            assert adapter._channel.retired
            with pytest.raises(AgentTaskError, match="quarantined"):
                adapter.cleanup()
            assert not adapter.can_reobserve
            with pytest.raises(AgentTaskError, match="owns"):
                other.ready(scope)
            release.set()
            assert completed.wait(timeout=2)
        assert not adapter.recover("writer retired; sample baseline", actor="admin")["recovered"]
        assert not adapter.recover("same generation cannot prove idle", actor="admin")["recovered"]
        epoch[0] = "reset-invalidating-old-commands"
        assert adapter.recover("reviewed trusted reset", actor="admin")["recovered"]
        assert other.ready(scope)[0]
    finally:
        other.cleanup()
        if adapter._resource is not None:
            epoch[0] = "final-cleanup-baseline"
            adapter.recover("test baseline", actor="admin")
            epoch[0] = "final-cleanup-new-epoch"
            adapter.recover("test reset", actor="admin")
        adapter.cleanup()


def test_host_write_failure_before_begin_ack_prevents_remote_dispatch(tmp_path, scope, monkeypatch):
    adapter = target(tmp_path)
    adapter.ready(scope)
    original = RemoteInputJournal._write

    def fail_begin(journal):
        if journal.pending:
            raise AgentTaskError("simulated fsync failure")
        original(journal)

    try:
        monkeypatch.setattr(RemoteInputJournal, "_write", fail_begin)
        with remote_server() as (url, started, _release, _completed):
            with pytest.raises(AgentTaskError, match="fsync"):
                adapter.perform("AC_increment", {"url": url})
            assert adapter._channel.retired
            assert not started.is_set()
        with pytest.raises(AgentTaskError, match="quarantined"):
            adapter.cleanup()
    finally:
        monkeypatch.setattr(RemoteInputJournal, "_write", original)
        # No ACK was sent; use a host proof fixture to settle only test-owned state.
        adapter._probe = lambda: {"device": adapter._device, "epoch": "retired", "writers_retired": True}
        adapter.recover("unacknowledged test event", actor="admin")
        adapter.cleanup()


@pytest.mark.parametrize("replacement", ["True", "0", "'1'", "1.0"])
def test_incompatible_remote_capability_is_rejected_before_configure(tmp_path, scope, replacement):
    helper = HELPER.replace("{'remote_effect_protocol': 1}", "{'remote_effect_protocol': " + replacement + "}")
    adapter = target(tmp_path, helper=helper)
    try:
        with pytest.raises(AgentTaskError, match="incompatible"):
            adapter.ready(scope)
        assert adapter._channel.retired
    finally:
        adapter.cleanup()


def test_omitted_end_retains_guard_and_refuses_resume_or_cleanup(tmp_path, scope):
    adapter = target(tmp_path)
    try:
        adapter.ready(scope)
        with pytest.raises(AgentTaskError, match="settle"):
            adapter.perform("AC_increment", {"omit_end": True})
        with pytest.raises(AgentTaskError, match="recovery"):
            adapter.observe()
        with pytest.raises(AgentTaskError, match="quarantined"):
            adapter.cleanup()
        with pytest.raises(AgentTaskError, match="no trusted"):
            adapter.recover("helper death is insufficient", actor="admin")
    finally:
        adapter._probe = lambda: {"device": adapter._device, "epoch": "baseline", "writers_retired": True}
        adapter.recover("test baseline", actor="admin")
        adapter._probe = lambda: {"device": adapter._device, "epoch": "new", "writers_retired": True}
        adapter.recover("test reset", actor="admin")
        adapter.cleanup()


def test_fresh_host_cannot_clear_stale_effect_without_post_retirement_epoch(tmp_path):
    device = device_identity("android", "fixture-device")
    journal = RemoteInputJournal(tmp_path / "device.lock", device)
    journal.acquire()
    journal.update({}, "perform")
    journal.consume({"kind": "remote_begin", "controller": journal.owner,
                     "device": device, "sequence": 1, "epoch": "old"})
    epoch = ["post-retirement-baseline"]
    adapter = target(tmp_path, probe=lambda: {"device": device, "epoch": epoch[0], "writers_retired": True})
    assert not adapter.recover("review stale host", actor="admin")["recovered"]
    with pytest.raises(AgentTaskError, match="recovery"):
        journal.acquire()
    epoch[0] = "new"
    assert adapter.recover("reviewed device reset", actor="admin")["recovered"]
    lock = RuntimeLock(tmp_path / "device.lock")
    lock.close()


def test_invalid_event_before_ack_never_dispatches_to_remote_endpoint(tmp_path, scope):
    helper = HELPER.replace("controller=guard['controller']", "controller='foreign-controller'")
    adapter = target(tmp_path, helper=helper)
    try:
        adapter.ready(scope)
        with remote_server() as (url, started, _release, _completed):
            with pytest.raises(AgentTaskError, match="controller"):
                adapter.perform("AC_increment", {"url": url})
            assert not started.is_set()
        adapter.cleanup()
        assert adapter._resource is None
    finally:
        adapter.cleanup()


def test_effect_during_observe_is_refused_before_ack(tmp_path, scope):
    helper = HELPER.replace("elif operation == 'observe': result =", "elif operation == 'observe':\n"
        "        notify(request, 'remote_begin')\n        result =")
    adapter = target(tmp_path, helper=helper)
    try:
        adapter.ready(scope)
        with pytest.raises(AgentTaskError, match="perform"):
            adapter.observe()
        assert adapter._channel.retired
    finally:
        adapter.cleanup()


def test_recovery_probe_runs_only_after_owned_helper_is_retired(tmp_path, scope):
    adapter = target(tmp_path)
    channel = None
    calls = []

    def probe():
        assert channel.retired
        calls.append(True)
        return {"device": adapter._device, "epoch": "post-retirement", "writers_retired": True}

    try:
        adapter.ready(scope)
        channel = adapter._channel
        adapter._probe = probe
        assert adapter.recover("review no remote writes", actor="admin")["recovered"]
        assert calls == [True]
        assert adapter._resource is None
    finally:
        adapter.cleanup()


def test_retirement_failure_prevents_probe_and_keeps_resource(tmp_path, scope, monkeypatch):
    adapter = target(tmp_path)
    adapter.ready(scope)
    channel = adapter._channel
    original = channel.close
    calls = []
    adapter._probe = lambda: calls.append(True)

    def fail_close():
        raise AgentTaskError("fixture writer has not retired")

    try:
        monkeypatch.setattr(channel, "close", fail_close)
        with pytest.raises(AgentTaskError, match="not retired"):
            adapter.recover("must not establish a baseline", actor="admin")
        assert not calls
        assert adapter._resource is not None
    finally:
        monkeypatch.setattr(channel, "close", original)
        adapter.cleanup()


def test_runtime_keeps_unknown_effect_lease_and_completion_unconfirmed(tmp_path):
    adapter = target(tmp_path)
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={"fixture": adapter})
    try:
        task = runtime.submit({"goal": "increment remote", "target": "fixture",
            "allowed_tools": ["AC_increment"], "budget": {"action_seconds": 1},
            "success_criteria": [{"kind": "result_equals", "key": "value", "value": 1}]})
        frame = runtime.observe(task.task_id)
        with pytest.raises(AgentTaskError):
            runtime.act(task.task_id, {"tool": "AC_increment", "arguments": {"omit_end": True},
                                     "observation_id": frame.observation_id})
        current = runtime.get(task.task_id)
        assert current.state == "waiting_user"
        assert current.metadata["input_released"] is False
        assert adapter._resource is not None
        assert runtime._leases
        assert current.state != "succeeded"
    finally:
        adapter._probe = lambda: {"device": adapter._device, "epoch": "baseline", "writers_retired": True}
        adapter.recover("test baseline", actor="admin")
        adapter._probe = lambda: {"device": adapter._device, "epoch": "new", "writers_retired": True}
        adapter.recover("test reset", actor="admin")
        runtime.close()


def test_cancellation_retires_local_writer_without_claiming_remote_stop(tmp_path, scope):
    adapter = target(tmp_path)
    epoch = ["post-cancel-baseline"]
    adapter._probe = lambda: {"device": adapter._device, "epoch": epoch[0], "writers_retired": True}
    try:
        adapter.ready(scope)
        with remote_server() as (url, started, release, completed):
            def checkpoint():
                if started.is_set():
                    raise CancelledError()

            with operation_scope(TaskOperation(scope, checkpoint, None)):
                with pytest.raises(CancelledError):
                    adapter.perform("AC_increment", {"url": url})
            assert adapter._channel.retired
            with pytest.raises(AgentTaskError, match="quarantined"):
                adapter.cleanup()
            release.set()
            assert completed.wait(timeout=2)
        assert not adapter.recover("cancel does not stop device", actor="admin")["recovered"]
    finally:
        adapter.recover("test baseline", actor="admin")
        epoch[0] = "new-test-epoch"
        adapter.recover("test reset", actor="admin")
        adapter.cleanup()
