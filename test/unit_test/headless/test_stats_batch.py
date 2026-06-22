"""Headless tests for statistics + A/B significance. Pure stdlib, no Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.stats import (
    chi_square_2x2, cohens_d, describe, normal_cdf, percentile,
    two_proportion_z_test, welch_t_test)


def test_percentile_linear_and_nearest():
    data = list(range(1, 11))
    assert percentile(data, 50) == pytest.approx(5.5)
    assert percentile(data, 90) == pytest.approx(9.1)
    assert percentile(data, 0) == 1
    assert percentile(data, 100) == 10
    assert percentile([1, 2, 3, 4], 50, method="nearest") == 2


def test_percentile_empty_raises():
    with pytest.raises(AutoControlException):
        percentile([], 50)


def test_describe():
    summary = describe([2, 4, 4, 4, 5, 5, 7, 9])
    assert summary["n"] == 8
    assert summary["mean"] == pytest.approx(5.0)
    assert summary["stdev"] == pytest.approx(2.0)   # population stdev
    assert summary["min"] == 2 and summary["max"] == 9
    assert "p95" in summary


def test_normal_cdf():
    assert normal_cdf(0) == pytest.approx(0.5)
    assert normal_cdf(1.96) == pytest.approx(0.975, abs=1e-3)
    assert normal_cdf(-1.96) == pytest.approx(0.025, abs=1e-3)


def test_two_proportion_z_test_textbook():
    result = two_proportion_z_test(90, 200, 110, 200)
    assert result["z"] == pytest.approx(2.0, abs=1e-2)
    assert result["p_value"] == pytest.approx(0.0455, abs=1e-3)
    assert result["significant"] is True
    assert result["ci_low"] < result["diff"] < result["ci_high"]


def test_two_proportion_no_difference():
    result = two_proportion_z_test(50, 100, 50, 100)
    assert result["p_value"] == pytest.approx(1.0, abs=1e-6)
    assert result["significant"] is False


def test_two_proportion_bad_args():
    with pytest.raises(AutoControlException):
        two_proportion_z_test(1, 0, 1, 10)


def test_welch_t_test_significant_and_not():
    sig = welch_t_test([5.1, 4.9, 5.0, 5.2, 4.8], [6.1, 5.9, 6.0, 6.2, 5.8])
    assert sig["significant"] is True
    assert sig["p_value"] < 0.001
    weak = welch_t_test([1, 2, 3, 4, 5], [2, 3, 4, 5, 6])
    assert weak["significant"] is False
    assert weak["p_value"] == pytest.approx(0.3466, abs=1e-3)


def test_welch_requires_two_values():
    with pytest.raises(AutoControlException):
        welch_t_test([1], [1, 2, 3])


def test_cohens_d():
    d = cohens_d([5.1, 4.9, 5.0, 5.2, 4.8], [6.1, 5.9, 6.0, 6.2, 5.8])
    assert d > 2.0    # very large effect


def test_chi_square_equals_z_squared():
    # the well-known identity: chi2 (df=1) == z^2 for the same 2x2 table
    z = two_proportion_z_test(90, 200, 110, 200)["z"]
    chi = chi_square_2x2(90, 110, 110, 90)
    assert chi["chi2"] == pytest.approx(z ** 2, abs=1e-6)
    assert chi["df"] == 1
    assert chi["significant"] is True


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_describe_stats", {"values": json.dumps([10, 20, 30, 40])},
    ]])
    summary = next(v for v in rec.values() if isinstance(v, dict))
    assert summary["n"] == 4 and summary["mean"] == pytest.approx(25.0)

    rec2 = ac.execute_action([[
        "AC_ab_significance",
        {"a_conv": 90, "a_n": 200, "b_conv": 110, "b_n": 200},
    ]])
    result = next(v for v in rec2.values() if isinstance(v, dict))
    assert result["significant"] is True


def test_wiring():
    assert {"AC_describe_stats", "AC_ab_significance"} <= ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_describe_stats", "ac_ab_significance"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_describe_stats", "AC_ab_significance"} <= cmds


def test_facade_exports():
    for attr in ("percentile", "describe", "normal_cdf",
                 "two_proportion_z_test", "welch_t_test", "cohens_d",
                 "chi_square_2x2"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
