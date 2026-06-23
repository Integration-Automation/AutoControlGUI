"""Headless tests for colour-histogram fingerprint / change detection. No Qt."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.img_histogram import (   # noqa: E402
    compare_histograms, histogram_changed, image_histogram,
)


def _palette_a():
    img = np.zeros((60, 80, 3), dtype=np.uint8)
    img[:, :40] = (200, 0, 0)            # red | green
    img[:, 40:] = (0, 200, 0)
    return img


def _palette_b():
    img = np.zeros((60, 80, 3), dtype=np.uint8)
    img[:, :40] = (0, 0, 200)            # blue | yellow (same shapes, new palette)
    img[:, 40:] = (200, 200, 0)
    return img


def test_histogram_length_per_channel():
    assert len(image_histogram(_palette_a(), bins=32, space="hsv")) == 96
    assert len(image_histogram(_palette_a(), bins=16, space="gray")) == 16


def test_identical_correlation_is_one():
    hist = image_histogram(_palette_a())
    assert compare_histograms(hist, hist) == pytest.approx(1.0)


def test_different_palette_lowers_correlation():
    score = compare_histograms(image_histogram(_palette_a()),
                               image_histogram(_palette_b()))
    assert score < 0.9


def test_changed_detects_palette_shift():
    assert histogram_changed(_palette_a(), _palette_b()) is True
    assert histogram_changed(_palette_a(), _palette_a().copy()) is False


def test_distance_method_semantics():
    score = compare_histograms(image_histogram(_palette_a()),
                               image_histogram(_palette_b()),
                               method="bhattacharyya")
    assert score > 0.3
    assert histogram_changed(_palette_a(), _palette_b(), method="bhattacharyya",
                             threshold=0.3) is True


def test_unknown_space_and_method_raise():
    with pytest.raises(ValueError):
        image_histogram(_palette_a(), space="cmyk")
    with pytest.raises(ValueError):
        compare_histograms([1.0], [1.0], method="cosine")


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_image_histogram", "AC_histogram_changed"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_image_histogram", "ac_histogram_changed"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_image_histogram", "AC_histogram_changed"} <= specs


def test_facade_exports():
    for attr in ("image_histogram", "compare_histograms", "histogram_changed"):
        assert hasattr(ac, attr) and attr in ac.__all__
