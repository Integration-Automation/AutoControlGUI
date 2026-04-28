"""Tests for the per-action profiler."""
import time

import pytest

from je_auto_control.utils.profiler.profiler import ActionProfiler


@pytest.fixture
def profiler():
    return ActionProfiler()


def test_profiler_disabled_by_default_records_nothing(profiler):
    with profiler.measure("AC_click_mouse"):
        time.sleep(0.001)
    assert profiler.stats() == []


def test_profiler_records_after_enable(profiler):
    profiler.enable()
    with profiler.measure("AC_click_mouse"):
        time.sleep(0.001)
    rows = profiler.stats()
    assert len(rows) == 1
    row = rows[0]
    assert row.name == "AC_click_mouse"
    assert row.calls == 1
    assert row.total_seconds >= 0.0
    assert row.last_seconds >= 0.0


def test_profiler_aggregates_multiple_calls(profiler):
    profiler.enable()
    for _ in range(3):
        profiler.record("AC_screenshot", 0.05)
    profiler.record("AC_screenshot", 0.10)
    row = profiler.get("AC_screenshot")
    assert row.calls == 4
    assert row.total_seconds == pytest.approx(0.25)
    assert row.min_seconds == pytest.approx(0.05)
    assert row.max_seconds == pytest.approx(0.10)
    assert row.average_seconds == pytest.approx(0.0625)


def test_hot_spots_sorted_by_total_time(profiler):
    profiler.enable()
    profiler.record("slow", 1.0)
    profiler.record("fast", 0.01)
    profiler.record("slow", 0.5)
    top = profiler.hot_spots(limit=2)
    assert [r.name for r in top] == ["slow", "fast"]


def test_reset_clears_samples(profiler):
    profiler.enable()
    profiler.record("AC_loop", 0.1)
    profiler.reset()
    assert profiler.stats() == []


def test_measure_records_error_and_reraises(profiler):
    profiler.enable()
    with pytest.raises(RuntimeError):
        with profiler.measure("AC_press_keyboard_key"):
            raise RuntimeError("boom")
    row = profiler.get("AC_press_keyboard_key")
    assert row.calls == 1
    assert row.errors == 1


def test_disable_keeps_existing_data(profiler):
    profiler.enable()
    profiler.record("kept", 0.2)
    profiler.disable()
    profiler.record("ignored", 0.1)
    rows = {r.name for r in profiler.stats()}
    assert rows == {"kept"}


def test_to_dict_includes_average_and_share(profiler):
    profiler.enable()
    profiler.record("a", 0.4)
    row = profiler.get("a")
    payload = row.to_dict()
    assert payload["name"] == "a"
    assert payload["calls"] == 1
    assert payload["average_seconds"] == pytest.approx(0.4)
    assert "min_seconds" in payload and "max_seconds" in payload
