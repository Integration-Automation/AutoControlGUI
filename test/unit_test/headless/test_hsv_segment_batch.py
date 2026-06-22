"""Headless tests for HSV colour segmentation. No Qt."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.hsv_segment import (   # noqa: E402
    color_mask, dominant_hue_regions, segment_hsv,
)


def _scene():
    """Bright red + dark red (same hue, different brightness) + a green patch."""
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    img[10:40, 10:60] = (255, 0, 0)        # bright red, V=255
    img[60:90, 10:50] = (120, 0, 0)        # dark red, V=120
    img[10:40, 120:170] = (0, 200, 0)      # green
    return img


def test_hue_band_catches_both_brightnesses_of_red():
    reds = dominant_hue_regions(_scene(), hue=0, hue_tol=10, sat_min=80,
                                val_min=80, min_area=100)
    boxes = sorted((r["y"], r["x"], r["width"], r["height"]) for r in reds)
    assert boxes == [(10, 10, 50, 30), (60, 10, 40, 30)]   # bright AND dark red


def test_red_hue_excludes_green():
    reds = dominant_hue_regions(_scene(), hue=0, hue_tol=10, min_area=100)
    assert all(r["x"] < 100 for r in reds)                 # green is at x=120


def test_green_hue_found():
    greens = dominant_hue_regions(_scene(), hue=60, hue_tol=15, min_area=100)
    assert len(greens) == 1 and greens[0]["x"] == 120


def test_explicit_band_segment_and_mask():
    boxes = segment_hsv(_scene(), lower_hsv=[40, 80, 80], upper_hsv=[80, 255, 255],
                        min_area=100)
    assert len(boxes) == 1 and boxes[0]["x"] == 120        # the green patch
    mask = color_mask(_scene(), lower_hsv=[40, 80, 80], upper_hsv=[80, 255, 255])
    assert int(mask.sum()) > 0


def test_val_floor_skips_dark():
    # require a high value floor -> the dark red (V=120) drops out, bright stays
    reds = dominant_hue_regions(_scene(), hue=0, hue_tol=10, val_min=200,
                                min_area=100)
    assert len(reds) == 1 and reds[0]["y"] == 10           # only the bright patch


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_segment_hsv", "AC_dominant_hue_regions"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_segment_hsv", "ac_dominant_hue_regions"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_segment_hsv", "AC_dominant_hue_regions"} <= specs


def test_facade_exports():
    for attr in ("segment_hsv", "color_mask", "dominant_hue_regions"):
        assert hasattr(ac, attr) and attr in ac.__all__
