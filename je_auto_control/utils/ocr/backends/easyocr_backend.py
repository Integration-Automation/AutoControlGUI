"""EasyOCR backend — deep-learning OCR with built-in CJK support.

Unlike Tesseract this backend needs no external binary; ``pip install
easyocr`` brings everything (PyTorch + a small CRNN model that is
downloaded on first use, ~64 MB per language). For Chinese / Japanese
games this is the simpler install path.
"""
from __future__ import annotations

from threading import Lock
from typing import Any, Dict, List

from je_auto_control.utils.ocr.backends.base import OCRBackendNotAvailableError


_easyocr = None
_readers: Dict[str, Any] = {}
_reader_lock = Lock()


def _load():
    global _easyocr
    if _easyocr is not None:
        return _easyocr
    try:
        import easyocr  # noqa: F401
    except ImportError as error:
        raise OCRBackendNotAvailableError(
            "easyocr backend needs the 'easyocr' package. "
            "Install with: pip install easyocr  (first run downloads a "
            "~64 MB model per language)"
        ) from error
    _easyocr = easyocr
    return easyocr


# Map AutoControl's canonical (Tesseract-style) lang codes to EasyOCR's
# code list. EasyOCR groups Chinese Traditional ('ch_tra') and Simplified
# ('ch_sim') separately and bundles Latin alphabets together.
EASYOCR_LANG = {
    "eng": ["en"], "en": ["en"],
    "chi_tra": ["ch_tra"], "ch_tra": ["ch_tra"], "zh-TW": ["ch_tra"],
    "chi_sim": ["ch_sim"], "ch_sim": ["ch_sim"], "zh-CN": ["ch_sim"],
    "jpn": ["ja"], "ja": ["ja"],
    "kor": ["ko"], "ko": ["ko"],
}


def _resolve_langs(lang: str) -> List[str]:
    """Translate a canonical lang code into EasyOCR's list-of-codes form.

    EasyOCR rejects mixing certain language groups (e.g. ch_tra + ch_sim
    must be loaded as separate Readers); we keep it to one code at a
    time and the caller layer reuses a cached Reader per code.
    """
    if lang in EASYOCR_LANG:
        return EASYOCR_LANG[lang]
    # Pass-through for codes EasyOCR already understands (best-effort).
    return [lang]


def _get_reader(lang: str):
    """Lazily build (and cache) the EasyOCR Reader for ``lang``."""
    codes = _resolve_langs(lang)
    key = ",".join(codes)
    with _reader_lock:
        reader = _readers.get(key)
        if reader is not None:
            return reader
        easyocr = _load()
        reader = easyocr.Reader(codes, gpu=False, verbose=False)
        _readers[key] = reader
        return reader


class EasyOCRBackend:
    """Backend wrapping :mod:`easyocr` for CJK-friendly OCR."""

    name = "easyocr"

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
        # Import inside to avoid circular import at module load.
        from je_auto_control.utils.ocr.ocr_engine import TextMatch
        import numpy as np

        reader = _get_reader(lang)
        # EasyOCR reads numpy arrays directly. Accept either PIL or ndarray.
        frame = image if isinstance(image, np.ndarray) else np.array(image)

        # readtext returns [(bbox, text, confidence), ...] where bbox is
        # four (x,y) corners in clockwise order from top-left.
        # Confidence is in 0-1.
        threshold = max(0.0, float(min_confidence) / 100.0)
        results = reader.readtext(frame, detail=1, paragraph=False)

        matches: List[TextMatch] = []
        for bbox, text, conf in results:
            if conf < threshold:
                continue
            xs = [int(p[0]) for p in bbox]
            ys = [int(p[1]) for p in bbox]
            x = min(xs)
            y = min(ys)
            width = max(xs) - x
            height = max(ys) - y
            matches.append(TextMatch(
                text=text.strip(),
                x=x, y=y, width=width, height=height,
                confidence=float(conf) * 100.0,  # back to the 0–100 scale
            ))
        return [m for m in matches if m.text]
