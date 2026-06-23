"""Headless tests for ORB feature matching. No Qt."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from je_auto_control.utils.feature_match import (   # noqa: E402
    FeatureMatch, feature_match,
)


def _template():
    """A 60x60 feature-rich patch (corners/blobs ORB can latch onto)."""
    tmpl = np.zeros((60, 60), dtype=np.uint8)
    cv2.rectangle(tmpl, (5, 5), (25, 20), 255, -1)
    cv2.rectangle(tmpl, (35, 10), (55, 40), 200, -1)
    cv2.circle(tmpl, (20, 45), 10, 150, -1)
    cv2.rectangle(tmpl, (40, 45), (52, 55), 90, 2)
    return tmpl


def _scene(rotate=False):
    """A 200x200 scene with the template pasted at (90, 60), optionally rotated."""
    scene = np.zeros((200, 200), dtype=np.uint8)
    patch = _template()
    if rotate:
        matrix = cv2.getRotationMatrix2D((30, 30), 20, 1.0)
        patch = cv2.warpAffine(patch, matrix, (60, 60))
    scene[60:120, 90:150] = patch
    return scene


def test_locates_unrotated_template():
    hit = feature_match(_template(), haystack=_scene(), min_inliers=8)
    assert hit is not None
    # the template was pasted at columns 90..150, rows 60..120 -> centre ~ (120, 90)
    assert 100 <= hit.center[0] <= 140
    assert 70 <= hit.center[1] <= 110
    assert hit.inliers >= 8
    assert len(hit.corners) == 4


def test_survives_rotation():
    hit = feature_match(_template(), haystack=_scene(rotate=True), min_inliers=6)
    assert hit is not None
    assert hit.inliers >= 6


def test_absent_template_returns_none():
    blank = np.zeros((200, 200), dtype=np.uint8)
    assert feature_match(_template(), haystack=blank, min_inliers=8) is None


def test_score_is_inlier_fraction():
    hit = feature_match(_template(), haystack=_scene(), min_inliers=8)
    assert 0.0 < hit.score <= 1.0
    assert hit.to_dict()["inliers"] == hit.inliers


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert "AC_feature_match" in known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_feature_match" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_feature_match" in specs


def test_facade_exports():
    assert hasattr(ac, "feature_match") and "feature_match" in ac.__all__
    assert isinstance(feature_match(_template(), haystack=_scene(),
                                    min_inliers=8), FeatureMatch)
