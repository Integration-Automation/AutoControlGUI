"""Headless tests for the DMN-style decision table. Pure stdlib, no Qt imports."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.decision_table import DecisionTable, evaluate_table

SPEC = {
    "inputs": ["age", "country"],
    "hit_policy": "FIRST",
    "rules": [
        {"conditions": {"age": {"op": "lt", "value": 18}},
         "outputs": {"tier": "minor"}},
        {"conditions": {"age": {"op": "ge", "value": 18}, "country": "US"},
         "outputs": {"tier": "us-adult"}},
        {"conditions": {"age": {"op": "ge", "value": 18}},
         "outputs": {"tier": "adult"}},
    ],
}


def test_first_match_wins():
    assert evaluate_table(SPEC, {"age": 10, "country": "US"}) == {"tier": "minor"}
    assert evaluate_table(SPEC, {"age": 30, "country": "US"}) == \
        {"tier": "us-adult"}
    assert evaluate_table(SPEC, {"age": 30, "country": "DE"}) == \
        {"tier": "adult"}


def test_no_match_returns_empty():
    spec = {"inputs": ["x"], "hit_policy": "FIRST",
            "rules": [{"conditions": {"x": 1}, "outputs": {"y": 1}}]}
    assert evaluate_table(spec, {"x": 99}) == {}


def test_collect_returns_all():
    collect = dict(SPEC, hit_policy="COLLECT")
    result = evaluate_table(collect, {"age": 30, "country": "US"})
    assert result == [{"tier": "us-adult"}, {"tier": "adult"}]


def test_unique_multi_match_raises():
    spec = {"inputs": ["x"], "hit_policy": "UNIQUE", "rules": [
        {"conditions": {"x": 1}, "outputs": {"a": 1}},
        {"conditions": {"x": {"op": "ge", "value": 0}}, "outputs": {"a": 2}},
    ]}
    with pytest.raises(ValueError):
        evaluate_table(spec, {"x": 1})


def test_wildcard_and_literal_conditions():
    spec = {"inputs": ["role", "active"], "hit_policy": "FIRST", "rules": [
        {"conditions": {"role": "admin", "active": None},   # active = wildcard
         "outputs": {"allow": True}},
        {"conditions": {"role": "-", "active": True},        # role = wildcard
         "outputs": {"allow": False}},
    ]}
    assert evaluate_table(spec, {"role": "admin", "active": False}) == \
        {"allow": True}
    assert evaluate_table(spec, {"role": "guest", "active": True}) == \
        {"allow": False}


def test_unknown_op_raises():
    spec = {"inputs": ["x"], "hit_policy": "FIRST",
            "rules": [{"conditions": {"x": {"op": "between", "value": 1}},
                       "outputs": {"y": 1}}]}
    with pytest.raises(ValueError):
        evaluate_table(spec, {"x": 1})


def test_direct_class_api():
    from je_auto_control.utils.decision_table import Rule
    table = DecisionTable(["n"], [Rule({"n": {"op": "gt", "value": 5}},
                                       {"big": True})], hit_policy="COLLECT")
    assert table.evaluate({"n": 9}) == [{"big": True}]
    assert table.evaluate({"n": 1}) == []


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    import json
    rec = ac.execute_action([[
        "AC_decision_table",
        {"spec": json.dumps(SPEC), "context": json.dumps({"age": 30,
                                                          "country": "DE"})},
    ]])
    out = next(v for v in rec.values() if isinstance(v, dict) and "result" in v)
    assert out["result"] == {"tier": "adult"}


def test_wiring():
    assert "AC_decision_table" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_decision_table" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert "AC_decision_table" in cmds


def test_facade_exports():
    for attr in ("DecisionTable", "Rule", "evaluate_table"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
