"""Audit round 3 regressions for RemoteDesktopHost (loopback sockets only).

Covers:
* Finding 1 — dead handlers must be reaped *before* the max_clients check,
  otherwise a full table of disconnected handlers rejects every new viewer
  forever.
* Finding 3 — the initial cursor + frame are sent from the per-client sender
  thread, not the shared accept thread, so a slow-reading viewer cannot block
  new connections.
"""
import threading
import time

from je_auto_control.utils.remote_desktop import (
    RemoteDesktopHost, RemoteDesktopViewer,
)
from je_auto_control.utils.remote_desktop.host import _ClientHandler


def _wait_until(predicate, timeout: float = 5.0,
                interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class _DeadHandler:
    """Stand-in for a client whose viewer already disconnected."""

    def __init__(self) -> None:
        self._shutdown = threading.Event()
        self._shutdown.set()
        self.authenticated = False

    def stop(self) -> None:
        pass

    def _close(self) -> None:
        pass


def _make_host(**kwargs) -> RemoteDesktopHost:
    params = dict(
        token="tok", bind="127.0.0.1", port=0,
        frame_provider=lambda: b"x",
        input_dispatcher=lambda message: None,
        enable_cursor_broadcast=False,
    )
    params.update(kwargs)
    return RemoteDesktopHost(**params)


def test_reap_runs_before_capacity_check_admits_new_viewer():
    """A table full of dead handlers must not permanently reject new viewers."""
    host = _make_host(max_clients=1)
    host.start()
    try:
        # Seed a dead handler so the (max_clients==1) table looks "full".
        with host._clients_lock:
            host._clients.append(_DeadHandler())
        viewer = RemoteDesktopViewer("127.0.0.1", host.port, "tok")
        viewer.connect(timeout=5.0)
        try:
            assert _wait_until(lambda: host.connected_clients == 1)
        finally:
            viewer.disconnect(timeout=2.0)
    finally:
        host.stop(timeout=2.0)


def test_slow_viewer_initial_frame_does_not_block_accept(monkeypatch):
    """Blocking the initial frame send must stall only that viewer's thread."""
    block = threading.Event()

    def _blocking_initial_frame(self) -> None:
        # Emulate a viewer that authenticated then stopped reading: the
        # initial full-screen frame send parks here until released.
        block.wait(timeout=5.0)

    monkeypatch.setattr(
        _ClientHandler, "_send_initial_frame", _blocking_initial_frame,
    )
    host = _make_host(max_clients=4)
    host.start()
    viewers = []
    try:
        for _ in range(2):
            viewer = RemoteDesktopViewer("127.0.0.1", host.port, "tok")
            # Pre-fix the accept thread blocks inside viewer #1's initial
            # frame send, so viewer #2 never receives AUTH_CHALLENGE and this
            # connect() raises on timeout.
            viewer.connect(timeout=3.0)
            viewers.append(viewer)
        assert _wait_until(lambda: host.connected_clients == 2)
    finally:
        block.set()
        for viewer in viewers:
            viewer.disconnect(timeout=2.0)
        host.stop(timeout=2.0)
