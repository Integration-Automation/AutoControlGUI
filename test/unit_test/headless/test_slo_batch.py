"""Headless tests for SLO / error budget / burn-rate. Pure stdlib, no Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.slo import (
    BurnRule, burn_alerts, burn_rate, default_burn_rules, evaluate_slo)


def _records(good, bad, ts=1000):
    return ([{"timestamp": ts, "ok": True}] * good
            + [{"timestamp": ts, "ok": False}] * bad)


def test_evaluate_slo_budget():
    report = evaluate_slo(_records(995, 5), 0.99, now=1000)
    assert report["sli"] == pytest.approx(0.995)
    assert report["budget_total"] == pytest.approx(10.0)
    assert report["budget_remaining"] == pytest.approx(5.0)
    assert report["burn_rate"] == pytest.approx(0.5)


def test_all_good_zero_burn():
    assert burn_rate(_records(10, 0), 0.99, now=1000) == pytest.approx(0.0)


def test_empty_is_full_budget():
    report = evaluate_slo([], 0.99, now=1)
    assert report["sli"] == 1.0
    assert report["budget_remaining_fraction"] == 1.0


def test_bad_target_raises():
    with pytest.raises(AutoControlException):
        evaluate_slo(_records(1, 0), 1.5, now=1)


def test_window_excludes_old_records():
    now = 10000
    old = [{"timestamp": 0, "ok": False}] * 100
    assert burn_rate(old, 0.99, window_s=3600, now=now) == pytest.approx(0.0)


def test_burn_alerts_fire_on_high_error_rate():
    now = 10000
    records = _records(50, 50, ts=now - 10)     # 50% errors -> burn ~50
    alerts = burn_alerts(records, 0.99, now=now)
    assert {a["severity"] for a in alerts} == {"page", "ticket"}
    assert len(alerts) == 3


def test_burn_alerts_quiet_when_healthy():
    now = 10000
    records = _records(1000, 0, ts=now - 10)
    assert burn_alerts(records, 0.99, now=now) == []


def test_default_burn_rules_shape():
    rules = default_burn_rules()
    assert all(isinstance(r, BurnRule) for r in rules)
    assert rules[0].threshold == pytest.approx(14.4)


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_evaluate_slo",
        {"records": json.dumps(_records(99, 1)), "target": 0.9},
    ]])
    report = next(v for v in rec.values() if isinstance(v, dict))
    assert report["sli"] == pytest.approx(0.99)

    rec2 = ac.execute_action([[
        "AC_burn_alerts",
        {"records": json.dumps(_records(99, 1)), "target": 0.99},
    ]])
    payload = next(v for v in rec2.values() if isinstance(v, dict))
    assert "firing" in payload and "alerts" in payload


def test_wiring():
    assert {"AC_evaluate_slo", "AC_burn_alerts"} <= ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_evaluate_slo", "ac_burn_alerts"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_evaluate_slo", "AC_burn_alerts"} <= cmds


def test_facade_exports():
    for attr in ("evaluate_slo", "burn_rate", "burn_alerts", "BurnRule",
                 "default_burn_rules"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
