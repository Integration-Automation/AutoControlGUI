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


def assert_clipboard(text: str,
                     mode: str = "equals",
                     ignore_case: bool = False,
                     present: bool = True,
                     raise_on_fail: bool = True,
                     capture_on_fail: bool = False) -> AssertionResult:
    """Assert the system clipboard text matches ``text``.

    :param mode: comparison strategy — ``"equals"`` (exact), ``"contains"``
        (substring), or ``"regex"`` (full-text regular-expression search).
    :param present: when True the comparison must hold; when False the
        assertion passes only when the comparison does **not** hold (e.g.
        verify a secret was cleared from the clipboard).
    """
    from je_auto_control.utils.clipboard.clipboard import get_clipboard
    observed = get_clipboard() or ""
    matched = _clipboard_matches(observed, text, mode, ignore_case)
    passed = (matched == present)
    state = "match" if present else "not match"
    message = (
        f"assert_clipboard passed: clipboard does {state} ({mode}) {text!r}"
        if passed else
        f"assert_clipboard failed: expected clipboard to {state} ({mode}) "
        f"{text!r}; clipboard held {observed!r}"
    )
    return _finalize(
        "clipboard", passed, message,
        expected={"text": text, "mode": mode, "present": present},
        actual=observed, raise_on_fail=raise_on_fail,
        capture_on_fail=capture_on_fail,
    )


def _clipboard_matches(observed: str, text: str,
                       mode: str, ignore_case: bool) -> bool:
    """Return True when ``observed`` satisfies ``text`` under ``mode``."""
    if mode == "regex":
        import re
        flags = re.IGNORECASE if ignore_case else 0
        return re.search(text, observed, flags) is not None
    left = observed.lower() if ignore_case else observed
    right = text.lower() if ignore_case else text
    if mode == "contains":
        return right in left
    if mode == "equals":
        return left == right
    raise AutoControlAssertionException(
        f"assert_clipboard: unknown mode {mode!r} "
        "(expected 'equals', 'contains', or 'regex')"
    )


def _evaluate_file(path: Path, exists: bool, contains: Optional[str],
                   sha256: Optional[str], min_size: Optional[int]
                   ) -> tuple[bool, str, Dict[str, Any]]:
    """Return (passed, detail, actual) for a file-state assertion."""
    present = path.is_file()
    actual: Dict[str, Any] = {"exists": present}
    if not present:
        return (not exists, "file does not exist", actual)
    if not exists:
        return (False, "file exists but expected absent", actual)
    data = path.read_bytes()
    actual["size"] = len(data)
    if min_size is not None and len(data) < int(min_size):
        return (False, f"size {len(data)} < min_size {min_size}", actual)
    if sha256 is not None:
        import hashlib
        digest = hashlib.sha256(data).hexdigest()
        actual["sha256"] = digest
        if digest.lower() != sha256.lower():
            return (False, f"sha256 {digest} != expected {sha256}", actual)
    if contains is not None:
        text = data.decode("utf-8", errors="replace")
        if contains not in text:
            return (False, f"text {contains!r} not found in file", actual)
    return (True, "file matches all checks", actual)


def assert_file(path: str,
                exists: bool = True,
                contains: Optional[str] = None,
                sha256: Optional[str] = None,
                min_size: Optional[int] = None,
                raise_on_fail: bool = True) -> AssertionResult:
    """Assert a file's state — existence, substring, SHA-256, or minimum size.

    Verifies the outcome of a download / export / log write without a GUI.
    The path is resolved with :func:`os.path.realpath` before any I/O so
    relative and symlinked inputs are normalised. When ``exists`` is False
    the assertion passes only when the file is absent (every other check is
    skipped). Extra checks (``contains`` / ``sha256`` / ``min_size``) are
    evaluated only when the file is present and expected to exist.
    """
    import os
    resolved = Path(os.path.realpath(path))
    passed, detail, actual = _evaluate_file(
        resolved, exists, contains, sha256, min_size,
    )
    message = (
        f"assert_file passed: {path!r} — {detail}"
        if passed else
        f"assert_file failed: {path!r} — {detail}"
    )
    return _finalize(
        "file", passed, message,
        expected={"path": path, "exists": exists, "contains": contains,
                  "sha256": sha256, "min_size": min_size},
        actual=actual, raise_on_fail=raise_on_fail, capture_on_fail=False,
    )


def _http_probe(url: str, timeout: float, method: str
                ) -> tuple[int, str]:
    """Issue an HTTP(S) request, returning (status_code, body_text)."""
    import urllib.error
    import urllib.request
    scheme = url.split("://", 1)[0].lower() if "://" in url else ""
    if scheme not in ("http", "https"):
        raise AutoControlAssertionException(
            f"assert_http: only http/https URLs allowed, got {url!r}"
        )
    request = urllib.request.Request(url, method=method.upper())
    try:
        with urllib.request.urlopen(  # nosec B310  # reason: scheme allow-listed
                request, timeout=float(timeout)) as response:
            body = response.read().decode("utf-8", errors="replace")
            return int(response.status), body
    except urllib.error.HTTPError as error:
        body = ""
        try:
            body = error.read().decode("utf-8", errors="replace")
        except (OSError, ValueError):
            body = ""
        return int(error.code), body


def assert_http(url: str,
                status: int = 200,
                contains: Optional[str] = None,
                timeout: float = 10.0,
                method: str = "GET",
                raise_on_fail: bool = True) -> AssertionResult:
    """Assert an HTTP(S) endpoint returns ``status`` (and optional body text).

    Drives backend health / readiness checks from an automation flow — pair
    it with :func:`assert_eventually` to poll an endpoint until it comes up.
    Only ``http``/``https`` URLs are accepted; the request always uses an
    explicit ``timeout``. A connection failure (DNS / refused / timeout)
    counts as a failed assertion rather than crashing the script.
    """
    import urllib.error
    actual: Dict[str, Any] = {}
    try:
        code, body = _http_probe(url, timeout, method)
    except urllib.error.URLError as error:
        passed = False
        actual = {"error": str(error.reason)}
        message = f"assert_http failed: {url!r} unreachable — {error.reason}"
        return _finalize(
            "http", passed, message,
            expected={"url": url, "status": status, "contains": contains},
            actual=actual, raise_on_fail=raise_on_fail, capture_on_fail=False,
        )
    actual = {"status": code}
    status_ok = (code == int(status))
    body_ok = (contains is None) or (contains in body)
    passed = status_ok and body_ok
    if passed:
        message = f"assert_http passed: {url!r} returned {code}"
    elif not status_ok:
        message = f"assert_http failed: {url!r} returned {code}, expected {status}"
    else:
        message = f"assert_http failed: {url!r} body missing {contains!r}"
    return _finalize(
        "http", passed, message,
        expected={"url": url, "status": status, "contains": contains},
        actual=actual, raise_on_fail=raise_on_fail, capture_on_fail=False,
    )


def _running_process_names(name_contains: str) -> List[str]:
    """Return the names of running processes matching ``name_contains``."""
    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError as error:
        raise AutoControlAssertionException(
            "assert_process requires psutil — pip install psutil"
        ) from error
    needle = name_contains.lower()
    names: List[str] = []
    for proc in psutil.process_iter(["name"]):
        name = (proc.info or {}).get("name") or ""
        if needle in name.lower():
            names.append(name)
    return names


def assert_process(name: str,
                   running: bool = True,
                   raise_on_fail: bool = True,
                   capture_on_fail: bool = False) -> AssertionResult:
    """Assert a process whose name contains ``name`` is (not) running.

    Useful for confirming a launched application actually started, or that
    a killed/closed process really exited. Requires ``psutil``.

    :param running: when True a matching process must exist; when False the
        assertion passes only when no matching process is running.
    """
    matches = _running_process_names(name)
    found = bool(matches)
    passed = (found == running)
    state = "running" if running else "not running"
    message = (
        f"assert_process passed: a process matching {name!r} is {state}"
        if passed else
        f"assert_process failed: expected a process matching {name!r} to "
        f"be {state}; matches={matches}"
    )
    return _finalize(
        "process", passed, message,
        expected={"name": name, "running": running},
        actual=matches, raise_on_fail=raise_on_fail,
        capture_on_fail=capture_on_fail,
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


def assert_by_description(description: str,
                          present: bool = True,
                          screen_region: Optional[Sequence[int]] = None,
                          model: Optional[str] = None,
                          backend: Any = None,
                          raise_on_fail: bool = True,
                          capture_on_fail: bool = False) -> AssertionResult:
    """Assert the screen does (or does not) match a natural-language description.

    The semantic complement to :func:`assert_text` / :func:`assert_image`:
    rather than exact OCR text or a pixel template, ask a vision-language
    model "is ``description`` true of the current screen?". Requires a
    configured VLM backend (``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``);
    raises :class:`VLMNotAvailableError` otherwise.
    """
    from je_auto_control.utils.vision.vlm_api import verify_description
    region = list(screen_region) if screen_region is not None else None
    matched = verify_description(
        description, screen_region=region, model=model, backend=backend,
    )
    passed = (matched == present)
    state = "shows" if present else "does not show"
    message = (
        f"assert_by_description passed: screen {state} {description!r}"
        if passed else
        f"assert_by_description failed: expected screen to {state} "
        f"{description!r} (VLM verdict: {'match' if matched else 'no match'})"
    )
    return _finalize(
        "vlm", passed, message,
        expected={"description": description, "present": present},
        actual={"matched": matched},
        raise_on_fail=raise_on_fail, capture_on_fail=capture_on_fail,
    )
