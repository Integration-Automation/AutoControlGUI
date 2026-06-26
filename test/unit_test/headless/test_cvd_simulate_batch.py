"""Headless tests for cvd_simulate (pure colour-vision-deficiency math)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.cvd_simulate import (
    CVD_KINDS, color_distance, colors_collide, simulate_cvd,
)


# --- simulate_cvd ---------------------------------------------------------

def test_simulate_severity_zero_is_identity():
    assert simulate_cvd((120, 200, 30), "deuteranopia", severity=0.0) == \
        (120, 200, 30)


def test_simulate_grey_is_unchanged():
    # rows of every matrix sum to 1, so a neutral grey maps to itself
    for kind in CVD_KINDS:
        assert simulate_cvd((128, 128, 128), kind) == (128, 128, 128)


def test_simulate_shifts_red_under_protanopia():
    simulated = simulate_cvd((255, 0, 0), "protanopia")
    # pure red is strongly altered for a protanope (red cones missing)
    assert simulated != (255, 0, 0)
    assert all(0 <= channel <= 255 for channel in simulated)


def test_simulate_accepts_aliases():
    assert simulate_cvd((10, 20, 30), "green") == \
        simulate_cvd((10, 20, 30), "deuteranopia")


def test_simulate_unknown_kind_raises():
    with pytest.raises(ValueError):
        simulate_cvd((1, 2, 3), "tetrachromacy")


def test_simulate_severity_clamped():
    # severity above 1 behaves like 1 (full simulation)
    assert simulate_cvd((200, 50, 10), "protanopia", severity=5.0) == \
        simulate_cvd((200, 50, 10), "protanopia", severity=1.0)


# --- color_distance -------------------------------------------------------

def test_color_distance_zero_for_identical():
    assert color_distance((10, 20, 30), (10, 20, 30)) == pytest.approx(0.0)


def test_color_distance_positive_and_symmetric():
    forward = color_distance((255, 0, 0), (0, 255, 0))
    backward = color_distance((0, 255, 0), (255, 0, 0))
    assert forward > 0
    assert forward == pytest.approx(backward)


# --- colors_collide -------------------------------------------------------

def test_cvd_reduces_red_green_distance():
    # deuteranopia pulls red and green closer together than normal vision
    red, green = (220, 60, 60), (60, 200, 60)
    normal = color_distance(red, green)
    cvd = color_distance(simulate_cvd(red, "deuteranopia"),
                         simulate_cvd(green, "deuteranopia"))
    assert cvd < normal


def test_colors_collide_close_pair():
    # two muddy shades that map to nearly the same colour for a deuteranope
    result = colors_collide((150, 120, 110), (135, 130, 110),
                            kind="deuteranopia")
    assert result["collide"] is True
    assert result["kind"] == "deuteranopia"
    assert len(result["simulated_left"]) == 3


def test_colors_collide_black_white_never_collide():
    result = colors_collide((0, 0, 0), (255, 255, 255))
    assert result["collide"] is False
    assert result["distance"] > 40.0


def test_colors_collide_threshold_respected():
    red, green = (220, 60, 60), (60, 200, 60)
    assert colors_collide(red, green, threshold=40.0)["collide"] is False
    assert colors_collide(red, green, threshold=200.0)["collide"] is True


# --- wiring ---------------------------------------------------------------

def test_executor_paths():
    from je_auto_control.utils.executor.action_executor import (
        _colors_collide, _simulate_cvd,
    )
    out = _simulate_cvd("[128, 128, 128]", "protanopia", 1.0)
    assert out["rgb"] == [128, 128, 128]
    collide = _colors_collide([150, 120, 110], [135, 130, 110],
                              "deuteranopia", 1.0, 40.0)
    assert collide["collide"] is True


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_simulate_cvd", "AC_colors_collide"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_simulate_cvd", "ac_colors_collide"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_simulate_cvd", "AC_colors_collide"} <= specs


def test_facade_exports():
    for name in ("simulate_cvd", "colors_collide", "color_distance"):
        assert hasattr(ac, name) and name in ac.__all__
