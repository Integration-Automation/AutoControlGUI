"""Headless tests for contrast_map (pure WCAG grade + fg/bg split)."""
import je_auto_control as ac
from je_auto_control.utils.contrast_map import (
    dominant_pair, grade_contrast, region_contrast,
)


# --- grade_contrast -------------------------------------------------------

def test_grade_black_on_white_passes_all():
    grade = grade_contrast((0, 0, 0), (255, 255, 255))
    assert grade["ratio"] > 20.0  # 21:1 black/white
    assert grade["aa"] is True and grade["aaa"] is True
    assert grade["aa_large"] is True and grade["aaa_large"] is True


def test_grade_low_contrast_fails_normal():
    # mid-grey on light-grey: legible as large text only, fails normal AAA
    grade = grade_contrast((120, 120, 120), (180, 180, 180))
    assert grade["aaa"] is False


def test_grade_symmetric():
    forward = grade_contrast((10, 20, 30), (200, 210, 220))["ratio"]
    backward = grade_contrast((200, 210, 220), (10, 20, 30))["ratio"]
    assert abs(forward - backward) < 1e-6


# --- dominant_pair --------------------------------------------------------

def test_dominant_pair_text_on_background():
    # mostly white background with a few black "text" pixels
    pixels = [(255, 255, 255)] * 8 + [(0, 0, 0)] * 2
    pair = dominant_pair(pixels)
    assert pair["background"] == [255, 255, 255]
    assert pair["foreground"] == [0, 0, 0]


def test_dominant_pair_uniform_region_no_contrast():
    pair = dominant_pair([(128, 128, 128)] * 5)
    assert pair["foreground"] == pair["background"] == [128, 128, 128]


def test_dominant_pair_empty():
    pair = dominant_pair([])
    assert pair["foreground"] == [0, 0, 0]
    assert pair["background"] == [0, 0, 0]


# --- region_contrast (injected sampler) -----------------------------------

def test_region_contrast_with_injected_sampler():
    pixels = [[245, 245, 245]] * 9 + [[20, 20, 20]]
    result = region_contrast(sampler=lambda region: pixels)
    assert result["background"] == [245, 245, 245]
    assert result["foreground"] == [20, 20, 20]
    assert result["samples"] == 10
    assert result["aa"] is True


def test_region_contrast_passes_region_to_sampler():
    seen = {}

    def sampler(region):
        seen["region"] = region
        return [(0, 0, 0), (255, 255, 255)]

    region_contrast(sampler=sampler, region=[10, 10, 50, 30])
    assert seen["region"] == [10, 10, 50, 30]


# --- wiring ---------------------------------------------------------------

def test_executor_pure_paths():
    from je_auto_control.utils.executor.action_executor import (
        _dominant_pair, _grade_contrast,
    )
    assert _grade_contrast([0, 0, 0], [255, 255, 255])["aa"] is True
    pair = _dominant_pair("[[255,255,255],[255,255,255],[0,0,0]]")
    assert pair["background"] == [255, 255, 255]


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_grade_contrast", "AC_dominant_pair",
            "AC_region_contrast"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_grade_contrast", "ac_dominant_pair",
            "ac_region_contrast"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_grade_contrast", "AC_dominant_pair",
            "AC_region_contrast"} <= specs


def test_facade_exports():
    for name in ("grade_contrast", "dominant_pair", "region_contrast"):
        assert hasattr(ac, name) and name in ac.__all__
