"""Headless tests for masked template matching. No Qt."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.visual_match import (   # noqa: E402
    match_masked, match_masked_all,
)


def _textured(height, width, seed):
    yy, xx = np.mgrid[0:height, 0:width]
    return ((yy * 53 + xx * 97 + yy * xx * 17 + seed * 31) % 256).astype(np.uint8)


def _template_with_border():
    """20x20: a distinctive 10x10 core (seed 1) inside a border (seed 2)."""
    tmpl = _textured(20, 20, 2)
    tmpl[5:15, 5:15] = _textured(10, 10, 1)
    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[5:15, 5:15] = 255
    return tmpl, mask


def _scene_with_different_border():
    """Haystack: the same core at (40, 30) but a DIFFERENT surrounding border."""
    hay = _textured(100, 100, 9)
    patch = _textured(20, 20, 7)               # border differs from template
    patch[5:15, 5:15] = _textured(10, 10, 1)   # core is identical
    hay[30:50, 40:60] = patch
    return hay


def test_mask_ignores_background():
    tmpl, mask = _template_with_border()
    hit = match_masked(tmpl, mask=mask, haystack=_scene_with_different_border(),
                       min_score=0.9)
    assert hit is not None
    assert (hit.x, hit.y) == (40, 30)
    assert hit.center == [50, 40]


def test_unmasked_is_dragged_down_by_border():
    """Without the mask the differing border lowers the score below threshold."""
    tmpl, _ = _template_with_border()
    assert match_masked(tmpl, haystack=_scene_with_different_border(),
                        min_score=0.999) is None


def test_alpha_channel_is_the_implicit_mask():
    tmpl, mask = _template_with_border()
    rgba = np.dstack([tmpl, tmpl, tmpl, mask])     # alpha == the core mask
    hit = match_masked(rgba, haystack=_scene_with_different_border(),
                       min_score=0.9)
    assert hit is not None and (hit.x, hit.y) == (40, 30)


def test_absent_template_returns_none():
    tmpl, mask = _template_with_border()
    blank = np.zeros((100, 100), dtype=np.uint8)
    assert match_masked(tmpl, mask=mask, haystack=blank, min_score=0.9) is None


def test_match_all_dedupes_to_one():
    tmpl, mask = _template_with_border()
    hits = match_masked_all(tmpl, mask=mask,
                            haystack=_scene_with_different_border(),
                            min_score=0.99)   # only the exact (1.0) core matches
    assert len(hits) == 1
    assert (hits[0].x, hits[0].y) == (40, 30)


def test_mask_shape_mismatch_raises():
    tmpl, _ = _template_with_border()
    bad = np.zeros((5, 5), dtype=np.uint8)
    with pytest.raises(ValueError):
        match_masked(tmpl, mask=bad, haystack=_scene_with_different_border())


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_match_masked", "AC_match_masked_all"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_match_masked", "ac_match_masked_all"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_match_masked", "AC_match_masked_all"} <= specs


def test_facade_exports():
    for attr in ("match_masked", "match_masked_all"):
        assert hasattr(ac, attr) and attr in ac.__all__
