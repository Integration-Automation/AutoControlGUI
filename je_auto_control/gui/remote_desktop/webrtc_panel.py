"""Compatible WebRTC panel imports; implementation is split into typed panels and controllers."""

from __future__ import annotations
from je_auto_control.gui.remote_desktop.webrtc_host_panel import _WebRTCHostPanel
from je_auto_control.gui.remote_desktop.webrtc_common import _PanelSignals as _PanelSignals
from je_auto_control.gui.remote_desktop.webrtc_viewer_panel import _WebRTCViewerPanel

__all__ = ["_WebRTCHostPanel", "_WebRTCViewerPanel"]
