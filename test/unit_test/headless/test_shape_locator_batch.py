"""Headless tests for edge/contour shape location. No Qt."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from je_auto_control.utils.shape_locator import (   # noqa: E402
    find_rectangles, find_shapes,
)


def _scene():
    """300x200 scene: a wide button, a square outline, and a circle."""
    img = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (120, 70), (255, 255, 255), -1)   # 100x50 button
    cv2.rectangle(img, (160, 30), (200, 70), (200, 200, 200), 2)   # 40x40 outline
    cv2.circle(img, (80, 150), 30, (180, 180, 180), -1)           # not a rectangle
    return img


def _near(value, target, tol=4):
    return abs(value - target) <= tol


def test_find_shapes_returns_all_three():
    shapes = find_shapes(_scene(), min_area=300)
    assert len(shapes) == 3                       # button, outline, circle bbox
    biggest = shapes[0]                           # largest first
    assert _near(biggest["width"], 100) and _near(biggest["height"], 50)


def test_find_rectangles_excludes_the_circle():
    rects = find_rectangles(_scene(), min_area=300)
    assert len(rects) == 2                         # circle dropped
    assert all(0.7 < r["aspect"] for r in rects)


def test_aspect_range_keeps_only_wide_button():
    wide = find_rectangles(_scene(), min_area=300, aspect_range=(1.5, 8.0))
    assert len(wide) == 1
    box = wide[0]
    assert _near(box["x"], 20) and _near(box["y"], 20)
    assert _near(box["center"][0], 70) and _near(box["center"][1], 45)


def test_max_area_filters_large_shapes():
    small = find_shapes(_scene(), min_area=300, max_area=3000)
    assert all(s["area"] <= 3000 for s in small)
    assert small                                   # the ~40x40 outline survives


def test_min_area_filters_specks():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.rectangle(img, (10, 10), (15, 15), (255, 255, 255), -1)   # tiny speck
    assert find_shapes(img, min_area=500) == []


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_find_shapes", "AC_find_rectangles"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_find_shapes", "ac_find_rectangles"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_find_shapes", "AC_find_rectangles"} <= specs


def test_facade_exports():
    for attr in ("find_shapes", "find_rectangles"):
        assert hasattr(ac, attr) and attr in ac.__all__
