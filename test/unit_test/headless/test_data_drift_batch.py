"""Headless tests for distribution drift detection. Pure stdlib, no Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.data_drift import (
    categorical_drift, detect_drift, ks_two_sample, psi,
)


def test_psi_zero_for_identical_distributions():
    sample = [float(value) for value in range(100)]
    assert psi(sample, sample) == pytest.approx(0.0, abs=1e-9)


def test_psi_grows_when_distribution_shifts():
    reference = [float(value) for value in range(100)]
    shifted = [value + 100.0 for value in reference]
    assert psi(reference, shifted) > 0.25       # large shift → significant PSI


def test_ks_identical_has_zero_statistic():
    sample = [float(value) for value in range(50)]
    result = ks_two_sample(sample, sample)
    assert result["statistic"] == pytest.approx(0.0)
    assert result["p_value"] == pytest.approx(1.0)


def test_ks_detects_separation():
    low = [float(value) for value in range(50)]
    high = [value + 1000.0 for value in low]
    result = ks_two_sample(low, high)
    assert result["statistic"] == pytest.approx(1.0)
    assert result["p_value"] < 0.05


def test_categorical_drift_summary():
    reference = ["a"] * 8 + ["b"] * 2
    current = ["a"] * 2 + ["b"] * 8
    result = categorical_drift(reference, current)
    assert result["categories"] == 2
    assert result["total_variation"] == pytest.approx(0.6)
    assert result["chi_square"] > 0


def test_detect_drift_report_and_threshold():
    reference = [float(value) for value in range(100)]
    same = list(reference)
    assert detect_drift(reference, same)["drifted"] is False
    shifted = [value + 100.0 for value in reference]
    report = detect_drift(reference, shifted)
    assert report["drifted"] is True and report["psi"] > 0.25
    assert "ks" in report


def test_empty_inputs_raise():
    with pytest.raises(ValueError):
        psi([], [1.0])


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    reference = list(range(100))
    shifted = [value + 100 for value in reference]
    rec = ac.execute_action([[
        "AC_detect_drift",
        {"reference": json.dumps(reference), "current": json.dumps(shifted)}]])
    report = next(v for v in rec.values() if isinstance(v, dict))
    assert report["drifted"] is True
    rec2 = ac.execute_action([[
        "AC_categorical_drift",
        {"reference": json.dumps(["a", "a", "b"]),
         "current": json.dumps(["b", "b", "a"])}]])
    cat = next(v for v in rec2.values() if isinstance(v, dict))
    assert cat["categories"] == 2


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_detect_drift", "AC_categorical_drift"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_detect_drift", "ac_categorical_drift"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_detect_drift", "AC_categorical_drift"} <= specs


def test_facade_exports():
    for attr in ("psi", "ks_two_sample", "categorical_drift", "detect_drift"):
        assert hasattr(ac, attr) and attr in ac.__all__
