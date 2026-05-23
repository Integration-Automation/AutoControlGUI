"""OCR backend factory — pick tesseract or easyocr based on env / availability."""
from __future__ import annotations

import os
from typing import Optional

from je_auto_control.utils.ocr.backends.base import (
    OCRBackend, OCRBackendNotAvailableError,
)

_cached: dict = {}


def get_backend(name: Optional[str] = None) -> OCRBackend:
    """Return a ready OCR backend.

    Selection order:

    1. Explicit ``name`` argument (``"tesseract"`` / ``"easyocr"``).
    2. ``$AUTOCONTROL_OCR_BACKEND`` environment variable.
    3. Auto-detect — try tesseract first (legacy default), fall back to
       easyocr.

    Raises :class:`OCRBackendNotAvailableError` only when *all* candidates
    fail; this lets ``find_text_matches`` degrade gracefully if the user
    installs either backend.
    """
    if name is None:
        name = os.environ.get("AUTOCONTROL_OCR_BACKEND", "").strip().lower() or None

    if name:
        return _build(name)

    # Auto-detect.
    errors: list[str] = []
    for candidate in ("tesseract", "easyocr", "paddleocr"):
        try:
            backend = _build(candidate)
            if backend.available:
                return backend
            errors.append(f"{candidate}: not available")
        except OCRBackendNotAvailableError as error:
            errors.append(f"{candidate}: {error}")
    raise OCRBackendNotAvailableError(
        "no OCR backend ready. Tried tesseract, easyocr, and paddleocr:\n  "
        + "\n  ".join(errors),
    )


def _build(name: str) -> OCRBackend:
    cached = _cached.get(name)
    if cached is not None:
        return cached
    if name == "tesseract":
        from je_auto_control.utils.ocr.backends.tesseract_backend import (
            TesseractBackend,
        )
        backend = TesseractBackend()
    elif name == "easyocr":
        from je_auto_control.utils.ocr.backends.easyocr_backend import (
            EasyOCRBackend,
        )
        backend = EasyOCRBackend()
    elif name == "paddleocr":
        from je_auto_control.utils.ocr.backends.paddleocr_backend import (
            PaddleOCRBackend,
        )
        backend = PaddleOCRBackend()
    else:
        raise OCRBackendNotAvailableError(f"unknown OCR backend: {name!r}")
    _cached[name] = backend
    return backend


def reset_cache() -> None:
    """Force ``get_backend()`` to re-detect on its next call."""
    _cached.clear()


__all__ = [
    "OCRBackend", "OCRBackendNotAvailableError",
    "get_backend", "reset_cache",
]
