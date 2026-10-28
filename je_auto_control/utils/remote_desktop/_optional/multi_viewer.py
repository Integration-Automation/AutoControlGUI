"""Resolve the multi viewer optional group as one outcome."""
from __future__ import annotations

from typing import TYPE_CHECKING as _TYPE_CHECKING


if _TYPE_CHECKING:
    from je_auto_control.utils.remote_desktop.multi_viewer import MultiViewerHost as _MultiViewerHost


def _load() -> type[_MultiViewerHost] | None:
    try:
        from je_auto_control.utils.remote_desktop.multi_viewer import MultiViewerHost
    except ImportError:
        return None
    return MultiViewerHost


MultiViewerHost = _load()
