"""Headless tests for the coarse labelled screen grid (pure stdlib)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.screen_grid import (
    cell_for_point, grid_cells, point_for_cell,
)

REGION = [0, 0, 400, 200]


def test_grid_cells_cover_region_row_major():
    cells = grid_cells(2, 4, region=REGION)
    assert len(cells) == 8
    assert [c.label for c in cells[:4]] == ["A1", "B1", "C1", "D1"]
    assert cells[0].left == 0 and cells[0].right == 100
    assert cells[-1].label == "D2" and cells[-1].right == 400
    assert cells[-1].bottom == 200


def test_cell_for_point_inside():
    cell = cell_for_point(150, 50, 2, 4, region=REGION)
    assert cell is not None
    assert cell.label == "B1"  # x 150 -> col 1, y 50 -> row 0


def test_cell_for_point_outside_is_none():
    assert cell_for_point(500, 50, 2, 4, region=REGION) is None
    assert cell_for_point(10, -1, 2, 4, region=REGION) is None


def test_point_for_cell_returns_centre():
    # C1 is the third column of four over width 400 -> x in [200,300), centre 250
    assert point_for_cell("C1", 2, 4, region=REGION) == [250, 50]


def test_round_trip_point_to_cell_to_point():
    cell = cell_for_point(317, 133, 3, 3, region=REGION)
    assert cell is not None
    back = point_for_cell(cell.label, 3, 3, region=REGION)
    again = cell_for_point(back[0], back[1], 3, 3, region=REGION)
    assert again.label == cell.label


def test_screen_size_default_origin():
    cells = grid_cells(1, 2, screen_size=[200, 100])
    assert cells[0].left == 0 and cells[1].right == 200
    assert cells[0].bottom == 100


def test_spreadsheet_labels_past_z():
    cells = grid_cells(1, 27, region=[0, 0, 270, 10])
    assert cells[25].label == "Z1"
    assert cells[26].label == "AA1"


def test_invalid_shape_and_label_raise():
    with pytest.raises(ValueError):
        grid_cells(0, 4, region=REGION)
    with pytest.raises(ValueError):
        point_for_cell("Z9", 2, 2, region=REGION)
    with pytest.raises(ValueError):
        point_for_cell("nope", 2, 2, region=REGION)


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_grid_cells", "AC_cell_for_point", "AC_point_for_cell"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_grid_cells", "ac_cell_for_point", "ac_point_for_cell"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_grid_cells", "AC_cell_for_point", "AC_point_for_cell"} <= specs


def test_facade_exports():
    for name in ("grid_cells", "cell_for_point", "point_for_cell", "GridCell"):
        assert hasattr(ac, name) and name in ac.__all__
