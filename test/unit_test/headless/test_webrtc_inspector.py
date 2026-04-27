"""Tests for the WebRTC inspector ring buffer (round 26)."""
import pytest

from je_auto_control.utils.remote_desktop.webrtc_inspector import (
    WebRTCInspector, default_webrtc_inspector,
)
from je_auto_control.utils.remote_desktop.webrtc_stats import StatsSnapshot


def test_empty_inspector_summary_is_zero():
    inspector = WebRTCInspector(capacity=10)
    summary = inspector.summary()
    assert summary["sample_count"] == 0
    assert summary["window_seconds"] == pytest.approx(0.0)
    assert summary["metrics"] == {}


def test_recent_returns_empty_when_no_samples():
    inspector = WebRTCInspector(capacity=10)
    assert inspector.recent(5) == []


def test_summary_computes_per_metric_statistics():
    inspector = WebRTCInspector(capacity=10)
    for i in range(3):
        inspector.record(StatsSnapshot(rtt_ms=10.0 + i,
                                       bitrate_kbps=1000.0 + i * 100))
    metrics = inspector.summary()["metrics"]
    assert metrics["rtt_ms"]["last"] == pytest.approx(12.0)
    assert metrics["rtt_ms"]["min"] == pytest.approx(10.0)
    assert metrics["rtt_ms"]["max"] == pytest.approx(12.0)
    assert metrics["bitrate_kbps"]["max"] == pytest.approx(1200.0)
    assert metrics["bitrate_kbps"]["avg"] == pytest.approx(1100.0)


def test_summary_handles_metric_with_only_none_values():
    """If every snapshot's rtt_ms is None, stats should be all-None, not crash."""
    inspector = WebRTCInspector(capacity=5)
    for _ in range(3):
        inspector.record(StatsSnapshot())  # all fields None
    metrics = inspector.summary()["metrics"]
    assert metrics["rtt_ms"] == {
        "last": None, "min": None, "max": None, "avg": None, "p95": None,
    }


def test_recent_returns_age_seconds_in_chronological_order():
    inspector = WebRTCInspector(capacity=10)
    for i in range(3):
        inspector.record(StatsSnapshot(rtt_ms=float(i)))
    recent = inspector.recent(3)
    assert len(recent) == 3
    # Most recent sample has age 0; older samples have larger ages.
    assert recent[-1]["age_seconds"] == pytest.approx(0.0)
    assert recent[0]["age_seconds"] >= recent[-1]["age_seconds"]


def test_ring_eviction_keeps_only_capacity_samples():
    inspector = WebRTCInspector(capacity=4)
    for i in range(10):
        inspector.record(StatsSnapshot(rtt_ms=float(i)))
    summary = inspector.summary()
    assert summary["sample_count"] == 4
    # Oldest 6 evicted; most recent should be 9.0.
    assert summary["metrics"]["rtt_ms"]["last"] == pytest.approx(9.0)


def test_reset_returns_cleared_count():
    inspector = WebRTCInspector(capacity=5)
    for _ in range(3):
        inspector.record(StatsSnapshot(rtt_ms=1.0))
    cleared = inspector.reset()
    assert cleared == 3
    assert inspector.summary()["sample_count"] == 0


def test_default_inspector_is_singleton():
    a = default_webrtc_inspector()
    b = default_webrtc_inspector()
    assert a is b


def test_recent_caps_at_buffer_size():
    """Asking for more samples than were recorded just returns what exists."""
    inspector = WebRTCInspector(capacity=10)
    for i in range(2):
        inspector.record(StatsSnapshot(rtt_ms=float(i)))
    recent = inspector.recent(50)
    assert len(recent) == 2


def test_recent_zero_is_empty():
    inspector = WebRTCInspector(capacity=10)
    inspector.record(StatsSnapshot(rtt_ms=1.0))
    assert inspector.recent(0) == []
