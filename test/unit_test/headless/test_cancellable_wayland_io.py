"""Cancellation reaches controlled socket/process/native waits and still performs owned cleanup."""
from concurrent.futures import CancelledError
import socket
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from headless.test_wayland_oeffis import FakeOeffis, HANDLE
from je_auto_control.linux_wayland import capture, oeffis, portal
from je_auto_control.utils.dbus_client.session_bus import SessionBus
from je_auto_control.utils.exception.cancellation import (
    CancellationToken, cancellation_checkpoint, cancellation_scope, current_cancellation_token,
)


def _scoped_worker(token, operation, failures):
    try:
        with cancellation_scope(token):
            operation()
    except BaseException as error:  # reason: assertions inspect the original worker control after resources retire
        failures.append(error)


def test_portal_cancel_wakes_socket_wait_and_sends_bounded_close_outside_cancelled_scope(monkeypatch):
    owned, peer = socket.socketpair()
    bus = SessionBus(address='unix:path=/controlled')
    bus._socket, bus.unique_name = owned, ':1.42'
    token = CancellationToken(1)
    entered, failures, closes = threading.Event(), [], []
    monkeypatch.setattr(bus, 'add_match', lambda _rule: None)

    def screenshot(_bus, handle_token):
        entered.set()
        return portal._request_path(bus.sender_token, handle_token)

    def close_call(_destination, handle, interface, member, _signature, _body, *, timeout):
        cancellation_checkpoint()
        closes.append((handle, interface, member, timeout, current_cancellation_token()))
        return []

    monkeypatch.setattr(portal, '_screenshot', screenshot)
    monkeypatch.setattr(bus, 'call', close_call)

    def request():
        try:
            portal._request_and_await(bus, 30)
        finally:
            bus.close()

    worker = threading.Thread(target=_scoped_worker, args=(token, request, failures))
    worker.start()
    try:
        assert entered.wait(1)
        token.cancel()
        worker.join(1)
        assert not worker.is_alive(), 'the cancelled portal still waits for its 30-second response deadline'
        assert len(failures) == 1 and isinstance(failures[0], CancelledError)
        assert len(closes) == 1 and closes[0][1:] == (portal.REQUEST_INTERFACE, 'Close', 0.25, None)
        assert owned.fileno() == -1
    finally:
        peer.close()
        worker.join(2)
        for error in failures:
            error.__traceback__ = None


def test_cancelled_capture_helper_is_terminated_and_reaped_without_waiting_for_capture_timeout(tmp_path, monkeypatch):
    ready = tmp_path/'helper-ready'
    token = CancellationToken(1)
    processes, failures = [], []
    popen = capture.subprocess.Popen

    def tracked(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(capture.subprocess, 'Popen', tracked)
    argv = [sys.executable, '-I', '-c',
            "import pathlib,sys,time;pathlib.Path(sys.argv[1]).write_text('ready',encoding='utf-8');time.sleep(30)",
            str(ready)]
    worker = threading.Thread(target=_scoped_worker,
                              args=(token, lambda: capture.run_tool(argv, timeout=30), failures))
    worker.start()
    try:
        deadline = time.monotonic()+3
        while not ready.exists() and time.monotonic() < deadline:
            threading.Event().wait(0.01)
        assert ready.exists()
        token.cancel()
        worker.join(2)
        assert not worker.is_alive(), 'capture cancellation still waits for the helper deadline'
        assert len(failures) == 1 and isinstance(failures[0], CancelledError)
        assert len(processes) == 1 and processes[0].poll() is not None
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
        worker.join(2)
        for error in failures:
            error.__traceback__ = None


def test_cancelled_portal_result_discards_its_owned_file_before_returning_bytes(tmp_path):
    image = tmp_path/'controlled.png'
    image.write_bytes(b'controlled PNG')
    token = CancellationToken(1)
    token.cancel()
    with cancellation_scope(token), pytest.raises(CancelledError):
        portal._read_and_discard(str(image))
    assert not image.exists()


def test_oeffis_cancel_during_poll_releases_only_its_session_and_never_returns_a_fd(monkeypatch):
    token = CancellationToken(1)
    fake = FakeOeffis()
    waits = []

    def poll(_read, _write, _error, timeout):
        waits.append(timeout)
        token.cancel()
        return [], [], []

    monkeypatch.setattr(oeffis, 'select', SimpleNamespace(select=poll))
    with cancellation_scope(token), pytest.raises(CancelledError):
        oeffis.connect_eis_fd(timeout=30, symbols=fake)
    assert waits and max(waits) <= 0.1
    assert fake.calls.count(('unref', HANDLE)) == 1


def test_already_cancelled_oeffis_does_not_even_start_a_portal_request():
    token, fake = CancellationToken(1), FakeOeffis()
    token.cancel()
    with cancellation_scope(token), pytest.raises(CancelledError):
        oeffis.connect_eis_fd(timeout=30, symbols=fake)
    assert fake.calls == []
