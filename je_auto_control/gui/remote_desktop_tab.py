"""Backwards-compatible re-exports for the Remote Desktop GUI panels.

The real implementation now lives under
``je_auto_control.gui.remote_desktop`` (host_panel / viewer_panel /
frame_display / tab / _helpers). This module keeps the original import
paths working — tests and main_widget import names like ``_HostPanel``,
``_ViewerPanel``, ``_FrameDisplay`` and ``RemoteDesktopTab`` from here.
"""
from je_auto_control.gui.remote_desktop import (
    RemoteDesktopTab, _FileSendThread, _FrameDisplay, _HostPanel,
    _ViewerPanel,
)

__all__ = [
    "RemoteDesktopTab", "_HostPanel", "_ViewerPanel", "_FrameDisplay",
    "_FileSendThread",
]
