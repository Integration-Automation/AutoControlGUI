"""Phase 9.3: PaddleOCR backend tests.

We don't import the real paddleocr package in CI — it pulls
~150 MB of paddlepaddle wheels. Instead the tests stub the
``_load`` + ``_get_reader`` helpers and verify the wire-level
behaviour of :class:`PaddleOCRBackend`.
"""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from je_auto_control.utils.ocr.backends.base import (
    OCRBackendNotAvailableError,
)
from je_auto_control.utils.ocr.backends.paddleocr_backend import (
    PADDLEOCR_LANG, PaddleOCRBackend, _resolve_lang,
)


def _stub_reader(rows):
    """Return a MagicMock that, when ``.ocr(...)``-ed, replays ``rows``."""
    reader = MagicMock()
    reader.ocr = MagicMock(return_value=[rows])
    return reader


@pytest.fixture(autouse=True)
def _clear_module_state():
    """Make sure each test starts with no cached reader / lazy import."""
    from je_auto_control.utils.ocr.backends import paddleocr_backend
    paddleocr_backend._paddle = None
    paddleocr_backend._readers.clear()
    yield
    paddleocr_backend._paddle = None
    paddleocr_backend._readers.clear()


def test_lang_resolution_covers_common_codes():
    assert _resolve_lang("eng") == "en"
    assert _resolve_lang("chi_sim") == "ch"
    assert _resolve_lang("chi_tra") == "chinese_cht"
    assert _resolve_lang("jpn") == "japan"
    # Unknown codes pass through.
    assert _resolve_lang("xx") == "xx"
    # Empty input falls back to English (sensible default).
    assert _resolve_lang("") == "en"


def test_lang_table_includes_traditional_and_simplified():
    """Distinct codes for traditional vs simplified Chinese."""
    assert PADDLEOCR_LANG["zh-CN"] != PADDLEOCR_LANG["zh-TW"]


def test_available_false_when_paddleocr_missing():
    """Constructor must not raise even when paddleocr isn't installed."""
    from je_auto_control.utils.ocr.backends import paddleocr_backend
    with patch.object(
        paddleocr_backend, "_load",
        side_effect=OCRBackendNotAvailableError("missing dep"),
    ):
        backend = PaddleOCRBackend()
    assert backend.available is False


def test_available_true_when_paddleocr_loads():
    from je_auto_control.utils.ocr.backends import paddleocr_backend
    with patch.object(paddleocr_backend, "_load", return_value=MagicMock()):
        backend = PaddleOCRBackend()
    assert backend.available is True


def test_image_to_matches_returns_textmatches():
    from je_auto_control.utils.ocr.backends import paddleocr_backend
    rows = [
        [[(10, 20), (110, 20), (110, 50), (10, 50)],
         ("Hello", 0.92)],
        [[(0, 100), (80, 100), (80, 130), (0, 130)],
         ("World", 0.31)],
    ]
    with patch.object(paddleocr_backend, "_load",
                      return_value=MagicMock()), \
         patch.object(paddleocr_backend, "_get_reader",
                      return_value=_stub_reader(rows)):
        backend = PaddleOCRBackend()
        backend._available = True
        matches = backend.image_to_matches(
            np.zeros((200, 200, 3), dtype=np.uint8),
            lang="eng", min_confidence=50.0,
        )
    # Hello (0.92 > 0.50) accepted, World (0.31 < 0.50) rejected.
    assert len(matches) == 1
    assert matches[0].text == "Hello"
    assert matches[0].x == 10
    assert matches[0].y == 20
    assert matches[0].width == 100
    assert matches[0].height == 30
    assert 91.0 < matches[0].confidence < 93.0


def test_image_to_matches_handles_empty_result():
    from je_auto_control.utils.ocr.backends import paddleocr_backend
    reader = MagicMock(ocr=MagicMock(return_value=[]))
    with patch.object(paddleocr_backend, "_load",
                      return_value=MagicMock()), \
         patch.object(paddleocr_backend, "_get_reader", return_value=reader):
        backend = PaddleOCRBackend()
        backend._available = True
        out = backend.image_to_matches(
            np.zeros((10, 10, 3), dtype=np.uint8),
            lang="eng", min_confidence=0,
        )
    assert out == []


def test_image_to_matches_skips_malformed_entries():
    """A row missing the (text, conf) tuple should be skipped, not crash."""
    from je_auto_control.utils.ocr.backends import paddleocr_backend
    rows = [
        [None],  # malformed
        [[(0, 0), (10, 0), (10, 10), (0, 10)], ("ok", 0.95)],
    ]
    reader = _stub_reader(rows)
    with patch.object(paddleocr_backend, "_load",
                      return_value=MagicMock()), \
         patch.object(paddleocr_backend, "_get_reader", return_value=reader):
        backend = PaddleOCRBackend()
        backend._available = True
        matches = backend.image_to_matches(
            np.zeros((20, 20, 3), dtype=np.uint8),
            lang="eng", min_confidence=0,
        )
    assert [m.text for m in matches] == ["ok"]


def test_factory_registers_paddleocr():
    """The OCR factory must accept ``paddleocr`` as an explicit name."""
    from je_auto_control.utils.ocr.backends import (
        _build, reset_cache,
    )
    reset_cache()
    # Force the constructor's _load to succeed so available is True.
    from je_auto_control.utils.ocr.backends import paddleocr_backend
    with patch.object(paddleocr_backend, "_load",
                      return_value=MagicMock()):
        backend = _build("paddleocr")
    assert backend.name == "paddleocr"
    reset_cache()
