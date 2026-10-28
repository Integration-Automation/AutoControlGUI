"""Resolve the session recorder optional group as one outcome."""
from __future__ import annotations

from typing import TYPE_CHECKING as _TYPE_CHECKING


if _TYPE_CHECKING:
    from je_auto_control.utils.remote_desktop.session_recorder import SessionRecorder as _SessionRecorder


def _load() -> type[_SessionRecorder] | None:
    try:
        from je_auto_control.utils.remote_desktop.session_recorder import SessionRecorder
    except ImportError:
        return None
    return SessionRecorder


SessionRecorder = _load()
