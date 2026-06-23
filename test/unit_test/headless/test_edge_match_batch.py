"""Headless tests for edge-shape (Chamfer) template matching."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from je_auto_control.utils.edge_match import (  # noqa: E402
    chamfer_distance, edge_match, edge_match_all,
)


def _scene():
    hay = np.zeros((200, 200), dtype=np.uint8)
    cv2.rectangle(hay, (50, 50), (110, 90), 255, 3)
    return hay


def _template_different_fill():
    # same outline as the scene rectangle, but drawn at a different grey level
    tmpl = np.zeros((50, 70), dtype=np.uint8)
    cv2.rectangle(tmpl, (5, 5), (65, 45), 150, 3)
    return tmpl


def test_finds_shape_despite_different_fill():
    match = edge_match(_template_different_fill(), haystack=_scene(), min_score=0.5)
    assert match is not None
    assert match.score >= 0.9                 # edges align even at a different grey
    assert abs(match.x - 45) <= 2 and abs(match.y - 45) <= 2


def test_chamfer_distance_near_zero_on_alignment():
    dist = chamfer_distance(_template_different_fill(), haystack=_scene())
    assert dist < 1.0                         # ~0 = edges coincide


def test_absent_returns_none():
    blank = np.zeros((200, 200), dtype=np.uint8)
    assert edge_match(_template_different_fill(), haystack=blank,
                      min_score=0.5) is None


def test_edge_match_all_dedupes():
    hits = edge_match_all(_template_different_fill(), haystack=_scene(),
                          min_score=0.85)
    assert len(hits) == 1


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_edge_match", "AC_edge_match_all"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_edge_match", "ac_edge_match_all"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_edge_match", "AC_edge_match_all"} <= specs


def test_facade_exports():
    for name in ("edge_match", "edge_match_all", "chamfer_distance"):
        assert hasattr(ac, name) and name in ac.__all__
