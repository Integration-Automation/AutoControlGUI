"""Headless tests for locale-aware parsing/formatting. Functional tests need
Babel (importorskip); wiring/facade tests always run. Pure stdlib, no Qt."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.locale_parse import (
    format_currency, format_date, format_decimal, parse_decimal, parse_number)


def test_parse_decimal_across_locales():
    pytest.importorskip("babel")
    assert parse_decimal("1.234,56", locale="de_DE") == pytest.approx(1234.56)
    assert parse_decimal("1,234.56", locale="en_US") == pytest.approx(1234.56)


def test_parse_number():
    pytest.importorskip("babel")
    assert parse_number("1,234", locale="en_US") == 1234


def test_format_decimal_and_currency():
    pytest.importorskip("babel")
    assert format_decimal(1234.5, locale="en_US") == "1,234.5"
    assert format_currency(1234.5, "USD", locale="en_US") == "$1,234.50"


def test_format_date_from_iso():
    pytest.importorskip("babel")
    assert format_date("2026-06-20", locale="de_DE", fmt="short") == "20.06.26"


def test_round_trip_de_de():
    pytest.importorskip("babel")
    text = format_decimal(1234.56, locale="de_DE")
    assert parse_decimal(text, locale="de_DE") == pytest.approx(1234.56)


# --- wiring (always runs) -------------------------------------------------

def test_executor_round_trip():
    pytest.importorskip("babel")
    rec = ac.execute_action([
        ["AC_parse_decimal", {"text": "1.234,56", "locale": "de_DE"}],
    ])
    value = next(v for v in rec.values() if isinstance(v, dict))["value"]
    assert value == pytest.approx(1234.56)


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_parse_decimal", "AC_parse_number", "AC_format_decimal",
            "AC_format_currency", "AC_format_date"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_parse_decimal", "ac_parse_number", "ac_format_decimal",
            "ac_format_currency", "ac_format_date"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_parse_decimal", "AC_parse_number", "AC_format_decimal",
            "AC_format_currency", "AC_format_date"} <= cmds


def test_facade_exports():
    for attr in ("parse_decimal", "parse_number", "format_decimal",
                 "format_currency", "format_date"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
