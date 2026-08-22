"""Renegotiation and recvonly-track management for the WebRTC host.

aiortc has no ``removeTransceiver``, so turning viewer video or Opus audio
on and off is not symmetric: enabling adds a recvonly transceiver and
re-offers, disabling can only set the existing one inactive and stop the
receiver. That asymmetry, the host-initiated offer that carries it, and the
re-subscription that runs after each answer are the whole of this mixin.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Mapping, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.webrtc_transport import (
    get_bridge, wait_for_ice_gathering,
)

if TYPE_CHECKING:  # imported lazily at runtime to keep startup cheap
    from je_auto_control.utils.remote_desktop.webrtc_audio import OpusMicReceiver
    from je_auto_control.utils.remote_desktop.webrtc_transport import (
        RTCPeerConnection, WebRTCConfig,
    )


class MediaNegotiationMixin:
    """Media-track half of :class:`WebRTCDesktopHost`.

    Requires the host to provide ``_pc``, ``_config``, ``_viewer_video_task``,
    ``_opus_audio_receiver``, ``_send_ctrl``, ``_spawn_bg``,
    ``_consume_viewer_video`` and ``_start_opus_audio_receive``.
    """

    if TYPE_CHECKING:
        # Declared, never defined: the host class this is mixed into owns
        # every one of these. The block is stripped at runtime, so nothing
        # here can shadow what the host actually binds.
        _pc: Optional["RTCPeerConnection"]
        _config: "WebRTCConfig"
        _viewer_video_task: Optional[asyncio.Task]
        _opus_audio_receiver: Optional["OpusMicReceiver"]
        _send_ctrl: Callable[[Mapping[str, Any]], None]
        _spawn_bg: Callable[[Any], asyncio.Task]
        _consume_viewer_video: Callable[[Any], Coroutine[Any, Any, None]]
        _start_opus_audio_receive: Callable[[Any], None]

    def _maybe_resubscribe_viewer_video(self) -> None:
        if not (self._config.accept_viewer_video
                and self._viewer_video_task is None
                and self._pc is not None):
            return
        video_ts = [
            t for t in self._pc.getTransceivers() if t.kind == "video"
        ]
        for transceiver in video_ts[1:]:  # skip our outbound slot
            track = self._receiver_track(transceiver)
            if track is None:
                continue
            self._viewer_video_task = self._spawn_bg(
                self._consume_viewer_video(track),
            )
            autocontrol_logger.info(
                "webrtc host: re-spawned viewer video consume task",
            )
            return

    def _maybe_resubscribe_viewer_audio(self) -> None:
        if not (self._config.accept_viewer_audio_opus
                and self._opus_audio_receiver is None
                and self._pc is not None):
            return
        for transceiver in self._pc.getTransceivers():
            if transceiver.kind != "audio":
                continue
            track = self._receiver_track(transceiver)
            if track is None:
                continue
            self._start_opus_audio_receive(track)
            return

    @staticmethod
    def _receiver_track(transceiver):
        receiver = transceiver.receiver
        return receiver.track if receiver is not None else None

    async def _async_renegotiate(self) -> None:
        """Host-initiated renegotiation: new offer → viewer over ctrl channel."""
        if self._pc is None:
            return
        try:
            offer = await self._pc.createOffer()
            await self._pc.setLocalDescription(offer)
            await wait_for_ice_gathering(self._pc)
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("renegotiate offer: %r", error)
            return
        self._send_ctrl({
            "type": "renegotiate_offer",
            "sdp": self._pc.localDescription.sdp,
        })
        autocontrol_logger.info("webrtc host: sent renegotiate offer")

    def request_renegotiation(self) -> None:
        """Public sync entry: kick off a fresh SDP exchange over ctrl channel."""
        if self._pc is None:
            return
        get_bridge().call_soon(
            lambda: self._spawn_bg(self._async_renegotiate()),
        )

    def enable_accept_viewer_video(self) -> None:
        """Live-add a recvonly video transceiver and renegotiate.

        ``enable_*`` only adds capacity — aiortc has no ``removeTransceiver``,
        so disabling needs a reconnect (or set the transceiver to inactive).
        """
        if self._pc is None:
            return
        self._config.accept_viewer_video = True
        get_bridge().call_soon(self._add_recvonly_video_and_renegotiate)

    def enable_accept_viewer_audio_opus(self) -> None:
        """Live-add a recvonly audio transceiver and renegotiate."""
        if self._pc is None:
            return
        self._config.accept_viewer_audio_opus = True
        get_bridge().call_soon(self._add_recvonly_audio_and_renegotiate)

    def _add_recvonly_video_and_renegotiate(self) -> None:
        if self._pc is None:
            return
        already = sum(
            1 for t in self._pc.getTransceivers() if t.kind == "video"
        )
        if already < 2:
            self._pc.addTransceiver("video", direction="recvonly")
        self._spawn_bg(self._async_renegotiate())

    def _add_recvonly_audio_and_renegotiate(self) -> None:
        if self._pc is None:
            return
        already = sum(
            1 for t in self._pc.getTransceivers() if t.kind == "audio"
        )
        if already < 1:
            self._pc.addTransceiver("audio", direction="recvonly")
        self._spawn_bg(self._async_renegotiate())

    def disable_accept_viewer_video(self) -> None:
        """Mark the recvonly video slot inactive + stop the consume task."""
        if self._pc is None:
            return
        self._config.accept_viewer_video = False
        get_bridge().call_soon(self._deactivate_recvonly_video)

    def disable_accept_viewer_audio_opus(self) -> None:
        """Mark the recvonly audio slot inactive + stop the Opus receiver."""
        if self._pc is None:
            return
        self._config.accept_viewer_audio_opus = False
        get_bridge().call_soon(self._deactivate_recvonly_audio)

    def _deactivate_recvonly_video(self) -> None:
        if self._pc is None:
            return
        # Find the second video transceiver (the recvonly one); first is our
        # outbound screen track.
        video_ts = [t for t in self._pc.getTransceivers() if t.kind == "video"]
        if len(video_ts) >= 2:
            try:
                video_ts[1].direction = "inactive"
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("inactivate video: %r", error)
        if self._viewer_video_task is not None:
            self._viewer_video_task.cancel()
            self._viewer_video_task = None
        self._spawn_bg(self._async_renegotiate())

    def _deactivate_recvonly_audio(self) -> None:
        if self._pc is None:
            return
        audio_ts = [t for t in self._pc.getTransceivers() if t.kind == "audio"]
        if audio_ts:
            try:
                audio_ts[0].direction = "inactive"
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("inactivate audio: %r", error)
        if self._opus_audio_receiver is not None:
            try:
                self._opus_audio_receiver.stop()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("opus receiver stop: %r", error)
            self._opus_audio_receiver = None
        self._spawn_bg(self._async_renegotiate())
