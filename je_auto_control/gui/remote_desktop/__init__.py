"""Remote-desktop GUI sub-package.

The legacy ``je_auto_control.gui.remote_desktop_tab`` module re-exports
:class:`RemoteDesktopTab` (and the panel/widget internals that the test
suite hooks into) so existing call sites keep working unchanged.
"""
from je_auto_control.gui.remote_desktop.frame_display import _FrameDisplay
from je_auto_control.gui.remote_desktop.host_panel import _HostPanel
from je_auto_control.gui.remote_desktop.tab import RemoteDesktopTab
from je_auto_control.gui.remote_desktop.viewer_panel import (
    _FileSendThread, _ViewerPanel,
)

__all__ = [
    "RemoteDesktopTab", "_HostPanel", "_ViewerPanel", "_FrameDisplay",
    "_FileSendThread",
]
