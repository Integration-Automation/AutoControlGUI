"""Tests for the OCR parser logic (no real Tesseract binary required)."""
from je_auto_control.utils.ocr.ocr_engine import TextMatch, _parse_matches


def _sample_data():
    return {
        "text": ["", "hello", "world", "low_conf"],
        "conf": ["-1", "95.0", "88.0", "10.0"],
        "left": [0, 10, 100, 50],
        "top": [0, 20, 30, 40],
        "width": [0, 40, 60, 30],
        "height": [0, 15, 15, 15],
    }


def test_parse_matches_skips_blank_and_low_conf():
    matches = _parse_matches(_sample_data(), 0, 0, min_confidence=60.0)
    assert [m.text for m in matches] == ["hello", "world"]


def test_parse_matches_applies_offsets():
    matches = _parse_matches(_sample_data(), 100, 200, min_confidence=60.0)
    # hello starts at (10, 20) -> (110, 220)
    assert matches[0].x == 110
    assert matches[0].y == 220


def test_text_match_center_is_midpoint():
    match = TextMatch(text="x", x=10, y=20, width=30, height=40, confidence=90.0)
    assert match.center == (25, 40)
