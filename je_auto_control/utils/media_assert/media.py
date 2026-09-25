"""Media assertions — verify audio activity and video motion.

Screen / audio recording already exists; this module adds the *assertion*
side so a script can check that something actually played or animated:

* :func:`assert_audio_activity` records from an input device for a short
  window and checks the RMS level against a threshold (sound vs silence).
* :func:`assert_video_changes` measures mean frame-to-frame difference over
  a segment of a recorded video and checks for motion vs a static frame.

The numeric cores (:func:`rms`, :func:`mean_frame_diff`) are pure and
unit-testable; the capture wrappers (sounddevice / OpenCV) are thin and
lazily imported, and the assertion helpers call the module-level measure
functions so tests can substitute a fake measurement.
"""
from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.exception.exceptions import (
    AutoControlAssertionException,
)


@dataclass(frozen=True)
class MediaAssertionResult:
    """Outcome of an audio / video assertion."""

    kind: str
    passed: bool
    message: str
    measured: float
    threshold: float
    expected: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def rms(samples: Sequence[float]) -> float:
    """Root-mean-square level of a sample sequence (pure)."""
    values = list(samples)
    if not values:
        return 0.0
    total = math.fsum(float(value) * float(value) for value in values)
    return math.sqrt(total / len(values))


def measure_audio_rms(duration_s: float = 1.0,
                      samplerate: int = 44100,
                      channels: int = 1,
                      device: Optional[int] = None) -> float:
    """Record from an input device and return the RMS level of the buffer."""
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as error:
        raise RuntimeError(
            "Audio assertions require sounddevice + numpy "
            "(pip install sounddevice numpy).",
        ) from error
    frames = max(1, int(float(duration_s) * int(samplerate)))
    recording = sd.rec(frames, samplerate=int(samplerate),
                       channels=int(channels), device=device)
    sd.wait()
    return float(np.sqrt(np.mean(np.square(recording))))


def assert_audio_activity(duration_s: float = 1.0,
                          threshold: float = 0.01,
                          expect_sound: bool = True,
                          samplerate: int = 44100,
                          channels: int = 1,
                          device: Optional[int] = None,
                          raise_on_fail: bool = True
                          ) -> MediaAssertionResult:
    """Assert the input device is (or is not) producing sound."""
    level = measure_audio_rms(
        duration_s=duration_s, samplerate=samplerate,
        channels=channels, device=device,
    )
    has_sound = level >= threshold
    passed = (has_sound == expect_sound)
    state = "sound" if expect_sound else "silence"
    message = (
        f"assert_audio_activity passed: RMS {level:.4f} indicates {state}"
        if passed else
        f"assert_audio_activity failed: RMS {level:.4f} vs threshold "
        f"{threshold} (expected {state})"
    )
    return _finalize_media(
        "audio", passed, message, level, threshold, expect_sound,
        raise_on_fail,
    )


def mean_frame_diff(frames: Sequence[Any]) -> float:
    """Mean absolute difference between consecutive grayscale frames (pure).

    ``frames`` is a sequence of 2-D numeric arrays (numpy arrays or nested
    lists). Returns 0.0 for fewer than two frames.
    """
    try:
        import numpy as np
    except ImportError as error:
        raise RuntimeError("mean_frame_diff requires numpy.") from error
    if len(frames) < 2:
        return 0.0
    diffs: List[float] = []
    previous = np.asarray(frames[0], dtype="float64")
    for frame in frames[1:]:
        current = np.asarray(frame, dtype="float64")
        diffs.append(float(np.mean(np.abs(current - previous))))
        previous = current
    return float(sum(diffs) / len(diffs)) if diffs else 0.0


def _segment_motion(video_path: str, start_s: float,
                    end_s: Optional[float],
                    region: Optional[Sequence[int]]) -> Tuple[int, float]:
    """Frame count and summed consecutive-frame difference within [start_s, end_s]."""
    import cv2
    resolved = os.path.realpath(os.path.expanduser(video_path))
    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"video not found: {resolved}")
    capture = cv2.VideoCapture(resolved)
    try:
        if not capture.isOpened():
            raise ValueError(f"cannot decode video: {resolved}")
        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        start_frame = int(max(0.0, start_s) * fps)
        end_frame = int(end_s * fps) if end_s is not None else None
        capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        return _sum_frame_diffs(capture, cv2, start_frame, end_frame, region)
    finally:
        capture.release()


def _clipped(region: Sequence[int], frame) -> Tuple[int, int, int, int]:
    """``region`` (x1, y1, x2, y2) clipped to ``frame``; ``ValueError`` if nothing is left.

    An off-frame, negative or zero-width region sliced an empty frame, and
    OpenCV's error escaped the executor.
    """
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = (int(v) for v in region)
    x1, x2 = max(0, x1), min(width, x2)
    y1, y2 = max(0, y1), min(height, y2)
    if x1 >= x2 or y1 >= y2:
        raise ValueError(f"region {list(region)} is outside the {width}x{height} video frame")
    return x1, y1, x2, y2


def _sum_frame_diffs(capture, cv2, start_frame: int, end_frame: Optional[int],
                     region: Optional[Sequence[int]]) -> Tuple[int, float]:
    """Read frames until ``end_frame`` or the end, keeping only the previous one.

    Every frame used to be kept, about 37 GB for ten minutes of 1080p30.
    """
    import numpy as np
    count, total, previous, bounds = 0, 0.0, None, None
    index = start_frame
    while end_frame is None or index < end_frame:
        ok, frame = capture.read()
        if not ok:
            break
        if region:
            bounds = bounds or _clipped(region, frame)
            frame = frame[bounds[1]:bounds[3], bounds[0]:bounds[2]]
        current = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype("float64")
        if previous is not None:
            total += float(np.mean(np.abs(current - previous)))
        previous, count = current, count + 1
        index += 1
    return count, total


def video_segment_motion(video_path: str,
                         start_s: float = 0.0,
                         end_s: Optional[float] = None,
                         region: Optional[Sequence[int]] = None) -> float:
    """Mean frame-to-frame difference over a video segment (0 = static).

    A segment with fewer than two frames has no motion to measure and raises
    ``ValueError``: it used to measure 0.0, so a corrupt file or an empty
    range passed ``expect_motion=False``.
    """
    count, total = _contained(_segment_motion, video_path, start_s, end_s, region)
    if count < 2:
        raise ValueError(
            f"video segment has {count} frame(s); motion needs at least 2")
    return total / (count - 1)


def _contained(function, *args):
    """Call ``function``, with OpenCV's ``cv2.error`` as a framework error the executor records."""
    from je_auto_control.utils.visual_match.visual_match import _contain_cv2_error
    return _contain_cv2_error(function)(*args)


def assert_video_changes(video_path: str,
                         start_s: float = 0.0,
                         end_s: Optional[float] = None,
                         threshold: float = 1.0,
                         expect_motion: bool = True,
                         region: Optional[Sequence[int]] = None,
                         raise_on_fail: bool = True) -> MediaAssertionResult:
    """Assert a video segment contains motion (or is static)."""
    motion = video_segment_motion(
        video_path, start_s=start_s, end_s=end_s, region=region,
    )
    has_motion = motion >= threshold
    passed = (has_motion == expect_motion)
    state = "motion" if expect_motion else "static"
    message = (
        f"assert_video_changes passed: diff {motion:.3f} indicates {state}"
        if passed else
        f"assert_video_changes failed: diff {motion:.3f} vs threshold "
        f"{threshold} (expected {state})"
    )
    return _finalize_media(
        "video", passed, message, motion, threshold, expect_motion,
        raise_on_fail,
    )


def _finalize_media(kind: str, passed: bool, message: str, measured: float,
                    threshold: float, expected: bool,
                    raise_on_fail: bool) -> MediaAssertionResult:
    """Build the result and raise on failure when requested."""
    if not passed and raise_on_fail:
        raise AutoControlAssertionException(message)
    return MediaAssertionResult(
        kind=kind, passed=passed, message=message,
        measured=round(measured, 6), threshold=threshold, expected=expected,
    )
