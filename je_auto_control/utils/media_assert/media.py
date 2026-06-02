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
from typing import Any, Dict, List, Optional, Sequence

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


def _read_segment_frames(video_path: str, start_s: float,
                         end_s: Optional[float],
                         region: Optional[Sequence[int]]) -> List[Any]:
    """Read grayscale frames of ``video_path`` within [start_s, end_s]."""
    import cv2
    resolved = os.path.realpath(os.path.expanduser(video_path))
    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"video not found: {resolved}")
    capture = cv2.VideoCapture(resolved)
    try:
        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        start_frame = int(max(0.0, start_s) * fps)
        end_frame = int(end_s * fps) if end_s is not None else None
        capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        return _collect_gray_frames(capture, cv2, start_frame, end_frame,
                                    region)
    finally:
        capture.release()


def _collect_gray_frames(capture, cv2, start_frame: int,
                         end_frame: Optional[int],
                         region: Optional[Sequence[int]]) -> List[Any]:
    """Pull and grayscale frames until ``end_frame`` or end of stream."""
    frames: List[Any] = []
    index = start_frame
    while end_frame is None or index < end_frame:
        ok, frame = capture.read()
        if not ok:
            break
        if region:
            x1, y1, x2, y2 = (int(v) for v in region)
            frame = frame[y1:y2, x1:x2]
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        index += 1
    return frames


def video_segment_motion(video_path: str,
                         start_s: float = 0.0,
                         end_s: Optional[float] = None,
                         region: Optional[Sequence[int]] = None) -> float:
    """Mean frame-to-frame difference over a video segment (0 = static)."""
    return mean_frame_diff(
        _read_segment_frames(video_path, start_s, end_s, region),
    )


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
