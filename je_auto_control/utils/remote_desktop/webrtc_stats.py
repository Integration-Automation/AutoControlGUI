"""Polling helper that turns aiortc's ``RTCStats`` reports into a small dict.

Used by the viewer GUI to render a translucent overlay (RTT, FPS, bitrate,
loss). Aiortc reports stats per stream; we aggregate the inbound video
stream's deltas across polls and expose the rolling rate.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_DEFAULT_INTERVAL_S = 1.0


@dataclass
class StatsSnapshot:
    """One sample's worth of derived metrics."""
    rtt_ms: Optional[float] = None
    fps: Optional[float] = None
    bitrate_kbps: Optional[float] = None
    packet_loss_pct: Optional[float] = None
    jitter_ms: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


class StatsPoller:
    """Drive a periodic ``getStats()`` poll on the asyncio bridge."""

    def __init__(self, pc, callback: Callable[[StatsSnapshot], None],
                 interval_s: float = _DEFAULT_INTERVAL_S) -> None:
        self._pc = pc
        self._callback = callback
        self._interval = max(0.25, float(interval_s))
        self._task: Optional[asyncio.Task] = None
        self._prev_packets_received = 0
        self._prev_packets_lost = 0
        self._prev_bytes_received = 0
        self._prev_frames_decoded = 0
        self._prev_sample_time: Optional[float] = None
        self._stopped = False

    def start(self) -> None:
        from je_auto_control.utils.remote_desktop.webrtc_transport import get_bridge
        future = get_bridge().submit(self._async_start())
        try:
            future.result(timeout=2.0)
        except (RuntimeError, TimeoutError, OSError) as error:
            autocontrol_logger.warning("stats poller start: %r", error)

    async def _async_start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.ensure_future(self._loop())

    def stop(self) -> None:
        self._stopped = True
        if self._task is None:
            return
        from je_auto_control.utils.remote_desktop.webrtc_transport import get_bridge
        get_bridge().call_soon(self._task.cancel)
        self._task = None

    async def _loop(self) -> None:
        try:
            while not self._stopped:
                await asyncio.sleep(self._interval)
                try:
                    snapshot = await self._sample()
                except (RuntimeError, OSError) as error:
                    autocontrol_logger.debug("stats sample: %r", error)
                    continue
                if snapshot is not None:
                    try:
                        self._callback(snapshot)
                    except (RuntimeError, OSError) as error:
                        autocontrol_logger.debug("stats cb: %r", error)
        except asyncio.CancelledError:
            return

    async def _sample(self) -> Optional[StatsSnapshot]:
        if self._pc is None:
            return None
        report = await self._pc.getStats()
        snap = StatsSnapshot()
        now = time.monotonic()
        delta_t = (now - self._prev_sample_time) if self._prev_sample_time else None
        self._prev_sample_time = now
        for entry in report.values():
            stat_type = getattr(entry, "type", None)
            if stat_type == "inbound-rtp" and getattr(entry, "kind", "") == "video":
                self._update_inbound(entry, delta_t, snap)
            elif stat_type == "remote-inbound-rtp":
                rtt = getattr(entry, "roundTripTime", None)
                if rtt is not None:
                    snap.rtt_ms = float(rtt) * 1000.0
                jitter = getattr(entry, "jitter", None)
                if jitter is not None:
                    snap.jitter_ms = float(jitter) * 1000.0
            elif stat_type == "candidate-pair":
                rtt = getattr(entry, "currentRoundTripTime", None)
                if rtt is not None and snap.rtt_ms is None:
                    snap.rtt_ms = float(rtt) * 1000.0
        return snap

    def _update_inbound(self, entry, delta_t, snap: StatsSnapshot) -> None:
        bytes_received = int(getattr(entry, "bytesReceived", 0) or 0)
        frames_decoded = int(getattr(entry, "framesDecoded", 0) or 0)
        packets_received = int(getattr(entry, "packetsReceived", 0) or 0)
        packets_lost = int(getattr(entry, "packetsLost", 0) or 0)
        if delta_t and delta_t > 0:
            byte_delta = bytes_received - self._prev_bytes_received
            if byte_delta >= 0:
                snap.bitrate_kbps = (byte_delta * 8 / 1000.0) / delta_t
            frame_delta = frames_decoded - self._prev_frames_decoded
            if frame_delta >= 0:
                snap.fps = frame_delta / delta_t
        total = packets_received + packets_lost
        if total > 0:
            recent_lost = packets_lost - self._prev_packets_lost
            recent_total = (packets_received + packets_lost
                            - self._prev_packets_received
                            - self._prev_packets_lost)
            if recent_total > 0:
                snap.packet_loss_pct = (recent_lost / recent_total) * 100.0
        self._prev_bytes_received = bytes_received
        self._prev_frames_decoded = frames_decoded
        self._prev_packets_received = packets_received
        self._prev_packets_lost = packets_lost


__all__ = ["StatsSnapshot", "StatsPoller"]
