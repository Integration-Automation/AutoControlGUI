"""Resolve the webrtc optional group as one outcome."""
from __future__ import annotations

from typing import TYPE_CHECKING as _TYPE_CHECKING


if _TYPE_CHECKING:
    from je_auto_control.utils.remote_desktop.webrtc_host import WebRTCDesktopHost as _WebRTCDesktopHost
    from je_auto_control.utils.remote_desktop.webrtc_transport import WebRTCConfig as _WebRTCConfig
    from je_auto_control.utils.remote_desktop.webrtc_viewer import WebRTCDesktopViewer as _WebRTCDesktopViewer


def _load() -> tuple[type[_WebRTCDesktopHost] | None, type[_WebRTCDesktopViewer] | None, type[_WebRTCConfig] | None]:
    """Lazy-import WebRTC classes; aiortc is an optional 'webrtc' extra."""
    try:
        from je_auto_control.utils.remote_desktop.webrtc_host import WebRTCDesktopHost
        from je_auto_control.utils.remote_desktop.webrtc_transport import WebRTCConfig
        from je_auto_control.utils.remote_desktop.webrtc_viewer import WebRTCDesktopViewer
    except ImportError:
        return (None, None, None)
    return (WebRTCDesktopHost, WebRTCDesktopViewer, WebRTCConfig)


WebRTCDesktopHost, WebRTCDesktopViewer, WebRTCConfig = _load()
