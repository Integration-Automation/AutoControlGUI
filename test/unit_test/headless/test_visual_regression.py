"""Phase 6.3: tests for the visual regression framework."""
import pytest

from PIL import Image

from je_auto_control.utils.visual_regression import (
    DiffResult, MaskRegion, compare_to_golden, image_difference,
    take_golden,
)


def _solid(width: int, height: int, color: tuple) -> Image.Image:
    return Image.new("RGB", (width, height), color=color)


def test_identical_images_match(tmp_path):
    golden = _solid(32, 32, (100, 200, 50))
    take_golden(tmp_path / "g.png", source=golden)
    result = compare_to_golden(
        tmp_path / "g.png", actual=_solid(32, 32, (100, 200, 50)),
    )
    assert result.matched is True
    assert result.diff_pct == pytest.approx(0.0)
    assert result.differing_pixels == 0


def test_completely_different_images_fail(tmp_path):
    take_golden(tmp_path / "g.png", source=_solid(16, 16, (0, 0, 0)))
    result = compare_to_golden(
        tmp_path / "g.png", actual=_solid(16, 16, (255, 255, 255)),
    )
    assert result.matched is False
    assert result.diff_pct == pytest.approx(100.0)
    assert result.diff_image is not None


def test_tolerance_admits_small_diff(tmp_path):
    """A single-pixel diff in a 100-pixel image is 1% — accept at tol=2."""
    take_golden(tmp_path / "g.png", source=_solid(10, 10, (0, 0, 0)))
    actual = _solid(10, 10, (0, 0, 0))
    actual.putpixel((0, 0), (255, 255, 255))
    strict = compare_to_golden(
        tmp_path / "g.png", actual=actual, tolerance=0.0,
    )
    lenient = compare_to_golden(
        tmp_path / "g.png", actual=actual, tolerance=2.0,
    )
    assert strict.matched is False
    assert lenient.matched is True


def test_per_pixel_threshold_ignores_minor_drift(tmp_path):
    """JPEG-style ±1 noise on a colour channel should not be a diff."""
    take_golden(tmp_path / "g.png", source=_solid(8, 8, (100, 100, 100)))
    drifted = _solid(8, 8, (101, 100, 100))  # +1 on red channel
    # Default threshold (16) treats this as identical.
    result = compare_to_golden(tmp_path / "g.png", actual=drifted)
    assert result.matched is True
    assert result.differing_pixels == 0
    # Tightening the threshold catches it.
    strict = compare_to_golden(
        tmp_path / "g.png", actual=drifted, per_pixel_threshold=0,
    )
    assert strict.matched is False


def test_masks_exclude_specified_regions(tmp_path):
    """Two images differ only inside a masked region → still matches."""
    expected = _solid(20, 20, (50, 50, 50))
    take_golden(tmp_path / "g.png", source=expected)
    actual = _solid(20, 20, (50, 50, 50))
    # Differ in a small box top-left.
    for x in range(5):
        for y in range(5):
            actual.putpixel((x, y), (255, 0, 0))
    plain = compare_to_golden(tmp_path / "g.png", actual=actual)
    assert plain.matched is False
    masked = compare_to_golden(
        tmp_path / "g.png", actual=actual,
        masks=[MaskRegion(0, 0, 5, 5)],
    )
    assert masked.matched is True


def test_take_golden_creates_parents(tmp_path):
    target = tmp_path / "nested" / "deep" / "g.png"
    take_golden(target, source=_solid(4, 4, (0, 0, 0)))
    assert target.exists()


def test_compare_raises_when_golden_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        compare_to_golden(
            tmp_path / "missing.png", actual=_solid(4, 4, (0, 0, 0)),
        )


def test_image_difference_rejects_size_mismatch():
    with pytest.raises(ValueError):
        image_difference(_solid(8, 8, (0, 0, 0)), _solid(4, 4, (0, 0, 0)))


def test_write_diff_persists_overlay(tmp_path):
    take_golden(tmp_path / "g.png", source=_solid(8, 8, (0, 0, 0)))
    result = compare_to_golden(
        tmp_path / "g.png", actual=_solid(8, 8, (255, 255, 255)),
    )
    diff_path = result.write_diff(tmp_path / "diff.png")
    assert diff_path.exists()
    loaded = Image.open(str(diff_path))
    assert loaded.size == (8, 8)


def test_summary_string_includes_pct():
    res = DiffResult(
        matched=False, diff_pct=1.234, differing_pixels=10,
        total_pixels=810, tolerance_pct=0.5, per_pixel_threshold=16,
    )
    assert "1.234%" in res.summary
    assert "0.500%" in res.summary
    assert "10/810" in res.summary
