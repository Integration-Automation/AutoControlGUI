"""Lifecycle races on RemoteDesktopHost.

The class docstring promises "start() is idempotent and stop() can be called
from any thread". Nothing enforced that, and for a tool that hands a remote
peer control of the local mouse and keyboard, a stop() that does not actually
stop is a safety problem rather than a tidiness one.
"""
import socket
import threading
import time

import pytest

from je_auto_control.utils.remote_desktop import host as host_mod
from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost


def _make_host() -> RemoteDesktopHost:
    return RemoteDesktopHost(token="t", bind="127.0.0.1", port=0,
                             frame_provider=lambda: None)


class _FakeChannel:
    """Stands in for a completed handshake."""

    def close(self):
        pass

    def settimeout(self, *_a):
        pass

    def send(self, *_a, **_k):
        pass

    def recv(self, *_a, **_k):
        time.sleep(9)
        raise OSError("closed")


def test_a_client_finishing_its_handshake_after_stop_is_not_attached(
        monkeypatch):
    """A viewer must never attach to a host the operator already stopped.

    Regression: _open_channel performs the auth/TLS handshake (bounded by
    _AUTH_TIMEOUT_S = 60s). stop() sets _shutdown, then snapshots and clears
    _clients under _clients_lock. _accept_loop appended the finished handler
    without re-checking _shutdown under that same lock, so a client landing in
    that window was never in stop()'s snapshot and was never stopped — its
    receiver thread kept dispatching remote INPUT to the local machine after
    stop() returned and is_running was already False.
    """
    parked, release = threading.Event(), threading.Event()

    def slow_open_channel(_self, _sock, _address):
        parked.set()
        release.wait(5.0)
        return _FakeChannel()

    monkeypatch.setattr(RemoteDesktopHost, "_open_channel", slow_open_channel)
    monkeypatch.setattr(host_mod._ClientHandler, "start", lambda self: None)

    host = _make_host()
    host.start()
    conn = socket.create_connection(("127.0.0.1", host.port), timeout=3)
    try:
        assert parked.wait(3.0), "accept thread never reached the handshake"
        host.stop(timeout=1.0)
        assert host.is_running is False

        release.set()
        time.sleep(0.8)          # let the accept thread finish its handshake

        assert host._clients == [], (
            "a client attached to a stopped host: it would keep applying "
            "remote input locally"
        )
    finally:
        release.set()
        try:
            conn.close()
        except OSError:
            pass
        host.stop(timeout=1.0)


def test_stop_racing_start_never_raises_or_leaks_a_thread_exception():
    """start() and stop() must be mutually exclusive.

    Three distinct regressions lived here, all reproducible only under a
    concurrent stop():
      * AttributeError — stop() nulled _capture_thread between start()'s
        assignment and its .start() call;
      * RuntimeError('cannot join thread before it is started') — stop()'s
        guard (_listen_sock) was already set, so it joined unstarted threads;
      * OSError WinError 10038 — the accept thread called settimeout() on the
        listening socket outside any try, racing stop() closing it.

    This is a stress test, so it is probabilistic by nature: against the
    unfixed code these surfaced at roughly 3/300 and 1/300, and 120 rounds was
    not enough to catch them. 400 keeps it reliable while still finishing in a
    couple of seconds. The two tests around it are deterministic.
    """
    caught: list = []
    original = threading.excepthook
    threading.excepthook = lambda args: caught.append(
        (args.thread.name, type(args.exc_value).__name__))
    raised: list = []
    try:
        for _ in range(400):
            host = _make_host()
            starter = threading.Thread(target=host.start)
            starter.start()
            for _ in range(2):
                try:
                    host.stop(timeout=0.2)
                except (RuntimeError, AttributeError) as error:
                    raised.append(type(error).__name__)
            starter.join(2.0)
            host.stop(timeout=0.2)
    finally:
        threading.excepthook = original

    assert raised == [], f"stop() raised: {raised[:3]}"
    assert caught == [], f"thread died: {caught[:3]}"


def test_listening_socket_timeout_is_set_before_the_thread_can_see_it():
    """The accept thread must not configure a socket stop() may close."""
    host = _make_host()
    host.start()
    try:
        assert host._listen_sock.gettimeout() == pytest.approx(
            host_mod._ACCEPT_POLL_TIMEOUT_S)
    finally:
        host.stop(timeout=1.0)
