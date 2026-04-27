"""Viewer → host microphone uplink over a dedicated DataChannel.

Why a DataChannel instead of an aiortc audio track? Reusing the existing
``AudioCapture`` / ``AudioPlayer`` (sounddevice + int16 PCM) keeps this
self-contained and lets us integrate without restarting the
PeerConnection. Bandwidth cost: 16 kHz × 16-bit mono ≈ 32 KB/s — fine
for voice on any reasonable link. If you need lower bandwidth, swap to
an Opus-based aiortc audio track in a follow-up.

Both sides have to opt in: the host runs a :class:`MicUplinkReceiver`
(playback) and the viewer runs a :class:`MicUplinkSender` (capture). The
receiver also gates by the host's ``allow_audio`` permission so a
view-only session can't have someone shouting through the host.
"""
from __future__ import annotations

import threading
from typing import Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.audio import (
    AudioBackendError, AudioCapture, AudioPlayer, is_audio_backend_available,
)
from je_auto_control.utils.remote_desktop.webrtc_transport import get_bridge


_DEFAULT_SAMPLE_RATE = 16000
_DEFAULT_CHANNELS = 1
_DEFAULT_BLOCK_FRAMES = 800  # 50 ms at 16 kHz


class MicUplinkSender:
    """Viewer side: stream microphone PCM to the host via a DataChannel."""

    def __init__(self, channel, *,
                 sample_rate: int = _DEFAULT_SAMPLE_RATE,
                 channels: int = _DEFAULT_CHANNELS,
                 block_frames: int = _DEFAULT_BLOCK_FRAMES,
                 device: Optional[int] = None) -> None:
        if channel is None:
            raise ValueError("mic uplink requires a DataChannel")
        self._channel = channel
        self._sample_rate = sample_rate
        self._channels = channels
        self._block_frames = block_frames
        self._device = device
        self._capture: Optional[AudioCapture] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if not is_audio_backend_available():
            raise AudioBackendError(
                "sounddevice not available; install with pip install sounddevice",
            )
        with self._lock:
            if self._capture is not None:
                return
            self._capture = AudioCapture(
                on_block=self._on_block,
                device=self._device,
                sample_rate=self._sample_rate,
                channels=self._channels,
                block_frames=self._block_frames,
            )
            self._capture.start()
        autocontrol_logger.info("mic uplink: capture started (%d Hz)",
                                self._sample_rate)

    def stop(self) -> None:
        with self._lock:
            if self._capture is None:
                return
            try:
                self._capture.stop()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("mic uplink stop: %r", error)
            self._capture = None

    def is_running(self) -> bool:
        return self._capture is not None and bool(self._capture.is_running)

    def _on_block(self, pcm_bytes: bytes) -> None:
        if self._channel is None:
            return
        get_bridge().call_soon(self._safe_send, pcm_bytes)

    def _safe_send(self, data: bytes) -> None:
        try:
            self._channel.send(data)
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("mic chunk send: %r", error)


class MicUplinkReceiver:
    """Host side: play PCM chunks arriving on the mic DataChannel."""

    def __init__(self, *,
                 sample_rate: int = _DEFAULT_SAMPLE_RATE,
                 channels: int = _DEFAULT_CHANNELS,
                 device: Optional[int] = None) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._device = device
        self._player: Optional[AudioPlayer] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if not is_audio_backend_available():
            raise AudioBackendError(
                "sounddevice not available; install with pip install sounddevice",
            )
        with self._lock:
            if self._player is not None:
                return
            self._player = AudioPlayer(
                device=self._device,
                sample_rate=self._sample_rate,
                channels=self._channels,
            )
            self._player.start()
        autocontrol_logger.info("mic uplink: playback started (%d Hz)",
                                self._sample_rate)

    def stop(self) -> None:
        with self._lock:
            if self._player is None:
                return
            try:
                self._player.stop()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("mic uplink stop: %r", error)
            self._player = None

    def is_running(self) -> bool:
        return self._player is not None and bool(self._player.is_running)

    def on_chunk(self, chunk) -> None:
        """Feed a PCM chunk into the player. Tolerates non-bytes silently."""
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            return
        with self._lock:
            player = self._player
        if player is None or not bool(player.is_running):
            return
        try:
            player.play(bytes(chunk))
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("mic playback: %r", error)


__all__ = ["MicUplinkSender", "MicUplinkReceiver"]
