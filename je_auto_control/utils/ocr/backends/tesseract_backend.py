"""Tesseract OCR backend (preserves the original ``ocr_engine`` behaviour)."""
from __future__ import annotations

from typing import List

from je_auto_control.utils.ocr.backends.base import OCRBackendNotAvailableError


_pytesseract = None


def _load():
    global _pytesseract
    if _pytesseract is not None:
        return _pytesseract
    try:
        import pytesseract as pt
    except ImportError as error:
        raise OCRBackendNotAvailableError(
            "tesseract backend needs 'pytesseract' and a Tesseract binary. "
            "Install with: pip install pytesseract  (and ensure tesseract.exe "
            "is on PATH, or call set_tesseract_cmd())"
        ) from error
    _pytesseract = pt
    return pt


class TesseractBackend:
    """Backend wrapping :mod:`pytesseract` for traditional OCR."""

    name = "tesseract"

    def __init__(self) -> None:
        try:
            _load()
            self._available = True
        except OCRBackendNotAvailableError:
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def set_cmd(self, path: str) -> None:
        """Override the Tesseract executable location."""
        pt = _load()
        pt.pytesseract.tesseract_cmd = path

    def image_to_matches(self, image, lang: str,
                         min_confidence: float) -> List:
        # Import inside to avoid circular import at module load.
        from je_auto_control.utils.ocr.ocr_engine import TextMatch

        pt = _load()
        try:
            data = pt.image_to_data(image, lang=lang, output_type=pt.Output.DICT)
        except (OSError, RuntimeError) as error:
            raise OCRBackendNotAvailableError(
                "Tesseract binary not found. Install it and/or call "
                "set_tesseract_cmd()."
            ) from error

        matches: List[TextMatch] = []
        count = len(data.get("text", []))
        for i in range(count):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            if conf < min_confidence:
                continue
            matches.append(TextMatch(
                text=text,
                x=int(data["left"][i]),
                y=int(data["top"][i]),
                width=int(data["width"][i]),
                height=int(data["height"][i]),
                confidence=conf,
            ))
        return matches


# Tesseract → EasyOCR/etc. language-code translation. Tesseract uses the
# legacy 3-letter codes; other engines tend to use 2-letter or
# region-suffixed variants. Backends translate at the edge.
TESSERACT_LANG = {
    "eng": "eng", "chi_tra": "chi_tra", "chi_sim": "chi_sim",
    "jpn": "jpn", "kor": "kor",
}
