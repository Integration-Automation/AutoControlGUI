"""Headless tests for RTF + CSV/TSV clipboard codecs (pure; Win32 set/get skipped)."""
import je_auto_control as ac
from je_auto_control.utils.clipboard_rich_formats import (
    build_rtf, csv_to_rows, rows_to_csv, rtf_to_text,
)


def test_rtf_round_trip_plain_and_breaks():
    for sample in ("Hello world", "Line1\nLine2\nLine3", "Tab\tsep", ""):
        assert rtf_to_text(build_rtf(sample)) == sample


def test_rtf_round_trip_unicode_and_escapes():
    for sample in ("café crème", "中文字符", "Braces {x} and \\ backslash"):
        assert rtf_to_text(build_rtf(sample)) == sample


def test_build_rtf_is_ascii_and_wrapped():
    rtf = build_rtf("café")
    assert rtf.startswith("{\\rtf1")
    assert rtf.endswith("}")
    rtf.encode("ascii")  # non-ASCII escaped to \uNNNN?, so this must not raise
    assert "\\u233?" in rtf  # é


def test_rtf_to_text_drops_metadata_and_decodes_hex():
    raw = (r"{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}"
           r"{\colortbl;\red0\green0\blue0;}Caf\'e9 here\par done}")
    assert rtf_to_text(raw) == "Café here\ndone"


def test_build_rtf_type_error():
    import pytest
    with pytest.raises(TypeError):
        build_rtf(123)


def test_csv_round_trip_with_embedded_specials():
    rows = [["a", "b,c"], ["d", "e\nf"], ["1", "2"]]
    assert csv_to_rows(rows_to_csv(rows)) == [["a", "b,c"], ["d", "e\nf"],
                                              ["1", "2"]]


def test_tsv_uses_tab_delimiter():
    text = rows_to_csv([["x", "y"], ["1", "2"]], delimiter="\t")
    assert text == "x\ty\r\n1\t2\r\n"
    assert csv_to_rows(text, delimiter="\t") == [["x", "y"], ["1", "2"]]


# --- wiring (Win32 set/get not executed in CI) -----------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_set_clipboard_rtf", "AC_get_clipboard_rtf",
            "AC_set_clipboard_csv", "AC_get_clipboard_csv"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_set_clipboard_rtf", "ac_get_clipboard_rtf",
            "ac_set_clipboard_csv", "ac_get_clipboard_csv"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_set_clipboard_rtf", "AC_get_clipboard_rtf",
            "AC_set_clipboard_csv", "AC_get_clipboard_csv"} <= specs


def test_facade_exports():
    for name in ("build_rtf", "rtf_to_text", "rows_to_csv", "csv_to_rows",
                 "set_clipboard_rtf", "get_clipboard_rtf",
                 "set_clipboard_csv", "get_clipboard_csv"):
        assert hasattr(ac, name) and name in ac.__all__
