"""Headless tests for spectral-residual saliency (cv2/numpy synthetic frames)."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.saliency import (   # noqa: E402
    most_salient, salient_regions, saliency_map,
)


def _structured():
    """A dark frame with three bright blocks."""
    img = np.full((240, 320, 3), 20, "uint8")
    img[40:80, 40:80] = 240
    img[150:190, 200:240] = 230
    img[100:130, 140:175] = 255
    return img


def test_saliency_map_shape_and_range():
    sal_map = saliency_map(_structured())
    assert sal_map.shape == (64, 64)
    assert sal_map.dtype == np.float32
    assert float(sal_map.min()) >= 0.0
    assert float(sal_map.max()) <= 1.0


def test_size_parameter_changes_map_resolution():
    assert saliency_map(_structured(), size=32).shape == (32, 32)


def test_salient_regions_in_bounds_and_ranked():
    regions = salient_regions(_structured())
    assert len(regions) >= 1
    for region in regions:
        assert 0 <= region["x"] and region["x"] + region["width"] <= 320
        assert 0 <= region["y"] and region["y"] + region["height"] <= 240
        assert 0.0 <= region["score"] <= 1.0
    scores = [r["score"] for r in regions]
    assert scores == sorted(scores, reverse=True)


def test_most_salient_matches_top_region():
    img = _structured()
    top = most_salient(img)
    assert top is not None and top == salient_regions(img)[0]


def test_high_threshold_yields_nothing():
    img = _structured()
    assert salient_regions(img, threshold=2.0) == []   # above the normalised max
    assert most_salient(img, threshold=2.0) is None


# --- wiring ---------------------------------------------------------------

def test_executor_pure_path():
    from je_auto_control.utils.executor.action_executor import _salient_regions
    out = _salient_regions(_structured())
    assert isinstance(out["regions"], list) and len(out["regions"]) >= 1


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_salient_regions", "AC_most_salient"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_salient_regions", "ac_most_salient"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_salient_regions", "AC_most_salient"} <= specs


def test_facade_exports():
    for name in ("saliency_map", "salient_regions", "most_salient"):
        assert hasattr(ac, name) and name in ac.__all__
