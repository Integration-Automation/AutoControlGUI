"""Headless tests for locale-aware list formatting. No Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.list_format import format_list


def test_english_oxford_comma():
    assert format_list(["A", "B", "C"]) == "A, B, and C"
    assert format_list(["A", "B", "C"], style="or") == "A, B, or C"


def test_two_and_one_and_empty():
    assert format_list(["A", "B"]) == "A and B"
    assert format_list(["only"]) == "only"
    assert format_list([]) == ""


def test_unit_style_has_no_conjunction():
    assert format_list(["A", "B", "C"], style="unit") == "A, B, C"
    assert format_list(["A", "B"], style="unit") == "A, B"


def test_other_locales_have_no_serial_comma():
    assert format_list(["manzana", "pera", "uva"], locale="es") == \
        "manzana, pera y uva"
    assert format_list(["A", "B", "C", "D"], locale="fr") == "A, B, C et D"
    assert format_list(["A", "B", "C"], locale="de", style="or") == "A, B oder C"


def test_unknown_locale_falls_back_to_english():
    assert format_list(["A", "B", "C"], locale="zz") == "A, B, and C"


def test_unknown_style_raises():
    with pytest.raises(ValueError):
        format_list(["A", "B"], style="nope")


def test_non_string_items_coerced():
    assert format_list([1, 2, 3]) == "1, 2, and 3"


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_format_list",
        {"items": json.dumps(["A", "B", "C"]), "style": "or"}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["text"] == "A, B, or C"


def test_wiring():
    known = ac.executor.known_commands()
    assert "AC_format_list" in set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_format_list" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_format_list" in specs


def test_facade_exports():
    assert hasattr(ac, "format_list") and "format_list" in ac.__all__
