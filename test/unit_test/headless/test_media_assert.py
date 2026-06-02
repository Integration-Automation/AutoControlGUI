"""Headless tests for media assertions (audio RMS + video motion).

The numeric cores are pure; the capture wrappers are exercised through
monkeypatched measurement functions so no microphone / video file is
required.
"""
import math

import pytest

import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import (
    AutoControlAssertionException,
)
from je_auto_control.utils.media_assert import media


def test_rms_pure():
    assert media.rms([]) == 0.0
    assert media.rms([3, 4]) == pytest.approx(math.sqrt((9 + 16) / 2))
    assert media.rms([0, 0, 0]) == 0.0


def test_mean_frame_diff_pure():
    np = pytest.importorskip("numpy")
    frame_a = np.zeros((2, 2))
    frame_b = np.full((2, 2), 10.0)
    assert media.mean_frame_diff([frame_a]) == 0.0
    assert media.mean_frame_diff([frame_a, frame_b]) == pytest.approx(10.0)


def test_assert_audio_activity_pass(monkeypatch):
    monkeypatch.setattr(media, "measure_audio_rms",
                        lambda **kwargs: 0.5)
    result = media.assert_audio_activity(threshold=0.01, expect_sound=True)
    assert result.passed is True
    assert result.kind == "audio"


def test_assert_audio_activity_fail_raises(monkeypatch):
    monkeypatch.setattr(media, "measure_audio_rms",
                        lambda **kwargs: 0.0001)
    with pytest.raises(AutoControlAssertionException):
        media.assert_audio_activity(threshold=0.01, expect_sound=True)


def test_assert_audio_expect_silence(monkeypatch):
    monkeypatch.setattr(media, "measure_audio_rms",
                        lambda **kwargs: 0.0001)
    result = media.assert_audio_activity(
        threshold=0.01, expect_sound=False, raise_on_fail=False,
    )
    assert result.passed is True


def test_assert_video_changes_motion(monkeypatch):
    monkeypatch.setattr(media, "video_segment_motion",
                        lambda *a, **k: 9.0)
    result = media.assert_video_changes(
        "x.mp4", threshold=1.0, expect_motion=True,
    )
    assert result.passed is True
    assert result.measured == 9.0


def test_assert_video_static_fail(monkeypatch):
    monkeypatch.setattr(media, "video_segment_motion",
                        lambda *a, **k: 0.0)
    with pytest.raises(AutoControlAssertionException):
        media.assert_video_changes("x.mp4", threshold=1.0, expect_motion=True)


def test_facade_exports():
    assert hasattr(ac, "assert_audio_activity")
    assert hasattr(ac, "assert_video_changes")
    assert hasattr(ac, "measure_audio_rms")
