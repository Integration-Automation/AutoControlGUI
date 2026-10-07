"""Legacy replay recording stays unavailable; explicit physical capture returns raw units."""
from __future__ import annotations

from typing import Any

from je_auto_control.linux_wayland.input_events import RecordingUnavailable


class _WaylandRecorder:
    """Preserve the legacy surface without fabricating a replay timeline from device units."""

    @staticmethod
    def record() -> None:
        """Reject a legacy hook; use action journals or opt-in raw physical capture."""
        raise RecordingUnavailable('legacy Wayland replay recording is unavailable; '
                                   'use api.wayland_input.start_physical_recording for raw device events')

    @staticmethod
    def stop_record() -> list[Any]:
        """Reject unsupported replay output; raw capture has its own explicit stop API."""
        raise RecordingUnavailable('legacy Wayland recording has no replay timeline')


wayland_recorder = _WaylandRecorder()

__all__ = ['wayland_recorder']
