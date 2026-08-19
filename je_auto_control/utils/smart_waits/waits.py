"""Frame-diff-based smart waits — replace ``time.sleep`` in flaky scripts.

A naive ``time.sleep(2)`` either waits too little (race conditions on
slow hosts) or too long (CI runs become molasses). The helpers here
return *as soon as the condition is true*, by polling cheap
observations against a numeric threshold.

* :func:`wait_until_screen_stable` — exit when the most-recent N
  frames differ from each other by less than ``threshold`` (default:
  any change at all).
* :func:`wait_until_pixel_changes` — exit when the pixel at ``(x, y)``
  differs from its initial value by more than ``rgb_tolerance``.
* :func:`wait_until_region_idle` — restriction of
  ``wait_until_screen_stable`` to a sub-region.

Each call has a hard ``timeout_s`` cap so tests can't hang
indefinitely. All capture is injectable for unit tests.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_TIMEOUT_POSITIVE = "timeout_s must be positive"
_POLL_POSITIVE = "poll_interval_s must be positive"


@dataclass(frozen=True)
class WaitOutcome:
    """Why the wait returned + how long it took."""

    succeeded: bool
    reason: str
    elapsed_s: float
    samples_taken: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Type alias for "give me a (width, height, RGB-bytes) snapshot".
ScreenSampler = Callable[[Optional[Sequence[int]]], "Frame"]


@dataclass(frozen=True)
class Frame:
    """Minimal screen capture stand-in: width × height bytes (mode-agnostic)."""

    width: int
    height: int
    pixels: bytes


def _default_sampler(region: Optional[Sequence[int]]) -> Frame:
    """Snapshot once through the platform's grabber. Fails closed on missing dep."""
    from je_auto_control.utils.cv2_utils.screen_grabber import image_grabber
    try:
        grabber = image_grabber()
    except ImportError as error:
        raise RuntimeError(
            "Smart waits require Pillow for screen capture.",
        ) from error
    bbox = tuple(int(v) for v in region) if region else None
    image = grabber.grab(bbox=bbox).convert("RGB")
    return Frame(width=image.width, height=image.height,
                  pixels=image.tobytes())


def wait_until_screen_stable(*,
                              region: Optional[Sequence[int]] = None,
                              timeout_s: float = 10.0,
                              poll_interval_s: float = 0.2,
                              stable_for_s: float = 0.5,
                              max_pixel_diff: int = 0,
                              sampler: Optional[ScreenSampler] = None,
                              ) -> WaitOutcome:
    """Return when consecutive frames differ by ≤ ``max_pixel_diff`` pixels.

    ``stable_for_s`` controls how long the screen must stay quiet
    before we declare victory; ``poll_interval_s`` is the gap between
    samples; ``timeout_s`` is the absolute cap.
    """
    if timeout_s <= 0:
        raise ValueError(_TIMEOUT_POSITIVE)
    if poll_interval_s <= 0:
        raise ValueError(_POLL_POSITIVE)
    if stable_for_s < 0:
        raise ValueError("stable_for_s must be >= 0")
    grab = sampler or _default_sampler
    started = time.monotonic()
    deadline = started + float(timeout_s)
    previous = grab(region)
    samples = 1
    stable_since: Optional[float] = None
    while time.monotonic() < deadline:
        time.sleep(float(poll_interval_s))
        current = grab(region)
        samples += 1
        diff = _frame_diff(previous, current)
        if diff <= int(max_pixel_diff):
            if stable_since is None:
                stable_since = time.monotonic()
            if time.monotonic() - stable_since >= float(stable_for_s):
                return _finish(True, "screen stable", started, samples)
        else:
            stable_since = None
        previous = current
    return _finish(False, "timeout while waiting for stable screen",
                   started, samples)


def wait_until_pixel_changes(*, x: int, y: int,
                              timeout_s: float = 10.0,
                              poll_interval_s: float = 0.1,
                              rgb_tolerance: int = 5,
                              sampler: Optional[ScreenSampler] = None,
                              ) -> WaitOutcome:
    """Return when the pixel at ``(x, y)`` changes beyond ``rgb_tolerance``."""
    if timeout_s <= 0:
        raise ValueError(_TIMEOUT_POSITIVE)
    # 與其他 wait_* 一致:0 會讓迴圈空轉燒滿一顆核心,負數則由
    # time.sleep 拋出無關的錯誤訊息。
    # Matches every sibling wait_*: 0 turns the loop into a busy-spin that
    # pegs a core (measured ~215k full-screen grabs in 0.5s), and a negative
    # surfaces as time.sleep's own unrelated error instead of ours.
    if poll_interval_s <= 0:
        raise ValueError(_POLL_POSITIVE)
    grab = sampler or _default_sampler
    started = time.monotonic()
    deadline = started + float(timeout_s)
    initial = _read_pixel(grab(None), int(x), int(y))
    samples = 1
    while time.monotonic() < deadline:
        time.sleep(float(poll_interval_s))
        current = _read_pixel(grab(None), int(x), int(y))
        samples += 1
        if _rgb_distance(initial, current) > int(rgb_tolerance):
            return _finish(True, f"pixel changed at ({x}, {y})",
                            started, samples)
    return _finish(False, f"pixel at ({x}, {y}) never changed",
                   started, samples)


def wait_until_region_idle(*, region: Sequence[int],
                           timeout_s: float = 10.0,
                           poll_interval_s: float = 0.2,
                           stable_for_s: float = 0.5,
                           max_pixel_diff: int = 0,
                           sampler: Optional[ScreenSampler] = None,
                           ) -> WaitOutcome:
    """Restriction of :func:`wait_until_screen_stable` to a sub-region."""
    if region is None or len(list(region)) != 4:
        raise ValueError("region must be a 4-tuple [x1, y1, x2, y2]")
    return wait_until_screen_stable(
        region=region, timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
        stable_for_s=stable_for_s,
        max_pixel_diff=max_pixel_diff, sampler=sampler,
    )


ClipboardReader = Callable[[], Optional[str]]


def wait_until_clipboard_changes(*,
                                 baseline: Optional[str] = None,
                                 target: Optional[str] = None,
                                 contains: bool = False,
                                 timeout_s: float = 10.0,
                                 poll_interval_s: float = 0.2,
                                 reader: Optional[ClipboardReader] = None,
                                 ) -> WaitOutcome:
    """Return when the clipboard text changes (or matches ``target``).

    Without ``target`` the wait succeeds as soon as the clipboard differs
    from ``baseline`` (captured at the start when ``baseline`` is None).
    With ``target`` it succeeds when the clipboard equals ``target`` — or
    *contains* it when ``contains`` is True. ``reader`` is injectable so
    tests need no real clipboard.
    """
    if timeout_s <= 0:
        raise ValueError(_TIMEOUT_POSITIVE)
    if poll_interval_s <= 0:
        raise ValueError(_POLL_POSITIVE)
    read = reader or _default_clipboard_reader
    started = time.monotonic()
    deadline = started + float(timeout_s)
    initial = baseline if baseline is not None else (read() or "")
    samples = 1
    while time.monotonic() < deadline:
        current = read() or ""
        samples += 1
        if _clipboard_satisfied(current, initial, target, contains):
            return _finish(True, "clipboard changed", started, samples)
        time.sleep(float(poll_interval_s))
    return _finish(False, "timeout while waiting for clipboard change",
                   started, samples)


def _clipboard_satisfied(current: str, initial: str,
                         target: Optional[str], contains: bool) -> bool:
    if target is not None:
        return target in current if contains else current == target
    return current != initial


def _default_clipboard_reader() -> Optional[str]:
    from je_auto_control.utils.clipboard.clipboard import get_clipboard
    return get_clipboard()


WindowFinder = Callable[[str, bool], bool]


def wait_until_window_closed(title: str, *, case_sensitive: bool = False,
                             timeout_s: float = 10.0,
                             poll_interval_s: float = 0.2,
                             finder: Optional[WindowFinder] = None
                             ) -> WaitOutcome:
    """Return when no window matching ``title`` exists (or timeout).

    The closing companion to ``wait_for_window`` (which waits for a window
    to *appear*). ``finder(title, case_sensitive) -> bool`` reports whether
    a matching window still exists; it is injectable for tests.
    """
    if timeout_s <= 0:
        raise ValueError(_TIMEOUT_POSITIVE)
    if poll_interval_s <= 0:
        raise ValueError(_POLL_POSITIVE)
    exists = finder or _default_window_finder
    started = time.monotonic()
    deadline = started + float(timeout_s)
    samples = 0
    while time.monotonic() < deadline:
        samples += 1
        if not exists(title, case_sensitive):
            return _finish(True, "window closed", started, samples)
        time.sleep(float(poll_interval_s))
    return _finish(False, "timeout while waiting for window to close",
                   started, samples)


def _default_window_finder(title: str, case_sensitive: bool) -> bool:
    from je_auto_control.wrapper.auto_control_window import find_window
    return find_window(title, case_sensitive=case_sensitive) is not None


WindowTitleLister = Callable[[], List[str]]


def _title_matches(titles: List[str], pattern: str,
                   compiled: Optional["re.Pattern"]) -> bool:
    if compiled is not None:
        return any(compiled.search(title) for title in titles)
    return any(pattern in title for title in titles)


def wait_until_window_title(pattern: str, *, present: bool = True,
                            regex: bool = True, timeout_s: float = 10.0,
                            poll_interval_s: float = 0.2,
                            title_lister: Optional[WindowTitleLister] = None
                            ) -> WaitOutcome:
    """Wait until a window whose title matches ``pattern`` appears (or vanishes).

    Unlike ``wait_for_window`` (substring, appear only) this matches a regular
    expression by default (``regex=False`` falls back to a substring test) and
    can wait for the title to *vanish* with ``present=False`` — e.g. wait for a
    browser tab to navigate to ``r".*— Checkout$"``. ``title_lister() -> [titles]``
    is injectable for tests.
    """
    if timeout_s <= 0:
        raise ValueError(_TIMEOUT_POSITIVE)
    if poll_interval_s <= 0:
        raise ValueError(_POLL_POSITIVE)
    titles_of = title_lister or _default_title_lister
    compiled = re.compile(pattern) if regex else None
    started = time.monotonic()
    deadline = started + float(timeout_s)
    samples = 0
    while time.monotonic() < deadline:
        samples += 1
        if _title_matches(titles_of(), pattern, compiled) == bool(present):
            return _finish(True, "window title condition met", started, samples)
        time.sleep(float(poll_interval_s))
    return _finish(False, "timeout while waiting for window title",
                   started, samples)


def _default_title_lister() -> List[str]:
    from je_auto_control.wrapper.auto_control_window import list_windows
    return [title for _id, title in list_windows()]


FileStatReader = Callable[[str], Optional[int]]


def wait_until_file(path: str, *,
                    timeout_s: float = 30.0,
                    poll_interval_s: float = 0.25,
                    stable_for_s: float = 1.0,
                    min_size: int = 1,
                    stat_reader: Optional[FileStatReader] = None,
                    ) -> WaitOutcome:
    """Return when ``path`` exists, is >= ``min_size`` bytes, and its size has
    held steady for ``stable_for_s`` (i.e. a download has finished writing).

    ``stat_reader(path) -> size or None`` is injectable so tests need no real
    growing file; the default reports the on-disk size (``None`` when absent).
    """
    if timeout_s <= 0:
        raise ValueError(_TIMEOUT_POSITIVE)
    if poll_interval_s <= 0:
        raise ValueError(_POLL_POSITIVE)
    if stable_for_s < 0:
        raise ValueError("stable_for_s must be >= 0")
    read = stat_reader or _default_file_size
    tracker = _StableSize(float(stable_for_s), int(min_size))
    started = time.monotonic()
    deadline = started + float(timeout_s)
    samples = 0
    while time.monotonic() < deadline:
        samples += 1
        if tracker.ready(read(str(path))):
            return _finish(True, "file ready", started, samples)
        time.sleep(float(poll_interval_s))
    return _finish(False, "timeout while waiting for file", started, samples)


class _StableSize:
    """Track whether a file's size has stayed >= min for long enough."""

    def __init__(self, stable_for_s: float, min_size: int) -> None:
        self._stable_for_s = stable_for_s
        self._min_size = min_size
        self._last: Optional[int] = None
        self._since: Optional[float] = None

    def ready(self, size: Optional[int]) -> bool:
        if size is None or size < self._min_size:
            self._last, self._since = size, None
            return False
        now = time.monotonic()
        if size != self._last:
            self._last, self._since = size, now
        return self._since is not None and now - self._since >= self._stable_for_s


def _default_file_size(path: str) -> Optional[int]:
    """Return the on-disk byte size of ``path``, or None if it is absent."""
    import os
    try:
        return os.path.getsize(path)
    except OSError:
        return None


PortConnector = Callable[[str, int, float], bool]


def wait_until_port(host: str, port: int, *,
                    timeout_s: float = 30.0,
                    poll_interval_s: float = 0.25,
                    connect_timeout_s: float = 1.0,
                    connector: Optional[PortConnector] = None,
                    ) -> WaitOutcome:
    """Return when a TCP connection to ``(host, port)`` succeeds, else timeout.

    The closing companion to launching a server: poll until the port
    accepts connections. ``connector(host, port, timeout) -> bool`` is
    injectable so tests need no real listener.
    """
    if timeout_s <= 0:
        raise ValueError(_TIMEOUT_POSITIVE)
    if poll_interval_s <= 0:
        raise ValueError(_POLL_POSITIVE)
    if not 0 < int(port) <= 65535:
        raise ValueError("port must be in 1..65535")
    probe = connector or _default_port_connector
    started = time.monotonic()
    deadline = started + float(timeout_s)
    samples = 0
    while time.monotonic() < deadline:
        samples += 1
        if probe(str(host), int(port), float(connect_timeout_s)):
            return _finish(True, f"port {host}:{port} open", started, samples)
        time.sleep(float(poll_interval_s))
    return _finish(False, f"timeout waiting for {host}:{port}",
                   started, samples)


def _default_port_connector(host: str, port: int, timeout: float) -> bool:
    """Return True if a TCP connection to ``(host, port)`` can be opened."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


ProcessLister = Callable[[str], List[str]]


def wait_until_process(name: str, *, present: bool = True,
                       timeout_s: float = 30.0,
                       poll_interval_s: float = 0.25,
                       lister: Optional[ProcessLister] = None,
                       ) -> WaitOutcome:
    """Return when a process whose name contains ``name`` appears, or exits.

    The companion to launching / killing a process: poll until a matching
    process exists (``present=True``) or is gone (``present=False``).
    ``lister(name) -> [matching names]`` is injectable so tests need no
    real processes; the default uses psutil.
    """
    if timeout_s <= 0:
        raise ValueError(_TIMEOUT_POSITIVE)
    if poll_interval_s <= 0:
        raise ValueError(_POLL_POSITIVE)
    find = lister or _default_process_lister
    started = time.monotonic()
    deadline = started + float(timeout_s)
    samples = 0
    verb = "appeared" if present else "exited"
    while time.monotonic() < deadline:
        samples += 1
        if bool(find(name)) == bool(present):
            return _finish(True, f"process {name!r} {verb}", started, samples)
        time.sleep(float(poll_interval_s))
    return _finish(False, f"timeout waiting for process {name!r} to {verb}",
                   started, samples)


def wait_until_gone(present: Callable[[], bool], *,
                    timeout_s: float = 10.0, poll_interval_s: float = 0.2,
                    gone_for_s: float = 0.0) -> WaitOutcome:
    """Return once ``present()`` has been falsey for ``gone_for_s`` seconds.

    The blocking complement of ``wait_for_image`` / ``wait_for_text``: wait for a
    spinner / toast / dialog to *disappear*. ``present`` is any predicate (e.g.
    "is this image still on screen"); it is polled every ``poll_interval_s`` up to
    ``timeout_s``. Injecting ``present`` keeps the loop headless-testable.
    """
    if timeout_s <= 0:
        raise ValueError(_TIMEOUT_POSITIVE)
    if poll_interval_s <= 0:
        raise ValueError(_POLL_POSITIVE)
    if gone_for_s < 0:
        raise ValueError("gone_for_s must be >= 0")
    started = time.monotonic()
    deadline = started + float(timeout_s)
    samples = 0
    gone_since: Optional[float] = None
    while time.monotonic() < deadline:
        samples += 1
        if present():
            gone_since = None
        else:
            if gone_since is None:
                gone_since = time.monotonic()
            if time.monotonic() - gone_since >= float(gone_for_s):
                return _finish(True, "target gone", started, samples)
        time.sleep(float(poll_interval_s))
    return _finish(False, "timeout while waiting for target to vanish",
                   started, samples)


def _image_present(image: Any, detect_threshold: float) -> bool:
    """Whether ``image`` is currently locatable on screen."""
    from je_auto_control.utils.exception.exceptions import ImageNotFoundException
    from je_auto_control.wrapper.auto_control_image import locate_image_center
    try:
        locate_image_center(image, detect_threshold=detect_threshold)
        return True
    except ImageNotFoundException:
        return False


def wait_until_image_gone(image: Any, *, detect_threshold: float = 1.0,
                          timeout_s: float = 10.0, poll_interval_s: float = 0.2,
                          gone_for_s: float = 0.0) -> WaitOutcome:
    """Wait until ``image`` is no longer found on screen."""
    return wait_until_gone(lambda: _image_present(image, detect_threshold),
                           timeout_s=timeout_s, poll_interval_s=poll_interval_s,
                           gone_for_s=gone_for_s)


def _text_present(text: str) -> bool:
    """Whether ``text`` is currently found on screen via OCR."""
    from je_auto_control.utils.ocr.ocr_engine import find_text_matches
    return bool(find_text_matches(text))


def wait_until_text_gone(text: str, *, timeout_s: float = 10.0,
                         poll_interval_s: float = 0.2,
                         gone_for_s: float = 0.0) -> WaitOutcome:
    """Wait until ``text`` is no longer found on screen (OCR)."""
    return wait_until_gone(lambda: _text_present(text), timeout_s=timeout_s,
                           poll_interval_s=poll_interval_s, gone_for_s=gone_for_s)


def _color_fraction(frame: "Frame", target: Sequence[int],
                    tolerance: int) -> float:
    """Fraction of the frame's pixels within ``tolerance`` of ``target`` RGB."""
    pixels = frame.pixels
    total = len(pixels) // 3
    if total == 0:
        return 0.0
    red, green, blue = int(target[0]), int(target[1]), int(target[2])
    tol = int(tolerance)
    matched = 0
    for offset in range(0, total * 3, 3):
        if (abs(pixels[offset] - red) <= tol
                and abs(pixels[offset + 1] - green) <= tol
                and abs(pixels[offset + 2] - blue) <= tol):
            matched += 1
    return matched / total


def wait_until_color(*, region: Optional[Sequence[int]] = None,
                     target_rgb: Sequence[int], tolerance: int = 10,
                     min_fraction: float = 0.5, present: bool = True,
                     timeout_s: float = 10.0, poll_interval_s: float = 0.2,
                     sampler: Optional[ScreenSampler] = None) -> WaitOutcome:
    """Wait until ``target_rgb`` covers (or stops covering) a fraction of ``region``.

    Counts pixels within ``tolerance`` (per channel) of ``target_rgb``. With
    ``present=True`` the wait succeeds once that fraction reaches
    ``min_fraction`` (a status light turns green, a progress bar fills); with
    ``present=False`` it succeeds once the fraction drops below it (the colour
    disappears). ``sampler`` is injectable for headless tests.
    """
    if timeout_s <= 0:
        raise ValueError(_TIMEOUT_POSITIVE)
    if poll_interval_s <= 0:
        raise ValueError(_POLL_POSITIVE)
    grab = sampler or _default_sampler
    started = time.monotonic()
    deadline = started + float(timeout_s)
    samples = 0
    while time.monotonic() < deadline:
        samples += 1
        fraction = _color_fraction(grab(region), target_rgb, tolerance)
        reached = fraction >= float(min_fraction)
        if reached == bool(present):
            return _finish(True, "colour condition met", started, samples)
        time.sleep(float(poll_interval_s))
    return _finish(False, "timeout while waiting for colour", started, samples)


def _default_process_lister(name: str) -> List[str]:
    """List running process names matching ``name`` (requires psutil)."""
    from je_auto_control.utils.assertion.assertions import _running_process_names
    return _running_process_names(name)


# --- internals -------------------------------------------------

def _frame_diff(a: Frame, b: Frame) -> int:
    """Number of PIXELS (not bytes) that differ between two frames.

    ``max_pixel_diff`` is documented and compared in *pixels*, but a single
    changed pixel spans up to three RGB bytes; counting bytes would make a
    one-pixel blink read as three, so ``max_pixel_diff=2`` would never settle.
    Group the buffer into per-pixel channel runs and count differing pixels.
    """
    if a.width != b.width or a.height != b.height:
        return max(a.width * a.height, b.width * b.height)
    pixel_count = a.width * a.height
    if pixel_count == 0:
        return 0
    left, right = a.pixels, b.pixels
    limit = min(len(left), len(right))
    channels = max(1, limit // pixel_count)
    changed = 0
    for base in range(0, (limit // channels) * channels, channels):
        if left[base:base + channels] != right[base:base + channels]:
            changed += 1
    return changed


def _read_pixel(frame: Frame, x: int, y: int) -> Tuple[int, int, int]:
    if x < 0 or y < 0 or x >= frame.width or y >= frame.height:
        raise ValueError(
            f"pixel ({x}, {y}) outside frame {frame.width}x{frame.height}",
        )
    offset = (y * frame.width + x) * 3
    if offset + 3 > len(frame.pixels):
        return (0, 0, 0)
    chunk: List[int] = list(frame.pixels[offset:offset + 3])
    return (chunk[0], chunk[1], chunk[2])


def _rgb_distance(a: Tuple[int, int, int],
                   b: Tuple[int, int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


def _finish(succeeded: bool, reason: str, started: float,
            samples: int) -> WaitOutcome:
    return WaitOutcome(
        succeeded=succeeded, reason=reason,
        elapsed_s=round(time.monotonic() - started, 3),
        samples_taken=samples,
    )


__all__ = [
    "ClipboardReader", "FileStatReader", "Frame", "PortConnector",
    "ProcessLister", "ScreenSampler", "WaitOutcome", "WindowFinder",
    "wait_until_clipboard_changes", "wait_until_file",
    "wait_until_pixel_changes", "wait_until_port", "wait_until_process",
    "wait_until_region_idle", "wait_until_screen_stable",
    "wait_until_window_closed",
]
