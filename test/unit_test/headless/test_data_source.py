"""Headless tests for data-driven execution (data sources)."""
import json
import sqlite3
from pathlib import Path

import pytest

from je_auto_control.utils.data_source import data_source_kinds, load_rows
from je_auto_control.utils.executor.action_executor import executor


def test_supported_kinds():
    kinds = data_source_kinds()
    assert {"csv", "json", "sqlite", "excel", "inline"} <= set(kinds)


def test_load_inline():
    rows = load_rows({"kind": "inline", "rows": [{"a": 1}, {"a": 2}]})
    assert rows == [{"a": 1}, {"a": 2}]


def test_load_inline_with_limit():
    rows = load_rows(
        {"kind": "inline", "rows": [{"a": 1}, {"a": 2}, {"a": 3}]}, limit=2,
    )
    assert len(rows) == 2


def test_load_csv(tmp_path: Path):
    csv_path = tmp_path / "users.csv"
    csv_path.write_text("user,pw\nalice,1\nbob,2\n", encoding="utf-8")
    rows = load_rows({"kind": "csv", "path": str(csv_path)})
    assert rows == [{"user": "alice", "pw": "1"}, {"user": "bob", "pw": "2"}]


def test_load_json_list(tmp_path: Path):
    json_path = tmp_path / "cases.json"
    json_path.write_text(json.dumps([{"x": 1}, {"x": 2}]), encoding="utf-8")
    assert load_rows({"kind": "json", "path": str(json_path)}) == [
        {"x": 1}, {"x": 2},
    ]


def test_load_json_rows_wrapper(tmp_path: Path):
    json_path = tmp_path / "cases.json"
    json_path.write_text(json.dumps({"rows": [{"x": 9}]}), encoding="utf-8")
    assert load_rows({"kind": "json", "path": str(json_path)}) == [{"x": 9}]


def test_load_sqlite(tmp_path: Path):
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (name TEXT, age INTEGER)")
    conn.execute("INSERT INTO users VALUES ('alice', 30), ('bob', 25)")
    conn.commit()
    conn.close()
    rows = load_rows({
        "kind": "sqlite", "path": str(db_path),
        "query": "SELECT name, age FROM users ORDER BY name",
    })
    assert rows == [{"name": "alice", "age": 30}, {"name": "bob", "age": 25}]


def test_sqlite_rejects_non_select(tmp_path: Path):
    db_path = tmp_path / "app.db"
    sqlite3.connect(db_path).close()
    with pytest.raises(ValueError):
        load_rows({
            "kind": "sqlite", "path": str(db_path),
            "query": "DROP TABLE users",
        })


def test_sqlite_rejects_multiple_statements(tmp_path: Path):
    db_path = tmp_path / "app.db"
    sqlite3.connect(db_path).close()
    with pytest.raises(ValueError):
        load_rows({
            "kind": "sqlite", "path": str(db_path),
            "query": "SELECT 1; DROP TABLE users",
        })


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_rows({"kind": "csv", "path": "/no/such/file_xyz.csv"})


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        load_rows({"kind": "parquet", "path": "x"})


def test_executor_for_each_row_binds_rows():
    actions = [
        ["AC_set_var", {"name": "last", "value": ""}],
        ["AC_for_each_row", {
            "source": {"kind": "inline",
                       "rows": [{"u": "alice"}, {"u": "bob"}]},
            "as": "row",
            "body": [["AC_set_var", {"name": "last", "value": "${row.u}"}]],
        }],
    ]
    executor.execute_action(actions)
    assert executor.variables.get_value("last") == "bob"


def test_executor_ac_load_data():
    rows = executor.event_dict["AC_load_data"](
        {"kind": "inline", "rows": [{"k": 1}]},
    )
    assert rows == [{"k": 1}]
