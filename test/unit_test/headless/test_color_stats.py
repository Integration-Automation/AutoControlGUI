"""Tests for region colour statistics (pure-Pillow analysis)."""
import io

import pytest
from PIL import Image

from je_auto_control.utils.color_stats import region_color_stats


def _solid(tmp_path, color, size=(60, 40)):
    path = tmp_path / "c.png"
    Image.new("RGB", size, color).save(str(path))
    return path


def test_solid_color_average_and_dominant(tmp_path):
    stats = region_color_stats(str(_solid(tmp_path, (200, 50, 50))))
    assert stats.average_rgb == (200, 50, 50)
    assert stats.dominant_rgb == (200, 50, 50)
    assert stats.dominant_fraction == pytest.approx(1.0)
    assert stats.pixel_count > 0


def test_dominant_picks_the_majority_colour(tmp_path):
    img = Image.new("RGB", (100, 10), (220, 20, 20))  # 80% red
    for x in range(80, 100):  # right 20% blue
        for y in range(10):
            img.putpixel((x, y), (20, 20, 220))
    path = tmp_path / "mix.png"
    img.save(str(path))
    stats = region_color_stats(str(path))
    assert stats.dominant_rgb[0] > stats.dominant_rgb[2]  # red-ish majority
    assert stats.dominant_fraction >= 0.5


def test_region_crop_restricts_analysis(tmp_path):
    img = Image.new("RGB", (100, 100), (0, 0, 0))
    for x in range(20):  # green 20x20 top-left
        for y in range(20):
            img.putpixel((x, y), (0, 200, 0))
    path = tmp_path / "r.png"
    img.save(str(path))
    stats = region_color_stats(str(path), region=[0, 0, 20, 20])
    assert stats.average_rgb == (0, 200, 0)


def test_accepts_bytes_source():
    buf = io.BytesIO()
    Image.new("RGB", (30, 30), (10, 20, 30)).save(buf, format="PNG")
    stats = region_color_stats(buf.getvalue())
    assert stats.average_rgb == (10, 20, 30)
