"""Headless tests for single-series anomaly detection. Pure stdlib, no Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.anomaly import (
    detect_anomalies, ewma_control, mad_anomalies, mad_scores,
    zscore_anomalies, zscore_scores,
)

_SERIES = [10, 11, 9, 10, 12, 10, 95, 11, 10]   # index 6 is the spike


def test_zscore_flags_spike():
    assert 6 in zscore_anomalies(_SERIES, threshold=2.0)
    assert zscore_anomalies([5, 5, 5, 5]) == []      # zero variance → none
    assert len(zscore_scores(_SERIES)) == len(_SERIES)


def test_mad_is_robust():
    # MAD ignores the spike's inflation of the spread, so it still flags it
    assert mad_anomalies(_SERIES) == [6]
    scores = mad_scores(_SERIES)
    assert abs(scores[6]) > abs(scores[0])


def test_ewma_control_flags_shift():
    flat = [10.0] * 10
    assert ewma_control(flat) == []                  # stable → no breach
    shifted = [10] * 5 + [40] * 5                     # sustained level shift
    # baseline established from the stable level → the shift breaches
    assert ewma_control(shifted, alpha=0.5,
                        target_mean=10, target_sigma=1) != []


def test_detect_anomalies_records():
    results = detect_anomalies(_SERIES, method="mad")
    assert len(results) == len(_SERIES)
    spike = results[6]
    assert spike["index"] == 6 and spike["value"] == 95
    assert spike["is_anomaly"] is True
    assert results[0]["is_anomaly"] is False


def test_detect_zscore_and_threshold():
    loose = detect_anomalies(_SERIES, method="zscore", threshold=10.0)
    assert all(r["is_anomaly"] is False for r in loose)   # threshold too high


def test_detect_unknown_method():
    with pytest.raises(ValueError):
        detect_anomalies(_SERIES, method="nope")


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_detect_anomalies", {"values": json.dumps(_SERIES)}]])
    results = next(v for v in rec.values() if isinstance(v, dict))["results"]
    assert results[6]["is_anomaly"] is True


def test_wiring():
    assert "AC_detect_anomalies" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_detect_anomalies" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_detect_anomalies" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("detect_anomalies", "ewma_control", "mad_anomalies",
                 "mad_scores", "zscore_anomalies", "zscore_scores"):
        assert hasattr(ac, attr) and attr in ac.__all__
