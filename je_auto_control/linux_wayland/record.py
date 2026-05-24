"""Wayland record stub.

Recording requires hooking global mouse + key events; Wayland forbids
that for unprivileged clients (see ``listener``). The Wayland backend
exposes the same module surface as the X11 backend so the wrapper
can swap them out, but every entry point raises a clear
NotImplementedError pointing at the X11 fallback.
"""
from __future__ import annotations

from typing import Any, List


class _WaylandRecorder:
    """Stand-in recorder that explains why recording is unavailable."""

    def __init__(self) -> None:
        self._reason = (
            "Wayland forbids global input recording from unprivileged "
            "clients. Set JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11 to "
            "use the X11 backend, or run on an X11 session."
        )

    def record(self) -> None:
        raise NotImplementedError(self._reason)

    def stop_record(self) -> List[Any]:
        raise NotImplementedError(self._reason)


wayland_recorder = _WaylandRecorder()


__all__ = ["wayland_recorder"]
