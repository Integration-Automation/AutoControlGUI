"""Exercise worker failures with subprocesses that never inject desktop input."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
from unittest.mock import MagicMock

import pytest

from je_auto_control.linux_wayland import ei_transport as transport
from je_auto_control.linux_wayland.permission import WaylandDependencyRequired


@pytest.fixture
def worker_factory(tmp_path):
    """Launch a scripted peer over the same inherited socket as native EI."""
    processes = []

    def launch(peer, *, mode="echo"):
        script = tmp_path / "peer.py"
        script.write_text(
            "import os, socket, sys\n"
            "from je_auto_control.linux_wayland.ei_transport import open_worker_channel, read_message, write_message\n"
            "peer = open_worker_channel(sys.argv[2])\n"
            "mode = sys.argv[1]\n"
            "while True:\n"
            "    request = read_message(peer)\n"
            "    if mode == 'die' and request['operation'] == 'send': os._exit(17)\n"
            "    if mode == 'hang':\n"
            "        import time\n"
            "        time.sleep(60)\n"
            "    reply = {'request_id': request['request_id'], 'applied': len(request.get('events', []))}\n"
            "    if mode == 'wrong': reply['request_id'] = 'stale'\n"
            "    write_message(peer, reply)\n"
            "    if request['operation'] == 'close': break\n",
            encoding="utf-8",
        )
        process = transport._spawn_process(peer, [sys.executable, str(script), mode], subprocess.DEVNULL)
        processes.append(process)
        return process

    yield launch
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)


def test_worker_death_reclaims_resources(worker_factory):
    client = transport.EiWorkerClient(process_factory=lambda peer: worker_factory(peer, mode="die"))
    client.connect(timeout=3)
    with pytest.raises(transport.EiWorkerError, match="worker"):
        client.send([transport.InputEvent("press_key", (29,))], timeout_s=3)
    assert client.is_connected is False
    assert client.worker_running is False
    assert client.open_channel is False
    client.close()


def test_half_open_worker_exit_reclaims_resources(worker_factory):
    client = transport.EiWorkerClient(process_factory=lambda peer: worker_factory(peer, mode="hang"))
    with pytest.raises(transport.EiWorkerError, match="timed out"):
        client.connect(timeout=0.3)
    assert client.worker_running is False
    assert client.open_channel is False
    with pytest.raises(transport.EiWorkerError):
        client.press_key(29)


def test_default_stop_cancels_pending_worker_ipc(worker_factory, monkeypatch):
    from je_auto_control.linux_wayland import libei
    from je_auto_control.linux_wayland.permission import WaylandPermissionRequired

    started = threading.Event()
    failures = []

    def factory(peer):
        process = worker_factory(peer, mode='hang')
        started.set()
        return process

    client = transport.EiWorkerClient(process_factory=factory)
    monkeypatch.setattr(libei, '_DEFAULT_BACKEND', None)
    monkeypatch.setattr(libei, '_PROBE_FAILED', False)
    monkeypatch.setattr(libei, '_PERMISSION_ERROR', None)
    monkeypatch.setattr(libei, '_new_default_backend', lambda: client)

    def connect():
        try:
            libei.connected_backend()
        except WaylandPermissionRequired as failure:
            failures.append(failure)

    worker = threading.Thread(target=connect)
    worker.start()
    try:
        assert started.wait(2)
        libei.stop_input_control()
        worker.join(2)
        assert not worker.is_alive()
        assert len(failures) == 1
        assert not client.worker_running and not client.open_channel
        assert libei.input_permission_status()[0] == 'needs_permission'
    finally:
        client.close()
        worker.join(6)


def test_reply_identity_and_batch_ack(worker_factory):
    client = transport.EiWorkerClient(process_factory=worker_factory)
    try:
        client.connect(timeout=3)
        ack = client.send([
            transport.InputEvent("press_key", (29,)), transport.InputEvent("release_key", (29,)),
        ], timeout_s=3)
        assert ack.applied == 2
        assert ack.request_id
        assert ack.elapsed_s >= 0
    finally:
        client.close()
    assert not client.worker_running
    assert not client.open_channel


def test_stale_reply_closes_channel(worker_factory):
    client = transport.EiWorkerClient(process_factory=lambda peer: worker_factory(peer, mode="wrong"))
    with pytest.raises(transport.EiWorkerError, match="request"):
        client.connect(timeout=3)
    assert not client.worker_running


def test_invalid_batch_is_rejected_before_launch(worker_factory):
    client = transport.EiWorkerClient(process_factory=worker_factory)
    with pytest.raises(transport.EiWorkerError):
        client.send([transport.InputEvent("press_key", (True,))], timeout_s=1)
    with pytest.raises(transport.EiWorkerError):
        client.send([transport.InputEvent("press_key", (29,))] * 129, timeout_s=1)
    assert not client.worker_running


def test_oversized_frame_is_refused():
    left, right = socket.socketpair()
    try:
        right.sendall((transport.MAX_MESSAGE_BYTES + 1).to_bytes(4, "big"))
        with pytest.raises(transport.EiWorkerError, match="size"):
            transport.read_message(left)
    finally:
        left.close()
        right.close()


def test_missing_dependency_is_typed():
    if sys.platform != "win32":
        pytest.skip("the native worker is exercised by the Linux EI verification job")
    client = transport.EiWorkerClient()
    with pytest.raises(WaylandDependencyRequired) as error:
        client.connect(timeout=5)
    assert error.value.capability == "input"
    assert not client.worker_running
    assert not client.open_channel


def test_close_cancels_pending_request(worker_factory):
    client = transport.EiWorkerClient(process_factory=lambda peer: worker_factory(peer, mode="hang"))
    started = threading.Event()
    errors = []

    def connect():
        started.set()
        try:
            client.connect(timeout=3)
        except transport.EiWorkerError as error:
            errors.append(error)

    thread = threading.Thread(target=connect)
    thread.start()
    assert started.wait(1)
    client.close()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors
    assert not client.worker_running


def test_malformed_json_is_refused():
    left, right = socket.socketpair()
    try:
        payload = json.dumps(["not", "an", "envelope"]).encode()
        right.sendall(len(payload).to_bytes(4, "big") + payload)
        with pytest.raises(transport.EiWorkerError):
            transport.read_message(left)
    finally:
        left.close()
        right.close()


def test_worker_cleanup_releases_pressed_keys_on_the_same_grant():
    from je_auto_control.linux_wayland.ei_worker import WorkerSession

    backend = MagicMock()
    session = WorkerSession(backend_factory=lambda **kwargs: backend)
    session.handle({"operation": "connect", "socket_path": "/controlled/eis"})
    session.handle({"operation": "send", "events": [
        {"kind": "press_key", "args": [29]}, {"kind": "press_button", "args": [272]},
    ]})
    session.close()
    session.close()
    backend.release_key.assert_called_once_with(29)
    backend.release_button.assert_called_once_with(272)
    backend.disconnect.assert_called_once()
    assert session.pressed == set()


def test_revoked_cleanup_ends_grant_without_switching_devices():
    from je_auto_control.linux_wayland.ei_worker import WorkerSession
    from je_auto_control.linux_wayland.permission import WaylandPermissionRequired

    backend = MagicMock()
    session = WorkerSession(backend_factory=lambda **kwargs: backend)
    session.backend = backend
    session.pressed.add(("key", 29))
    backend.release_key.side_effect = WaylandPermissionRequired("input", "revoked")
    session.close()
    backend.disconnect.assert_called_once()
    assert session.pressed == set()


def test_owner_eof_releases_held_input_and_ends_worker_cleanly():
    from je_auto_control.linux_wayland.ei_worker import WorkerSession, serve

    backend = MagicMock()
    session = WorkerSession(backend_factory=lambda **kwargs: backend)
    owner, peer = socket.socketpair()
    errors = []

    def run():
        try:
            serve(peer, session)
        except transport.EiWorkerError as error:
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        transport.write_message(owner, {"request_id": "connect", "operation": "connect"})
        assert transport.read_message(owner)["request_id"] == "connect"
        transport.write_message(owner, {"request_id": "press", "operation": "send", "events": [
            {"kind": "press_key", "args": [29]},
        ]})
        assert transport.read_message(owner)["applied"] == 1
    finally:
        owner.close()
        thread.join(timeout=3)
    assert not thread.is_alive()
    assert errors == []
    backend.release_key.assert_called_once_with(29)
    backend.disconnect.assert_called_once()


def test_worker_validates_entire_batch_before_emitting():
    from je_auto_control.linux_wayland.ei_worker import WorkerSession

    backend = MagicMock()
    session = WorkerSession()
    session.backend = backend
    with pytest.raises(transport.EiWorkerError):
        session.handle({"operation": "send", "events": [
            {"kind": "press_key", "args": [29]}, {"kind": "arbitrary_code", "args": []},
        ]})
    backend.press_key.assert_not_called()
    session.close()


def test_default_backend_creates_no_native_context_in_the_parent(monkeypatch):
    from je_auto_control.linux_wayland import libei

    symbols = MagicMock()
    monkeypatch.setattr(libei, "_load_symbols", lambda: symbols)
    client = libei._new_default_backend()
    assert isinstance(client, transport.EiWorkerClient)
    symbols.ei_new_sender.assert_not_called()
    assert not client.worker_running
    client.close()


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), -1, 0, None])
def test_bad_timeout_does_not_launch_worker(timeout):
    client = transport.EiWorkerClient()
    try:
        with pytest.raises(transport.EiWorkerError):
            client.connect(timeout=timeout)
        assert not client.worker_running
    finally:
        client.close()


def test_startup_failure_closes_socket_and_temporary_diagnostics():
    peers = []

    def fail(peer):
        peers.append(peer)
        raise OSError("controlled spawn failure")

    client = transport.EiWorkerClient(process_factory=fail)
    with pytest.raises(transport.EiWorkerError, match="connection failed"):
        client.connect(timeout=1)
    assert not client.worker_running
    assert not client.open_channel
    assert peers[0].fileno() == -1
    assert client._resources.diagnostics is None
