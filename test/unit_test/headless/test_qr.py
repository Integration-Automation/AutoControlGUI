"""Tests for read_qr_codes (injected decoder; no real QR needed)."""
from PIL import Image

from je_auto_control.utils.qr import read_qr_codes


def test_read_qr_codes_with_injected_decoder(tmp_path):
    path = tmp_path / "x.png"
    Image.new("RGB", (50, 50), (255, 255, 255)).save(str(path))
    codes = read_qr_codes(
        str(path), decoder=lambda image: ["https://example.com"],
    )
    assert codes == ["https://example.com"]


def test_read_qr_codes_empty_when_none_found(tmp_path):
    path = tmp_path / "x.png"
    Image.new("RGB", (30, 30), (0, 0, 0)).save(str(path))
    assert read_qr_codes(str(path), decoder=lambda image: []) == []


def test_read_qr_codes_crops_to_region(tmp_path):
    seen = {}
    path = tmp_path / "x.png"
    Image.new("RGB", (100, 100), (255, 255, 255)).save(str(path))

    def decoder(image):
        seen["shape"] = image.shape[:2]  # (height, width)
        return []

    read_qr_codes(str(path), region=[0, 0, 40, 20], decoder=decoder)
    assert seen["shape"] == (20, 40)
