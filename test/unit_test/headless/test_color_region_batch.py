"""Headless tests for colour-region location. No Qt."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.color_region import (   # noqa: E402
    find_color_region, find_color_regions,
)


def _scene():
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    img[20:40, 30:80] = (0, 200, 0)       # big green (50x20 = 1000)
    img[60:70, 100:120] = (0, 205, 5)     # small near-green (20x10 = 200)
    img[80:90, 10:20] = (200, 0, 0)       # red
    return img


def test_finds_regions_sorted_by_area():
    greens = find_color_regions((0, 200, 0), haystack=_scene(), tolerance=20,
                                min_area=10)
    boxes = [(r["x"], r["y"], r["width"], r["height"]) for r in greens]
    assert boxes == [(30, 20, 50, 20), (100, 60, 20, 10)]   # largest first
    assert greens[0]["area"] == 1000


def test_find_largest_center():
    assert find_color_region((0, 200, 0), haystack=_scene())["center"] == [54, 29]


def test_red_and_absent_colour():
    assert find_color_region((200, 0, 0), haystack=_scene(),
                             min_area=10)["center"] == [14, 84]
    assert find_color_region((0, 0, 255), haystack=_scene()) is None


def test_min_area_filters_small_blobs():
    assert len(find_color_regions((0, 200, 0), haystack=_scene(),
                                  tolerance=20, min_area=300)) == 1


def test_tolerance_widens_match():
    # the near-green (0,205,5) only matches (0,200,0) within a wide tolerance
    tight = find_color_regions((0, 200, 0), haystack=_scene(), tolerance=2,
                               min_area=10)
    assert all(r["y"] < 50 for r in tight)        # only the exact big block


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = ac.executor.known_commands()
    assert "AC_find_color_region" in set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_find_color_region" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_find_color_region" in specs


def test_facade_exports():
    for attr in ("find_color_region", "find_color_regions"):
        assert hasattr(ac, attr) and attr in ac.__all__
