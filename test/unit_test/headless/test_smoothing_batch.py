"""Headless tests for moving-average smoothing. Pure stdlib, no Qt."""
import json
import statistics

import pytest

import je_auto_control as ac
from je_auto_control.utils.smoothing import ewma, rolling, sma, wma


def test_sma_trailing():
    assert sma([1, 2, 3, 4], 2) == pytest.approx([1.0, 1.5, 2.5, 3.5])
    assert sma([5, 5, 5], 3) == pytest.approx([5.0, 5.0, 5.0])


def test_wma_weights_latest():
    # weights [1,2] weight the latest point twice
    assert wma([1, 3], [1, 2]) == pytest.approx([1.0, (1 * 1 + 3 * 2) / 3])


def test_ewma():
    out = ewma([1, 2, 3], alpha=0.5)
    assert out[0] == pytest.approx(1.0)
    assert out[1] == pytest.approx(1.5)
    assert out[2] == pytest.approx(2.25)


def test_rolling_generic():
    assert rolling([1, 9, 2, 8], 2, max) == pytest.approx([1, 9, 9, 8])
    assert rolling([1, 2, 3], 3, statistics.fmean)[-1] == pytest.approx(2.0)


def test_validation():
    for bad in (lambda: sma([1], 0), lambda: rolling([1], 0, sum),
                lambda: wma([1], []), lambda: list(ewma([1], alpha=0))):
        with pytest.raises(ValueError):
            bad()


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_sma", {"values": json.dumps([1, 2, 3, 4]), "window": 2}]])
    assert next(v for v in rec.values()
                if isinstance(v, dict))["series"] == pytest.approx(
        [1.0, 1.5, 2.5, 3.5])
    rec2 = ac.execute_action([[
        "AC_ewma", {"values": json.dumps([1, 2, 3]), "alpha": 0.5}]])
    assert next(v for v in rec2.values()
                if isinstance(v, dict))["series"][-1] == pytest.approx(2.25)


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_sma", "AC_ewma"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_sma", "ac_ewma"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_sma", "AC_ewma"} <= specs


def test_facade_exports():
    for attr in ("sma", "wma", "ewma", "rolling"):
        assert hasattr(ac, attr) and attr in ac.__all__
