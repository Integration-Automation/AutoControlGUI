"""Tests for the OCR parser logic (no real Tesseract binary required)."""
import re

from je_auto_control.utils.ocr import ocr_engine
from je_auto_control.utils.ocr.ocr_engine import (
    TextMatch, _parse_matches, find_text_regex, read_text_in_region,
)


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


class _FakePytesseract:
    """Stand-in for pytesseract that returns a canned image_to_data dict."""

    class Output:
        DICT = "dict"

    def __init__(self, data):
        self._data = data

    def image_to_data(self, _frame, lang="eng", output_type=None):
        del lang, output_type
        return self._data


def _install_fake_backend(monkeypatch, data):
    fake = _FakePytesseract(data)
    monkeypatch.setattr(ocr_engine, "_pytesseract", fake)
    monkeypatch.setattr(ocr_engine, "_image_grab", object())
    monkeypatch.setattr(ocr_engine, "_load_backend",
                        lambda: (fake, ocr_engine._image_grab))
    monkeypatch.setattr(ocr_engine, "_grab",
                        lambda region: (object(), 0, 0))


def test_read_text_in_region_returns_all_hits(monkeypatch):
    _install_fake_backend(monkeypatch, {
        "text": ["alpha", "beta", "gamma"],
        "conf": ["91.0", "82.0", "75.0"],
        "left": [0, 30, 60], "top": [0, 0, 0],
        "width": [20, 20, 20], "height": [10, 10, 10],
    })
    matches = read_text_in_region(region=[0, 0, 200, 100], min_confidence=60.0)
    assert [m.text for m in matches] == ["alpha", "beta", "gamma"]


def test_read_text_in_region_filters_by_confidence(monkeypatch):
    _install_fake_backend(monkeypatch, {
        "text": ["high", "low"],
        "conf": ["95.0", "20.0"],
        "left": [0, 30], "top": [0, 0],
        "width": [20, 20], "height": [10, 10],
    })
    matches = read_text_in_region(min_confidence=60.0)
    assert [m.text for m in matches] == ["high"]


def test_find_text_regex_matches_pattern(monkeypatch):
    _install_fake_backend(monkeypatch, {
        "text": ["Order#42", "ignore", "Order#99"],
        "conf": ["95.0", "95.0", "95.0"],
        "left": [0, 30, 60], "top": [0, 0, 0],
        "width": [20, 20, 20], "height": [10, 10, 10],
    })
    matches = find_text_regex(r"Order#\d+")
    assert [m.text for m in matches] == ["Order#42", "Order#99"]


def test_find_text_regex_accepts_compiled_pattern(monkeypatch):
    _install_fake_backend(monkeypatch, {
        "text": ["FOO", "foo", "bar"],
        "conf": ["90.0", "90.0", "90.0"],
        "left": [0, 10, 20], "top": [0, 0, 0],
        "width": [10, 10, 10], "height": [10, 10, 10],
    })
    matches = find_text_regex(re.compile(r"foo", re.IGNORECASE))
    assert {m.text for m in matches} == {"FOO", "foo"}
