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

import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


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
    """Use PIL ImageGrab to snapshot once. Fails closed on missing dep."""
    try:
        from PIL import ImageGrab
    except ImportError as error:
        raise RuntimeError(
            "Smart waits require Pillow for screen capture.",
        ) from error
    bbox = tuple(int(v) for v in region) if region else None
    image = ImageGrab.grab(bbox=bbox).convert("RGB")
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
        raise ValueError("timeout_s must be positive")
    if poll_interval_s <= 0:
        raise ValueError("poll_interval_s must be positive")
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
        raise ValueError("timeout_s must be positive")
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


# --- internals -------------------------------------------------

def _frame_diff(a: Frame, b: Frame) -> int:
    """Number of bytes that differ between two frames (lower bound on px diff)."""
    if a.width != b.width or a.height != b.height:
        return max(len(a.pixels), len(b.pixels))
    return sum(1 for left, right in zip(a.pixels, b.pixels) if left != right)


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
    "Frame", "ScreenSampler", "WaitOutcome",
    "wait_until_pixel_changes", "wait_until_region_idle",
    "wait_until_screen_stable",
]
