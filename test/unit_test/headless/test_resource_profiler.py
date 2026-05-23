"""Phase 7.3: tests for the CPU / RSS / FPS resource profiler."""
import json
import time

import pytest

from je_auto_control.utils.profiler.resource_profiler import (
    ResourceProfiler, _Sample,  # noqa: SLF001  test-only access
)


# --- without psutil (FPS-only mode) -------------------------------

def test_starts_and_stops_without_psutil(monkeypatch):
    monkeypatch.setattr(
        "je_auto_control.utils.profiler.resource_profiler._try_psutil",
        lambda: None,
    )
    prof = ResourceProfiler(interval=0.05)
    assert prof.has_psutil is False
    prof.start()
    # FPS still works without psutil.
    for _ in range(3):
        prof.tick_frame()
    time.sleep(0.05)
    prof.stop()
    report = prof.report()
    assert report.sample_count == 0  # no CPU/RSS samples
    assert report.fps_avg > 0  # but FPS got counted


# --- happy path with synthetic samples ---------------------------

def _seed_samples(prof: ResourceProfiler, samples: list) -> None:
    """Inject synthetic samples so we don't have to wait for the real thread."""
    prof._started_at = time.monotonic() - 1.0  # noqa: SLF001
    prof._samples.extend(samples)  # noqa: SLF001


def test_report_aggregates_cpu_and_rss():
    prof = ResourceProfiler()
    _seed_samples(prof, [
        _Sample(timestamp=time.monotonic(), cpu_percent=10.0,
                rss_bytes=100, action="AC_a"),
        _Sample(timestamp=time.monotonic() + 0.5, cpu_percent=80.0,
                rss_bytes=300, action="AC_a"),
        _Sample(timestamp=time.monotonic() + 1.0, cpu_percent=20.0,
                rss_bytes=150, action="AC_b"),
    ])
    report = prof.report()
    assert report.sample_count == 3
    assert report.cpu_percent_max == pytest.approx(80.0)
    assert report.cpu_percent_avg == pytest.approx(round((10 + 80 + 20) / 3, 2))
    assert report.rss_bytes_max == 300
    assert set(report.per_action.keys()) == {"AC_a", "AC_b"}
    assert report.per_action["AC_a"]["samples"] == 2
    assert report.per_action["AC_a"]["cpu_percent_max"] == pytest.approx(80.0)


def test_per_action_idle_when_no_span_tag():
    prof = ResourceProfiler()
    _seed_samples(prof, [
        _Sample(timestamp=time.monotonic(), cpu_percent=1.0,
                rss_bytes=10, action=None),
    ])
    report = prof.report()
    assert "(idle)" in report.per_action


def test_fps_calculated_against_real_duration():
    prof = ResourceProfiler()
    prof._started_at = time.monotonic() - 2.0  # noqa: SLF001
    for _ in range(50):
        prof.tick_frame()
    report = prof.report()
    # 50 frames over ~2 s = ~25 FPS; allow some slack.
    assert 20 < report.fps_avg < 35


def test_to_dict_round_trips():
    prof = ResourceProfiler()
    report = prof.report()
    body = report.to_dict()
    assert set(body.keys()) >= {
        "duration_s", "sample_count", "cpu_percent_avg",
        "cpu_percent_max", "rss_bytes_avg", "rss_bytes_max",
        "fps_avg", "per_action",
    }


# --- span tagging -------------------------------------------------

def test_span_changes_current_action_for_subsequent_samples():
    prof = ResourceProfiler()
    captured: list = []
    with prof.span("AC_outer"):
        captured.append(prof._current_action)  # noqa: SLF001
        with prof.span("AC_inner"):
            captured.append(prof._current_action)  # noqa: SLF001
        captured.append(prof._current_action)  # noqa: SLF001
    captured.append(prof._current_action)  # noqa: SLF001
    assert captured == ["AC_outer", "AC_inner", "AC_outer", None]


def test_span_restores_previous_action_after_exception():
    prof = ResourceProfiler()
    with prof.span("AC_outer"):
        try:
            with prof.span("AC_inner"):
                raise RuntimeError("oops")
        except RuntimeError:
            pass
        assert prof._current_action == "AC_outer"  # noqa: SLF001
    assert prof._current_action is None  # noqa: SLF001


# --- speedscope export -------------------------------------------

def test_speedscope_payload_lists_frames_and_weights():
    prof = ResourceProfiler(interval=0.5)
    base = time.monotonic()
    _seed_samples(prof, [
        _Sample(timestamp=base, cpu_percent=10.0, rss_bytes=100, action="A"),
        _Sample(timestamp=base + 0.2, cpu_percent=20.0,
                rss_bytes=110, action="B"),
        _Sample(timestamp=base + 0.5, cpu_percent=30.0,
                rss_bytes=120, action="A"),
    ])
    payload = prof.speedscope_payload()
    names = [f["name"] for f in payload["shared"]["frames"]]
    assert "A" in names and "B" in names
    profile = payload["profiles"][0]
    assert profile["type"] == "sampled"
    assert len(profile["samples"]) == 3
    assert len(profile["weights"]) == 3


def test_speedscope_json_parses_back():
    prof = ResourceProfiler()
    parsed = json.loads(prof.speedscope_json())
    # Even with zero samples the payload structure is valid speedscope.
    assert parsed["profiles"][0]["type"] == "sampled"


# --- lifecycle ----------------------------------------------------

def test_double_start_is_a_noop():
    prof = ResourceProfiler(interval=0.05)
    prof.start()
    prof.start()
    prof.stop()


def test_stop_without_start_is_a_noop():
    ResourceProfiler().stop()
