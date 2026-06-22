"""Headless tests for the JSONPath subset engine. Pure stdlib, no Qt imports."""
import json

import je_auto_control as ac
from je_auto_control.utils.jsonpath import (
    json_extract, json_query, json_query_one)

DATA = {
    "store": {
        "books": [
            {"title": "A", "price": 5},
            {"title": "B", "price": 12},
            {"title": "C", "price": 9},
        ],
        "name": "Main",
    },
    "tags": ["x", "y", "z"],
}


def test_dotted_and_index():
    assert json_query(DATA, "$.store.name") == ["Main"]
    assert json_query(DATA, "$.store.books[0].title") == ["A"]
    assert json_query(DATA, "store.books[-1].title") == ["C"]


def test_wildcard():
    assert json_query(DATA, "$.store.books[*].title") == ["A", "B", "C"]
    assert json_query(DATA, "$.tags[*]") == ["x", "y", "z"]


def test_filter():
    assert json_query(DATA, "$.store.books[?(@.price > 8)].title") == ["B", "C"]
    assert json_query(DATA, "$.store.books[?(@.title == 'A')].price") == [5]


def test_recursive_descent():
    assert json_query(DATA, "$..price") == [5, 12, 9]
    assert json_query(DATA, "$..title") == ["A", "B", "C"]


def test_query_one_and_default():
    assert json_query_one(DATA, "$.store.books[1].title") == "B"
    assert json_query_one(DATA, "$.missing.path", "DEF") == "DEF"


def test_extract_mapping():
    out = json_extract(DATA, {"first_book": "$.store.books[0].title",
                              "store_name": "store.name",
                              "missing": "$.nope"})
    assert out == {"first_book": "A", "store_name": "Main", "missing": None}


def test_quoted_key():
    data = {"a.b": {"c": 1}}
    assert json_query(data, "$['a.b'].c") == [1]


def test_no_match_returns_empty():
    assert json_query(DATA, "$.store.books[99].title") == []


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_json_query",
        {"data": json.dumps(DATA), "path": "$.store.books[?(@.price>8)].title"},
    ]])
    matches = next(v for v in rec.values() if isinstance(v, dict))["matches"]
    assert matches == ["B", "C"]

    rec2 = ac.execute_action([[
        "AC_json_extract",
        {"data": json.dumps(DATA), "mapping": json.dumps({"n": "store.name"})},
    ]])
    result = next(v for v in rec2.values() if isinstance(v, dict))["result"]
    assert result == {"n": "Main"}


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_json_query", "AC_json_extract"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_json_query", "ac_json_extract"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_json_query", "AC_json_extract"} <= cmds


def test_facade_exports():
    for attr in ("json_query", "json_query_one", "json_extract"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
