"""Headless tests for theme_normalize (cv2 behaviour + cv2-free wiring)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.theme_normalize import match_theme, normalize_theme


# --- cv2 behaviour (gated per-function so wiring still runs without cv2) ---

def test_normalize_theme_polarity_invariant():
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    rng = np.random.default_rng(0)
    image = rng.integers(0, 256, (60, 80)).astype("uint8")
    light = normalize_theme(image, method="sobel")
    dark = normalize_theme(255 - image, method="sobel")
    assert light.shape == image.shape
    # gradient magnitude is identical for an image and its colour inverse
    assert np.array_equal(light, dark)


def test_normalize_theme_zscore_shape():
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    rng = np.random.default_rng(1)
    image = rng.integers(0, 256, (40, 40)).astype("uint8")
    out = normalize_theme(image, method="zscore")
    assert out.shape == image.shape
    assert out.dtype == np.uint8


def test_normalize_theme_unknown_method_raises():
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    image = np.zeros((10, 10), dtype="uint8")
    with pytest.raises(ValueError):
        normalize_theme(image, method="bogus")


def test_match_theme_finds_template_across_inversion():
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    haystack = np.full((100, 120), 128, dtype="uint8")
    template = np.full((20, 20), 220, dtype="uint8")
    template[5:15, 5:15] = 40            # internal edge structure
    haystack[30:50, 40:60] = template    # place at x=40, y=30
    dark_haystack = 255 - haystack       # dark-mode: colours inverted
    result = match_theme(template, haystack=dark_haystack, method="sobel",
                         min_score=0.3)
    assert result is not None
    assert abs(result["x"] - 40) <= 5
    assert abs(result["y"] - 30) <= 5


# --- wiring (cv2-free: the module imports cv2 lazily) ----------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert "AC_match_theme" in known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_match_theme" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_match_theme" in specs


def test_facade_exports():
    for name in ("normalize_theme", "match_theme"):
        assert hasattr(ac, name) and name in ac.__all__
