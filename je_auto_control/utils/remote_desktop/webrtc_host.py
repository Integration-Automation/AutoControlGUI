"""WebRTC host: streams screen video and accepts viewer input.

Phase 1 of the AnyDesk-style migration. Signaling is manual: the caller
generates an offer, ships the SDP to the viewer out-of-band, gets back an
answer SDP, and feeds it to :meth:`accept_answer`. A signaling server is
added in Phase 2 (see ``signaling_server.py``) but is not required here.

Auth uses the existing HMAC token. Because aiortc's DataChannel rides on
DTLS-SRTP (encrypted by default), we accept a plain token comparison on
the first ``auth`` message rather than the TCP-style nonce dance.

A pluggable ``offer_consent`` callback lets the GUI prompt the user before
accepting an offer (Phase 4 accept/reject flow). Default: auto-accept.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Callable, Mapping, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.audit_log import default_audit_log
from je_auto_control.utils.remote_desktop.fingerprint import (
    load_or_create_host_fingerprint,
)
from je_auto_control.utils.remote_desktop.input_dispatch import (
    InputDispatchError, dispatch_input,
)
from je_auto_control.utils.remote_desktop.permissions import SessionPermissions
from je_auto_control.utils.remote_desktop.rate_limit import (
    RateLimitConfig, RateLimiter,
)
from je_auto_control.utils.remote_desktop.trust_list import TrustList
from je_auto_control.utils.remote_desktop.webrtc_transport import (
    RTCPeerConnection, RTCSessionDescription, ScreenVideoTrack, WebRTCConfig,
    get_bridge, wait_for_ice_gathering,
)


_AUTH_GRACE_S = 5.0
_OFFER_TIMEOUT_S = 12.0
_ANSWER_TIMEOUT_S = 8.0


StateCallback = Callable[[str], None]
ConsentCallback = Callable[[str], bool]


class WebRTCDesktopHost:
    """Single-viewer WebRTC host with manual SDP signaling.

    Multiple simultaneous viewers would require one ``RTCPeerConnection``
    per viewer; for Phase 1 we keep it 1:1 because that matches the typical
    "one person controls my machine" workflow and keeps the GUI simple.
    """

    def __init__(self, *, token: str,  # NOSONAR python:S107  # public constructor; callbacks/permissions are kept as discrete kwargs to keep the call site readable at the GUI layer (see gui/remote_desktop/webrtc_panel.py + utils/remote_desktop/multi_viewer.py)
                 config: Optional[WebRTCConfig] = None,
                 on_state_change: Optional[StateCallback] = None,
                 on_authenticated: Optional[Callable[[], None]] = None,
                 on_pending_viewer: Optional[Callable[[], None]] = None,
                 input_dispatcher: Optional[Callable[[Mapping[str, Any]], Any]] = None,
                 offer_consent: Optional[ConsentCallback] = None,
                 trust_list: Optional[TrustList] = None,
                 read_only: bool = False,
                 permissions: Optional[SessionPermissions] = None,
                 external_video_track=None,
                 inbox_dir=None,
                 ip_whitelist: Optional[list] = None,
                 rate_limit: Optional[RateLimitConfig] = None,
                 on_annotation: Optional[Callable[[dict], None]] = None) -> None:
        if not token:
            raise ValueError("WebRTC host requires a non-empty token")
        self._token = token
        self._config = config or WebRTCConfig()
        self._on_state_change = on_state_change
        self._on_authenticated = on_authenticated
        self._on_pending_viewer = on_pending_viewer
        self._dispatch = input_dispatcher or dispatch_input
        self._offer_consent = offer_consent or (lambda peer: True)
        self._trust_list = trust_list
        # permissions argument wins; otherwise derive from read_only shorthand
        self._permissions = (
            permissions if permissions is not None
            else SessionPermissions.from_read_only(read_only)
        )
        self._external_video_track = external_video_track
        self._inbox_dir = inbox_dir  # None → FileTransferReceiver default
        self._ip_whitelist = list(ip_whitelist) if ip_whitelist else []
        self._remote_ip: Optional[str] = None
        self._rate_limiter = RateLimiter(rate_limit)
        self._on_annotation = on_annotation
        self._pending_viewer_id: Optional[str] = None
        self._pc: Optional[RTCPeerConnection] = None
        self._video_track: Optional[ScreenVideoTrack] = None
        self._control_channel = None
        self._mic_channel = None
        self._mic_receiver = None  # Optional[MicUplinkReceiver]
        self._files_channel = None
        self._files_receiver = None  # Optional[FileTransferReceiver]
        self._on_file_received: Optional[Callable] = None
        self._on_viewer_video_frame: Optional[Callable] = None
        self._viewer_video_task = None
        self._opus_audio_receiver = None  # Optional[OpusMicReceiver]
        self._host_voice_track = None     # Optional[OpusMicAudioTrack] (outbound)
        self._authenticated = False
        self._has_pending_viewer = False
        self._auth_deadline_handle = None
        # Hold strong refs to fire-and-forget tasks so the asyncio event
        # loop doesn't garbage-collect them mid-flight (S7502). Tasks
        # remove themselves from this set in their done callback.
        self._background_tasks: set = set()
        self._closed = threading.Event()
        self._lock = threading.Lock()

    # --- public sync API ----------------------------------------------------

    def create_offer(self, peer_label: str = "remote viewer") -> str:
        """Build the PC, generate SDP offer (with ICE candidates baked in)."""
        if not self._offer_consent(peer_label):
            raise PermissionError("offer rejected by consent callback")
        future = get_bridge().submit(self._async_create_offer())
        return future.result(timeout=_OFFER_TIMEOUT_S)

    def accept_answer(self, answer_sdp: str) -> None:
        """Apply the viewer's answer to complete the handshake."""
        if not answer_sdp or not answer_sdp.strip():
            raise ValueError("answer_sdp is empty")
        future = get_bridge().submit(self._async_accept_answer(answer_sdp))
        future.result(timeout=_ANSWER_TIMEOUT_S)

    def stop(self) -> None:
        """Tear down the PeerConnection and capture executor."""
        if self._pc is None:
            return
        self._closed.set()
        future = get_bridge().submit(self._async_stop())
        try:
            future.result(timeout=3.0)
        except (asyncio.TimeoutError, OSError, RuntimeError) as error:
            autocontrol_logger.warning("webrtc host stop: %r", error)

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    @property
    def connection_state(self) -> str:
        return self._pc.connectionState if self._pc is not None else "closed"

    # --- async internals ----------------------------------------------------

    async def _async_create_offer(self) -> str:
        if self._pc is not None:
            await self._pc.close()
        self._pc = RTCPeerConnection(
            configuration=self._config.to_rtc_configuration(),
        )
        if self._external_video_track is not None:
            self._video_track = self._external_video_track
        else:
            self._video_track = ScreenVideoTrack(
                monitor_index=self._config.monitor_index,
                fps=self._config.fps,
                region=self._config.region,
                show_cursor=self._config.show_cursor,
            )
        self._pc.addTrack(self._video_track)
        if self._config.accept_viewer_video:
            self._pc.addTransceiver("video", direction="recvonly")
        if self._config.accept_viewer_audio_opus:
            self._pc.addTransceiver("audio", direction="recvonly")
        if self._config.host_voice:
            try:
                from je_auto_control.utils.remote_desktop.webrtc_audio import (
                    OpusMicAudioTrack,
                )
                self._host_voice_track = OpusMicAudioTrack()
                self._pc.addTrack(self._host_voice_track)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.warning("host voice init: %r", error)
                self._host_voice_track = None
        self._control_channel = self._pc.createDataChannel("ctrl")
        self._wire_control_channel(self._control_channel)
        self._mic_channel = self._pc.createDataChannel("mic")
        self._wire_mic_channel(self._mic_channel)
        self._files_channel = self._pc.createDataChannel("files")
        self._wire_files_channel(self._files_channel)
        self._wire_state_handlers(self._pc)
        self._wire_viewer_video_handler(self._pc)
        offer = await self._pc.createOffer()
        await self._pc.setLocalDescription(offer)
        await wait_for_ice_gathering(self._pc)
        return self._pc.localDescription.sdp

    async def _async_accept_answer(self, answer_sdp: str) -> None:
        if self._pc is None:
            raise RuntimeError("call create_offer() first")
        answer = RTCSessionDescription(sdp=answer_sdp, type="answer")
        await self._pc.setRemoteDescription(answer)
        loop = asyncio.get_event_loop()
        self._auth_deadline_handle = loop.call_later(
            _AUTH_GRACE_S, self._enforce_auth_deadline,
        )

    async def _async_stop(self) -> None:
        if self._host_voice_track is not None:
            try:
                self._host_voice_track.stop()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("host voice stop: %r", error)
            self._host_voice_track = None
        if self._opus_audio_receiver is not None:
            try:
                self._opus_audio_receiver.stop()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("opus receiver stop: %r", error)
            self._opus_audio_receiver = None
        if self._viewer_video_task is not None:
            self._viewer_video_task.cancel()
            self._viewer_video_task = None
        if self._mic_receiver is not None:
            try:
                self._mic_receiver.stop()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("mic receiver stop: %r", error)
            self._mic_receiver = None
        if self._video_track is not None and self._external_video_track is None:
            # Only stop tracks we created; relayed/external tracks belong to the owner.
            self._video_track.stop()
        self._video_track = None
        if self._pc is not None:
            await self._pc.close()
            self._pc = None
        self._control_channel = None
        self._mic_channel = None
        self._files_channel = None
        self._files_receiver = None
        self._authenticated = False
        if self._auth_deadline_handle is not None:
            self._auth_deadline_handle.cancel()
            self._auth_deadline_handle = None

    def _spawn_bg(self, coro) -> "asyncio.Task":
        """Schedule ``coro`` and pin a strong ref while it runs (S7502)."""
        task = asyncio.ensure_future(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    # --- channel wiring -----------------------------------------------------

    def _wire_viewer_video_handler(self, pc: RTCPeerConnection) -> None:
        @pc.on("track")
        def _on_track(track) -> None:
            if track.kind == "video":
                autocontrol_logger.info("webrtc host: receiving viewer video")
                self._viewer_video_task = self._spawn_bg(
                    self._consume_viewer_video(track),
                )
            elif track.kind == "audio":
                if not self._config.accept_viewer_audio_opus:
                    return
                self._start_opus_audio_receive(track)

    def _start_opus_audio_receive(self, track) -> None:
        from je_auto_control.utils.remote_desktop.webrtc_audio import (
            OpusMicReceiver,
        )
        if self._opus_audio_receiver is not None:
            return
        try:
            self._opus_audio_receiver = OpusMicReceiver()
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("opus audio receiver init: %r", error)
            return
        self._opus_audio_receiver.consume(track)
        autocontrol_logger.info("webrtc host: receiving Opus audio from viewer")

    async def _consume_viewer_video(self, track) -> None:
        from aiortc.mediastreams import MediaStreamError
        try:
            while True:
                frame = await track.recv()
                if not self._authenticated:
                    continue
                cb = self._on_viewer_video_frame
                if cb is not None:
                    try:
                        cb(frame)
                    except (RuntimeError, OSError) as error:
                        autocontrol_logger.debug("viewer video cb: %r", error)
        except (asyncio.CancelledError, MediaStreamError):
            autocontrol_logger.info("viewer video stream ended")
        except (OSError, RuntimeError) as error:
            autocontrol_logger.info("viewer video stream ended: %r", error)
        finally:
            self._viewer_video_task = None

    def set_viewer_video_callback(self, callback) -> None:
        """Register ``cb(av.VideoFrame)`` for incoming viewer-screen frames."""
        self._on_viewer_video_frame = callback

    def _wire_state_handlers(self, pc: RTCPeerConnection) -> None:
        cb = self._on_state_change

        @pc.on("connectionstatechange")
        async def _on_state() -> None:
            state = pc.connectionState
            autocontrol_logger.info("webrtc host: connection %s", state)
            if state == "connected":
                await self._snapshot_remote_ip()
            if cb is not None:
                try:
                    cb(state)
                except (RuntimeError, OSError) as error:
                    autocontrol_logger.warning("state cb: %r", error)
            if state in ("failed", "closed", "disconnected"):
                self._authenticated = False

    async def _snapshot_remote_ip(self) -> None:
        if self._pc is None:
            return
        try:
            report = await self._pc.getStats()
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("getStats remote ip: %r", error)
            return
        for entry in report.values():
            if (getattr(entry, "type", None) == "candidate-pair"
                    and getattr(entry, "selected", False)):
                remote_id = getattr(entry, "remoteCandidateId", None)
                if remote_id and remote_id in report:
                    cand = report[remote_id]
                    ip = (getattr(cand, "ip", None)
                          or getattr(cand, "address", None))
                    if ip:
                        self._remote_ip = str(ip)
                        autocontrol_logger.info(
                            "webrtc host: remote ip = %s", self._remote_ip,
                        )
                return

    def _wire_mic_channel(self, channel) -> None:
        @channel.on("message")
        def _on_message(message) -> None:
            if not self._authenticated or self._mic_receiver is None:
                return
            if not self._permissions.allow_audio:
                return
            self._mic_receiver.on_chunk(message)

    def _wire_files_channel(self, channel) -> None:
        from je_auto_control.utils.remote_desktop.webrtc_files import (
            FileTransferReceiver,
        )
        if self._files_receiver is None:
            self._files_receiver = FileTransferReceiver(inbox_dir=self._inbox_dir)

        @channel.on("message")
        def _on_message(message) -> None:
            if not self._authenticated or not self._permissions.allow_files:
                return
            # Rate limit file_begin envelopes; binary chunks pass through
            # since they belong to an already-allowed transfer.
            if isinstance(message, str) and "file_begin" in message:
                if not self._rate_limiter.allow_file():
                    if self._rate_limiter.should_warn_files():
                        try:
                            default_audit_log().log(
                                "rate_limit_files",
                                viewer_id=self._pending_viewer_id,
                                detail=f"remote_ip={self._remote_ip}",
                            )
                        except (RuntimeError, OSError):
                            pass
                    return
            self._files_receiver.handle_message(
                message,
                on_done=self._on_file_done,
            )

    def set_file_received_callback(self, callback) -> None:
        """Register a sync callback ``cb(path: Path)`` for completed transfers."""
        self._on_file_received = callback

    def push_file(self, local_path, remote_name=None) -> None:
        """Send a local file to this connected viewer via the files channel."""
        if self._files_channel is None or not self._authenticated:
            raise RuntimeError("not connected to a viewer yet")
        from je_auto_control.utils.remote_desktop.webrtc_files import (
            FileTransferSender,
        )
        FileTransferSender(self._files_channel).send(
            local_path, remote_name=remote_name,
        )

    def _on_file_done(self, path) -> None:
        try:
            default_audit_log().log(
                "file_received", viewer_id=self._pending_viewer_id,
                detail=str(path),
            )
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("audit log file: %r", error)
        if self._on_file_received is not None:
            try:
                self._on_file_received(path)
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("file done cb: %r", error)

    def enable_mic_receive(self) -> None:
        """Start playing incoming mic PCM from the viewer."""
        from je_auto_control.utils.remote_desktop.webrtc_mic import (
            MicUplinkReceiver,
        )
        if self._mic_receiver is not None:
            return
        self._mic_receiver = MicUplinkReceiver()
        self._mic_receiver.start()

    def disable_mic_receive(self) -> None:
        if self._mic_receiver is None:
            return
        try:
            self._mic_receiver.stop()
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("mic receiver stop: %r", error)
        self._mic_receiver = None

    def _wire_control_channel(self, channel) -> None:
        @channel.on("open")
        def _on_open() -> None:
            autocontrol_logger.info("webrtc host: control channel open")

        @channel.on("message")
        def _on_message(message) -> None:
            self._handle_ctrl_message(message)

        @channel.on("close")
        def _on_close() -> None:
            self._authenticated = False

    def _handle_ctrl_message(self, message: Any) -> None:
        if not isinstance(message, str):
            return
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            autocontrol_logger.debug("webrtc host: bad json")
            return
        if not isinstance(data, dict):
            return
        msg_type = data.get("type")
        if not self._authenticated:
            if msg_type == "auth":
                self._handle_auth(data)
            return
        if msg_type == "input":
            if not self._permissions.allow_input:
                return
            if not self._rate_limiter.allow_input():
                if self._rate_limiter.should_warn_input():
                    try:
                        default_audit_log().log(
                            "rate_limit_input",
                            viewer_id=self._pending_viewer_id,
                            detail=f"remote_ip={self._remote_ip}",
                        )
                    except (RuntimeError, OSError):
                        pass
                return
            self._dispatch_input_safely(data.get("payload"))
        elif msg_type == "send_sas":
            if not self._permissions.allow_input:
                return
            self._handle_send_sas()
        elif msg_type == "list_inbox":
            self._handle_list_inbox()
        elif msg_type == "request_file":
            self._handle_request_file(data)
        elif msg_type == "delete_inbox_file":
            self._handle_delete_inbox_file(data)
        elif msg_type == "annotate":
            if self._on_annotation is not None:
                try:
                    self._on_annotation(dict(data))
                except (RuntimeError, OSError) as error:
                    autocontrol_logger.debug("annotation cb: %r", error)
        elif msg_type == "renegotiate_request":
            self._spawn_bg(self._async_renegotiate())
        elif msg_type == "renegotiate_answer":
            sdp = data.get("sdp")
            if isinstance(sdp, str) and self._pc is not None:
                self._spawn_bg(self._async_apply_renegotiate_answer(sdp))

    async def _async_apply_renegotiate_answer(self, sdp: str) -> None:
        if self._pc is None:
            return
        try:
            await self._pc.setRemoteDescription(
                RTCSessionDescription(sdp=sdp, type="answer"),
            )
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("apply renegotiate answer: %r", error)
            return
        # Viewer may have just attached a fresh track. If our consume task
        # has died (because the previous track stopped), spawn a new one
        # against the same receiver.
        if (self._config.accept_viewer_video
                and self._viewer_video_task is None):
            video_ts = [
                t for t in self._pc.getTransceivers() if t.kind == "video"
            ]
            for transceiver in video_ts[1:]:  # skip our outbound slot
                receiver = transceiver.receiver
                if receiver is None or receiver.track is None:
                    continue
                self._viewer_video_task = self._spawn_bg(
                    self._consume_viewer_video(receiver.track),
                )
                autocontrol_logger.info(
                    "webrtc host: re-spawned viewer video consume task",
                )
                break
        if (self._config.accept_viewer_audio_opus
                and self._opus_audio_receiver is None):
            for transceiver in self._pc.getTransceivers():
                if transceiver.kind != "audio":
                    continue
                receiver = transceiver.receiver
                if receiver is None or receiver.track is None:
                    continue
                self._start_opus_audio_receive(receiver.track)
                break

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

    def _ensure_files_receiver(self):
        from je_auto_control.utils.remote_desktop.webrtc_files import (
            FileTransferReceiver,
        )
        if self._files_receiver is None:
            self._files_receiver = FileTransferReceiver(inbox_dir=self._inbox_dir)
        return self._files_receiver

    def _handle_list_inbox(self) -> None:
        if not self._permissions.allow_files:
            self._send_ctrl({"type": "list_inbox_response", "files": [],
                             "error": "files not permitted"})
            return
        try:
            inbox = self._ensure_files_receiver()._inbox
            files = []
            for entry in sorted(inbox.iterdir()):
                if not entry.is_file():
                    continue
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
        except OSError as error:
            self._send_ctrl({"type": "list_inbox_response", "files": [],
                             "error": str(error)})
            return
        self._send_ctrl({"type": "list_inbox_response", "files": files})

    def _handle_request_file(self, data: Mapping[str, Any]) -> None:
        if not self._permissions.allow_files:
            return
        name = data.get("name")
        if not isinstance(name, str):
            return
        try:
            from je_auto_control.utils.remote_desktop.webrtc_files import (
                _safe_basename,
            )
            safe = _safe_basename(name)
            inbox = self._ensure_files_receiver()._inbox
            target = inbox / safe
            if not target.is_file():
                self._send_ctrl({"type": "request_file_response",
                                 "name": safe, "ok": False,
                                 "error": "not found"})
                return
            self.push_file(str(target), remote_name=safe)
        except (OSError, ValueError, RuntimeError) as error:
            self._send_ctrl({"type": "request_file_response",
                             "name": str(name), "ok": False,
                             "error": str(error)})

    def _handle_delete_inbox_file(self, data: Mapping[str, Any]) -> None:
        name = data.get("name")
        if not isinstance(name, str):
            return
        if not self._permissions.allow_files:
            self._send_ctrl({"type": "delete_inbox_response", "name": name,
                             "ok": False, "error": "files not permitted"})
            return
        try:
            from je_auto_control.utils.remote_desktop.webrtc_files import (
                _safe_basename,
            )
            safe = _safe_basename(name)
            inbox = self._ensure_files_receiver()._inbox
            target = inbox / safe
            target.unlink(missing_ok=False)
        except (OSError, ValueError) as error:
            self._send_ctrl({"type": "delete_inbox_response", "name": str(name),
                             "ok": False, "error": str(error)})
            return
        self._send_ctrl({"type": "delete_inbox_response", "name": safe,
                         "ok": True})

    def set_read_only(self, value: bool) -> None:
        """Backwards-compat shim: toggles input/clipboard/files only."""
        self.set_permissions(SessionPermissions.from_read_only(bool(value)))

    def set_permissions(self, permissions: SessionPermissions) -> None:
        """Update the granular permissions at runtime."""
        self._permissions = permissions
        self._send_ctrl({"type": "permissions", "value": permissions.to_dict()})

    @property
    def read_only(self) -> bool:
        return not self._permissions.allow_input

    @property
    def permissions(self) -> SessionPermissions:
        return self._permissions

    def _handle_send_sas(self) -> None:
        try:
            from je_auto_control.utils.remote_desktop.session_actions import (
                send_secure_attention_sequence,
            )
            send_secure_attention_sequence()
            self._send_ctrl({"type": "sas_ok"})
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("SendSAS: %r", error)
            self._send_ctrl({"type": "sas_fail", "error": str(error)})

    def _handle_auth(self, data: Mapping[str, Any]) -> None:
        token = data.get("token")
        if not isinstance(token, str) or token != self._token:
            self._send_ctrl({"type": "auth_fail"})
            try:
                default_audit_log().log(
                    "auth_fail",
                    viewer_id=str(data.get("viewer_id", "")) or None,
                    detail=f"remote_ip={self._remote_ip}",
                )
            except (RuntimeError, OSError) as error:
                autocontrol_logger.debug("audit log auth_fail: %r", error)
            get_bridge().call_soon(self._schedule_close_after_fail)
            return
        viewer_id = data.get("viewer_id")
        self._pending_viewer_id = (
            viewer_id if isinstance(viewer_id, str) else None
        )
        if self._is_trusted_viewer(self._pending_viewer_id):
            autocontrol_logger.info(
                "webrtc host: viewer_id %s is trusted; auto-approving",
                self._pending_viewer_id,
            )
            if self._trust_list is not None:
                try:
                    self._trust_list.touch(self._pending_viewer_id)
                except (RuntimeError, OSError) as error:
                    autocontrol_logger.debug("trust touch: %r", error)
            self._approve_pending_viewer()
            return
        if self._is_ip_whitelisted(self._remote_ip):
            autocontrol_logger.info(
                "webrtc host: remote ip %s matches whitelist; auto-approving",
                self._remote_ip,
            )
            self._approve_pending_viewer()
            return
        if self._on_pending_viewer is None:
            self._approve_pending_viewer()
            return
        self._has_pending_viewer = True
        try:
            self._on_pending_viewer()
        except (RuntimeError, OSError) as error:
            autocontrol_logger.warning("pending viewer cb: %r", error)

    def _is_ip_whitelisted(self, ip: Optional[str]) -> bool:
        if not ip or not self._ip_whitelist:
            return False
        import ipaddress
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        for cidr in self._ip_whitelist:
            try:
                if addr in ipaddress.ip_network(cidr.strip(), strict=False):
                    return True
            except ValueError:
                continue
        return False

    def _is_trusted_viewer(self, viewer_id: Optional[str]) -> bool:
        if self._trust_list is None or not viewer_id:
            return False
        try:
            return self._trust_list.is_trusted(viewer_id)
        except (OSError, RuntimeError) as error:
            autocontrol_logger.warning("trust list check: %r", error)
            return False

    def trust_pending_viewer(self, label: str = "") -> None:
        """Add the current pending viewer to the trust list, then approve."""
        viewer_id = self._pending_viewer_id
        if self._trust_list is not None and viewer_id:
            try:
                self._trust_list.add(viewer_id, label=label)
            except (OSError, ValueError, RuntimeError) as error:
                autocontrol_logger.warning("trust list add: %r", error)
        self.approve_pending_viewer()

    @property
    def pending_viewer_id(self) -> Optional[str]:
        return self._pending_viewer_id

    def approve_pending_viewer(self) -> None:
        """Thread-safe accept; call from GUI when user clicks Accept."""
        get_bridge().call_soon(self._approve_pending_viewer)

    def reject_pending_viewer(self) -> None:
        """Thread-safe reject; call from GUI when user clicks Reject."""
        get_bridge().call_soon(self._reject_pending_viewer)

    def _approve_pending_viewer(self) -> None:
        if not self._has_pending_viewer and self._authenticated:
            return
        self._has_pending_viewer = False
        self._authenticated = True
        self._send_ctrl({
            "type": "auth_ok",
            "read_only": not self._permissions.allow_input,
            "permissions": self._permissions.to_dict(),
            "fingerprint": load_or_create_host_fingerprint(),
        })
        try:
            default_audit_log().log(
                "auth_ok",
                viewer_id=self._pending_viewer_id,
                detail=f"remote_ip={self._remote_ip}",
            )
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("audit log auth_ok: %r", error)
        if self._auth_deadline_handle is not None:
            self._auth_deadline_handle.cancel()
            self._auth_deadline_handle = None
        if self._on_authenticated is not None:
            try:
                self._on_authenticated()
            except (RuntimeError, OSError) as error:
                autocontrol_logger.warning("auth cb: %r", error)

    def _reject_pending_viewer(self) -> None:
        self._has_pending_viewer = False
        self._send_ctrl({"type": "auth_fail"})
        get_bridge().call_soon(self._schedule_close_after_fail)

    @property
    def has_pending_viewer(self) -> bool:
        return self._has_pending_viewer

    def _schedule_close_after_fail(self) -> None:
        loop = asyncio.get_event_loop()
        loop.call_later(0.5, lambda: self._spawn_bg(self._async_stop()))

    def _enforce_auth_deadline(self) -> None:
        if self._authenticated:
            return
        autocontrol_logger.warning(
            "webrtc host: viewer failed to authenticate within grace period",
        )
        self._spawn_bg(self._async_stop())

    def _dispatch_input_safely(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        try:
            self._dispatch(payload)
        except InputDispatchError as error:
            autocontrol_logger.warning("input dispatch: %r", error)

    def _send_ctrl(self, payload: Mapping[str, Any]) -> None:
        if self._control_channel is None:
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


__all__ = ["WebRTCDesktopHost"]
