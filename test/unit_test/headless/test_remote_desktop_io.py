"""End-to-end tests for RemoteDesktopHost <-> RemoteDesktopViewer.

These exercise real localhost sockets but stub the screen-capture and
input-dispatch sides so no OS-level mouse/keyboard interaction happens.
"""
import time
from typing import List

import pytest

from je_auto_control.utils.remote_desktop import (
    RemoteDesktopHost, RemoteDesktopViewer,
)
from je_auto_control.utils.remote_desktop.protocol import AuthenticationError


def _wait_until(predicate, timeout: float = 2.0,
                interval: float = 0.02) -> bool:
    """Poll until ``predicate`` returns True or ``timeout`` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture()
def fake_frame_provider():
    """Frame provider returning sequential payloads so tests can spot updates."""
    state = {"i": 0}

    def provide() -> bytes:
        state["i"] += 1
        return f"frame-{state['i']}".encode("ascii")

    return provide


@pytest.fixture()
def host_factory(fake_frame_provider):
    """Build hosts with a stub frame provider; clean up on teardown."""
    started: List[RemoteDesktopHost] = []
    captured_input: List[dict] = []

    def make(token: str = "secret",
             dispatcher=None,
             fps: float = 50.0) -> RemoteDesktopHost:
        host = RemoteDesktopHost(
            token=token,
            bind="127.0.0.1",
            port=0,
            fps=fps,
            quality=70,
            frame_provider=fake_frame_provider,
            input_dispatcher=dispatcher or captured_input.append,
        )
        host.start()
        started.append(host)
        return host

    yield make, captured_input
    for host in started:
        host.stop(timeout=1.0)


def _connect_viewer(host: RemoteDesktopHost, *, token: str = "secret"
                    ) -> "ViewerHarness":
    received: List[bytes] = []
    errors: List[Exception] = []
    viewer = RemoteDesktopViewer(
        host="127.0.0.1", port=host.port, token=token,
        on_frame=received.append, on_error=errors.append,
    )
    viewer.connect(timeout=2.0)
    return ViewerHarness(viewer=viewer, frames=received, errors=errors)


class ViewerHarness:
    """Wrapper that pairs a viewer with the lists its callbacks fill."""

    def __init__(self, *, viewer: RemoteDesktopViewer,
                 frames: List[bytes], errors: List[Exception]) -> None:
        self.viewer = viewer
        self.frames = frames
        self.errors = errors

    def close(self) -> None:
        self.viewer.disconnect(timeout=1.0)


def test_viewer_authenticates_and_receives_frames(host_factory):
    make_host, _ = host_factory
    host = make_host()
    harness = _connect_viewer(host)
    try:
        assert _wait_until(lambda: len(harness.frames) >= 2, timeout=2.0)
        assert all(frame.startswith(b"frame-") for frame in harness.frames)
    finally:
        harness.close()


def test_viewer_with_wrong_token_is_rejected(host_factory):
    make_host, _ = host_factory
    host = make_host(token="right")
    viewer = RemoteDesktopViewer(
        host="127.0.0.1", port=host.port, token="wrong",
    )
    with pytest.raises(AuthenticationError):
        viewer.connect(timeout=2.0)
    assert host.connected_clients == 0


def test_viewer_input_reaches_host_dispatcher(host_factory):
    make_host, captured_input = host_factory
    host = make_host()
    harness = _connect_viewer(host)
    try:
        harness.viewer.send_input({"action": "mouse_move", "x": 7, "y": 9})
        harness.viewer.send_input({"action": "type", "text": "hi"})
        assert _wait_until(lambda: len(captured_input) >= 2, timeout=2.0)
        assert captured_input[0] == {"action": "mouse_move", "x": 7, "y": 9}
        assert captured_input[1] == {"action": "type", "text": "hi"}
    finally:
        harness.close()


def test_host_reports_connected_clients(host_factory):
    make_host, _ = host_factory
    host = make_host()
    harness = _connect_viewer(host)
    try:
        assert _wait_until(lambda: host.connected_clients == 1, timeout=2.0)
    finally:
        harness.close()
    assert _wait_until(lambda: host.connected_clients == 0, timeout=2.0)


def test_host_stop_disconnects_viewer(host_factory):
    make_host, _ = host_factory
    host = make_host()
    harness = _connect_viewer(host)
    try:
        assert _wait_until(lambda: len(harness.frames) >= 1, timeout=2.0)
        host.stop(timeout=1.0)
        assert _wait_until(lambda: not harness.viewer.connected, timeout=2.0)
    finally:
        harness.close()


def test_host_rejects_invalid_construction():
    with pytest.raises(ValueError):
        RemoteDesktopHost(token="")
    with pytest.raises(ValueError):
        RemoteDesktopHost(token="t", fps=0)
    with pytest.raises(ValueError):
        RemoteDesktopHost(token="t", quality=99)


def test_viewer_send_before_connect_raises():
    viewer = RemoteDesktopViewer(host="127.0.0.1", port=1, token="t")
    with pytest.raises(ConnectionError):
        viewer.send_input({"action": "ping"})
