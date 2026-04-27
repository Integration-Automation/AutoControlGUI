"""Aiortc audio track for the viewer mic uplink.

Lets aiortc encode the mic stream as Opus (~6× smaller than the raw
PCM-over-DataChannel path in :mod:`webrtc_mic`). Capture stays on
sounddevice via :class:`AudioCapture`; we just bridge the int16 PCM
blocks into ``av.AudioFrame`` objects that aiortc consumes.

Usage on the viewer side:
  * Host adds a recvonly audio transceiver in its offer.
  * Viewer attaches a :class:`OpusMicAudioTrack` to that transceiver
    before ``createAnswer``; aiortc negotiates Opus.
  * Host receives via ``pc.on('track')`` for ``kind == 'audio'``,
    decodes frames, and feeds ``AudioPlayer`` (see
    :class:`OpusMicReceiver`).
"""
from __future__ import annotations

import asyncio
import fractions
import threading
from typing import Optional

try:
    import av  # type: ignore
    import numpy as np
    from aiortc import MediaStreamTrack
except ImportError as exc:  # pragma: no cover - optional dep
    raise ImportError(
        "Opus audio uplink requires the 'webrtc' extra (aiortc + av).",
    ) from exc

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.audio import (
    AudioBackendError, AudioCapture, AudioPlayer, is_audio_backend_available,
)


_DEFAULT_SAMPLE_RATE = 48000  # Opus's preferred rate
_DEFAULT_CHANNELS = 1
_BLOCK_FRAMES = 960  # 20 ms @ 48 kHz


class OpusMicAudioTrack(MediaStreamTrack):
    """Pulls int16 PCM blocks from sounddevice and emits ``av.AudioFrame``.

    The capture thread blocks on sounddevice; ``recv`` blocks on an
    asyncio ``Queue`` that the capture callback feeds. aiortc handles
    Opus encoding / packetization downstream.
    """
    kind = "audio"

    def __init__(self, sample_rate: int = _DEFAULT_SAMPLE_RATE,
                 channels: int = _DEFAULT_CHANNELS,
                 device: Optional[int] = None) -> None:
        super().__init__()
        if not is_audio_backend_available():
            raise AudioBackendError(
                "sounddevice not available; install with pip install sounddevice",
            )
        self._sample_rate = sample_rate
        self._channels = channels
        self._device = device
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._loop = asyncio.get_event_loop()
        self._timestamp = 0
        self._capture: Optional[AudioCapture] = None
        self._lock = threading.Lock()
        self._start_capture()

    def _start_capture(self) -> None:
        with self._lock:
            if self._capture is not None:
                return
            self._capture = AudioCapture(
                on_block=self._on_block,
                device=self._device,
                sample_rate=self._sample_rate,
                channels=self._channels,
                block_frames=_BLOCK_FRAMES,
            )
            self._capture.start()
        autocontrol_logger.info(
            "OpusMicAudioTrack: capture started (%d Hz)", self._sample_rate,
        )

    def _on_block(self, pcm_bytes: bytes) -> None:
        # Called from the sounddevice thread.
        try:
            self._loop.call_soon_threadsafe(self._enqueue, pcm_bytes)
        except RuntimeError:
            pass  # loop closed; drop block silently

    def _enqueue(self, pcm_bytes: bytes) -> None:
        if self._queue.full():
            try:
                self._queue.get_nowait()  # drop oldest to keep latency bounded
            except asyncio.QueueEmpty:
                pass
        try:
            self._queue.put_nowait(pcm_bytes)
        except asyncio.QueueFull:
            pass

    async def recv(self) -> "av.AudioFrame":
        pcm_bytes = await self._queue.get()
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        # av.AudioFrame.from_ndarray expects shape (channels, samples) for
        # planar layouts; for "s16" (interleaved) it expects (1, total).
        layout = "mono" if self._channels == 1 else "stereo"
        frame = av.AudioFrame.from_ndarray(
            samples.reshape(1, -1), format="s16", layout=layout,
        )
        frame.sample_rate = self._sample_rate
        frame.pts = self._timestamp
        frame.time_base = fractions.Fraction(1, self._sample_rate)
        self._timestamp += samples.shape[0] // self._channels
        return frame

    def stop(self) -> None:
        try:
            super().stop()
        finally:
            with self._lock:
                if self._capture is not None:
                    try:
                        self._capture.stop()
                    except (RuntimeError, OSError) as error:
                        autocontrol_logger.debug("opus mic stop: %r", error)
                    self._capture = None


class OpusMicReceiver:
    """Host-side: pull frames from the incoming audio track and play them."""

    def __init__(self, sample_rate: int = _DEFAULT_SAMPLE_RATE,
                 channels: int = _DEFAULT_CHANNELS,
                 device: Optional[int] = None) -> None:
        if not is_audio_backend_available():
            raise AudioBackendError(
                "sounddevice not available; install with pip install sounddevice",
            )
        self._sample_rate = sample_rate
        self._channels = channels
        self._player = AudioPlayer(
            device=device, sample_rate=sample_rate, channels=channels,
        )
        self._player.start()
        self._task: Optional[asyncio.Task] = None
        self._stopped = False

    def consume(self, track) -> None:
        """Spawn a background task that drains ``track.recv()`` into the player."""
        if self._task is not None:
            return
        self._task = asyncio.ensure_future(self._loop(track))

    async def _loop(self, track) -> None:
        from aiortc.mediastreams import MediaStreamError
        try:
            while not self._stopped:
                frame = await track.recv()
                if not bool(self._player.is_running):
                    return
                # av.AudioFrame -> int16 PCM bytes
                try:
                    arr = frame.to_ndarray()
                except (ValueError, RuntimeError) as error:
                    autocontrol_logger.debug("audio frame to_ndarray: %r", error)
                    continue
                if arr.dtype != np.int16:
                    arr = arr.astype(np.int16)
                self._player.play(arr.tobytes())
        except (asyncio.CancelledError, MediaStreamError):
            autocontrol_logger.info("opus mic receiver ended")
        except (OSError, RuntimeError) as error:
            autocontrol_logger.info("opus mic receiver ended: %r", error)

    def stop(self) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            self._task = None
        try:
            self._player.stop()
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("audio player stop: %r", error)


__all__ = ["OpusMicAudioTrack", "OpusMicReceiver"]
