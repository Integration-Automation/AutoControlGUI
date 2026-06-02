"""Assertion DSL — verify the screen state, not just drive it.

A naive automation script only *performs* actions; it never checks that
they produced the expected result. These helpers close that gap: each
``assert_*`` function observes the current screen / window state, decides
whether it matches the caller's expectation, and (by default) raises
:class:`AutoControlAssertionException` on mismatch so a script — or a
``pytest`` test, or a scheduled run — fails loudly at the point of the
broken assumption.

Every function returns an :class:`AssertionResult` describing what was
expected versus observed, and can optionally save a screenshot of the
failing screen for the run-history / audit trail.

The module is GUI-free: it depends only on the headless wrapper / OCR
layer, so ``import je_auto_control as ac; ac.assert_text(...)`` works
without instantiating Qt.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.exception.exceptions import (
    AutoControlAssertionException,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_DEFAULT_THRESHOLD = 0.9
_DEFAULT_MIN_CONFIDENCE = 60.0


@dataclass(frozen=True)
class AssertionResult:
    """Outcome of a single assertion check."""

    kind: str
    passed: bool
    message: str
    expected: Any = None
    actual: Any = None
    screenshot_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _capture_failure_screenshot(kind: str) -> Optional[str]:
    """Best-effort screenshot of the failing screen; never raises."""
    try:
        from je_auto_control.wrapper.auto_control_screen import screenshot
    except ImportError as error:
        autocontrol_logger.warning("assert capture import failed: %r", error)
        return None
    target = Path.home() / ".je_auto_control" / "assertions"
    try:
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"assert_{kind}_{int(time.time() * 1000)}.png"
        screenshot(file_path=str(path))
        return str(path)
    except (OSError, RuntimeError, ValueError) as error:
        autocontrol_logger.warning("assert screenshot failed: %r", error)
        return None


def _finalize(kind: str, passed: bool, message: str,
              expected: Any, actual: Any,
              raise_on_fail: bool, capture_on_fail: bool) -> AssertionResult:
    """Build the result, capturing + raising on failure as requested."""
    screenshot_path = (
        _capture_failure_screenshot(kind)
        if (not passed and capture_on_fail) else None
    )
    result = AssertionResult(
        kind=kind, passed=passed, message=message,
        expected=expected, actual=actual, screenshot_path=screenshot_path,
    )
    if not passed:
        autocontrol_logger.info("assertion failed: %s", message)
        if raise_on_fail:
            raise AutoControlAssertionException(message)
    return result


def _region_text(region: Optional[Sequence[int]], lang: str,
                 min_confidence: float) -> str:
    """Return the concatenated OCR text inside ``region`` (or whole screen)."""
    from je_auto_control.utils.ocr.ocr_engine import read_text_in_region
    matches = read_text_in_region(
        region=region, lang=lang, min_confidence=min_confidence,
    )
    return " ".join(match.text for match in matches)


def assert_text(text: str,
                region: Optional[Sequence[int]] = None,
                lang: str = "eng",
                regex: bool = False,
                present: bool = True,
                ignore_case: bool = True,
                min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
                raise_on_fail: bool = True,
                capture_on_fail: bool = False) -> AssertionResult:
    """Assert that ``text`` is (or is not) visible on screen via OCR.

    :param regex: treat ``text`` as a regular expression instead of a
        literal substring.
    :param present: when True (default) the text must be found; when
        False the assertion passes only when the text is absent.
    """
    if regex:
        from je_auto_control.utils.ocr.ocr_engine import find_text_regex
        found = bool(find_text_regex(
            text, lang=lang, region=region, min_confidence=min_confidence,
        ))
        observed = _region_text(region, lang, min_confidence)
    else:
        observed = _region_text(region, lang, min_confidence)
        haystack = observed.lower() if ignore_case else observed
        needle = text.lower() if ignore_case else text
        found = needle in haystack
    passed = (found == present)
    state = "present" if present else "absent"
    message = (
        f"assert_text passed: {text!r} is {state}"
        if passed else
        f"assert_text failed: expected {text!r} to be {state}; "
        f"OCR saw {observed!r}"
    )
    return _finalize(
        "text", passed, message,
        expected={"text": text, "present": present, "regex": regex},
        actual=observed, raise_on_fail=raise_on_fail,
        capture_on_fail=capture_on_fail,
    )


def assert_image(template_path: str,
                 threshold: float = _DEFAULT_THRESHOLD,
                 present: bool = True,
                 raise_on_fail: bool = True,
                 capture_on_fail: bool = False) -> AssertionResult:
    """Assert that the template image is (or is not) on screen."""
    from je_auto_control.utils.exception.exceptions import (
        ImageNotFoundException,
    )
    from je_auto_control.wrapper.auto_control_image import locate_image_center
    coords: Optional[Any] = None
    try:
        coords = locate_image_center(template_path, threshold)
        found = True
    except (ImageNotFoundException, OSError, RuntimeError, ValueError,
            TypeError):
        found = False
    passed = (found == present)
    state = "present" if present else "absent"
    message = (
        f"assert_image passed: {template_path!r} is {state}"
        if passed else
        f"assert_image failed: expected {template_path!r} to be {state} "
        f"(threshold={threshold})"
    )
    return _finalize(
        "image", passed, message,
        expected={"template_path": template_path, "present": present,
                  "threshold": threshold},
        actual={"found": found, "coords": list(coords) if coords else None},
        raise_on_fail=raise_on_fail, capture_on_fail=capture_on_fail,
    )


def _pixel_matches(x: int, y: int, rgb: Sequence[int], tolerance: int) -> bool:
    """Return True when the live pixel at (x, y) matches rgb within tolerance."""
    from je_auto_control.wrapper.auto_control_screen import get_pixel
    color = get_pixel(x, y)
    if color is None or len(color) < 3 or len(rgb) < 3:
        return False
    return all(abs(int(color[i]) - int(rgb[i])) <= tolerance for i in range(3))


def assert_pixel(x: int, y: int, rgb: Sequence[int],
                 tolerance: int = 0,
                 match: bool = True,
                 raise_on_fail: bool = True,
                 capture_on_fail: bool = False) -> AssertionResult:
    """Assert the pixel at ``(x, y)`` matches (or differs from) ``rgb``."""
    from je_auto_control.wrapper.auto_control_screen import get_pixel
    actual_color = get_pixel(int(x), int(y))
    matched = _pixel_matches(int(x), int(y), rgb, int(tolerance))
    passed = (matched == match)
    verb = "match" if match else "differ from"
    message = (
        f"assert_pixel passed: ({x},{y}) {verb} {list(rgb)}"
        if passed else
        f"assert_pixel failed: expected ({x},{y})={actual_color} to "
        f"{verb} {list(rgb)} (tolerance={tolerance})"
    )
    return _finalize(
        "pixel", passed, message,
        expected={"x": x, "y": y, "rgb": list(rgb), "match": match,
                  "tolerance": tolerance},
        actual=list(actual_color) if actual_color else None,
        raise_on_fail=raise_on_fail, capture_on_fail=capture_on_fail,
    )


def _window_titles() -> List[str]:
    """Return the titles of every visible top-level window."""
    from je_auto_control.wrapper.auto_control_window import list_windows
    return [title for _, title in list_windows()]


def assert_window(title: str,
                  exists: bool = True,
                  ignore_case: bool = True,
                  raise_on_fail: bool = True,
                  capture_on_fail: bool = False) -> AssertionResult:
    """Assert a window whose title contains ``title`` does (not) exist."""
    titles = _window_titles()
    needle = title.lower() if ignore_case else title
    found = any(
        (t.lower() if ignore_case else t).find(needle) >= 0 for t in titles
    )
    passed = (found == exists)
    state = "exist" if exists else "not exist"
    message = (
        f"assert_window passed: a window matching {title!r} does {state}"
        if passed else
        f"assert_window failed: expected a window matching {title!r} to "
        f"{state}; open titles={titles}"
    )
    return _finalize(
        "window", passed, message,
        expected={"title": title, "exists": exists},
        actual=titles, raise_on_fail=raise_on_fail,
        capture_on_fail=capture_on_fail,
    )
