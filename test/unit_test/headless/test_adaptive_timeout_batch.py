"""Headless tests for adaptive_timeout (pure timeout recommendation)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.adaptive_timeout import (
    recommend_timeout, timeout_stats,
)


# --- recommend_timeout ----------------------------------------------------

def test_recommend_scales_percentile_by_factor():
    # p95 of 1..10 ~ 9.55; * 1.0 factor, within [0.1, 100] -> ~9.55
    durations = list(range(1, 11))
    value = recommend_timeout(durations, percentile_q=95.0, factor=1.0,
                              min_s=0.1, max_s=100.0)
    assert value == pytest.approx(9.55, abs=0.1)


def test_recommend_applies_factor():
    value = recommend_timeout([2.0, 2.0, 2.0], percentile_q=95.0, factor=2.0,
                              min_s=0.1, max_s=100.0)
    assert value == pytest.approx(4.0)


def test_recommend_floors_to_min():
    value = recommend_timeout([0.01, 0.02], percentile_q=95.0, factor=1.0,
                              min_s=1.0, max_s=100.0)
    assert value == pytest.approx(1.0)


def test_recommend_caps_to_max():
    value = recommend_timeout([100.0, 200.0], percentile_q=95.0, factor=2.0,
                              min_s=1.0, max_s=10.0)
    assert value == pytest.approx(10.0)


def test_recommend_empty_uses_default_then_min():
    assert recommend_timeout([], default_s=7.0) == pytest.approx(7.0)
    assert recommend_timeout([], min_s=3.0) == pytest.approx(3.0)


def test_recommend_ignores_none_samples():
    value = recommend_timeout([None, 2.0, None, 2.0], percentile_q=50.0,
                              factor=1.0, min_s=0.1, max_s=100.0)
    assert value == pytest.approx(2.0)


# --- timeout_stats --------------------------------------------------------

def test_timeout_stats_exposes_percentiles_and_flags():
    stats = timeout_stats([1.0, 2.0, 3.0, 4.0], percentile_q=95.0, factor=1.0,
                          min_s=0.1, max_s=100.0)
    assert stats["n"] == 4
    assert stats["p50"] == pytest.approx(2.5)
    assert stats["floored"] is False
    assert stats["capped"] is False
    assert stats["recommended"] == pytest.approx(stats["p_high"])


def test_timeout_stats_flags_capped():
    stats = timeout_stats([50.0, 60.0], percentile_q=95.0, factor=2.0,
                          min_s=1.0, max_s=10.0)
    assert stats["capped"] is True
    assert stats["recommended"] == pytest.approx(10.0)


def test_timeout_stats_empty():
    stats = timeout_stats([], default_s=5.0)
    assert stats["n"] == 0
    assert stats["p50"] is None
    assert stats["recommended"] == pytest.approx(5.0)


# --- wiring ---------------------------------------------------------------

def test_executor_paths():
    from je_auto_control.utils.executor.action_executor import (
        _adaptive_timeout, _timeout_stats,
    )
    out = _adaptive_timeout([2.0, 2.0, 2.0], 95.0, 2.0, 0.1, 100.0)
    assert out["timeout_s"] == pytest.approx(4.0)
    # accepts a JSON-list string (Script Builder text field)
    out2 = _adaptive_timeout("[2.0, 2.0]", 50.0, 1.0, 0.1, 100.0)
    assert out2["timeout_s"] == pytest.approx(2.0)
    assert _timeout_stats([1.0, 2.0], 95.0, 1.0, 0.1, 100.0)["n"] == 2


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_adaptive_timeout", "AC_timeout_stats"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_adaptive_timeout", "ac_timeout_stats"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_adaptive_timeout", "AC_timeout_stats"} <= specs


def test_facade_exports():
    for name in ("recommend_timeout", "timeout_stats"):
        assert hasattr(ac, name) and name in ac.__all__
