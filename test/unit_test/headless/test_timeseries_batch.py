"""Headless tests for time-series transforms. Pure stdlib, no Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.timeseries import (
    ts_delta, ts_downsample, ts_idelta, ts_increase, ts_irate, ts_rate,
    ts_resample,
)


def test_rate_and_increase():
    series = [(0, 0), (10, 50), (20, 120)]
    assert ts_increase(series) == pytest.approx(120.0)
    assert ts_rate(series) == pytest.approx(6.0)        # 120 over 20s


def test_rate_handles_counter_reset():
    series = [(0, 90), (10, 100), (20, 5), (30, 25)]    # reset between 100 and 5
    # increase = (100-90) + reset(5) + (25-5) = 10 + 5 + 20 = 35
    assert ts_increase(series) == pytest.approx(35.0)
    assert ts_rate(series) == pytest.approx(35.0 / 30)


def test_rate_window():
    series = [(0, 0), (10, 10), (20, 30), (30, 60)]
    # window 10 keeps the last two points (20,30),(30,60) → 30 over 10s
    assert ts_rate(series, window_s=10) == pytest.approx(3.0)


def test_irate_and_delta():
    series = [(0, 0), (10, 10), (20, 40)]
    assert ts_irate(series) == pytest.approx(3.0)       # (40-10)/10
    assert ts_delta(series) == pytest.approx(40.0)
    assert ts_idelta(series) == pytest.approx(30.0)


def test_downsample_aggregates():
    series = [(0, 1), (3, 3), (5, 10), (12, 9)]
    buckets = ts_downsample(series, 5, "avg")
    assert buckets[0] == (0, pytest.approx(2.0))        # bucket [0,5): 1,3
    assert dict(ts_downsample(series, 5, "max"))[5] == pytest.approx(10.0)
    assert dict(ts_downsample(series, 5, "count"))[0] == 2


def test_downsample_validation():
    with pytest.raises(ValueError):
        ts_downsample([(0, 1)], 0)
    with pytest.raises(ValueError):
        ts_downsample([(0, 1)], 5, "median")


def test_resample_fill_modes():
    series = [(0, 0), (20, 20)]
    last = ts_resample(series, 10, fill="last")
    assert [t for t, _ in last] == [0, 10, 20]
    assert [v for _, v in last] == pytest.approx([0.0, 0.0, 20.0])
    linear = ts_resample(series, 10, fill="linear")
    assert linear[1][1] == pytest.approx(10.0)          # midpoint interpolated
    nofill = ts_resample(series, 10, fill=None)
    assert nofill[1][1] is None


def test_empty_series():
    assert ts_rate([]) == pytest.approx(0.0) and ts_resample([], 5) == []


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    series = json.dumps([[0, 0], [10, 50], [20, 120]])
    rec = ac.execute_action([["AC_ts_rate", {"series": series}]])
    assert next(v for v in rec.values()
                if isinstance(v, dict))["rate"] == pytest.approx(6.0)
    rec2 = ac.execute_action([[
        "AC_ts_downsample", {"series": series, "bucket_s": 10}]])
    buckets = next(v for v in rec2.values() if isinstance(v, dict))["buckets"]
    assert len(buckets) == 3


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_ts_rate", "AC_ts_downsample"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_ts_rate", "ac_ts_downsample"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_ts_rate", "AC_ts_downsample"} <= specs


def test_facade_exports():
    for attr in ("ts_rate", "ts_irate", "ts_increase", "ts_delta", "ts_idelta",
                 "ts_downsample", "ts_resample"):
        assert hasattr(ac, attr) and attr in ac.__all__
