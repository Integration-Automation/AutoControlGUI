"""Headless tests for filling a ruling-line grid with OCR text (pure stdlib)."""
import je_auto_control as ac
from je_auto_control.utils.table_grid_fill import (
    assign_text_to_grid, populate_table, table_to_csv, table_to_records,
)

# a 2-row x 2-col grid: x edges 0,100,200 ; y edges 0,30,60
GRID = {"cols": [0, 100, 200], "rows": [0, 30, 60],
        "cells": [{"x": 0, "y": 0, "width": 100, "height": 30}]}


def _box(x, y, w, h, text):
    return {"x": x, "y": y, "width": w, "height": h, "text": text}


def _header_grid_boxes():
    return [_box(10, 5, 60, 20, "Name"), _box(110, 5, 60, 20, "Age"),
            _box(10, 35, 60, 20, "Ann"), _box(110, 35, 40, 20, "30")]


def test_assign_fills_cells_row_major():
    table = assign_text_to_grid(GRID, _header_grid_boxes())
    assert table == [["Name", "Age"], ["Ann", "30"]]


def test_words_in_one_cell_join_in_reading_order():
    boxes = [_box(60, 5, 30, 20, "Doe"), _box(10, 5, 40, 20, "John")]
    table = assign_text_to_grid(GRID, boxes)
    assert table[0][0] == "John Doe"  # left-to-right despite input order


def test_box_outside_grid_is_dropped():
    table = assign_text_to_grid(GRID, [_box(500, 500, 20, 20, "nope")])
    assert table == [["", ""], ["", ""]]


def test_populate_table_reports_dims_and_cells():
    result = populate_table(GRID, _header_grid_boxes())
    assert result["n_rows"] == 2 and result["n_cols"] == 2
    assert {"row": 1, "col": 1, "text": "30"} in result["cells"]
    assert result["spans"] == []


def test_span_detection_flags_merged_cell():
    # a wide box covering both columns of row 0
    result = populate_table(GRID, [_box(10, 5, 180, 20, "Merged Header")])
    assert len(result["spans"]) == 1
    assert result["spans"][0]["col_span"] == 2


def test_records_and_csv():
    table = assign_text_to_grid(GRID, _header_grid_boxes())
    assert table_to_records(table) == [{"Name": "Ann", "Age": "30"}]
    assert table_to_csv(table).replace("\r\n", "\n") == "Name,Age\nAnn,30\n"


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_populate_table" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_populate_table" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_populate_table" in specs


def test_facade_exports():
    for name in ("assign_text_to_grid", "populate_table",
                 "table_to_records", "table_to_csv"):
        assert hasattr(ac, name) and name in ac.__all__
