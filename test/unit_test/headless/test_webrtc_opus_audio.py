"""The Opus mic uplink: a sounddevice thread on one end, asyncio on the other.

`webrtc_audio` sits on a thread boundary in both directions and had no test
at all -- it needs aiortc *and* av to import, so it read 0% on every CI
square until the `[webrtc]` extra joined the measured install.

What the tests below are actually about:

* **The capture callback runs on the sounddevice thread.** It may not touch
  the asyncio queue directly, so it hops through `call_soon_threadsafe` --
  and when the loop has already closed under it (the viewer disconnected
  while a block was in flight) the `RuntimeError` that raises is the normal
  case, not an error to report.
* **The queue drops the oldest block, not the newest.** A bounded queue is
  what keeps mic latency from growing without limit when the encoder falls
  behind; dropping the *newest* block would bound the queue just as well
  and make the audio permanently stale.
* **`recv` mints the presentation timestamps itself.** aiortc packetises
  what it is handed, so a pts that does not advance by exactly the sample
  count is a stream that drifts against its own clock.
* **The receiver's drain loop is a containment boundary.** It runs as a
  fire-and-forget task on the shared bridge loop; every way a track can end
  -- cancellation, `MediaStreamError`, a decode failure, the player being
  stopped underneath it -- has to end the loop quietly rather than take the
  loop down with it.

`AudioCapture` and `AudioPlayer` are replaced with recorders: they are the
sounddevice boundary, and sounddevice is not installed on a CI runner. The
frames are real `av.AudioFrame`s, because their layout is the contract
between this module and aiortc.
"""
from __future__ import annotations

import asyncio

import numpy as np
import pytest

from headless._webrtc_doubles import FrameTrack
from je_auto_control.utils.remote_desktop import webrtc_audio as audio_mod
from je_auto_control.utils.remote_desktop.audio import AudioBackendError
from je_auto_control.utils.remote_desktop.webrtc_audio import (
    OpusMicAudioTrack, OpusMicReceiver,
)


class _FakeCapture:
    instances = []

    def __init__(self, *, on_block, device, sample_rate, channels,
                 block_frames) -> None:
        self.on_block = on_block
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_frames = block_frames
        self.started = False
        self.stopped = False
        self.stop_error = None
        _FakeCapture.instances.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        if self.stop_error is not None:
            raise self.stop_error
        self.stopped = True


class _FakePlayer:
    instances = []

    def __init__(self, *, device, sample_rate, channels) -> None:
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_running = False
        self.played = []
        self.stopped = False
        self.stop_error = None
        _FakePlayer.instances.append(self)

    def start(self) -> None:
        self.is_running = True

    def play(self, pcm_bytes) -> None:
        self.played.append(pcm_bytes)

    def stop(self) -> None:
        if self.stop_error is not None:
            raise self.stop_error
        self.stopped = True


class _Frame:
    """Stands in for an ``av.AudioFrame`` the decoder handed us."""

    def __init__(self, array=None, error=None) -> None:
        self._array = array
        self._error = error

    def to_ndarray(self):
        if self._error is not None:
            raise self._error
        return self._array


@pytest.fixture(autouse=True)
def fake_audio_backend(monkeypatch):
    """Swap the sounddevice boundary out; keep everything above it real."""
    _FakeCapture.instances = []
    _FakePlayer.instances = []
    monkeypatch.setattr(audio_mod, "is_audio_backend_available", lambda: True)
    monkeypatch.setattr(audio_mod, "AudioCapture", _FakeCapture)
    monkeypatch.setattr(audio_mod, "AudioPlayer", _FakePlayer)
    yield
    _FakeCapture.instances = []
    _FakePlayer.instances = []


# --- the viewer's outbound track ----------------------------------------------

def test_track_refuses_to_start_without_a_sounddevice_backend(monkeypatch):
    monkeypatch.setattr(audio_mod, "is_audio_backend_available", lambda: False)

    async def _build():
        OpusMicAudioTrack()

    with pytest.raises(AudioBackendError, match="sounddevice"):
        asyncio.run(_build())


def test_track_starts_capture_at_the_rate_opus_wants():
    async def _build():
        return OpusMicAudioTrack()

    track = asyncio.run(_build())
    [capture] = _FakeCapture.instances
    assert capture.started
    assert (capture.sample_rate, capture.channels) == (48000, 1)
    assert capture.block_frames == 960, "20 ms at 48 kHz"
    assert track.kind == "audio"


def test_track_passes_the_chosen_input_device_through():
    async def _build():
        return OpusMicAudioTrack(sample_rate=16000, channels=2, device=3)

    asyncio.run(_build())
    [capture] = _FakeCapture.instances
    assert (capture.device, capture.sample_rate, capture.channels) == (
        3, 16000, 2,
    )


def test_a_second_start_does_not_open_a_second_stream():
    async def _build():
        track = OpusMicAudioTrack()
        track._start_capture()
        return track

    asyncio.run(_build())
    assert len(_FakeCapture.instances) == 1


def test_a_captured_block_reaches_the_queue_from_the_capture_thread():
    async def _drive():
        track = OpusMicAudioTrack()
        capture = _FakeCapture.instances[0]
        capture.on_block(b"\x01\x02")
        await asyncio.sleep(0)     # let call_soon_threadsafe land
        return track._queue.get_nowait()

    assert asyncio.run(_drive()) == b"\x01\x02"


def test_a_block_arriving_after_the_loop_closed_is_dropped_silently():
    # The sounddevice thread outlives the loop by design: it is stopped from
    # `stop()`, which itself runs after the viewer has already gone away.
    async def _build():
        return OpusMicAudioTrack()

    track = asyncio.run(_build())
    track._on_block(b"\x00\x00")   # the loop from _build is closed now


def test_a_full_queue_drops_the_oldest_block():
    async def _drive():
        track = OpusMicAudioTrack()
        for index in range(track._queue.maxsize):
            track._enqueue(bytes([index]))
        track._enqueue(b"\xff")
        first = track._queue.get_nowait()
        drained = [first]
        while not track._queue.empty():
            drained.append(track._queue.get_nowait())
        return drained

    drained = asyncio.run(_drive())
    assert drained[0] == b"\x01", "the oldest block made room"
    assert drained[-1] == b"\xff", "the newest one is kept"


def test_recv_turns_pcm_into_an_interleaved_s16_frame():
    pcm = np.arange(960, dtype=np.int16).tobytes()

    async def _drive():
        track = OpusMicAudioTrack()
        track._enqueue(pcm)
        return await track.recv()

    frame = asyncio.run(_drive())
    assert frame.sample_rate == 48000
    assert frame.samples == 960
    assert frame.time_base.denominator == 48000
    assert frame.pts == 0


def test_recv_advances_the_timestamp_by_the_samples_it_sent():
    pcm = np.zeros(960, dtype=np.int16).tobytes()

    async def _drive():
        track = OpusMicAudioTrack()
        track._enqueue(pcm)
        track._enqueue(pcm)
        first = await track.recv()
        second = await track.recv()
        return first.pts, second.pts

    # A pts that does not advance by exactly one block's worth of samples is
    # a stream that drifts against the clock aiortc packetises it with.
    assert asyncio.run(_drive()) == (0, 960)


def test_recv_counts_samples_per_channel_on_a_stereo_capture():
    pcm = np.zeros(960 * 2, dtype=np.int16).tobytes()

    async def _drive():
        track = OpusMicAudioTrack(channels=2)
        track._enqueue(pcm)
        track._enqueue(pcm)
        await track.recv()
        return (await track.recv()).pts

    assert asyncio.run(_drive()) == 960


def test_stopping_the_track_stops_the_capture_once():
    async def _drive():
        track = OpusMicAudioTrack()
        track.stop()
        track.stop()
        return track

    asyncio.run(_drive())
    [capture] = _FakeCapture.instances
    assert capture.stopped


def test_a_capture_that_fails_to_close_still_leaves_the_track_stopped():
    async def _drive():
        track = OpusMicAudioTrack()
        _FakeCapture.instances[0].stop_error = OSError("device unplugged")
        track.stop()
        return track

    track = asyncio.run(_drive())
    assert track._capture is None


# --- the host's inbound receiver ----------------------------------------------

def test_receiver_refuses_to_start_without_a_sounddevice_backend(monkeypatch):
    monkeypatch.setattr(audio_mod, "is_audio_backend_available", lambda: False)
    with pytest.raises(AudioBackendError, match="sounddevice"):
        OpusMicReceiver()


def test_receiver_opens_the_player_at_the_requested_rate():
    OpusMicReceiver(sample_rate=16000, channels=2, device=4)
    [player] = _FakePlayer.instances
    assert (player.device, player.sample_rate, player.channels) == (
        4, 16000, 2,
    )
    assert player.is_running


def test_receiver_plays_the_decoded_frames_it_drains():
    samples = np.array([[1, 2, 3, 4]], dtype=np.int16)

    async def _drive():
        receiver = OpusMicReceiver()
        track = FrameTrack(_Frame(samples))
        receiver.consume(track)
        await receiver._task
        return receiver

    asyncio.run(_drive())
    [player] = _FakePlayer.instances
    assert player.played == [samples.tobytes()]


def test_receiver_converts_a_float_frame_before_playing_it():
    # av hands back whatever the decoder produced; the player only speaks
    # int16 PCM, so a float layout has to be narrowed rather than passed on.
    async def _drive():
        receiver = OpusMicReceiver()
        receiver.consume(FrameTrack(_Frame(np.array([[1.0, 2.0]],
                                                dtype=np.float32))))
        await receiver._task

    asyncio.run(_drive())
    [player] = _FakePlayer.instances
    assert player.played == [np.array([[1, 2]], dtype=np.int16).tobytes()]


def test_a_second_consume_does_not_start_a_second_drain():
    async def _drive():
        receiver = OpusMicReceiver()
        track = FrameTrack(_Frame(np.array([[1]], dtype=np.int16)))
        receiver.consume(track)
        first = receiver._task
        receiver.consume(FrameTrack())
        assert receiver._task is first
        await first

    asyncio.run(_drive())


def test_an_undecodable_frame_is_skipped_rather_than_ending_the_stream():
    good = np.array([[5, 6]], dtype=np.int16)

    async def _drive():
        receiver = OpusMicReceiver()
        receiver.consume(FrameTrack(_Frame(error=ValueError("bad plane")),
                                _Frame(good)))
        await receiver._task

    asyncio.run(_drive())
    [player] = _FakePlayer.instances
    assert player.played == [good.tobytes()], "the good frame still played"


def test_the_drain_stops_when_the_player_is_no_longer_running():
    async def _drive():
        receiver = OpusMicReceiver()
        _FakePlayer.instances[0].is_running = False
        track = FrameTrack(_Frame(np.array([[1]], dtype=np.int16)),
                       _Frame(np.array([[2]], dtype=np.int16)))
        receiver.consume(track)
        await receiver._task
        return track

    track = asyncio.run(_drive())
    assert len(track.frames) == 1, "it did not keep pulling from the track"
    assert _FakePlayer.instances[0].played == []


def test_the_drain_ends_quietly_when_the_track_dies():
    # The viewer closing its tab surfaces here as an OSError out of recv;
    # this task runs on the shared bridge loop, so it may not propagate.
    async def _drive():
        receiver = OpusMicReceiver()
        receiver.consume(FrameTrack(ending=OSError("connection reset")))
        await receiver._task

    asyncio.run(_drive())


def test_stopping_the_receiver_cancels_the_drain_and_closes_the_player():
    async def _drive():
        receiver = OpusMicReceiver()
        receiver.consume(FrameTrack(_Frame(np.array([[1]], dtype=np.int16))))
        task = receiver._task
        receiver.stop()
        assert receiver._task is None
        await asyncio.sleep(0)
        return task

    task = asyncio.run(_drive())
    assert task.cancelled() or task.done()
    assert _FakePlayer.instances[0].stopped


def test_stopping_a_receiver_that_never_consumed_still_closes_the_player():
    receiver = OpusMicReceiver()
    receiver.stop()
    assert _FakePlayer.instances[0].stopped


def test_a_player_that_fails_to_close_does_not_escape_stop():
    receiver = OpusMicReceiver()
    _FakePlayer.instances[0].stop_error = OSError("stream already closed")
    receiver.stop()
