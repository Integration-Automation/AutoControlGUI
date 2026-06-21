"""Headless tests for the streaming latency digest. Pure stdlib, no Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.percentiles import LatencyDigest, exact_percentiles


def test_exact_percentiles():
    result = exact_percentiles(list(range(1, 101)), qs=(50, 90, 99))
    assert result[50] == pytest.approx(50.5)
    assert result[90] == pytest.approx(90.1)


def test_digest_percentiles_approximate():
    digest = LatencyDigest(sig_figs=3)
    for value in range(1, 1001):
        digest.record(value)
    assert digest.count == 1000
    assert digest.percentile(50) == pytest.approx(500, abs=5)
    assert digest.percentile(99) == pytest.approx(990, abs=5)


def test_digest_summary():
    digest = LatencyDigest()
    for value in (10, 20, 30, 40):
        digest.record(value)
    summary = digest.summary()
    assert summary["count"] == 4
    assert summary["min"] == pytest.approx(10)
    assert summary["max"] == pytest.approx(40)
    assert summary["mean"] == pytest.approx(25)


def test_digest_merge_is_associative():
    left = LatencyDigest()
    right = LatencyDigest()
    for value in range(1, 501):
        left.record(value)
    for value in range(501, 1001):
        right.record(value)
    left.merge(right)
    assert left.count == 1000
    assert left.percentile(50) == pytest.approx(500, abs=5)


def test_empty_digest():
    digest = LatencyDigest()
    assert digest.percentile(50) == pytest.approx(0.0)
    assert digest.count == 0


def test_quantiles_helper():
    digest = LatencyDigest()
    for value in (100, 100, 100, 200):
        digest.record(value)
    quantiles = digest.quantiles([50, 100])
    assert quantiles[100] == pytest.approx(200, abs=1)


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_percentiles",
        {"samples": json.dumps([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
         "qs": json.dumps([50, 90])},
    ]])
    payload = next(v for v in rec.values() if isinstance(v, dict))["percentiles"]
    assert "50" in payload and "90" in payload


def test_wiring():
    assert "AC_percentiles" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_percentiles" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_percentiles" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("LatencyDigest", "exact_percentiles"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
