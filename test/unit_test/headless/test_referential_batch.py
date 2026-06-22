"""Headless tests for referential-integrity checks. Pure stdlib, no Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.referential import (
    check_accepted_values, check_foreign_key, check_row_count, check_unique_key,
)

_PARENTS = [{"id": 1}, {"id": 2}, {"id": 3}]
_CHILDREN = [{"user_id": 1}, {"user_id": 2}, {"user_id": 9}, {"user_id": None}]


def test_foreign_key_reports_orphans():
    report = check_foreign_key(_CHILDREN, "user_id", _PARENTS, "id")
    assert report["ok"] is False
    assert report["violations"] == 1 and report["missing"] == [9]


def test_foreign_key_passes_when_all_present():
    children = [{"user_id": 1}, {"user_id": 2}]
    assert check_foreign_key(children, "user_id", _PARENTS, "id")["ok"] is True


def test_unique_key_single_and_composite():
    dup = check_unique_key([{"id": 1}, {"id": 1}, {"id": 2}], "id")
    assert dup["ok"] is False
    assert dup["duplicates"] == [{"key": 1, "count": 2}]
    rows = [{"r": "us", "id": 1}, {"r": "us", "id": 1}, {"r": "eu", "id": 1}]
    comp = check_unique_key(rows, ["r", "id"])
    assert comp["duplicates"] == [{"key": ["us", 1], "count": 2}]


def test_accepted_values():
    rows = [{"s": "open"}, {"s": "closed"}, {"s": "weird"}, {"s": None}]
    report = check_accepted_values(rows, "s", ["open", "closed"])
    assert report["ok"] is False and report["unexpected"] == ["weird"]
    assert check_accepted_values(rows[:2], "s", ["open", "closed"])["ok"]


def test_row_count_bounds():
    rows = [{"id": index} for index in range(5)]
    assert check_row_count(rows, minimum=1, maximum=10)["ok"] is True
    assert check_row_count(rows, minimum=6)["ok"] is False
    assert check_row_count(rows, maximum=4)["ok"] is False
    assert check_row_count(rows)["count"] == 5


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_check_foreign_key",
        {"child_rows": json.dumps(_CHILDREN), "child_col": "user_id",
         "parent_rows": json.dumps(_PARENTS), "parent_col": "id"}]])
    report = next(v for v in rec.values() if isinstance(v, dict))
    assert report["missing"] == [9]
    rec2 = ac.execute_action([[
        "AC_check_unique_key",
        {"rows": json.dumps([{"id": 1}, {"id": 1}]), "cols": "id"}]])
    assert next(v for v in rec2.values()
                if isinstance(v, dict))["ok"] is False


def test_wiring():
    cmds = {"AC_check_foreign_key", "AC_check_unique_key",
            "AC_check_accepted_values", "AC_check_row_count"}
    assert cmds <= set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_check_foreign_key", "ac_check_unique_key",
            "ac_check_accepted_values", "ac_check_row_count"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert cmds <= specs


def test_facade_exports():
    for attr in ("check_foreign_key", "check_unique_key",
                 "check_accepted_values", "check_row_count"):
        assert hasattr(ac, attr) and attr in ac.__all__
