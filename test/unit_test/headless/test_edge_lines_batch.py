"""Headless tests for Hough line / grid / separator detection. No Qt."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from je_auto_control.utils.edge_lines import (   # noqa: E402
    find_grid, find_lines, find_separators,
)


def _grid_image():
    img = np.full((240, 300), 255, dtype=np.uint8)
    for x in (50, 150, 250):
        cv2.line(img, (x, 40), (x, 200), 0, 2)
    for y in (40, 120, 200):
        cv2.line(img, (50, y), (250, y), 0, 2)
    return img


def test_find_lines_classifies_orientation():
    lines = find_lines(_grid_image(), min_length=80)
    assert lines
    assert {line["orientation"] for line in lines} == {"horizontal", "vertical"}
    assert all(line["length"] >= 80 for line in lines)


def test_find_lines_orientation_filter():
    horizontals = find_lines(_grid_image(), min_length=80, orientation="horizontal")
    assert horizontals and all(h["orientation"] == "horizontal" for h in horizontals)


def test_find_grid_recovers_rows_cols_cells():
    grid = find_grid(_grid_image(), min_length=100)
    assert grid["rows"] == [40, 120, 200]
    assert grid["cols"] == [50, 150, 250]
    assert len(grid["cells"]) == 4                     # 2x2 cells from a 3x3 grid
    first = grid["cells"][0]
    assert first == {"x": 50, "y": 40, "width": 100, "height": 80}


def test_find_separators_both_axes():
    assert find_separators(_grid_image(), axis="horizontal", min_length=100) == [
        40, 120, 200]
    assert find_separators(_grid_image(), axis="vertical", min_length=100) == [
        50, 150, 250]


def test_blank_image_has_no_lines():
    blank = np.full((100, 100), 255, dtype=np.uint8)
    assert find_lines(blank) == []
    assert find_grid(blank)["cells"] == []
    assert find_separators(blank) == []


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_find_lines", "AC_find_grid", "AC_find_separators"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_find_lines", "ac_find_grid", "ac_find_separators"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_find_lines", "AC_find_grid", "AC_find_separators"} <= specs


def test_facade_exports():
    for attr in ("find_lines", "find_grid", "find_separators"):
        assert hasattr(ac, attr) and attr in ac.__all__
