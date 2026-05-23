"""PaddleOCR backend — Baidu's deep-learning OCR with best-in-class CJK.

PaddleOCR's PP-OCR models are still the strongest open-source option
for Chinese and Japanese text. Unlike EasyOCR it ships separate
detector + recognizer models so first-call latency is higher but
per-frame throughput on a CPU is comparable.

Install with ``pip install paddlepaddle paddleocr`` (the
``paddlepaddle`` wheel is large — ~150 MB — and pulls platform-
specific BLAS, so most users will only want this backend on a CJK-
heavy machine).
"""
from __future__ import annotations

from threading import Lock
from typing import Dict, List

from je_auto_control.utils.ocr.backends.base import (
    OCRBackendNotAvailableError,
)


_paddle = None
_readers: Dict[str, object] = {}
_reader_lock = Lock()


def _load():
    """Lazily import paddleocr. Raises a clear error if missing."""
    global _paddle
    if _paddle is not None:
        return _paddle
    try:
        from paddleocr import PaddleOCR  # noqa: F401
    except ImportError as error:
        raise OCRBackendNotAvailableError(
            "paddleocr backend needs both 'paddlepaddle' and "
            "'paddleocr'. Install with: pip install paddlepaddle paddleocr "
            "(first run downloads ~50 MB of detector + recognizer models).",
        ) from error
    _paddle = PaddleOCR
    return PaddleOCR


# Map AutoControl's canonical lang codes to PaddleOCR's.
PADDLEOCR_LANG = {
    "eng": "en", "en": "en",
    "chi_sim": "ch", "ch_sim": "ch", "zh-CN": "ch", "ch": "ch",
    "chi_tra": "chinese_cht", "ch_tra": "chinese_cht", "zh-TW": "chinese_cht",
    "jpn": "japan", "ja": "japan", "japan": "japan",
    "kor": "korean", "ko": "korean", "korean": "korean",
    "fra": "fr", "fr": "fr",
    "ger": "german", "de": "german",
}


def _resolve_lang(lang: str) -> str:
    """Translate to PaddleOCR's lang code; default to English."""
    return PADDLEOCR_LANG.get(lang, lang or "en")


def _get_reader(lang: str):
    """Build + cache one PaddleOCR Reader per language."""
    code = _resolve_lang(lang)
    with _reader_lock:
        reader = _readers.get(code)
        if reader is not None:
            return reader
        # PaddleOCR is the upstream class name; keep the case to match
        # the library's public API.
        PaddleOCR = _load()  # NOSONAR python:S117  # reason: third-party class name
        # ``show_log=False`` silences the per-call banner; use_gpu=False
        # keeps the default CPU-only install path working.
        reader = PaddleOCR(use_angle_cls=True, lang=code, show_log=False)
        _readers[code] = reader
        return reader


def _entry_to_match(entry, threshold: float):
    """Convert one PaddleOCR row into a ``TextMatch`` or ``None`` to skip."""
    from je_auto_control.utils.ocr.ocr_engine import TextMatch
    if not entry or len(entry) < 2:
        return None
    box, text_conf = entry[0], entry[1]
    if not isinstance(text_conf, (list, tuple)) or len(text_conf) < 2:
        return None
    text_raw, conf_raw = text_conf[0], text_conf[1]
    conf = float(conf_raw)
    text = str(text_raw).strip()
    if conf < threshold or not text:
        return None
    xs = [int(p[0]) for p in box]
    ys = [int(p[1]) for p in box]
    x, y = min(xs), min(ys)
    return TextMatch(
        text=text,
        x=x, y=y,
        width=max(xs) - x, height=max(ys) - y,
        confidence=conf * 100.0,
    )


class PaddleOCRBackend:
    """Backend wrapping :mod:`paddleocr` for best-quality CJK OCR."""

    name = "paddleocr"

    def __init__(self) -> None:
        try:
            _load()
            self._available = True
        except OCRBackendNotAvailableError:
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def image_to_matches(self, image, lang: str,
                         min_confidence: float) -> List:
        import numpy as np

        reader = _get_reader(lang)
        frame = image if isinstance(image, np.ndarray) else np.array(image)
        threshold = max(0.0, float(min_confidence) / 100.0)
        # PaddleOCR returns nested lists: [[ [box, (text, conf)], ... ]].
        result = reader.ocr(frame, cls=True)
        if not result:
            return []
        page = result[0] if isinstance(result[0], list) else result
        matches = []
        for entry in page or []:
            converted = _entry_to_match(entry, threshold)
            if converted is not None:
                matches.append(converted)
        return matches


__all__ = ["PaddleOCRBackend", "PADDLEOCR_LANG"]
