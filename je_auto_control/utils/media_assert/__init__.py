"""Media assertions — audio activity and video motion checks.

Public surface::

    from je_auto_control import (
        assert_audio_activity, assert_video_changes,
        measure_audio_rms, video_segment_motion, MediaAssertionResult,
    )
"""
from je_auto_control.utils.media_assert.media import (
    MediaAssertionResult,
    assert_audio_activity,
    assert_video_changes,
    mean_frame_diff,
    measure_audio_rms,
    rms,
    video_segment_motion,
)


__all__ = [
    "MediaAssertionResult",
    "assert_audio_activity",
    "assert_video_changes",
    "mean_frame_diff",
    "measure_audio_rms",
    "rms",
    "video_segment_motion",
]
