"""Headless tests for icon_classify (pure classifier + cv2 features)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.icon_classify import (
    box_features, classify_icon, classify_widget,
)


# --- pure classify_widget -------------------------------------------------

def test_classify_radio_round():
    assert classify_widget(
        {"aspect": 1.0, "circularity": 0.92, "fill": 0.4}) == "radio"


def test_classify_toggle_wide_rounded():
    assert classify_widget(
        {"aspect": 2.4, "circularity": 0.6, "fill": 0.5}) == "toggle"


def test_classify_checkbox_square_sparse():
    assert classify_widget(
        {"aspect": 1.0, "circularity": 0.2, "fill": 0.1}) == "checkbox"


def test_classify_text_field_wide_hollow():
    assert classify_widget(
        {"aspect": 4.0, "circularity": 0.1, "fill": 0.05}) == "text_field"


def test_classify_button_wide_filled():
    assert classify_widget(
        {"aspect": 2.0, "circularity": 0.2, "fill": 0.5}) == "button"


def test_classify_icon_fallback():
    assert classify_widget(
        {"aspect": 1.1, "circularity": 0.3, "fill": 0.9}) == "icon"


def test_classify_widget_defaults_dont_crash():
    assert classify_widget({}) in ("checkbox", "icon")


# --- cv2 box_features / classify_icon (per-function importorskip) ----------

def test_box_features_circle_rounder_than_square():
    np = pytest.importorskip("numpy")
    cv2 = pytest.importorskip("cv2")
    canvas = np.full((40, 40), 255, dtype="uint8")
    cv2.circle(canvas, (20, 20), 14, 0, -1)
    circle = box_features(canvas, [3, 3, 34, 34])
    square_canvas = np.full((40, 40), 255, dtype="uint8")
    cv2.rectangle(square_canvas, (6, 6), (34, 34), 0, -1)
    square = box_features(square_canvas, [3, 3, 34, 34])
    assert circle["circularity"] > square["circularity"]
    assert circle["circularity"] > 0.8


def test_classify_icon_detects_radio_from_pixels():
    np = pytest.importorskip("numpy")
    cv2 = pytest.importorskip("cv2")
    canvas = np.full((40, 40), 255, dtype="uint8")
    cv2.circle(canvas, (20, 20), 13, 0, -1)   # filled round dot
    result = classify_icon(canvas, [4, 4, 32, 32])
    assert result["type"] == "radio"
    assert set(result["features"]) == {"aspect", "fill", "edge_density",
                                       "circularity"}


def test_box_features_empty_box():
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    import numpy as np
    canvas = np.zeros((10, 10), dtype="uint8")
    feats = box_features(canvas, [0, 0, 0, 0])
    assert feats == {"aspect": 0.0, "fill": 0.0, "edge_density": 0.0,
                     "circularity": 0.0}


# --- wiring (cv2-free) ----------------------------------------------------

def test_executor_pure_classify_path():
    from je_auto_control.utils.executor.action_executor import (
        _classify_widget,
    )
    out = _classify_widget('{"aspect": 1.0, "circularity": 0.9, "fill": 0.3}')
    assert out["type"] == "radio"


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_classify_widget", "AC_classify_icon"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_classify_widget", "ac_classify_icon"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_classify_widget", "AC_classify_icon"} <= specs


def test_facade_exports():
    for name in ("classify_widget", "box_features", "classify_icon"):
        assert hasattr(ac, name) and name in ac.__all__
