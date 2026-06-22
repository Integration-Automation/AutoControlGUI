"""Headless tests for grid / table cell addressing. No Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.grid_locator import cluster_grid, locate_cell

# a 2-row x 3-col grid, deliberately shuffled
_BOXES = [
    (210, 100, 20, 10), (10, 100, 20, 10), (110, 100, 20, 10),
    (110, 200, 20, 10), (10, 200, 20, 10), (210, 200, 20, 10),
]


def test_cluster_groups_rows_and_orders_columns():
    grid = cluster_grid(_BOXES)
    assert len(grid) == 2 and [len(r) for r in grid] == [3, 3]
    assert [b[0] for b in grid[0]] == [10, 110, 210]   # left-to-right
    assert [b[1] for b in grid[0]] == [100, 100, 100]   # top row


def test_locate_cell_returns_center():
    cell = locate_cell(_BOXES, 1, 2)
    assert cell["found"] is True
    assert cell["center"] == [220, 205] and cell["box"] == [210, 200, 20, 10]
    assert cell["rows"] == 2 and cell["cols"] == 3


def test_out_of_range():
    assert locate_cell(_BOXES, 5, 0)["found"] is False
    assert locate_cell(_BOXES, 0, 9)["reason"] == "col out of range"


def test_row_tolerance_merges_near_y():
    # second row jitters by 4px in y -> still one row at tolerance 10
    jittered = [(10, 100, 20, 10), (110, 104, 20, 10), (210, 98, 20, 10)]
    assert len(cluster_grid(jittered, row_tolerance=10)) == 1
    assert len(cluster_grid(jittered, row_tolerance=2)) >= 2   # splits


def test_empty_boxes():
    assert cluster_grid([]) == []
    assert locate_cell([], 0, 0)["found"] is False


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_grid_cell", {"boxes": json.dumps([[10, 100, 20, 10],
                                              [110, 100, 20, 10]]),
                         "row": 0, "col": 1}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["found"] is True and out["center"] == [120, 105]


def test_wiring():
    known = ac.executor.known_commands()
    assert "AC_grid_cell" in set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_grid_cell" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_grid_cell" in specs


def test_facade_exports():
    for attr in ("cluster_grid", "locate_cell"):
        assert hasattr(ac, attr) and attr in ac.__all__
