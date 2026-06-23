"""Headless tests for whitespace-projection column inference (pure stdlib)."""
import je_auto_control as ac
from je_auto_control.utils.column_layout import (
    assign_columns, column_gutters, detect_borderless_table, vertical_projection,
)


def _box(x, y, text, w=60, h=18):
    return {"x": x, "y": y, "width": w, "height": h, "text": text}


def _two_column_three_rows():
    # column 1 spans x[10,70], column 2 spans x[120,180]; gutter x[70,120]
    return [_box(10, 0, "Name"), _box(120, 0, "Age"),
            _box(10, 30, "Ann"), _box(120, 30, "30"),
            _box(10, 60, "Bob"), _box(120, 60, "25")]


def test_vertical_projection_has_a_zero_gutter():
    profile = vertical_projection(_two_column_three_rows())
    assert profile[40] > 0 and profile[150] > 0   # inside the two columns
    assert profile[95] == 0                        # the gutter band is empty


def test_column_gutters_finds_the_interior_band():
    gutters = column_gutters(_two_column_three_rows())
    assert len(gutters) == 1
    assert gutters[0]["start"] == 70 and gutters[0]["end"] == 120


def test_assign_columns_tags_each_box():
    tagged = {b["text"]: b["column"] for b in assign_columns(_two_column_three_rows())}
    assert tagged["Name"] == 0 and tagged["Ann"] == 0
    assert tagged["Age"] == 1 and tagged["30"] == 1


def test_detect_borderless_table():
    table = detect_borderless_table(_two_column_three_rows())
    assert table is not None
    assert table["n_rows"] == 3 and table["n_cols"] == 2
    assert table["rows"] == [["Name", "Age"], ["Ann", "30"], ["Bob", "25"]]


def test_single_column_is_not_a_table():
    boxes = [_box(10, 0, "A"), _box(10, 30, "B"), _box(10, 60, "C")]
    assert detect_borderless_table(boxes) is None


def test_empty_returns_none():
    assert detect_borderless_table([]) is None


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_detect_borderless_table", "AC_column_gutters"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_detect_borderless_table", "ac_column_gutters"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_detect_borderless_table", "AC_column_gutters"} <= specs


def test_facade_exports():
    for name in ("vertical_projection", "column_gutters", "assign_columns",
                 "detect_borderless_table"):
        assert hasattr(ac, name) and name in ac.__all__
