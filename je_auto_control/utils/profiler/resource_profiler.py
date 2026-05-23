"""Phase 7.3: psutil-based CPU / RSS / FPS sampling profiler.

Sits next to :class:`ActionProfiler` (wall-clock only). Where the action
profiler answers "which action is slow?" this one answers "is the
process CPU-starved or memory-bloated *while* that action runs?". A
background thread polls ``psutil.Process()`` every ``interval``
seconds; the executor wraps each action in :meth:`ResourceProfiler.span`
to tag the samples with the action name.

The sampler is **opt-in** and **psutil is optional** — if psutil is
not installed the profiler degrades to a no-op sampler that still
records FPS via :meth:`tick_frame` (useful for streaming hosts).

Output (:meth:`flame_graph_payload`) is a JSON blob compatible with
the `speedscope <https://www.speedscope.app/>`_ "single-thread"
format, so an operator can drop it into the speedscope web viewer
and get the usual flame-graph treatment for free.
"""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional


@dataclass
class _Sample:
    """One CPU/memory snapshot tagged with the active action name."""
    timestamp: float
    cpu_percent: float
    rss_bytes: int
    action: Optional[str]


@dataclass
class ResourceReport:
    """Aggregated counters; produced by :meth:`ResourceProfiler.report`."""
    duration_s: float
    sample_count: int
    cpu_percent_avg: float
    cpu_percent_max: float
    rss_bytes_avg: int
    rss_bytes_max: int
    fps_avg: float
    per_action: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "duration_s": self.duration_s,
            "sample_count": self.sample_count,
            "cpu_percent_avg": self.cpu_percent_avg,
            "cpu_percent_max": self.cpu_percent_max,
            "rss_bytes_avg": self.rss_bytes_avg,
            "rss_bytes_max": self.rss_bytes_max,
            "fps_avg": self.fps_avg,
            "per_action": self.per_action,
        }


def _try_psutil():
    try:
        import psutil  # noqa: F401
        return psutil
    except ImportError:
        return None


class ResourceProfiler:
    """Background CPU / RSS / FPS sampler with per-action tagging."""

    def __init__(self, *, interval: float = 0.5) -> None:
        self._interval = max(0.05, float(interval))
        self._psutil = _try_psutil()
        self._proc = self._psutil.Process(os.getpid()) if self._psutil else None
        self._lock = threading.Lock()
        self._samples: List[_Sample] = []
        self._frames: List[float] = []
        self._current_action: Optional[str] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started_at: Optional[float] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def has_psutil(self) -> bool:
        return self._psutil is not None

    def start(self) -> None:
        """Spawn the sampling thread (no-op when already running)."""
        if self.is_running:
            return
        self._stop.clear()
        self._samples = []
        self._frames = []
        self._started_at = time.monotonic()
        if self._psutil is None:
            return  # FPS-only mode; no sampling thread needed
        # Warm up cpu_percent so the first real call returns a real number.
        try:
            self._proc.cpu_percent(interval=None)
        except (AttributeError, OSError):
            pass
        self._thread = threading.Thread(
            target=self._sample_loop, name="resource-profiler", daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        """Stop the sampling thread; idempotent."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    @contextmanager
    def span(self, action_name: str) -> Iterator[None]:
        """Tag the samples taken while the ``with`` block runs."""
        previous: Optional[str]
        with self._lock:
            previous = self._current_action
            self._current_action = action_name
        try:
            yield
        finally:
            with self._lock:
                self._current_action = previous

    def tick_frame(self) -> None:
        """Record one frame timestamp for FPS aggregation."""
        with self._lock:
            self._frames.append(time.monotonic())

    def report(self) -> ResourceReport:
        """Snapshot the current counters into a :class:`ResourceReport`."""
        with self._lock:
            samples = list(self._samples)
            frames = list(self._frames)
            started = self._started_at
        duration = max(time.monotonic() - (started or 0.0), 0.0001)
        if samples:
            cpus = [s.cpu_percent for s in samples]
            rsses = [s.rss_bytes for s in samples]
            cpu_avg = sum(cpus) / len(cpus)
            cpu_max = max(cpus)
            rss_avg = int(sum(rsses) / len(rsses))
            rss_max = max(rsses)
        else:
            cpu_avg = cpu_max = rss_avg = rss_max = 0
        return ResourceReport(
            duration_s=round(duration, 3),
            sample_count=len(samples),
            cpu_percent_avg=round(cpu_avg, 2),
            cpu_percent_max=round(cpu_max, 2),
            rss_bytes_avg=int(rss_avg),
            rss_bytes_max=int(rss_max),
            fps_avg=round(len(frames) / duration, 2),
            per_action=_aggregate_per_action(samples),
        )

    def speedscope_payload(self) -> Dict[str, Any]:
        """Render the samples in speedscope's ``sampled`` JSON format.

        Drop the resulting JSON into https://www.speedscope.app/ for an
        instant flame-graph view tagged by AC_* action name.
        """
        with self._lock:
            samples = list(self._samples)
        names: List[str] = []
        name_index: Dict[str, int] = {}
        sample_ids: List[List[int]] = []
        weights: List[float] = []
        for i, sample in enumerate(samples):
            label = sample.action or "(idle)"
            if label not in name_index:
                name_index[label] = len(names)
                names.append(label)
            sample_ids.append([name_index[label]])
            if i + 1 < len(samples):
                weights.append(samples[i + 1].timestamp - sample.timestamp)
            else:
                weights.append(self._interval)
        return {
            "exporter": "autocontrol-resource-profiler",
            "shared": {"frames": [{"name": n} for n in names]},
            "profiles": [{
                "type": "sampled",
                "name": "autocontrol",
                "unit": "seconds",
                "startValue": 0,
                "endValue": sum(weights) if weights else 0,
                "samples": sample_ids,
                "weights": weights,
            }],
        }

    def speedscope_json(self) -> str:
        """Convenience: speedscope payload serialised."""
        return json.dumps(self.speedscope_payload(), indent=2)

    def _sample_loop(self) -> None:
        psutil = self._psutil
        proc = self._proc
        if psutil is None or proc is None:
            return
        while not self._stop.is_set():
            try:
                cpu = proc.cpu_percent(interval=None)
                rss = proc.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                break
            with self._lock:
                action = self._current_action
                self._samples.append(_Sample(
                    timestamp=time.monotonic(),
                    cpu_percent=cpu, rss_bytes=int(rss),
                    action=action,
                ))
            if self._stop.wait(self._interval):
                break


def _aggregate_per_action(samples: List[_Sample]) -> Dict[str, Dict[str, float]]:
    """Group samples by action and compute averages."""
    buckets: Dict[str, List[_Sample]] = {}
    for s in samples:
        buckets.setdefault(s.action or "(idle)", []).append(s)
    out: Dict[str, Dict[str, float]] = {}
    for name, items in buckets.items():
        cpus = [i.cpu_percent for i in items]
        rsses = [i.rss_bytes for i in items]
        out[name] = {
            "samples": len(items),
            "cpu_percent_avg": round(sum(cpus) / len(cpus), 2),
            "cpu_percent_max": round(max(cpus), 2),
            "rss_bytes_avg": int(sum(rsses) / len(rsses)),
            "rss_bytes_max": max(rsses),
        }
    return out


_default_resource_profiler: Optional[ResourceProfiler] = None
_default_lock = threading.Lock()


def default_resource_profiler() -> ResourceProfiler:
    """Process-wide profiler used by GUI / REST adapters."""
    global _default_resource_profiler
    with _default_lock:
        if _default_resource_profiler is None:
            _default_resource_profiler = ResourceProfiler()
        return _default_resource_profiler


__all__ = [
    "ResourceProfiler", "ResourceReport", "default_resource_profiler",
]
