"""Headless tests for JSON contract / snapshot matching. Pure stdlib, no Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.json_contract import (
    MatchReport, diff_json, match_json, normalize_json, snapshot)


def test_exact_match():
    report = match_json({"a": 1, "b": [1, 2]}, {"a": 1, "b": [1, 2]})
    assert isinstance(report, MatchReport)
    assert report.ok is True and report.mismatches == []


def test_changed_value():
    report = match_json({"a": 1, "b": 2}, {"a": 1, "b": 3})
    assert report.ok is False
    assert report.mismatches[0]["path"] == "$.b"
    assert report.mismatches[0]["kind"] == "changed"


def test_missing_and_extra():
    report = match_json({"a": 1, "c": 9}, {"a": 1, "b": 2})
    kinds = sorted(d["kind"] for d in report.mismatches)
    assert kinds == ["extra", "missing"]


def test_partial_ignores_extra():
    assert match_json({"a": 1, "extra": 9}, {"a": 1}, partial=True).ok is True
    assert match_json({"a": 1, "extra": 9}, {"a": 1}).ok is False


def test_match_type():
    assert match_json({"name": "Bob", "age": 40},
                      {"name": "Alice", "age": 30}, match_type=True).ok is True
    assert match_json({"age": "x"}, {"age": 30}, match_type=True).ok is False


def test_ignore_path():
    assert match_json({"a": 1, "ts": 999}, {"a": 1, "ts": 111},
                      ignore=["$.ts"]).ok is True


def test_bool_distinct_from_int():
    assert match_json({"a": True}, {"a": 1}).ok is False


def test_nested_list_index_path():
    report = match_json({"u": {"tags": ["x", "Y"]}},
                        {"u": {"tags": ["x", "y"]}})
    assert report.mismatches[0]["path"] == "$.u.tags[1]"


def test_diff_json_list_length():
    diffs = diff_json([1, 2], [1, 2, 3])
    assert diffs == [{"path": "$[2]", "kind": "missing", "expected": 3}]


def test_normalize_sorts_and_drops():
    assert normalize_json({"b": 2, "a": 1, "secret": "x"}, drop=["secret"]) == \
        {"a": 1, "b": 2}


def test_snapshot_create_then_compare(tmp_path):
    path = str(tmp_path / "snap.json")
    assert snapshot({"x": 1}, path) is True     # created
    assert snapshot({"x": 1}, path) is True      # matches
    assert snapshot({"x": 2}, path) is False     # differs


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_match_json",
        {"actual": json.dumps({"a": 1, "b": 9}),
         "expected": json.dumps({"a": 1, "b": 2})},
    ]])
    payload = next(v for v in rec.values() if isinstance(v, dict))
    assert payload["ok"] is False

    rec2 = ac.execute_action([[
        "AC_diff_json",
        {"actual": json.dumps([1]), "expected": json.dumps([1, 2])},
    ]])
    diffs = next(v for v in rec2.values() if isinstance(v, dict))["diffs"]
    assert diffs[0]["kind"] == "missing"


def test_wiring():
    assert {"AC_match_json", "AC_diff_json"} <= ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_match_json", "ac_diff_json"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_match_json", "AC_diff_json"} <= cmds


def test_facade_exports():
    for attr in ("match_json", "diff_json", "normalize_json", "snapshot",
                 "MatchReport"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
