"""Headless tests for the generic SQL steps (sql_to_var / assert_db).

Uses a real temporary SQLite database file (stdlib sqlite3); no PySide6.
"""
import sqlite3

import pytest

import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import AutoControlAssertionException
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.executor.flow_data_commands import (
    exec_assert_db, exec_sql_to_var,
)
from je_auto_control.utils.sql.sql_query import query_sqlite


@pytest.fixture()
def users_db(tmp_path):
    path = tmp_path / "app.db"
    with sqlite3.connect(str(path)) as conn:
        conn.execute("CREATE TABLE users (id INTEGER, name TEXT, active INT)")
        conn.executemany(
            "INSERT INTO users VALUES (?, ?, ?)",
            [(1, "Sam", 1), (2, "Lee", 0), (3, "Ann", 1)],
        )
        conn.commit()
    return str(path)


def test_query_all_returns_row_dicts(users_db):
    rows = query_sqlite(users_db, "SELECT id, name FROM users ORDER BY id")
    assert rows == [{"id": 1, "name": "Sam"},
                    {"id": 2, "name": "Lee"},
                    {"id": 3, "name": "Ann"}]


def test_query_scalar_and_params(users_db):
    count = query_sqlite(users_db, "SELECT COUNT(*) FROM users WHERE active = ?",
                         params=[1], fetch="scalar")
    assert count == 2


def test_query_one_or_none(users_db):
    row = query_sqlite(users_db, "SELECT name FROM users WHERE id = ?",
                       params=[2], fetch="one")
    assert row == {"name": "Lee"}
    missing = query_sqlite(users_db, "SELECT name FROM users WHERE id = ?",
                           params=[99], fetch="one")
    assert missing is None


def test_named_params(users_db):
    name = query_sqlite(users_db, "SELECT name FROM users WHERE id = :id",
                        params={"id": 3}, fetch="scalar")
    assert name == "Ann"


def test_non_select_rejected(users_db):
    with pytest.raises(ValueError):
        query_sqlite(users_db, "DELETE FROM users")


def test_multi_statement_rejected(users_db):
    with pytest.raises(ValueError):
        query_sqlite(users_db, "SELECT 1; SELECT 2")


def test_unknown_fetch_rejected(users_db):
    with pytest.raises(ValueError):
        query_sqlite(users_db, "SELECT 1", fetch="many")


def test_missing_db_rejected(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError)):
        query_sqlite(str(tmp_path / "nope.db"), "SELECT 1")


def test_sql_to_var_stores_scalar(users_db):
    executor = Executor()
    exec_sql_to_var(executor, {
        "database": users_db, "query": "SELECT COUNT(*) FROM users",
        "var": "n", "fetch": "scalar"})
    assert executor.variables.get_value("n") == 3


def test_assert_db_passes_and_fails(users_db):
    executor = Executor()
    ok = exec_assert_db(executor, {
        "database": users_db,
        "query": "SELECT COUNT(*) FROM users WHERE active = 1",
        "op": "eq", "expected": 2})
    assert ok["passed"] is True
    with pytest.raises(AutoControlAssertionException):
        exec_assert_db(executor, {
            "database": users_db, "query": "SELECT COUNT(*) FROM users",
            "op": "eq", "expected": 999})


def test_facade_and_executor_wiring(users_db):
    assert ac.query_sqlite is query_sqlite
    known = ac.executor.known_commands()
    assert "AC_sql_to_var" in known
    assert "AC_assert_db" in known
    record = ac.execute_action([
        ["AC_sql_to_var", {"database": users_db, "var": "total",
                           "query": "SELECT COUNT(*) FROM users",
                           "fetch": "scalar"}],
        ["AC_assert_db", {"database": users_db, "op": "ge", "expected": 1,
                          "query": "SELECT COUNT(*) FROM users"}],
    ])
    assert record  # both steps executed


def test_mcp_tools_registered():
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {tool.name for tool in build_default_tool_registry()}
    assert {"ac_sql_query", "ac_assert_db"} <= names
