"""OCR backend protocol shared by tesseract / easyocr implementations.

Each backend takes a PIL image plus a language code and returns a list of
:class:`~je_auto_control.utils.ocr.ocr_engine.TextMatch` records expressed
in *image-local* coordinates (the engine adds the screen-region offset
afterwards). The protocol is intentionally narrow so we can grow
backends without touching the public ``find_text_matches`` API.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover
    from je_auto_control.utils.ocr.ocr_engine import TextMatch


class OCRBackendNotAvailableError(RuntimeError):
    """Raised when the requested OCR backend can't be loaded."""


@runtime_checkable
class OCRBackend(Protocol):
    """Headless OCR backend producing ``TextMatch`` records."""

    name: str

    @property
    def available(self) -> bool:
        """True if the backend's dependencies are importable."""

    def image_to_matches(self,
                         image,
                         lang: str,
                         min_confidence: float) -> "List[TextMatch]":
        """Extract text from ``image`` (PIL.Image) at confidence ≥ threshold.

        Coordinates are image-local (top-left = 0,0). Callers add the
        screen-region offset to make them absolute.
        """
