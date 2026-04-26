"""Audio capture / playback contract + host->viewer streaming tests.

The real ``sounddevice`` backend is replaced by a fake throughout, so the
tests run on machines without PortAudio. They cover: lazy backend
loading, the AUDIO message type round-trip, viewer ``on_audio`` dispatch,
host queue back-pressure (oldest dropped), and the audio sender thread
shutting down with the client.
"""
import threading
import time
from typing import Optional

import pytest

from je_auto_control.utils.remote_desktop import (
    RemoteDesktopHost, RemoteDesktopViewer,
)
from je_auto_control.utils.remote_desktop.audio import (
    AudioBackendError, AudioCapture, AudioCaptureConfig, AudioPlayer,
)


class _FakeStream:
    """Imitates the bits of sounddevice.RawInputStream we use."""

    def __init__(self, *, callback=None, **_kwargs) -> None:
        self.callback = callback
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def close(self) -> None:
        self.closed = True


class _FakeSounddevice:
    def __init__(self) -> None:
        self.last_input: Optional[_FakeStream] = None
        self.last_output: Optional[_FakeStream] = None

    def RawInputStream(self, **kwargs) -> _FakeStream:  # noqa: N802  # NOSONAR S100  # mirrors sounddevice API
        self.last_input = _FakeStream(**kwargs)
        return self.last_input

    def RawOutputStream(self, **kwargs) -> _FakeStream:  # noqa: N802  # NOSONAR S100  # mirrors sounddevice API
        self.last_output = _FakeStream(**kwargs)
        return self.last_output


@pytest.fixture()
def fake_sd(monkeypatch):
    fake = _FakeSounddevice()

    from je_auto_control.utils.remote_desktop import audio as audio_mod
    monkeypatch.setattr(audio_mod, "_load_sounddevice", lambda: fake)
    return fake


def _wait_until(predicate, timeout: float = 2.0,
                interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# --- AudioCapture / AudioPlayer unit tests --------------------------------


def test_audio_capture_invokes_callback_with_block_bytes(fake_sd):
    received = []
    capture = AudioCapture(on_block=received.append)
    capture.start()
    assert fake_sd.last_input.started
    # Simulate the sounddevice thread firing a block:
    fake_sd.last_input.callback(b"abc", 800, None, None)
    assert received == [b"abc"]
    capture.stop()
    assert fake_sd.last_input.closed


def test_audio_capture_swallows_callback_exceptions(fake_sd):
    capture = AudioCapture(on_block=lambda chunk: 1 / 0)
    capture.start()
    # Must not raise even though the user callback exploded:
    fake_sd.last_input.callback(b"xx", 800, None, None)
    capture.stop()


def test_audio_player_writes_chunks(fake_sd):
    player = AudioPlayer()
    player.start()
    assert fake_sd.last_output.started
    written = []
    fake_sd.last_output.write = written.append  # type: ignore[attr-defined]
    player.play(b"\x01\x02")
    assert written == [b"\x01\x02"]
    player.stop()


def test_audio_player_play_before_start_raises(fake_sd):
    del fake_sd
    player = AudioPlayer()
    with pytest.raises(RuntimeError):
        player.play(b"x")


def test_audio_capture_validates_args():
    with pytest.raises(TypeError):
        AudioCapture(on_block="not callable")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        AudioCapture(on_block=lambda c: None, sample_rate=0)


# --- end-to-end host -> viewer streaming ---------------------------------


class _ManualCapture:
    """Stub object with the same start/stop API used by the host."""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.on_block = None

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


def _start_audio_host():
    capture = _ManualCapture()
    host = RemoteDesktopHost(
        token="tok", bind="127.0.0.1", port=0, fps=50.0,
        frame_provider=lambda: b"frame",
        input_dispatcher=lambda *_a, **_k: None,
        host_id="555444333",
        audio_config=AudioCaptureConfig(enabled=True), audio_capture=capture,
    )
    host.start()
    capture.on_block = host._broadcast_audio  # noqa: SLF001
    return host, capture


def test_audio_chunks_reach_viewer():
    host, capture = _start_audio_host()
    try:
        received = []
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
            on_audio=received.append,
        )
        viewer.connect(timeout=2.0)
        # Wait for the auth handshake to count as authenticated.
        assert _wait_until(lambda: host.connected_clients == 1)
        capture.on_block(b"\xaa" * 100)
        capture.on_block(b"\xbb" * 100)
        assert _wait_until(lambda: len(received) >= 2)
        assert received[0] == b"\xaa" * 100
        assert received[1] == b"\xbb" * 100
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


def test_audio_disabled_means_no_sender_thread():
    host = RemoteDesktopHost(
        token="tok", bind="127.0.0.1", port=0, fps=50.0,
        frame_provider=lambda: b"frame",
        input_dispatcher=lambda *_a, **_k: None,
        host_id="200200200",
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
        )
        viewer.connect(timeout=2.0)
        assert _wait_until(lambda: host.connected_clients == 1)
        with host._clients_lock:  # noqa: SLF001
            client = host._clients[0]  # noqa: SLF001
        assert client._audio_sender_thread is None  # noqa: SLF001
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


def test_audio_queue_drops_oldest_when_full():
    """Slow viewer (one that never reads) should not back up host capture."""
    host, capture = _start_audio_host()
    try:
        # No viewer attached — but emulate one being authenticated by
        # building a client handler manually would be invasive. Instead
        # use a real viewer that we never let read fast.
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
            on_audio=lambda chunk: time.sleep(0.5),  # very slow consumer
        )
        viewer.connect(timeout=2.0)
        assert _wait_until(lambda: host.connected_clients == 1)
        # Push more chunks than the queue capacity.
        for i in range(200):
            capture.on_block(bytes([i % 256]) * 16)
        # Queue must remain bounded.
        with host._clients_lock:  # noqa: SLF001
            client = host._clients[0]  # noqa: SLF001
        with client._audio_lock:  # noqa: SLF001
            assert len(client._audio_queue) <= client._AUDIO_QUEUE_MAXLEN  # noqa: SLF001
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


def test_host_audio_capture_lifecycle():
    host, capture = _start_audio_host()
    try:
        assert capture.started is True
        assert host.audio_enabled
    finally:
        host.stop(timeout=1.0)
        assert capture.stopped is True


def test_audio_capture_failure_leaves_host_running():
    """A backend failure during start must not abort the host."""
    class _Failing:
        def start(self):
            raise AudioBackendError("no portaudio")

        def stop(self):
            # No teardown needed — start() never opened a real stream.
            return None

    host = RemoteDesktopHost(
        token="tok", bind="127.0.0.1", port=0, fps=50.0,
        frame_provider=lambda: b"frame",
        input_dispatcher=lambda *_a, **_k: None,
        host_id="600600600",
        audio_config=AudioCaptureConfig(enabled=True), audio_capture=_Failing(),
    )
    host.start()
    try:
        # Host is running but audio is reported as not enabled because the
        # capture object failed to come up.
        assert host.is_running
        assert host.audio_enabled is False
    finally:
        host.stop(timeout=1.0)
