"""Tests for the OCR parser logic (no real Tesseract / EasyOCR binary required).

The engine was refactored to pluggable backends, so these tests:

1. Exercise ``TesseractBackend.image_to_matches`` directly with a
   stand-in pytesseract module (no binary needed).
2. Exercise the public ``ocr_engine`` helpers with an injected backend
   so we never touch real image grabs or external processes.
"""
import re

import pytest

from je_auto_control.utils.ocr import ocr_engine
from je_auto_control.utils.ocr.backends import OCRBackendNotAvailableError
from je_auto_control.utils.ocr.backends.tesseract_backend import (
    TesseractBackend,
)
from je_auto_control.utils.ocr.ocr_engine import (
    TextMatch, find_text_matches, find_text_regex, locate_text_center,
    read_text_in_region,
)


# --- Tesseract backend parser ---------------------------------------

def _sample_tess_data():
    return {
        "text": ["", "hello", "world", "low_conf"],
        "conf": ["-1", "95.0", "88.0", "10.0"],
        "left": [0, 10, 100, 50],
        "top": [0, 20, 30, 40],
        "width": [0, 40, 60, 30],
        "height": [0, 15, 15, 15],
    }


class _FakePytesseract:
    """Stand-in for pytesseract returning a canned ``image_to_data`` dict."""

    class Output:
        DICT = "dict"

    def __init__(self, data):
        self._data = data
        self.pytesseract = self  # mimic the nested ``pt.pytesseract.tesseract_cmd``
        self.tesseract_cmd = None

    def image_to_data(self, _frame, lang="eng", output_type=None):
        del lang, output_type
        return self._data


def _install_fake_pytesseract(monkeypatch, data):
    fake = _FakePytesseract(data)
    # Force the tesseract backend to use the fake instead of the real import.
    import je_auto_control.utils.ocr.backends.tesseract_backend as tess_mod
    monkeypatch.setattr(tess_mod, "_pytesseract", fake)
    monkeypatch.setattr(tess_mod, "_load", lambda: fake)
    return fake


def test_tesseract_backend_skips_blank_and_low_conf(monkeypatch):
    _install_fake_pytesseract(monkeypatch, _sample_tess_data())
    backend = TesseractBackend()
    backend._available = True  # bypass real binary probe
    matches = backend.image_to_matches(object(), "eng", 60.0)
    assert [m.text for m in matches] == ["hello", "world"]


def test_tesseract_backend_keeps_image_local_coords(monkeypatch):
    _install_fake_pytesseract(monkeypatch, _sample_tess_data())
    backend = TesseractBackend()
    backend._available = True
    matches = backend.image_to_matches(object(), "eng", 60.0)
    # Image-local — the engine layer adds the screen-region offset.
    assert (matches[0].x, matches[0].y) == (10, 20)


def test_text_match_center_is_midpoint():
    match = TextMatch(text="x", x=10, y=20, width=30, height=40, confidence=90.0)
    assert match.center == (25, 40)


# --- High-level helpers with an injected backend --------------------

class _StubBackend:
    """Returns a fixed list of ``TextMatch`` regardless of arguments."""

    name = "stub"
    available = True

    def __init__(self, matches):
        self._matches = matches

    def image_to_matches(self, _image, _lang, _min_confidence):
        return list(self._matches)


@pytest.fixture
def patched_grab(monkeypatch):
    """Skip real screen capture: ``_grab`` returns sentinel image + zero offset."""
    monkeypatch.setattr(
        ocr_engine, "_grab",
        lambda region: (object(), 0, 0),
    )


def test_read_text_in_region_returns_all_hits(patched_grab):
    backend = _StubBackend([
        TextMatch("alpha", 0, 0, 20, 10, 91.0),
        TextMatch("beta", 30, 0, 20, 10, 82.0),
        TextMatch("gamma", 60, 0, 20, 10, 75.0),
    ])
    matches = read_text_in_region(
        region=[0, 0, 200, 100], min_confidence=60.0, backend=backend,
    )
    assert [m.text for m in matches] == ["alpha", "beta", "gamma"]


def test_read_text_in_region_applies_grab_offset(monkeypatch):
    monkeypatch.setattr(
        ocr_engine, "_grab",
        lambda region: (object(), 100, 200),
    )
    backend = _StubBackend([
        TextMatch("hello", 10, 20, 40, 15, 95.0),
    ])
    matches = read_text_in_region(backend=backend)
    # Image-local (10, 20) + screen offset (100, 200) = (110, 220).
    assert (matches[0].x, matches[0].y) == (110, 220)


def test_find_text_regex_matches_pattern(patched_grab):
    backend = _StubBackend([
        TextMatch("Order#42", 0, 0, 20, 10, 95.0),
        TextMatch("ignore", 30, 0, 20, 10, 95.0),
        TextMatch("Order#99", 60, 0, 20, 10, 95.0),
    ])
    matches = find_text_regex(r"Order#\d+", backend=backend)
    assert [m.text for m in matches] == ["Order#42", "Order#99"]


def test_find_text_regex_accepts_compiled_pattern(patched_grab):
    backend = _StubBackend([
        TextMatch("FOO", 0, 0, 10, 10, 90.0),
        TextMatch("foo", 10, 0, 10, 10, 90.0),
        TextMatch("bar", 20, 0, 10, 10, 90.0),
    ])
    matches = find_text_regex(
        re.compile(r"foo", re.IGNORECASE), backend=backend,
    )
    assert {m.text for m in matches} == {"FOO", "foo"}


def test_find_text_matches_filters_case_insensitive(patched_grab):
    backend = _StubBackend([
        TextMatch("Hello", 0, 0, 10, 10, 95.0),
        TextMatch("WORLD", 10, 0, 10, 10, 95.0),
    ])
    matches = find_text_matches("hello", backend=backend)
    assert [m.text for m in matches] == ["Hello"]


def test_find_text_matches_supports_case_sensitive(patched_grab):
    backend = _StubBackend([
        TextMatch("Hello", 0, 0, 10, 10, 95.0),
        TextMatch("hello", 10, 0, 10, 10, 95.0),
    ])
    matches = find_text_matches(
        "hello", case_sensitive=True, backend=backend,
    )
    assert [m.text for m in matches] == ["hello"]


def test_locate_text_center_raises_when_missing(patched_grab):
    backend = _StubBackend([])
    from je_auto_control.utils.exception.exceptions import (
        AutoControlActionException,
    )
    with pytest.raises(AutoControlActionException, match="not found"):
        locate_text_center("anything", backend=backend)


# --- Backend factory -----------------------------------------------

def test_backend_factory_rejects_unknown_name():
    from je_auto_control.utils.ocr.backends import get_backend, reset_cache
    reset_cache()
    with pytest.raises(OCRBackendNotAvailableError, match="unknown"):
        get_backend("not-a-real-engine")
