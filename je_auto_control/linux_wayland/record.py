"""Wayland record stub.

Recording, as the platform seam means it, is hooking every mouse and key
event on the desktop; Wayland forbids that for unprivileged clients (see
``listener``). The Wayland backend exposes the same module surface as the X11
backend so the wrapper can swap them out, and every entry point here still
raises a clear NotImplementedError.

What Wayland *does* allow lives in :mod:`input_events`, and the error now
says so instead of only pointing at X11: the steps this program executes are
journalled with no hook at all (``InputStepLog``), and the user's own input
can be read from kernel devices they name (``PhysicalRecorder``, opt-in).
Neither is wired in here, on purpose — the seam's ``record()`` promises "start
capturing everything", and neither of those is that.
"""
from __future__ import annotations

from typing import Any, List


class _WaylandRecorder:
    """Stand-in recorder that explains why recording is unavailable."""

    def __init__(self) -> None:
        self._reason = (
            "Wayland forbids global input recording from unprivileged "
            "clients. To record what this program executes, use "
            "InputStepLog (no hook needed); to record your own keyboard "
            "and mouse, use PhysicalRecorder with devices you name in "
            "JE_AUTOCONTROL_WAYLAND_RECORD_DEVICES. Setting "
            "JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11 uses the X11 backend, "
            "which under XWayland sees X11 applications only."
        )

    def record(self) -> None:
        raise NotImplementedError(self._reason)

    def stop_record(self) -> List[Any]:
        raise NotImplementedError(self._reason)


wayland_recorder = _WaylandRecorder()


__all__ = ["wayland_recorder"]
