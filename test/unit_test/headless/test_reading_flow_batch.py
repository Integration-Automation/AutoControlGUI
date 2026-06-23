"""Headless tests for column-aware reading order (XY-cut, pure stdlib)."""
import je_auto_control as ac
from je_auto_control.utils.reading_flow import flow_order, to_blocks, xy_cut


def _box(x, y, name, w=40, h=20):
    return {"x": x, "y": y, "width": w, "height": h, "text": name}


def _two_columns():
    # column A at x[0,40], column B at x[100,140]; rows at y 0 and 30
    return [_box(0, 0, "A1"), _box(100, 0, "B1"),
            _box(0, 30, "A2"), _box(100, 30, "B2")]


def test_column_aware_order_reads_down_columns():
    order = [b["text"] for b in flow_order(_two_columns(), min_gap=12)]
    # column A fully, then column B — NOT the naive A1,B1,A2,B2 interleave
    assert order == ["A1", "A2", "B1", "B2"]


def test_top_level_split_is_vertical():
    tree = xy_cut(_two_columns(), min_gap=12)
    assert tree["type"] == "split" and tree["axis"] == "x"


def test_single_column_is_top_to_bottom():
    boxes = [_box(0, 60, "c"), _box(0, 0, "a"), _box(0, 30, "b")]
    order = [b["text"] for b in flow_order(boxes, min_gap=12)]
    assert order == ["a", "b", "c"]


def test_to_blocks_counts_leaves():
    blocks = to_blocks(xy_cut(_two_columns(), min_gap=12))
    assert len(blocks) == 2          # one leaf per column
    assert [b["text"] for b in blocks[0]] == ["A1", "A2"]


def test_index_is_assigned():
    ordered = flow_order(_two_columns(), min_gap=12)
    assert [b["index"] for b in ordered] == [0, 1, 2, 3]


def test_empty():
    assert flow_order([]) == []
    assert xy_cut([])["boxes"] == []


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_flow_order", "AC_xy_cut"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_flow_order", "ac_xy_cut"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_flow_order", "AC_xy_cut"} <= specs


def test_facade_exports():
    for name in ("flow_order", "xy_cut", "to_blocks"):
        assert hasattr(ac, name) and name in ac.__all__
