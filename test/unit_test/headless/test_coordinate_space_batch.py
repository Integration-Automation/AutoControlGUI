"""Headless tests for coordinate-space mapping. The math path is pure stdlib;
the PNG downscale runs under importorskip(PIL). No Qt imports."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.coordinate_space import (
    CoordinateSpace, normalized_space, xga_space)


def test_normalized_space_round_trip():
    space = normalized_space(1920, 1080, grid=1000)
    assert space.model_size == (1000, 1000)
    # centre maps both ways within rounding
    mx, my = space.to_model(960, 540)
    assert (mx, my) == (500, 500)
    px, py = space.to_physical(500, 500)
    assert abs(px - 960) <= 1 and abs(py - 540) <= 1


def test_to_physical_scales_from_grid():
    space = normalized_space(1000, 500, grid=100)
    assert space.to_physical(50, 50) == (500, 250)
    assert space.to_physical(100, 100) == (999, 499)   # clamped to last pixel


def test_xga_preserves_aspect_and_fits():
    space = xga_space(1920, 1080)        # 16:9 fits in 1024x768
    assert space.model_w <= 1024 and space.model_h <= 768
    # aspect ratio preserved
    assert abs(space.model_w / space.model_h - 1920 / 1080) < 0.02
    assert space.model_w == 1024         # width-bound for 16:9


def test_xga_no_upscale_for_small_screens():
    space = xga_space(800, 600)          # already within XGA -> unchanged
    assert (space.model_w, space.model_h) == (800, 600)


def test_clamping_is_in_bounds():
    space = CoordinateSpace(100, 100, 10, 10)
    assert space.to_physical(999, 999) == (99, 99)
    assert space.to_model(-5, -5) == (0, 0)


def test_downscale_png_matches_model_size():
    pil_image = pytest.importorskip("PIL.Image")
    import io
    buf = io.BytesIO()
    pil_image.new("RGB", (640, 480), (1, 2, 3)).save(buf, format="PNG")
    from je_auto_control.utils.coordinate_space import downscale_png
    space = normalized_space(640, 480, grid=64)
    out = downscale_png(buf.getvalue(), space)
    with pil_image.open(io.BytesIO(out)) as resized:
        assert resized.size == (64, 64)


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_to_physical",
        {"x": 500, "y": 500, "physical_w": 1920, "physical_h": 1080,
         "model_w": 1000, "model_h": 1000},
    ]])
    point = next(v for v in rec.values() if isinstance(v, dict))
    assert abs(point["x"] - 960) <= 1 and abs(point["y"] - 540) <= 1


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_to_physical", "AC_to_model"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_to_physical", "ac_to_model"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_to_physical", "AC_to_model"} <= cmds


def test_facade_exports():
    for attr in ("CoordinateSpace", "xga_space", "normalized_space",
                 "downscale_png"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
