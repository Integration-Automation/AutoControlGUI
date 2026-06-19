"""Headless tests for Office I/O (Excel / Word / PowerPoint).

The document round-trips require the optional [office] extra
(openpyxl / python-docx / python-pptx) and skip when it is missing; the
wiring/facade tests always run (they only check registration)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.office import (
    read_document, read_presentation, read_workbook,
    write_document, write_presentation, write_workbook)


# --- document round-trips (need the [office] extra) ----------------------

def test_excel_roundtrip(tmp_path):
    pytest.importorskip("openpyxl")
    path = str(tmp_path / "data.xlsx")
    rows = [{"name": "Ada", "age": 36}, {"name": "Bo", "age": 41}]
    write_workbook(path, rows, sheet="People")
    loaded = read_workbook(path, sheet="People")
    assert loaded == rows


def test_word_roundtrip(tmp_path):
    pytest.importorskip("docx")
    path = str(tmp_path / "doc.docx")
    paragraphs = ["Title line", "Body one", "Body two"]
    write_document(path, paragraphs)
    assert read_document(path)["paragraphs"] == paragraphs


def test_powerpoint_roundtrip(tmp_path):
    pytest.importorskip("pptx")
    path = str(tmp_path / "deck.pptx")
    write_presentation(path, [{"title": "Intro", "body": ["alpha", "beta"]}])
    slides = read_presentation(path)["slides"]
    flat = " ".join(slides[0])
    assert "Intro" in flat and "alpha" in flat and "beta" in flat


def test_read_missing_file_raises():
    pytest.importorskip("openpyxl")
    with pytest.raises(FileNotFoundError):
        read_workbook("does-not-exist-12345.xlsx")


# --- wiring (always runs) -------------------------------------------------

def test_executor_roundtrip(tmp_path):
    pytest.importorskip("openpyxl")
    path = str(tmp_path / "e.xlsx")
    ac.execute_action([["AC_write_workbook", {
        "path": path, "rows": [{"a": 1, "b": 2}]}]])
    rec = ac.execute_action([["AC_read_workbook", {"path": path}]])
    assert any("'a': 1" in str(v) for v in rec.values())


def test_command_wiring():
    known = ac.executor.known_commands()
    assert {"AC_read_workbook", "AC_write_workbook", "AC_read_document",
            "AC_write_document", "AC_read_presentation",
            "AC_write_presentation"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_read_workbook", "ac_write_workbook", "ac_read_document",
            "ac_write_document", "ac_read_presentation",
            "ac_write_presentation"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_read_workbook", "AC_write_workbook", "AC_read_document",
            "AC_write_document", "AC_read_presentation",
            "AC_write_presentation"} <= cmds


def test_facade_exports():
    for attr in ("read_workbook", "write_workbook", "read_document",
                 "write_document", "read_presentation",
                 "write_presentation"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
