"""Headless tests for tabular row-set diffing. Pure stdlib, no Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.dataset_diff import (
    cell_changes, diff_rows, summarize_diff,
)

_OLD = [
    {"id": 1, "name": "alice", "age": 30},
    {"id": 2, "name": "bob", "age": 25},
    {"id": 3, "name": "carol", "age": 40},
]
_NEW = [
    {"id": 1, "name": "alice", "age": 31},     # changed (age)
    {"id": 3, "name": "carol", "age": 40},     # unchanged
    {"id": 4, "name": "dave", "age": 22},      # added
]                                              # id 2 removed


def test_diff_buckets():
    diff = diff_rows(_OLD, _NEW, "id")
    assert [row["id"] for row in diff["added"]] == [4]
    assert [row["id"] for row in diff["removed"]] == [2]
    assert [entry["key"] for entry in diff["changed"]] == [1]
    assert [row["id"] for row in diff["unchanged"]] == [3]


def test_changed_entry_carries_old_and_new():
    [changed] = diff_rows(_OLD, _NEW, "id")["changed"]
    assert changed["old"]["age"] == 30 and changed["new"]["age"] == 31


def test_summarize_diff_counts():
    summary = summarize_diff(diff_rows(_OLD, _NEW, "id"))
    assert summary == {"added": 1, "removed": 1, "changed": 1, "unchanged": 1}


def test_cell_changes():
    changes = cell_changes(_OLD, _NEW, "id")
    assert changes == [{"key": 1, "column": "age", "old": 30, "new": 31}]


def test_composite_key():
    old = [{"region": "us", "id": 1, "v": 1}]
    new = [{"region": "us", "id": 1, "v": 2}, {"region": "eu", "id": 1, "v": 9}]
    diff = diff_rows(old, new, ["region", "id"])
    assert [row["region"] for row in diff["added"]] == ["eu"]
    assert diff["changed"][0]["key"] == ["us", 1]


def test_duplicate_key_last_wins():
    old = [{"id": 1, "v": "a"}, {"id": 1, "v": "b"}]
    diff = diff_rows(old, [{"id": 1, "v": "b"}], "id")
    assert diff["unchanged"] and not diff["changed"]


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_diff_rows",
        {"old_rows": json.dumps(_OLD), "new_rows": json.dumps(_NEW),
         "key": "id"}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["summary"] == {"added": 1, "removed": 1,
                              "changed": 1, "unchanged": 1}
    rec2 = ac.execute_action([[
        "AC_cell_changes",
        {"old_rows": json.dumps(_OLD), "new_rows": json.dumps(_NEW),
         "key": "id"}]])
    changes = next(v for v in rec2.values() if isinstance(v, dict))["changes"]
    assert changes[0]["column"] == "age"


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_diff_rows", "AC_cell_changes"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_diff_rows", "ac_cell_changes"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_diff_rows", "AC_cell_changes"} <= specs


def test_facade_exports():
    for attr in ("diff_rows", "cell_changes", "summarize_diff"):
        assert hasattr(ac, attr) and attr in ac.__all__
