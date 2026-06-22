"""Headless tests for locale-aware string collation. No Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.locale_collation import (
    collation_key, compare, sort_strings,
)

_SWEDISH = "abcdefghijklmnopqrstuvwxyzåäö"


def test_default_case_insensitive_primary():
    # lowercase sorts before uppercase at the tertiary level
    assert sort_strings(["banana", "Apple", "apple", "cherry"]) == [
        "apple", "Apple", "banana", "cherry"]


def test_accent_is_secondary():
    # plain letters sort before their accented form, after base ordering
    assert sort_strings(["résumé", "rest", "resume"]) == [
        "rest", "resume", "résumé"]
    assert compare("resume", "résumé") == -1
    assert compare("resume", "résumé", strength="primary") == 0


def test_case_is_tertiary():
    assert compare("apple", "Apple") == -1            # lower before upper
    assert compare("apple", "Apple", strength="secondary") == 0


def test_tailoring_orders_alphabet():
    # Swedish: å ä ö sort after z, not next to a/o
    assert sort_strings(["zebra", "äpple", "apple", "örn"],
                        tailoring=_SWEDISH) == ["apple", "zebra", "äpple", "örn"]
    assert compare("zebra", "åa", tailoring=_SWEDISH) == -1


def test_sort_by_key_and_reverse():
    rows = [{"n": "béta"}, {"n": "alpha"}, {"n": "Gamma"}]
    assert [r["n"] for r in sort_strings(rows, key=lambda r: r["n"])] == [
        "alpha", "béta", "Gamma"]
    assert sort_strings(["a", "b", "c"], reverse=True) == ["c", "b", "a"]


def test_collation_key_levels_and_validation():
    assert collation_key("Ab", strength="primary") == ((97, 98),)
    assert len(collation_key("Ab", strength="tertiary")) == 3
    with pytest.raises(ValueError):
        collation_key("x", strength="quaternary")


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_collation_sort",
        {"items": json.dumps(["zebra", "äpple", "apple"]),
         "tailoring": _SWEDISH}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["sorted"] == ["apple", "zebra", "äpple"]
    rec2 = ac.execute_action([[
        "AC_collation_compare", {"first": "resume", "second": "résumé"}]])
    assert next(v for v in rec2.values() if isinstance(v, dict))["order"] == -1


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_collation_sort", "AC_collation_compare"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_collation_sort", "ac_collation_compare"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_collation_sort", "AC_collation_compare"} <= specs


def test_facade_exports():
    for attr in ("collation_key", "collation_compare", "sort_strings"):
        assert hasattr(ac, attr) and attr in ac.__all__
