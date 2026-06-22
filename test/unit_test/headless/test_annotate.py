"""Tests for screenshot annotation (pure-Pillow drawing)."""
import io

from PIL import Image

from je_auto_control.utils.annotate import annotate_screenshot


def _base(tmp_path, size=(120, 80)):
    path = tmp_path / "base.png"
    Image.new("RGB", size, (30, 30, 30)).save(str(path))
    return path


def test_annotate_writes_png_preserving_size(tmp_path):
    base = _base(tmp_path)
    out = tmp_path / "out.png"
    result = annotate_screenshot(
        str(base),
        [
            {"type": "box", "rect": [10, 10, 80, 50], "label": "btn"},
            {"type": "highlight", "rect": [20, 20, 60, 40], "alpha": 90},
            {"type": "arrow", "start": [5, 5], "end": [70, 45]},
            {"type": "text", "position": [5, 60], "text": "step 1"},
        ],
        str(out),
    )
    assert result == str(out)
    with Image.open(str(out)) as img:
        assert img.size == (120, 80)
        assert img.format == "PNG"


def test_annotate_accepts_bytes_source(tmp_path):
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (0, 0, 0)).save(buf, format="PNG")
    out = tmp_path / "b.png"
    annotate_screenshot(
        buf.getvalue(), [{"type": "box", "rect": [1, 1, 30, 30]}], str(out),
    )
    assert out.exists()


def test_unknown_annotation_type_is_ignored(tmp_path):
    base = _base(tmp_path)
    out = tmp_path / "o.png"
    annotate_screenshot(str(base), [{"type": "spiral"}], str(out))
    assert out.exists()


def test_creates_missing_output_directory(tmp_path):
    base = _base(tmp_path)
    out = tmp_path / "nested" / "deep" / "o.png"
    annotate_screenshot(str(base), [], str(out))
    assert out.exists()
