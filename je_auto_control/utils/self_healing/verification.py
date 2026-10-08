"""Declarative post-click checks for :func:`self_heal_click`.

A Python caller passes ``verify=`` a callable. A JSON action, an MCP call or
the GUI cannot, so ``action_verified`` was always ``None`` for them. A check
written as data fills it::

    {"type": "image_gone"}                              # the clicked template
    {"type": "image_present", "template_path": "dialog.png", "timeout_s": 3}
    {"type": "text_present", "text": "Saved", "screen_region": [0, 0, 800, 200]}

``image_gone`` / ``image_present`` look for a template with the same matcher
the heal locator uses, and ``text_present`` reads the screen with the OCR
engine. The check is polled until it holds or ``timeout_s`` runs out, because
a screen needs a moment to change after a click.

A check that could not run -- the template file is missing, no OCR engine is
installed, the capture failed -- raises :class:`HealVerificationError`. It is
never reported as ``False`` and never as ``True``: "the image is gone" must
not be concluded from "the image could not be looked for".

Imports no ``PySide6``; OpenCV and the OCR engine are imported when a check runs.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple

from je_auto_control.utils.exception.exceptions import (
    AutoControlException, ImageNotFoundException,
)
from je_auto_control.utils.executor.run_control import pause

VERIFY_IMAGE_GONE = "image_gone"
VERIFY_IMAGE_PRESENT = "image_present"
VERIFY_TEXT_PRESENT = "text_present"
VERIFY_TYPES = (VERIFY_IMAGE_GONE, VERIFY_IMAGE_PRESENT, VERIFY_TEXT_PRESENT)

DEFAULT_TIMEOUT_S = 2.0
DEFAULT_POLL_S = 0.2
MAX_TIMEOUT_S = 300.0

_COMMON = frozenset({"type", "screen_region", "timeout_s", "poll_s"})
_OPTIONS = {
    VERIFY_IMAGE_GONE: _COMMON | {"template_path", "detect_threshold"},
    VERIFY_IMAGE_PRESENT: _COMMON | {"template_path", "detect_threshold"},
    VERIFY_TEXT_PRESENT: _COMMON | {"text", "lang", "min_confidence", "case_sensitive"},
}
_PROBE_ERRORS = (AutoControlException, OSError, RuntimeError, ValueError, TypeError,
                 ImportError)

Region = Optional[Tuple[int, int, int, int]]
Probe = Callable[[], bool]


class HealVerificationError(AutoControlException, ValueError):
    """A post-click check is malformed, or could not be carried out."""


def _number(spec: Mapping[str, Any], key: str, default: float, upper: float) -> float:
    value = spec.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HealVerificationError(f"verify.{key} must be a number, got {value!r}")
    if not 0 <= value <= upper:
        raise HealVerificationError(f"verify.{key} must be between 0 and {upper:g}, got {value!r}")
    return float(value)


def _region(value: Any, fallback: Region) -> Region:
    if value is None:
        return fallback
    try:
        x1, y1, x2, y2 = (int(item) for item in value)
    except (TypeError, ValueError) as error:
        raise HealVerificationError(
            f"verify.screen_region must be [x1, y1, x2, y2], got {value!r}") from error
    if x2 <= x1 or y2 <= y1:
        raise HealVerificationError(
            f"verify.screen_region must have x2 > x1 and y2 > y1, got {value!r}")
    return x1, y1, x2, y2


def image_on_screen(template_path: str, detect_threshold: float, region: Region) -> bool:
    """Whether the template is on screen now (inside ``region`` when given).

    Uses the matcher the heal locator uses. Anything other than "found" or
    "not found" raises: an unreadable template is not an absent image.
    """
    from je_auto_control.utils.cv2_utils import template_detection
    box: Optional[Sequence[int]] = None
    if region is not None:
        # The matcher takes (x, y, width, height); a region is two corners.
        box = (region[0], region[1], region[2] - region[0], region[3] - region[1])
    try:
        result = template_detection.find_image(
            template_path, float(detect_threshold), screen_region=box)
    except ImageNotFoundException:
        return False
    return bool(result[0])


def text_on_screen(text: str, region: Region, lang: str = "eng",
                   min_confidence: float = 60.0, case_sensitive: bool = False) -> bool:
    """Whether the OCR engine reads ``text`` on screen now (inside ``region``)."""
    from je_auto_control.utils.ocr.ocr_engine import find_text_matches
    return bool(find_text_matches(
        text, lang=lang, region=None if region is None else list(region),
        min_confidence=float(min_confidence), case_sensitive=bool(case_sensitive)))


def _image_probe(spec: Mapping[str, Any], kind: str, template_path: Optional[str],
                 region: Region) -> Probe:
    template = spec.get("template_path", template_path)
    if not isinstance(template, str) or not template:
        raise HealVerificationError(
            f"verify type {kind!r} needs template_path (the click had no template to reuse)")
    threshold = _number(spec, "detect_threshold", 0.9, 1.0)
    wanted = kind == VERIFY_IMAGE_PRESENT
    return lambda: image_on_screen(template, threshold, region) is wanted


def _text_probe(spec: Mapping[str, Any], region: Region) -> Probe:
    text = spec.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HealVerificationError("verify type 'text_present' needs a non-empty text")
    lang = spec.get("lang", "eng")
    if not isinstance(lang, str) or not lang:
        raise HealVerificationError(f"verify.lang must be a language code, got {lang!r}")
    confidence = _number(spec, "min_confidence", 60.0, 100.0)
    case_sensitive = bool(spec.get("case_sensitive", False))
    return lambda: text_on_screen(text, region, lang, confidence, case_sensitive)


def _poll(probe: Probe, kind: str, timeout_s: float, poll_s: float,
          clock: Callable[[], float], sleep: Callable[[float], None]) -> bool:
    """Run ``probe`` until it holds or ``timeout_s`` has passed; at least once."""
    deadline = clock() + timeout_s
    while True:
        try:
            if probe():
                return True
        except _PROBE_ERRORS as error:
            raise HealVerificationError(
                f"verify type {kind!r} could not be carried out: {error!r}") from error
        remaining = deadline - clock()
        if remaining <= 0:
            return False
        sleep(min(poll_s, remaining) if poll_s > 0 else 0.0)


def build_verifier(spec: Mapping[str, Any], *, template_path: Optional[str] = None,
                   screen_region: Region = None,
                   clock: Callable[[], float] = time.monotonic,
                   sleep: Callable[[float], None] = pause,
                   ) -> Callable[[Any], bool]:
    """Turn a ``verify`` object into the check :func:`self_heal_click` calls.

    ``template_path`` and ``screen_region`` are the click's own and are what
    the check uses when the spec names neither. The spec is validated here,
    before anything is clicked; ``clock`` and ``sleep`` exist for tests.
    """
    if not isinstance(spec, Mapping):
        raise HealVerificationError(f"verify must be an object, got {spec!r}")
    named = spec.get("type")
    allowed = _OPTIONS.get(named) if isinstance(named, str) else None
    if allowed is None:
        raise HealVerificationError(
            f"unknown verify type {named!r}; expected one of {list(VERIFY_TYPES)}")
    kind = str(named)
    unknown = sorted(set(spec) - allowed)
    if unknown:
        raise HealVerificationError(f"unknown verify option(s) {unknown} for type {kind!r}")
    region = _region(spec.get("screen_region"), screen_region)
    timeout_s = _number(spec, "timeout_s", DEFAULT_TIMEOUT_S, MAX_TIMEOUT_S)
    poll_s = _number(spec, "poll_s", DEFAULT_POLL_S, MAX_TIMEOUT_S)
    probe = (_text_probe(spec, region) if kind == VERIFY_TEXT_PRESENT
             else _image_probe(spec, kind, template_path, region))

    def verify(_outcome: Any) -> bool:
        return _poll(probe, kind, timeout_s, poll_s, clock, sleep)

    return verify


__all__ = [
    "DEFAULT_POLL_S", "DEFAULT_TIMEOUT_S", "HealVerificationError", "VERIFY_TYPES",
    "build_verifier", "image_on_screen", "text_on_screen",
]
