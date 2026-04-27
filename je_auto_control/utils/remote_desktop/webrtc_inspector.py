"""Process-global rolling window of WebRTC :class:`StatsSnapshot` samples.

Decoupled from the peer connection — anything that produces ``StatsSnapshot``
(today: :class:`StatsPoller` instances created by the GUI panel) can call
``default_webrtc_inspector().record(snapshot)`` to feed live data in. The
inspector is the read side: REST, executor, and GUI all pull from it.

Default capacity is 600 samples — enough for ~10 minutes at 1 Hz, which
is what the existing pollers run at. Old samples evict FIFO.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional

from je_auto_control.utils.remote_desktop.webrtc_stats import StatsSnapshot


_DEFAULT_CAPACITY = 600


@dataclass
class _SamplePoint:
    """One ``record()`` call: monotonic timestamp + the snapshot."""
    ts: float
    snapshot: StatsSnapshot


class WebRTCInspector:
    """Bounded ring buffer of stats samples + summary helpers."""

    def __init__(self, capacity: int = _DEFAULT_CAPACITY) -> None:
        self._capacity = max(1, int(capacity))
        self._samples: Deque[_SamplePoint] = deque(maxlen=self._capacity)
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def record(self, snapshot: StatsSnapshot) -> None:
        with self._lock:
            self._samples.append(_SamplePoint(ts=time.monotonic(),
                                              snapshot=snapshot))

    def reset(self) -> int:
        with self._lock:
            count = len(self._samples)
            self._samples.clear()
        return count

    def recent(self, n: int = 60) -> List[Dict[str, Any]]:
        n = max(0, int(n))
        if n == 0:
            return []
        with self._lock:
            tail = list(self._samples)[-n:]
        if not tail:
            return []
        anchor = tail[-1].ts
        return [
            {
                "age_seconds": round(anchor - point.ts, 3),
                **point.snapshot.to_dict(),
            }
            for point in tail
        ]

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            samples = list(self._samples)
        if not samples:
            return {"sample_count": 0, "window_seconds": 0.0, "metrics": {}}
        first_ts = samples[0].ts
        last_ts = samples[-1].ts
        return {
            "sample_count": len(samples),
            "window_seconds": round(last_ts - first_ts, 3),
            "metrics": {
                metric: _summarize(metric, samples)
                for metric in (
                    "rtt_ms", "fps", "bitrate_kbps",
                    "packet_loss_pct", "jitter_ms",
                )
            },
        }


def _summarize(metric: str,
               samples: List[_SamplePoint]) -> Dict[str, Optional[float]]:
    values: List[float] = []
    for point in samples:
        value = getattr(point.snapshot, metric, None)
        if value is None:
            continue
        values.append(float(value))
    if not values:
        return {"last": None, "min": None, "max": None,
                "avg": None, "p95": None}
    return {
        "last": values[-1],
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
        "p95": _percentile(values, 0.95),
    }


def _percentile(values: List[float], pct: float) -> float:
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = pct * (len(ordered) - 1)
    low = int(rank)
    high = min(len(ordered) - 1, low + 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


_default_inspector: Optional[WebRTCInspector] = None
_default_lock = threading.Lock()


def default_webrtc_inspector() -> WebRTCInspector:
    """Process-wide singleton fed by the panel's StatsPoller callbacks."""
    global _default_inspector
    with _default_lock:
        if _default_inspector is None:
            _default_inspector = WebRTCInspector()
        return _default_inspector


__all__ = [
    "WebRTCInspector", "default_webrtc_inspector",
]
