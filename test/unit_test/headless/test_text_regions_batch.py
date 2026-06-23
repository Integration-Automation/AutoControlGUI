"""Headless tests for MSER text-region detection. No Qt."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from je_auto_control.utils.text_regions import (   # noqa: E402
    find_text_lines, find_text_regions,
)


def _two_rows():
    img = np.full((120, 300), 235, dtype=np.uint8)
    for i, ch in enumerate("ABCD"):
        cv2.putText(img, ch, (20 + i * 30, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
    for i, ch in enumerate("XY"):
        cv2.putText(img, ch, (20 + i * 30, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
    return img


def test_finds_glyph_regions():
    regions = find_text_regions(_two_rows(), min_area=60)
    assert len(regions) >= 4                      # at least the four top-row glyphs
    assert all("center" in r and r["area"] >= 60 for r in regions)


def test_groups_into_two_lines():
    lines = find_text_lines(_two_rows(), y_tolerance=8)
    assert len(lines) == 2
    top, bottom = sorted(lines, key=lambda line: line["y"])
    assert top["width"] > bottom["width"]         # ABCD wider than XY
    assert bottom["y"] > top["y"]


def test_blank_image_has_no_text():
    blank = np.full((100, 100), 235, dtype=np.uint8)
    assert find_text_regions(blank) == []
    assert find_text_lines(blank) == []


def test_min_area_filters_small():
    big = find_text_regions(_two_rows(), min_area=100000)
    assert big == []


def test_merge_reduces_region_count():
    scene = _two_rows()
    unmerged = find_text_regions(scene, min_area=40, merge=False)
    merged = find_text_regions(scene, min_area=40, merge=True)
    assert len(merged) <= len(unmerged)


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_find_text_regions", "AC_find_text_lines"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_find_text_regions", "ac_find_text_lines"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_find_text_regions", "AC_find_text_lines"} <= specs


def test_facade_exports():
    for attr in ("find_text_regions", "find_text_lines"):
        assert hasattr(ac, attr) and attr in ac.__all__
