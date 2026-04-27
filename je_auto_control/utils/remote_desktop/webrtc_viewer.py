"""WebRTC viewer: receives screen video and sends input to the host.

Pair with :class:`WebRTCDesktopHost`. The viewer is offer-consumer: caller
takes the host's offer SDP, calls :meth:`process_offer` to get an answer
SDP, ships it back out-of-band, then drives input via :meth:`send_input`.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Callable, Mapping, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.webrtc_transport import (
    RTCPeerConnection, RTCSessionDescription, WebRTCConfig,
    get_bridge, wait_for_ice_gathering,
)


_OFFER_TIMEOUT_S = 12.0


FrameCallback = Callable[["object"], None]
StateCallback = Callable[[str], None]
AuthCallback = Callable[[bool], None]
FingerprintCallback = Callable[[str], None]
InboxListingCallback = Callable[[list], None]
InboxOpResultCallback = Callable[[str, bool, Optional[str]], None]


class WebRTCDesktopViewer:
    """Single-host viewer with manual SDP exchange.

    ``on_frame(av_frame)`` fires on the asyncio thread every time a video
    frame lands. The GUI side converts the frame to ``QImage`` and emits a
    Qt signal so the actual paint happens on the Qt thread.
    """

    def __init__(self, *, token: str,
                 config: Optional[WebRTCConfig] = None,
                 viewer_id: Optional[str] = None,
                 on_frame: Optional[FrameCallback] = None,
                 on_state_change: Optional[StateCallback] = None,
                 on_auth_result: Optional[AuthCallback] = None,
                 on_fingerprint: Optional[FingerprintCallback] = None) -> None:
        if not token:
            raise ValueError("WebRTC viewer requires a non-empty token")
        self._token = token
        self._config = config or WebRTCConfig()
        self._viewer_id = viewer_id
        self._on_frame = on_frame
        self._on_state_change = on_state_change
        self._on_auth_result = on_auth_result
        self._on_fingerprint = on_fingerprint
        self._pc: Optional[RTCPeerConnection] = None
        self._control_channel = None
        self._mic_channel = None
        self._mic_sender = None  # Optional[MicUplinkSender]
        self._files_channel = None
        self._files_receiver = None  # Optional[FileTransferReceiver]
        self._on_file_received = None
        self._on_inbox_listing: Optional[InboxListingCallback] = None
        self._on_inbox_op_result: Optional[InboxOpResultCallback] = None
        self._viewer_screen_track = None
        self._opus_audio_track = None
        self._host_voice_receiver = None  # OpusMicReceiver-like
        self._receive_task: Optional[asyncio.Task] = None
        self._authenticated = False
        self._read_only = False
        self._host_fingerprint: Optional[str] = None
        self._closed = threading.Event()
        # Pin fire-and-forget asyncio tasks so they aren't reaped before
        # they finish (S7502). Tasks self-discard via a done callback.
        self._background_tasks: set = set()

    def _spawn_bg(self, coro) -> "asyncio.Task":
        task = asyncio.ensure_future(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    # --- public sync API ----------------------------------------------------

    def process_offer(self, offer_sdp: str,
                      expected_dtls_fingerprint: Optional[str] = None) -> str:
        """Apply host offer, build & return answer SDP (with ICE).

        If ``expected_dtls_fingerprint`` is provided, the offer's
        ``a=fingerprint`` line must match before any DTLS handshake; raises
        :class:`FingerprintMismatchError` otherwise (catches a hijacked
        signaling slot before encrypted bytes flow).
        """
        if not offer_sdp or not offer_sdp.strip():
            raise ValueError("offer_sdp is empty")
        if expected_dtls_fingerprint:
            from je_auto_control.utils.remote_desktop.fingerprint import (
                verify_dtls_fingerprint,
            )
            verify_dtls_fingerprint(offer_sdp, expected_dtls_fingerprint)
        future = get_bridge().submit(self._async_process_offer(offer_sdp))
        return future.result(timeout=_OFFER_TIMEOUT_S)

    def send_input(self, payload: Mapping[str, Any]) -> None:
        """Send an input dict to the host (mouse/keyboard event)."""
        self._send({"type": "input", "payload": dict(payload)})

    def request_send_sas(self) -> None:
        """Ask the host to fire Ctrl+Alt+Del (Windows-only at the host)."""
        self._send({"type": "send_sas"})

    def enable_mic_send(self) -> None:
        """Start streaming local microphone PCM to the host."""
        if self._mic_sender is not None:
            return
        if self._mic_channel is None:
            raise RuntimeError("mic channel not open yet; connect first")
        from je_auto_control.utils.remote_desktop.webrtc_mic import (
            MicUplinkSender,
        )
        self._mic_sender = MicUplinkSender(self._mic_channel)
        self._mic_sender.start()

    def disable_mic_send(self) -> None:
        if self._mic_sender is None:
            return
        try:
            self._mic_sender.stop()
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("mic sender stop: %r", error)
        self._mic_sender = None

    @property
    def mic_active(self) -> bool:
        return self._mic_sender is not None and self._mic_sender.is_running()

    def send_file(self, local_path, remote_name: Optional[str] = None,
                  on_progress: Optional[Callable[[int, int], None]] = None) -> None:
        """Stream a local file to the host's inbox via the files DataChannel."""
        if self._files_channel is None:
            raise RuntimeError("files channel not open yet")
        from je_auto_control.utils.remote_desktop.webrtc_files import (
            FileTransferSender,
        )
        FileTransferSender(self._files_channel).send(
            local_path, remote_name=remote_name, on_progress=on_progress,
        )

    def set_file_received_callback(self, callback) -> None:
        """Register ``cb(path)`` for files the host pushes to the viewer."""
        self._on_file_received = callback

    def set_inbox_listing_callback(self, callback) -> None:
        """Register ``cb(files: list[dict])`` for list_inbox responses."""
        self._on_inbox_listing = callback

    def set_inbox_op_result_callback(self, callback) -> None:
        """Register ``cb(name: str, ok: bool, error: Optional[str])``."""
        self._on_inbox_op_result = callback

    def request_inbox_listing(self) -> None:
        """Ask the host to send its current inbox file listing."""
        self._send({"type": "list_inbox"})

    def request_inbox_file(self, name: str) -> None:
        """Ask the host to push a specific inbox file via the files channel."""
        if not name:
            raise ValueError("name required")
        self._send({"type": "request_file", "name": name})

    def delete_inbox_file(self, name: str) -> None:
        """Ask the host to delete a file from its inbox."""
        if not name:
            raise ValueError("name required")
        self._send({"type": "delete_inbox_file", "name": name})

    def request_renegotiation(self) -> None:
        """Ask the host to send a fresh offer (so we can attach new tracks)."""
        self._send({"type": "renegotiate_request"})

    def toggle_share_screen(self, enable: bool) -> None:
        """Live-toggle viewer→host screen share.

        OFF path is in-place: ``replaceTrack(None)`` and stop the track,
        keeping the SDP direction so the slot survives. Host's
        ``_consume_viewer_video`` sees a clean ``MediaStreamError`` and
        exits its task, but the transceiver remains.

        ON path always renegotiates: a fresh ``ScreenVideoTrack`` is
        created and the host needs a new ``track`` event to spawn its
        consume task again. Repeated ON/OFF cycles thus cost one
        renegotiation per ON; the OFF side is free.
        """
        self._config.share_my_screen = bool(enable)
        if not enable:
            self._inplace_detach_track(kind="video")
            return  # no renegotiation on OFF
        if self._viewer_screen_track is not None:
            return  # already on
        # Need fresh negotiation so host re-spawns its consume task
        self.request_renegotiation()

    def toggle_opus_mic(self, enable: bool) -> None:
        """Live-toggle Opus mic uplink (OFF in-place, ON renegotiates)."""
        self._config.share_my_audio_opus = bool(enable)
        if not enable:
            self._inplace_detach_track(kind="audio")
            return
        if self._opus_audio_track is not None:
            return
        self.request_renegotiation()

    def _inplace_detach_track(self, *, kind: str) -> None:
        """OFF path: replaceTrack(None) + stop, but skip renegotiation."""
        if self._pc is None:
            return
        track_attr = ("_viewer_screen_track" if kind == "video"
                      else "_opus_audio_track")
        track = getattr(self, track_attr, None)
        if track is None:
            return
        for transceiver in self._pc.getTransceivers():
            if transceiver.kind != kind:
                continue
            if transceiver.sender.track is not track:
                continue
            try:
                transceiver.sender.replaceTrack(None)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("detach track: %r", error)
            break
        try:
            track.stop()
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("track.stop on detach: %r", error)
        setattr(self, track_attr, None)

    async def _async_handle_renegotiate(self, offer_sdp: str) -> None:
        """Apply a host-initiated renegotiation offer."""
        if self._pc is None:
            return
        try:
            await self._pc.setRemoteDescription(
                RTCSessionDescription(sdp=offer_sdp, type="offer"),
            )
            if self._config.share_my_screen and self._viewer_screen_track is None:
                self._attach_viewer_screen_track()
            if (self._config.share_my_audio_opus
                    and self._opus_audio_track is None):
                self._attach_opus_audio_track()
            answer = await self._pc.createAnswer()
            await self._pc.setLocalDescription(answer)
            await wait_for_ice_gathering(self._pc)
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("renegotiate handle: %r", error)
            return
        self._send({
            "type": "renegotiate_answer",
            "sdp": self._pc.localDescription.sdp,
        })
        autocontrol_logger.info("webrtc viewer: sent renegotiate answer")

    def _wire_files_channel(self, channel) -> None:
        from je_auto_control.utils.remote_desktop.webrtc_files import (
            FileTransferReceiver,
        )
        if self._files_receiver is None:
            self._files_receiver = FileTransferReceiver()

        @channel.on("message")
        def _on_message(message) -> None:
            self._files_receiver.handle_message(
                message,
                on_done=self._on_viewer_file_done,
            )

    def _on_viewer_file_done(self, path) -> None:
        if self._on_file_received is not None:
            try:
                self._on_file_received(path)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("viewer file done cb: %r", error)

    def stop(self) -> None:
        if self._pc is None:
            return
        self._closed.set()
        future = get_bridge().submit(self._async_stop())
        try:
            future.result(timeout=3.0)
        except (asyncio.TimeoutError, OSError, RuntimeError) as error:
            autocontrol_logger.warning("webrtc viewer stop: %r", error)

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    @property
    def read_only(self) -> bool:
        """True if the host has put this session into read-only mode."""
        return self._read_only

    @property
    def host_fingerprint(self) -> Optional[str]:
        """The host's stable fingerprint, available once authenticated."""
        return self._host_fingerprint

    @property
    def connection_state(self) -> str:
        return self._pc.connectionState if self._pc is not None else "closed"

    # --- async internals ----------------------------------------------------

    async def _async_process_offer(self, offer_sdp: str) -> str:
        if self._pc is not None:
            await self._pc.close()
        self._pc = RTCPeerConnection(
            configuration=self._config.to_rtc_configuration(),
        )
        self._wire_pc_handlers(self._pc)
        offer = RTCSessionDescription(sdp=offer_sdp, type="offer")
        await self._pc.setRemoteDescription(offer)
        if self._config.share_my_screen:
            self._attach_viewer_screen_track()
        if self._config.share_my_audio_opus:
            self._attach_opus_audio_track()
        answer = await self._pc.createAnswer()
        await self._pc.setLocalDescription(answer)
        await wait_for_ice_gathering(self._pc)
        return self._pc.localDescription.sdp

    def _attach_viewer_screen_track(self) -> None:
        """Attach our screen to the host's recvonly video slot.

        After ``setRemoteDescription``, aiortc gives every answerer
        transceiver the default ``recvonly`` direction regardless of what
        the remote requested, so we can't filter by direction. Instead we
        rely on m-line order: the second video transceiver corresponds to
        the host's recvonly slot (the first is its outbound screen).
        """
        from je_auto_control.utils.remote_desktop.webrtc_transport import (
            ScreenVideoTrack,
        )
        video_transceivers = [
            t for t in self._pc.getTransceivers() if t.kind == "video"
        ]
        if len(video_transceivers) < 2:
            autocontrol_logger.warning(
                "viewer share_my_screen: host did not advertise a second "
                "video slot (set accept_viewer_video=True on the host)",
            )
            return
        target = video_transceivers[1]
        track = ScreenVideoTrack(
            monitor_index=self._config.monitor_index,
            fps=self._config.fps,
            region=self._config.region,
            show_cursor=self._config.show_cursor,
        )
        self._viewer_screen_track = track
        target.sender.replaceTrack(track)
        target.direction = "sendonly"

    def _attach_opus_audio_track(self) -> None:
        """Attach an Opus mic track to the host's recvonly audio slot."""
        from je_auto_control.utils.remote_desktop.webrtc_audio import (
            OpusMicAudioTrack,
        )
        audio_transceivers = [
            t for t in self._pc.getTransceivers() if t.kind == "audio"
        ]
        if not audio_transceivers:
            autocontrol_logger.warning(
                "viewer share_my_audio_opus: host did not advertise an audio "
                "slot (set accept_viewer_audio_opus=True on the host)",
            )
            return
        target = audio_transceivers[0]
        try:
            track = OpusMicAudioTrack()
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("opus mic track init: %r", error)
            return
        self._opus_audio_track = track
        target.sender.replaceTrack(track)
        target.direction = "sendonly"

    async def _async_stop(self) -> None:
        if self._host_voice_receiver is not None:
            try:
                self._host_voice_receiver.stop()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("host voice stop: %r", error)
            self._host_voice_receiver = None
        if self._opus_audio_track is not None:
            try:
                self._opus_audio_track.stop()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("opus mic track stop: %r", error)
            self._opus_audio_track = None
        if self._viewer_screen_track is not None:
            try:
                self._viewer_screen_track.stop()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("viewer screen track stop: %r", error)
            self._viewer_screen_track = None
        if self._mic_sender is not None:
            try:
                self._mic_sender.stop()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("mic sender stop: %r", error)
            self._mic_sender = None
        if self._receive_task is not None:
            self._receive_task.cancel()
            self._receive_task = None
        if self._pc is not None:
            await self._pc.close()
            self._pc = None
        self._control_channel = None
        self._mic_channel = None
        self._files_channel = None
        self._authenticated = False

    # --- wiring -------------------------------------------------------------

    def _wire_pc_handlers(self, pc: RTCPeerConnection) -> None:
        cb = self._on_state_change

        @pc.on("connectionstatechange")
        async def _on_state() -> None:
            state = pc.connectionState
            autocontrol_logger.info("webrtc viewer: connection %s", state)
            if cb is not None:
                try:
                    cb(state)
                except (RuntimeError, OSError) as error:
                    autocontrol_logger.warning("state cb: %r", error)
            if state in ("failed", "closed", "disconnected"):
                self._authenticated = False

        @pc.on("track")
        def _on_track(track) -> None:
            autocontrol_logger.info("webrtc viewer: got %s track", track.kind)
            if track.kind == "video":
                self._receive_task = asyncio.ensure_future(
                    self._consume_video(track),
                )
            elif track.kind == "audio":
                self._start_host_voice_play(track)

        @pc.on("datachannel")
        def _on_datachannel(channel) -> None:
            autocontrol_logger.info(
                "webrtc viewer: data channel %r open", channel.label,
            )
            if channel.label == "mic":
                self._mic_channel = channel
                return
            if channel.label == "files":
                self._files_channel = channel
                self._wire_files_channel(channel)
                return
            self._control_channel = channel
            self._wire_control_channel(channel)

    def _wire_control_channel(self, channel) -> None:
        @channel.on("open")
        def _on_open() -> None:
            self._send_auth()

        @channel.on("message")
        def _on_message(message) -> None:
            self._handle_ctrl_message(message)

        @channel.on("close")
        def _on_close() -> None:
            self._authenticated = False

        # Channel may already be open by the time aiortc fires the
        # "datachannel" event; in that case "open" never fires again.
        if getattr(channel, "readyState", "") == "open":
            self._send_auth()

    def _start_host_voice_play(self, track) -> None:
        from je_auto_control.utils.remote_desktop.webrtc_audio import (
            OpusMicReceiver,
        )
        if self._host_voice_receiver is not None:
            return
        try:
            self._host_voice_receiver = OpusMicReceiver()
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("host voice play init: %r", error)
            return
        self._host_voice_receiver.consume(track)
        autocontrol_logger.info("webrtc viewer: playing host voice")

    async def _consume_video(self, track) -> None:
        # CancelledError is intentionally not caught — it must propagate
        # so the awaiter knows the consumer ended via cancellation
        # rather than a stream error (S7497).
        try:
            while not self._closed.is_set():
                frame = await track.recv()
                if self._on_frame is not None:
                    try:
                        self._on_frame(frame)
                    except (RuntimeError, OSError) as error:
                        autocontrol_logger.debug("frame cb: %r", error)
        except (OSError, RuntimeError) as error:
            autocontrol_logger.info("webrtc viewer: video stream ended: %r", error)

    def _send_auth(self) -> None:
        payload = {"type": "auth", "token": self._token}
        if self._viewer_id:
            payload["viewer_id"] = self._viewer_id
        self._send(payload)

    def _handle_ctrl_message(self, message: Any) -> None:
        if not isinstance(message, str):
            return
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return
        msg_type = data.get("type")
        if msg_type == "auth_ok":
            self._authenticated = True
            self._read_only = bool(data.get("read_only", False))
            fingerprint = data.get("fingerprint")
            if isinstance(fingerprint, str) and fingerprint:
                self._host_fingerprint = fingerprint
                if self._on_fingerprint is not None:
                    try:
                        self._on_fingerprint(fingerprint)
                    except (RuntimeError, OSError) as error:
                        autocontrol_logger.debug("fingerprint cb: %r", error)
            self._fire_auth_result(True)
        elif msg_type == "auth_fail":
            self._authenticated = False
            self._fire_auth_result(False)
        elif msg_type == "read_only":
            self._read_only = bool(data.get("value", False))
        elif msg_type == "permissions":
            value = data.get("value")
            if isinstance(value, dict):
                self._read_only = not bool(value.get("allow_input", True))
        elif msg_type == "list_inbox_response":
            files = data.get("files") or []
            if self._on_inbox_listing is not None:
                try:
                    self._on_inbox_listing(files)
                except (RuntimeError, OSError) as error:
                    autocontrol_logger.debug("inbox listing cb: %r", error)
        elif msg_type == "renegotiate_offer":
            sdp = data.get("sdp")
            if isinstance(sdp, str) and self._pc is not None:
                self._spawn_bg(self._async_handle_renegotiate(sdp))
        elif msg_type in ("delete_inbox_response", "request_file_response"):
            if self._on_inbox_op_result is None:
                return
            try:
                self._on_inbox_op_result(
                    str(data.get("name", "")),
                    bool(data.get("ok", False)),
                    data.get("error"),
                )
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("inbox op cb: %r", error)

    def _fire_auth_result(self, ok: bool) -> None:
        if self._on_auth_result is None:
            return
        try:
            self._on_auth_result(ok)
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("auth cb: %r", error)

    def _send(self, payload: Mapping[str, Any]) -> None:
        if self._control_channel is None:
            autocontrol_logger.debug("viewer send before channel open")
            return
        text = json.dumps(payload)
        get_bridge().call_soon(self._safe_channel_send, text)

    def _safe_channel_send(self, text: str) -> None:
        if self._control_channel is None:
            return
        try:
            self._control_channel.send(text)
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("ctrl send: %r", error)


__all__ = ["WebRTCDesktopViewer"]
