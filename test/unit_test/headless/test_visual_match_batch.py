"""Headless tests for confidence-returning template matching. No Qt."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.visual_match import (   # noqa: E402
    Match, best_matches, match_template, match_template_all,
)


def _patch():
    """A 20x20 textured patch (non-constant, so CCOEFF_NORMED is well-defined)."""
    return np.tile(np.arange(0, 200, 10, dtype=np.uint8), (20, 1))


def _haystack():
    hay = np.zeros((100, 200), dtype=np.uint8)
    patch = _patch()
    hay[30:50, 50:70] = patch
    hay[30:50, 120:140] = patch
    return hay


def test_match_returns_score_and_box():
    match = match_template(_patch(), haystack=_haystack(), min_score=0.9)
    assert isinstance(match, Match)
    assert (match.x, match.y, match.width, match.height) == (50, 30, 20, 20)
    assert match.score == pytest.approx(1.0)
    assert match.center == [60, 40]


def test_no_match_below_threshold():
    other = np.tile(np.arange(200, 0, -10, dtype=np.uint8), (20, 1))[:8, :8]
    assert match_template(other, haystack=_haystack(), min_score=0.99) is None


def test_match_all_with_nms():
    matches = match_template_all(_patch(), haystack=_haystack(), min_score=0.9)
    assert len(matches) == 2                       # two patches, neighbours merged
    xs = sorted(m.x for m in matches)
    assert xs == [50, 120]
    assert all(m.score == pytest.approx(1.0) for m in matches)


def test_multiscale_finds_scaled_template():
    import cv2
    yy, xx = np.mgrid[0:20, 0:20]                # non-self-similar texture
    tmpl = ((yy * 53 + xx * 97 + yy * xx * 17) % 256).astype(np.uint8)
    big = cv2.resize(tmpl, (40, 40))             # == _resize(tmpl, 2.0)
    hay = np.zeros((120, 200), dtype=np.uint8)
    hay[10:50, 60:100] = big                     # embed only the 2x version
    match = match_template(tmpl, haystack=hay, scales=(1.0, 2.0), min_score=0.9)
    assert match is not None and match.scale == pytest.approx(2.0)


def test_unknown_method_raises():
    with pytest.raises(ValueError):
        match_template(_patch(), haystack=_haystack(), method="bogus")


def test_to_dict_has_center():
    match = match_template(_patch(), haystack=_haystack(), min_score=0.9)
    data = match.to_dict()
    assert data["center"] == [60, 40] and data["score"] == pytest.approx(1.0)


# --- screen coordinates ----------------------------------------------------

def _stub_grab(monkeypatch, image, origin):
    """Replace the screen grab with a fixed frame at a fixed screen origin."""
    from je_auto_control.utils.visual_match import visual_match as vm
    monkeypatch.setattr(vm, "_grab_gray_with_origin",
                        lambda region: (image, origin[0], origin[1]))


def test_grabbed_matches_are_translated_to_screen_coordinates(monkeypatch):
    # The virtual desktop starts at a negative origin whenever a monitor sits
    # left of or above the primary one; an untranslated hit is unclickable.
    _stub_grab(monkeypatch, _haystack(), (-100, -164))
    match = match_template(_patch(), min_score=0.9)
    assert (match.x, match.y) == (50 - 100, 30 - 164)
    assert match.center == [60 - 100, 40 - 164]


def test_match_all_translates_every_hit(monkeypatch):
    _stub_grab(monkeypatch, _haystack(), (10, 20))
    hits = match_template_all(_patch(), min_score=0.9)
    assert sorted((m.x, m.y) for m in hits) == [(60, 50), (130, 50)]


def test_supplied_haystack_keeps_its_own_coordinates(monkeypatch):
    # An injected image is its own space — adding a screen origin to it would
    # be wrong, and would break every synthetic-array test above.
    _stub_grab(monkeypatch, _haystack(), (999, 999))
    match = match_template(_patch(), haystack=_haystack(), min_score=0.9)
    assert (match.x, match.y) == (50, 30)


# --- degenerate templates --------------------------------------------------

def test_flat_template_is_refused_rather_than_matched_anywhere():
    # Normalised correlation divides by the template's variance, so a single
    # colour saturates the whole score map at 1.0 and "finds" the target at an
    # arbitrary position — worse than failing, because the caller clicks there.
    flat = np.full((20, 20), 128, dtype=np.uint8)
    with pytest.raises(ac.AutoControlScreenException):
        match_template(flat, haystack=_haystack())
    with pytest.raises(ac.AutoControlScreenException):
        match_template_all(flat, haystack=_haystack())


def test_template_larger_than_haystack_finds_nothing():
    big = np.tile(np.arange(0, 250, 1, dtype=np.uint8), (250, 1))
    assert match_template_all(big, haystack=_haystack()) == []


# --- file loading ----------------------------------------------------------

def test_template_loads_from_a_non_ascii_path(tmp_path):
    # cv2.imread goes through the C locale on Windows and returns None for a
    # path with non-ASCII characters — indistinguishable from a corrupt file.
    import cv2
    ascii_path = tmp_path / "ascii.png"
    cv2.imwrite(str(ascii_path), _patch())
    target = tmp_path / "樣板圖.png"
    target.write_bytes(ascii_path.read_bytes())
    match = match_template(str(target), haystack=_haystack(), min_score=0.9)
    assert match is not None and (match.x, match.y) == (50, 30)


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_match_template", "AC_match_template_all"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_match_template", "ac_match_template_all"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_match_template", "AC_match_template_all"} <= specs


def test_facade_exports():
    for attr in ("TemplateMatch", "match_template", "match_template_all",
                 "best_matches"):
        assert hasattr(ac, attr) and attr in ac.__all__
    assert callable(best_matches)
