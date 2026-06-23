"""Headless tests for localized motion / activity detection. No Qt."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.motion_regions import (   # noqa: E402
    activity_score, changed_regions, has_motion,
)


def _before():
    return np.full((120, 160), 100, dtype=np.uint8)


def _after_block():
    after = _before()
    after[40:70, 50:90] = 255            # a 40x30 region lights up
    return after


def test_changed_regions_locates_the_block():
    regions = changed_regions(_before(), _after_block(), min_area=50)
    assert len(regions) == 1
    box = regions[0]
    assert 30 <= box["x"] <= 55 and 25 <= box["y"] <= 45   # ~the (50,40) block


def test_has_motion_true_and_false():
    assert has_motion(_before(), _after_block()) is True
    assert has_motion(_before(), _before().copy()) is False


def test_activity_score_fraction():
    # 40*30 changed of 120*160 = 0.0625
    assert activity_score(_before(), _after_block()) == pytest.approx(0.0625,
                                                                      abs=0.01)
    assert activity_score(_before(), _before().copy()) == pytest.approx(0.0, abs=1e-9)


def test_min_area_filters_specks():
    after = _before()
    after[10:13, 10:13] = 255            # tiny 3x3 speck
    assert changed_regions(_before(), after, min_area=500) == []


def test_size_mismatch_raises():
    small = np.zeros((40, 40), dtype=np.uint8)
    with pytest.raises(ValueError):
        changed_regions(_before(), small)


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_changed_regions", "AC_has_motion"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_changed_regions", "ac_has_motion"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_changed_regions", "AC_has_motion"} <= specs


def test_facade_exports():
    for attr in ("changed_regions", "has_motion", "activity_score"):
        assert hasattr(ac, attr) and attr in ac.__all__
