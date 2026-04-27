"""Stats-driven adaptive controller that tunes the host's capture FPS.

aiortc 1.14 doesn't expose a public ``RTCRtpSender.setParameters`` for
live bitrate changes, so the most reliable lever we have without
restarting the encoder is dropping/raising the source frame rate. Halving
fps roughly halves the bandwidth at libx264's default CRF.

Heuristic:
  * if recent packet loss > LOSS_DOWN_PCT for STREAK samples → step fps down
  * if loss < LOSS_UP_PCT and current fps < user_max for STREAK samples → step up
  * RTT spikes > RTT_DOWN_MS also trigger a downstep

Driven from ``StatsPoller`` callbacks, so the controller runs on the Qt /
caller thread (no extra event loop needed).
"""
from __future__ import annotations

import threading
from typing import Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.webrtc_stats import StatsSnapshot


_LOSS_DOWN_PCT = 5.0
_LOSS_UP_PCT = 1.0
_RTT_DOWN_MS = 250.0
_DOWNSCALE_STREAK = 2
_UPSCALE_STREAK = 4
_STEP = 4  # fps step per adjustment
_FLOOR_FPS = 5


class AdaptiveBitrateController:
    """Adjusts a ScreenVideoTrack's target FPS based on stats samples."""

    def __init__(self, video_track, *, max_fps: Optional[int] = None,
                 floor_fps: int = _FLOOR_FPS,
                 max_bitrate_kbps: int = 0) -> None:
        self._track = video_track
        self._max_fps = int(max_fps) if max_fps else int(video_track.fps)
        self._floor_fps = max(1, int(floor_fps))
        self._max_bitrate_kbps = int(max_bitrate_kbps)
        self._down_streak = 0
        self._up_streak = 0
        self._lock = threading.Lock()
        self._enabled = True

    def set_enabled(self, value: bool) -> None:
        with self._lock:
            self._enabled = bool(value)

    def on_stats(self, snapshot: StatsSnapshot) -> None:
        with self._lock:
            if not self._enabled or self._track is None:
                return
            current_fps = int(self._track.fps)
            if self._react_to_hard_cap(snapshot, current_fps):
                return
            self._react_to_quality(snapshot, current_fps)

    def _react_to_hard_cap(self, snapshot: StatsSnapshot,
                           current_fps: int) -> bool:
        """Step down immediately when configured bitrate cap is exceeded."""
        if not (self._max_bitrate_kbps > 0
                and snapshot.bitrate_kbps is not None
                and snapshot.bitrate_kbps > self._max_bitrate_kbps):
            return False
        new_fps = max(self._floor_fps, current_fps - _STEP)
        if new_fps != current_fps:
            autocontrol_logger.info(
                "adaptive_bitrate: cap %d kbps exceeded "
                "(actual %.0f) %d -> %d fps",
                self._max_bitrate_kbps, snapshot.bitrate_kbps,
                current_fps, new_fps,
            )
            self._track.set_target_fps(new_fps)
        self._down_streak = 0
        self._up_streak = 0
        return True

    def _react_to_quality(self, snapshot: StatsSnapshot,
                          current_fps: int) -> None:
        if self._should_downscale(snapshot):
            self._handle_downscale(snapshot, current_fps)
        elif self._should_upscale(snapshot) and current_fps < self._max_fps:
            self._handle_upscale(snapshot, current_fps)
        else:
            self._down_streak = 0
            self._up_streak = 0

    @staticmethod
    def _should_downscale(snapshot: StatsSnapshot) -> bool:
        return (
            (snapshot.packet_loss_pct is not None
             and snapshot.packet_loss_pct > _LOSS_DOWN_PCT)
            or (snapshot.rtt_ms is not None and snapshot.rtt_ms > _RTT_DOWN_MS)
        )

    @staticmethod
    def _should_upscale(snapshot: StatsSnapshot) -> bool:
        return (
            snapshot.packet_loss_pct is not None
            and snapshot.packet_loss_pct < _LOSS_UP_PCT
            and (snapshot.rtt_ms is None or snapshot.rtt_ms < _RTT_DOWN_MS)
        )

    def _handle_downscale(self, snapshot: StatsSnapshot,
                          current_fps: int) -> None:
        self._down_streak += 1
        self._up_streak = 0
        if self._down_streak < _DOWNSCALE_STREAK:
            return
        new_fps = max(self._floor_fps, current_fps - _STEP)
        if new_fps != current_fps:
            rtt_label = (
                "{:.0f}ms".format(snapshot.rtt_ms) if snapshot.rtt_ms else "?"
            )
            autocontrol_logger.info(
                "adaptive_bitrate: down %d -> %d fps (loss=%.1f%% rtt=%s)",
                current_fps, new_fps,
                snapshot.packet_loss_pct or 0.0, rtt_label,
            )
            self._track.set_target_fps(new_fps)
        self._down_streak = 0

    def _handle_upscale(self, snapshot: StatsSnapshot,
                        current_fps: int) -> None:
        self._up_streak += 1
        self._down_streak = 0
        if self._up_streak < _UPSCALE_STREAK:
            return
        new_fps = min(self._max_fps, current_fps + _STEP)
        if new_fps != current_fps:
            autocontrol_logger.info(
                "adaptive_bitrate: up %d -> %d fps (loss=%.1f%%)",
                current_fps, new_fps,
                snapshot.packet_loss_pct or 0.0,
            )
            self._track.set_target_fps(new_fps)
        self._up_streak = 0

    @property
    def current_fps(self) -> int:
        return int(self._track.fps) if self._track is not None else 0


__all__ = ["AdaptiveBitrateController"]
