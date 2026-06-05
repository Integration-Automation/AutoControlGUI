"""Headless tests for the assertion DSL (no Qt imports)."""
import sys
from types import SimpleNamespace

import pytest

import je_auto_control as ac
from je_auto_control.utils.assertion import (
    AssertionResult, assert_image, assert_pixel, assert_text, assert_window,
)
from je_auto_control.utils.exception.exceptions import (
    AutoControlAssertionException,
)


def test_facade_exports_assertions():
    assert hasattr(ac, "assert_text")
    assert hasattr(ac, "assert_window")
    assert hasattr(ac, "assert_image")
    assert hasattr(ac, "assert_pixel")


def test_assertion_import_stays_qt_free():
    """Import the facade in a fresh interpreter so the check isn't polluted
    by GUI tests that may have already imported PySide6 in this session."""
    import subprocess
    script = (
        "import sys, je_auto_control as ac\n"
        "ac.assert_window  # touch the assertion surface\n"
        "qt = [m for m in sys.modules if 'PySide6' in m]\n"
        "import json; print(json.dumps(qt))\n"
    )
    result = subprocess.run(  # nosec B603  # nosemgrep
        [sys.executable, "-c", script],
        capture_output=True, text=True, check=True, timeout=60,
    )
    assert result.stdout.strip() in ("[]", "")


# === assert_window =========================================================

def _patch_windows(monkeypatch, titles):
    import je_auto_control.wrapper.auto_control_window as win
    monkeypatch.setattr(
        win, "list_windows",
        lambda: [(i, t) for i, t in enumerate(titles)],
    )


def test_assert_window_present_passes(monkeypatch):
    _patch_windows(monkeypatch, ["Notepad", "Calculator"])
    result = assert_window("notepad", exists=True)
    assert isinstance(result, AssertionResult)
    assert result.passed is True
    assert result.kind == "window"


def test_assert_window_absent_raises(monkeypatch):
    _patch_windows(monkeypatch, ["Calculator"])
    with pytest.raises(AutoControlAssertionException):
        assert_window("Notepad", exists=True)


def test_assert_window_no_raise_returns_failed(monkeypatch):
    _patch_windows(monkeypatch, ["Calculator"])
    result = assert_window("Notepad", exists=True, raise_on_fail=False)
    assert result.passed is False
    assert "Calculator" in result.actual


def test_assert_window_expect_absent(monkeypatch):
    _patch_windows(monkeypatch, ["Calculator"])
    result = assert_window("Notepad", exists=False)
    assert result.passed is True


# === assert_pixel ==========================================================

def _patch_pixel(monkeypatch, color):
    import je_auto_control.wrapper.auto_control_screen as scr
    monkeypatch.setattr(scr, "get_pixel", lambda x, y: color)


def test_assert_pixel_match_within_tolerance(monkeypatch):
    _patch_pixel(monkeypatch, (100, 100, 100))
    result = assert_pixel(0, 0, [102, 98, 100], tolerance=5)
    assert result.passed is True


def test_assert_pixel_mismatch_raises(monkeypatch):
    _patch_pixel(monkeypatch, (0, 0, 0))
    with pytest.raises(AutoControlAssertionException):
        assert_pixel(0, 0, [255, 255, 255], tolerance=0)


def test_assert_pixel_expect_differ(monkeypatch):
    _patch_pixel(monkeypatch, (0, 0, 0))
    result = assert_pixel(0, 0, [255, 255, 255], match=False)
    assert result.passed is True


# === assert_image ==========================================================

def test_assert_image_present(monkeypatch):
    import je_auto_control.wrapper.auto_control_image as img
    monkeypatch.setattr(img, "locate_image_center", lambda p, t: (5, 6))
    result = assert_image("button.png", present=True)
    assert result.passed is True
    assert result.actual["coords"] == [5, 6]


def test_assert_image_absent_raises(monkeypatch):
    import je_auto_control.wrapper.auto_control_image as img
    from je_auto_control.utils.exception.exceptions import (
        ImageNotFoundException,
    )

    def _miss(_p, _t):
        raise ImageNotFoundException("nope")

    monkeypatch.setattr(img, "locate_image_center", _miss)
    with pytest.raises(AutoControlAssertionException):
        assert_image("button.png", present=True)


# === assert_text ===========================================================

def _patch_ocr_text(monkeypatch, text):
    import je_auto_control.utils.ocr.ocr_engine as ocr
    matches = [SimpleNamespace(text=word) for word in text.split()]
    monkeypatch.setattr(
        ocr, "read_text_in_region",
        lambda region=None, lang="eng", min_confidence=60.0: matches,
    )


def test_assert_text_substring_present(monkeypatch):
    _patch_ocr_text(monkeypatch, "Login Successful Welcome")
    result = assert_text("successful", present=True)
    assert result.passed is True


def test_assert_text_absent_raises(monkeypatch):
    _patch_ocr_text(monkeypatch, "Error 404")
    with pytest.raises(AutoControlAssertionException):
        assert_text("Welcome", present=True)


def test_assert_text_regex(monkeypatch):
    import je_auto_control.utils.ocr.ocr_engine as ocr
    _patch_ocr_text(monkeypatch, "Order 12345 placed")
    monkeypatch.setattr(
        ocr, "find_text_regex",
        lambda pattern, lang="eng", region=None, min_confidence=60.0:
        [SimpleNamespace(text="12345")],
    )
    result = assert_text(r"\d{5}", regex=True, present=True)
    assert result.passed is True
