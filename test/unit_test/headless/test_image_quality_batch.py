"""Headless tests for image-quality scoring (cv2 synthetic frames)."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from je_auto_control.utils.image_quality import (   # noqa: E402
    image_quality, is_blurry, quality_gate,
)


def _sharp():
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, (120, 120)).astype("uint8")  # noisy = high Laplacian var


def _blurry():
    return cv2.GaussianBlur(_sharp(), (0, 0), 8)              # heavy blur = low var


def test_metrics_present_and_typed():
    metrics = image_quality(_sharp())
    assert set(metrics) == {"sharpness", "contrast", "brightness"}
    assert all(isinstance(v, float) for v in metrics.values())
    assert 0.0 <= metrics["brightness"] <= 255.0


def test_sharp_is_sharper_than_blurry():
    assert image_quality(_sharp())["sharpness"] > image_quality(_blurry())["sharpness"]
    assert is_blurry(_sharp(), threshold=100.0) is False
    assert is_blurry(_blurry(), threshold=100.0) is True


def test_quality_gate_pass_and_fail():
    good = quality_gate(_sharp())
    assert good["passed"] is True and good["issues"] == []
    bad = quality_gate(_blurry())
    assert bad["passed"] is False
    assert "blurry" in bad["issues"]


def test_quality_gate_flags_dark():
    dark = np.full((80, 80), 5, "uint8")
    report = quality_gate(dark)
    assert report["passed"] is False
    assert "too_dark" in report["issues"]


def test_quality_gate_brightness_range_tunable():
    mid = np.full((40, 40), 130, "uint8")
    # a flat frame is blurry+low-contrast, but brightness must not be flagged
    issues = quality_gate(mid, brightness_range=(40.0, 220.0))["issues"]
    assert "too_dark" not in issues and "too_bright" not in issues


# --- wiring ---------------------------------------------------------------

def test_executor_pure_path():
    from je_auto_control.utils.executor.action_executor import _quality_gate
    report = _quality_gate(_blurry())
    assert report["passed"] is False and "blurry" in report["issues"]


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_image_quality", "AC_quality_gate"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_image_quality", "ac_quality_gate"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_image_quality", "AC_quality_gate"} <= specs


def test_facade_exports():
    for name in ("image_quality", "is_blurry", "quality_gate"):
        assert hasattr(ac, name) and name in ac.__all__
