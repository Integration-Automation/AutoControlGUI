"""Headless tests for the window tiling/layout geometry planner. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.window_layout import (
    WindowRect, available_slots, cascade_rects, grid_rects, tile_rect,
)

_SCREEN = (0, 0, 1920, 1080)


def test_tile_halves_and_quadrants():
    assert tile_rect(_SCREEN, "left").as_tuple() == (0, 0, 960, 1080)
    assert tile_rect(_SCREEN, "right").as_tuple() == (960, 0, 960, 1080)
    assert tile_rect(_SCREEN, "top").as_tuple() == (0, 0, 1920, 540)
    assert tile_rect(_SCREEN, "bottom_right").as_tuple() == (960, 540, 960, 540)
    assert tile_rect(_SCREEN, "full").as_tuple() == (0, 0, 1920, 1080)


def test_thirds_split_the_width():
    left = tile_rect(_SCREEN, "left_third")
    center = tile_rect(_SCREEN, "center_third")
    right = tile_rect(_SCREEN, "right_third")
    assert left.x == 0 and center.x == 640 and right.x == 1280
    assert left.width == center.width == right.width == 640


def test_screen_offset_is_honoured():
    rect = tile_rect((100, 50, 800, 600), "left")
    assert rect.as_tuple() == (100, 50, 400, 600)


def test_gap_insets_all_sides():
    rect = tile_rect(_SCREEN, "left", gap=10)
    assert rect.as_tuple() == (10, 10, 940, 1060)


def test_unknown_slot_raises():
    try:
        tile_rect(_SCREEN, "diagonal")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown slot")


def test_grid_rects_row_major_and_tiled():
    rects = grid_rects(_SCREEN, 2, 2)
    assert [r.as_tuple() for r in rects] == [
        (0, 0, 960, 540), (960, 0, 960, 540),
        (0, 540, 960, 540), (960, 540, 960, 540)]


def test_grid_rejects_zero_dimensions():
    for rows, cols in ((0, 2), (2, 0)):
        try:
            grid_rects(_SCREEN, rows, cols)
        except ValueError:
            continue
        raise AssertionError("expected ValueError for non-positive grid")


def test_cascade_staggers_and_clamps():
    rects = cascade_rects(_SCREEN, 3, offset=40, size=(800, 600))
    assert rects[0].as_tuple() == (0, 0, 800, 600)
    assert rects[1].as_tuple() == (40, 40, 800, 600)
    assert all(r.x + r.width <= 1920 and r.y + r.height <= 1080 for r in rects)


def test_cascade_default_size_is_60_percent():
    rect = cascade_rects(_SCREEN, 1)[0]
    assert rect.width == 1152 and rect.height == 648    # 0.6 * 1920 / 1080


def test_available_slots_lists_known_names():
    slots = available_slots()
    assert {"left", "right", "center", "left_third"} <= set(slots)


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_tile_rect", "AC_grid_rects", "AC_cascade_rects"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_tile_rect", "ac_grid_rects", "ac_cascade_rects"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_tile_rect", "AC_grid_rects", "AC_cascade_rects"} <= specs


def test_executor_adapters_return_plans():
    from je_auto_control.utils.executor.action_executor import (
        _cascade_rects, _grid_rects, _tile_rect)
    assert _tile_rect("left", screen=[0, 0, 100, 80])["rect"] == {
        "x": 0, "y": 0, "width": 50, "height": 80}
    assert _grid_rects(2, 2, screen=[0, 0, 100, 80])["count"] == 4
    assert _cascade_rects(3, screen=[0, 0, 100, 80])["count"] == 3


def test_facade_exports():
    for attr in ("tile_rect", "grid_rects", "cascade_rects", "available_slots",
                 "WindowRect"):
        assert hasattr(ac, attr) and attr in ac.__all__
    assert isinstance(tile_rect(_SCREEN, "left"), WindowRect)
