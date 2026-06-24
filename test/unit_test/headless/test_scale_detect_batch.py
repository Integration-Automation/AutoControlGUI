"""Headless tests for display-scale / visual-DPI detection (cv2 synthetic frames)."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from je_auto_control.utils.scale_detect import detect_scale, scale_sweep  # noqa: E402


def _template():
    rng = np.random.default_rng(1)
    return rng.integers(0, 256, (40, 40, 3)).astype("uint8")


def _haystack_at(template, factor):
    """Embed the template resized by ``factor`` into a blank canvas."""
    size = int(40 * factor)
    big = cv2.resize(template, (size, size), interpolation=cv2.INTER_LINEAR)
    canvas = np.zeros((260, 260, 3), "uint8")
    canvas[60:60 + size, 50:50 + size] = big
    return canvas


def test_detect_scale_finds_the_rendering_scale():
    template = _template()
    result = detect_scale(template, _haystack_at(template, 1.5),
                          scales=(1.0, 1.25, 1.5, 1.75, 2.0))
    assert result["scale"] == pytest.approx(1.5)
    assert result["scale_percent"] == 150
    assert result["margin"] > 0.3   # clearly beats the runner-up
    # centre near the embedded 60x60 block at (50,60)
    cx, cy = result["center"]
    assert 70 <= cx <= 110 and 80 <= cy <= 120


def test_detect_scale_at_unity():
    template = _template()
    result = detect_scale(template, _haystack_at(template, 1.0))
    assert result["scale"] == pytest.approx(1.0)
    assert result["scale_percent"] == 100


def test_scale_sweep_returns_full_profile():
    template = _template()
    sweep = scale_sweep(template, _haystack_at(template, 1.25),
                        scales=(1.0, 1.25, 1.5))
    assert [round(c["scale"], 2) for c in sweep] == [1.0, 1.25, 1.5]
    best = max(sweep, key=lambda c: c["score"])
    assert best["scale"] == pytest.approx(1.25)
    assert {"scale", "score", "x", "y", "width", "height", "center"} <= set(sweep[0])


def test_detect_scale_none_when_template_too_big():
    template = _template()
    assert detect_scale(template, np.zeros((10, 10, 3), "uint8")) is None
    assert scale_sweep(template, np.zeros((10, 10, 3), "uint8")) == []


# --- wiring ---------------------------------------------------------------

def test_executor_pure_path():
    template = _template()
    from je_auto_control.utils.executor.action_executor import _detect_scale
    # pass ndarrays straight through (executor coerces only str args)
    out = _detect_scale(template, _haystack_at(template, 2.0))
    assert out["found"] is True and out["result"]["scale_percent"] == 200


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_detect_scale", "AC_scale_sweep"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_detect_scale", "ac_scale_sweep"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_detect_scale", "AC_scale_sweep"} <= specs


def test_facade_exports():
    for name in ("detect_scale", "scale_sweep"):
        assert hasattr(ac, name) and name in ac.__all__
