"""Headless tests for colour-aware (HSV) template matching."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.color_match import (  # noqa: E402
    match_color, match_color_all,
)

RED, GREEN, BLUE, YELLOW = [255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0]


def _patch(left, right):
    patch = np.zeros((24, 24, 3), dtype=np.uint8)
    patch[:, :12] = left
    patch[:, 12:] = right
    return patch


def _scene():
    hay = np.zeros((160, 200, 3), dtype=np.uint8)
    hay[50:74, 40:64] = _patch(RED, GREEN)        # the target
    hay[50:74, 140:164] = _patch(BLUE, YELLOW)    # same shape, different colours
    return hay


def test_finds_the_colour_target():
    match = match_color(_patch(RED, GREEN), haystack=_scene(), channels=("h",),
                        min_score=0.7)
    assert match is not None
    assert abs(match.x - 40) <= 1 and abs(match.y - 50) <= 1
    assert match.score >= 0.99


def test_discriminates_colour_not_just_shape():
    # at a high threshold only the matching-colour patch survives — the blue/yellow
    # decoy of identical shape is rejected (grayscale matching would accept it)
    hits = match_color_all(_patch(RED, GREEN), haystack=_scene(), channels=("h",),
                           min_score=0.95)
    assert len(hits) == 1
    assert abs(hits[0].x - 40) <= 1


def test_absent_returns_none():
    blank = np.zeros((160, 200, 3), dtype=np.uint8)
    assert match_color(_patch(BLUE, YELLOW), haystack=blank, channels=("h",),
                       min_score=0.7) is None


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_match_color", "AC_match_color_all"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_match_color", "ac_match_color_all"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_match_color", "AC_match_color_all"} <= specs


def test_facade_exports():
    for name in ("match_color", "match_color_all"):
        assert hasattr(ac, name) and name in ac.__all__
