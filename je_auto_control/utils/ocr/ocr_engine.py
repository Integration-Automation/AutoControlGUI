"""Headless OCR wrapper using ``pytesseract``.

Text search can be restricted to a region to reduce CPU cost. The Tesseract
binary is loaded lazily; if it is missing, a clear ``RuntimeError`` is raised
rather than ``ImportError`` so callers can degrade gracefully.
"""
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Pattern, Sequence, Tuple, Union

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_pytesseract = None
_image_grab = None


def _load_backend():
    """Import pytesseract + PIL.ImageGrab lazily; raise helpful error if missing."""
    global _pytesseract, _image_grab
    if _pytesseract is not None:
        return _pytesseract, _image_grab
    try:
        import pytesseract as pt
        from PIL import ImageGrab
    except ImportError as error:
        raise RuntimeError(
            "OCR requires 'pytesseract' and a Tesseract binary. "
            "Install with: pip install pytesseract"
        ) from error
    _pytesseract = pt
    _image_grab = ImageGrab
    return pt, ImageGrab


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
    """Override the Tesseract executable path (useful on Windows)."""
    pt, _ = _load_backend()
    pt.pytesseract.tesseract_cmd = path


def _grab(region: Optional[Sequence[int]]):
    _, image_grab = _load_backend()
    if region is None:
        return image_grab.grab(all_screens=True), 0, 0
    x, y, w, h = region
    bbox = (int(x), int(y), int(x) + int(w), int(y) + int(h))
    return image_grab.grab(bbox=bbox, all_screens=True), int(x), int(y)


def _parse_matches(data: dict, offset_x: int, offset_y: int,
                   min_confidence: float) -> List[TextMatch]:
    """Convert ``image_to_data`` dict into TextMatch records."""
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
            x=int(data["left"][i]) + offset_x,
            y=int(data["top"][i]) + offset_y,
            width=int(data["width"][i]),
            height=int(data["height"][i]),
            confidence=conf,
        ))
    return matches


def find_text_matches(target: str,
                      lang: str = "eng",
                      region: Optional[Sequence[int]] = None,
                      min_confidence: float = 60.0,
                      case_sensitive: bool = False) -> List[TextMatch]:
    """Return every on-screen match for ``target`` as TextMatch records."""
    pt, _ = _load_backend()
    frame, offset_x, offset_y = _grab(region)
    try:
        data = pt.image_to_data(frame, lang=lang, output_type=pt.Output.DICT)
    except (OSError, RuntimeError) as error:
        raise RuntimeError(
            "Tesseract binary not found. Install it and/or call set_tesseract_cmd()."
        ) from error

    needle = target if case_sensitive else target.lower()
    matches = _parse_matches(data, offset_x, offset_y, min_confidence)
    return [m for m in matches
            if (m.text if case_sensitive else m.text.lower()) == needle
            or needle in (m.text if case_sensitive else m.text.lower())]


def read_text_in_region(region: Optional[Sequence[int]] = None,
                        lang: str = "eng",
                        min_confidence: float = 60.0) -> List[TextMatch]:
    """Return every OCR hit in ``region`` (or whole screen) as TextMatch records."""
    pt, _ = _load_backend()
    frame, offset_x, offset_y = _grab(region)
    try:
        data = pt.image_to_data(frame, lang=lang, output_type=pt.Output.DICT)
    except (OSError, RuntimeError) as error:
        raise RuntimeError(
            "Tesseract binary not found. Install it and/or call set_tesseract_cmd()."
        ) from error
    return _parse_matches(data, offset_x, offset_y, min_confidence)


def find_text_regex(pattern: Union[str, Pattern[str]],
                    lang: str = "eng",
                    region: Optional[Sequence[int]] = None,
                    min_confidence: float = 60.0,
                    flags: int = 0) -> List[TextMatch]:
    """Return every match whose text matches ``pattern`` (regex search)."""
    compiled = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern, flags)
    matches = read_text_in_region(region=region, lang=lang,
                                  min_confidence=min_confidence)
    return [m for m in matches if compiled.search(m.text) is not None]


def locate_text_center(target: str,
                       lang: str = "eng",
                       region: Optional[Sequence[int]] = None,
                       min_confidence: float = 60.0,
                       case_sensitive: bool = False) -> Tuple[int, int]:
    """Return the centre (x, y) of the first match; raise if not found."""
    hits = find_text_matches(target, lang, region, min_confidence, case_sensitive)
    if not hits:
        raise AutoControlActionException(f"OCR: text not found: {target!r}")
    return hits[0].center


def wait_for_text(target: str,
                  lang: str = "eng",
                  region: Optional[Sequence[int]] = None,
                  timeout: float = 10.0,
                  poll: float = 0.5,
                  min_confidence: float = 60.0,
                  case_sensitive: bool = False) -> Tuple[int, int]:
    """Poll until ``target`` appears on screen; raise on timeout."""
    poll = max(0.05, float(poll))
    deadline = time.monotonic() + float(timeout)
    while time.monotonic() < deadline:
        try:
            return locate_text_center(target, lang, region, min_confidence,
                                      case_sensitive)
        except AutoControlActionException:
            time.sleep(poll)
    raise AutoControlActionException(f"OCR: wait_for_text timeout: {target!r}")


def click_text(target: str,
               mouse_keycode: Union[int, str] = "mouse_left",
               lang: str = "eng",
               region: Optional[Sequence[int]] = None,
               min_confidence: float = 60.0,
               case_sensitive: bool = False) -> Tuple[int, int]:
    """Locate ``target`` text and click its centre."""
    # Import here to avoid circular import when executor loads this module.
    from je_auto_control.wrapper.auto_control_mouse import click_mouse, set_mouse_position
    center = locate_text_center(target, lang, region, min_confidence, case_sensitive)
    set_mouse_position(*center)
    click_mouse(mouse_keycode)
    autocontrol_logger.info("click_text %r @ %s", target, center)
    return center
