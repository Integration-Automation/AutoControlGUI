"""Headless OCR wrapper — pluggable backend (tesseract / easyocr).

Backend choice is made by :mod:`je_auto_control.utils.ocr.backends`. The
public API stays single-call: pass ``backend="tesseract"`` or
``backend="easyocr"`` to force one; omit to auto-detect (env var
``$AUTOCONTROL_OCR_BACKEND`` or first installed).

Tesseract remains the legacy default because it's lighter when already
installed; EasyOCR ships its own neural model and is the right pick for
CJK games where tesseract.exe + language packs are a nuisance.
"""
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Pattern, Sequence, Tuple, Union

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.ocr.backends import (
    OCRBackend, OCRBackendNotAvailableError, get_backend,
)


_image_grab = None


def _load_image_grab():
    global _image_grab
    if _image_grab is not None:
        return _image_grab
    try:
        from PIL import ImageGrab
    except ImportError as error:
        raise RuntimeError(
            "OCR requires Pillow for screen capture. Install with: pip install Pillow"
        ) from error
    _image_grab = ImageGrab
    return ImageGrab


@dataclass(frozen=True)
class TextMatch:
    """One OCR hit with absolute screen coordinates."""
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float

    @property
    def center(self) -> Tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


def set_tesseract_cmd(path: str) -> None:
    """Override the Tesseract executable path (useful on Windows).

    Convenience shim that delegates to the tesseract backend instance.
    """
    from je_auto_control.utils.ocr.backends.tesseract_backend import (
        TesseractBackend,
    )
    backend = get_backend("tesseract")
    if isinstance(backend, TesseractBackend):
        backend.set_cmd(path)


def _virtual_screen_origin() -> Tuple[int, int]:
    """Return (x, y) origin of the virtual desktop in screen coordinates.

    On Windows with multiple monitors, the virtual screen can start at
    negative coordinates (e.g. a monitor positioned above or to the left
    of the primary). ``ImageGrab.grab(all_screens=True)`` captures the
    full virtual screen with its top-left at (0, 0) of the captured
    image — meaning image-local coords differ from screen coords by the
    virtual-screen origin. Without compensating, OCR-derived
    coordinates can't be clicked on directly.
    """
    try:
        import ctypes
        user32 = ctypes.windll.user32
        return int(user32.GetSystemMetrics(76)), int(user32.GetSystemMetrics(77))
    except Exception:
        return 0, 0


def _grab(region: Optional[Sequence[int]]):
    image_grab = _load_image_grab()
    if region is None:
        # Full virtual screen capture — origin may be negative on
        # multi-monitor setups, so report it as the coord offset to add
        # to image-local matches.
        vx, vy = _virtual_screen_origin()
        return image_grab.grab(all_screens=True), vx, vy
    x, y, w, h = region
    bbox = (int(x), int(y), int(x) + int(w), int(y) + int(h))
    return image_grab.grab(bbox=bbox, all_screens=True), int(x), int(y)


def _resolve(backend: Optional[Union[str, OCRBackend]]) -> OCRBackend:
    if backend is None or isinstance(backend, str):
        return get_backend(backend)
    return backend


def find_text_matches(target: str,
                      lang: str = "eng",
                      region: Optional[Sequence[int]] = None,
                      min_confidence: float = 60.0,
                      case_sensitive: bool = False,
                      backend: Optional[Union[str, OCRBackend]] = None,
                      ) -> List[TextMatch]:
    """Return every on-screen match for ``target`` as TextMatch records.

    ``backend`` selects the OCR engine: ``"tesseract"``, ``"easyocr"``,
    or an already-built backend instance. ``None`` (default) defers to
    the auto-detection in :func:`backends.get_backend`.
    """
    engine = _resolve(backend)
    frame, offset_x, offset_y = _grab(region)
    matches = engine.image_to_matches(frame, lang, min_confidence)
    # image_to_matches returns image-local coords; translate to absolute.
    shifted = [TextMatch(
        text=m.text, x=m.x + offset_x, y=m.y + offset_y,
        width=m.width, height=m.height, confidence=m.confidence,
    ) for m in matches]

    needle = target if case_sensitive else target.lower()
    return [m for m in shifted
            if (m.text if case_sensitive else m.text.lower()) == needle
            or needle in (m.text if case_sensitive else m.text.lower())]


def read_text_in_region(region: Optional[Sequence[int]] = None,
                        lang: str = "eng",
                        min_confidence: float = 60.0,
                        backend: Optional[Union[str, OCRBackend]] = None,
                        ) -> List[TextMatch]:
    """Return every OCR hit in ``region`` (or whole screen) as TextMatch records."""
    engine = _resolve(backend)
    frame, offset_x, offset_y = _grab(region)
    matches = engine.image_to_matches(frame, lang, min_confidence)
    return [TextMatch(
        text=m.text, x=m.x + offset_x, y=m.y + offset_y,
        width=m.width, height=m.height, confidence=m.confidence,
    ) for m in matches]


def find_text_regex(pattern: Union[str, Pattern[str]],
                    lang: str = "eng",
                    region: Optional[Sequence[int]] = None,
                    min_confidence: float = 60.0,
                    flags: int = 0,
                    backend: Optional[Union[str, OCRBackend]] = None,
                    ) -> List[TextMatch]:
    """Return every match whose text matches ``pattern`` (regex search)."""
    compiled = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern, flags)
    matches = read_text_in_region(region=region, lang=lang,
                                  min_confidence=min_confidence,
                                  backend=backend)
    return [m for m in matches if compiled.search(m.text) is not None]


def locate_text_center(target: str,
                       lang: str = "eng",
                       region: Optional[Sequence[int]] = None,
                       min_confidence: float = 60.0,
                       case_sensitive: bool = False,
                       backend: Optional[Union[str, OCRBackend]] = None,
                       ) -> Tuple[int, int]:
    """Return the centre (x, y) of the first match; raise if not found."""
    hits = find_text_matches(target, lang, region, min_confidence,
                             case_sensitive, backend=backend)
    if not hits:
        raise AutoControlActionException(f"OCR: text not found: {target!r}")
    return hits[0].center


def wait_for_text(target: str,
                  lang: str = "eng",
                  region: Optional[Sequence[int]] = None,
                  timeout: float = 10.0,
                  poll: float = 0.5,
                  min_confidence: float = 60.0,
                  case_sensitive: bool = False,
                  backend: Optional[Union[str, OCRBackend]] = None,
                  ) -> Tuple[int, int]:
    """Poll until ``target`` appears on screen; raise on timeout."""
    poll = max(0.05, float(poll))
    deadline = time.monotonic() + float(timeout)
    while time.monotonic() < deadline:
        try:
            return locate_text_center(target, lang, region, min_confidence,
                                      case_sensitive, backend=backend)
        except AutoControlActionException:
            time.sleep(poll)
    raise AutoControlActionException(f"OCR: wait_for_text timeout: {target!r}")


def click_text(target: str,
               mouse_keycode: Union[int, str] = "mouse_left",
               lang: str = "eng",
               region: Optional[Sequence[int]] = None,
               min_confidence: float = 60.0,
               case_sensitive: bool = False,
               backend: Optional[Union[str, OCRBackend]] = None,
               ) -> Tuple[int, int]:
    """Locate ``target`` text and click its centre."""
    from je_auto_control.wrapper.auto_control_mouse import click_mouse, set_mouse_position
    center = locate_text_center(target, lang, region, min_confidence,
                                case_sensitive, backend=backend)
    set_mouse_position(*center)
    click_mouse(mouse_keycode)
    autocontrol_logger.info("click_text %r @ %s (backend=%s)",
                            target, center, (backend or "auto"))
    return center


__all__ = [
    "TextMatch", "OCRBackendNotAvailableError",
    "set_tesseract_cmd",
    "find_text_matches", "read_text_in_region", "find_text_regex",
    "locate_text_center", "wait_for_text", "click_text",
]
