"""The optional WebRTC classes as types, for annotations in the panel modules.

``je_auto_control.utils.remote_desktop`` exports these names as variables that
are ``None`` without the ``webrtc`` extra, which is right at run time and
useless to a type checker ("variable is not valid as a type"). Annotations use
the names below instead; calls keep using the package's own names.
"""
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from je_auto_control.utils.remote_desktop.multi_viewer import (
        MultiViewerHost as MultiViewerHostT,
    )
    from je_auto_control.utils.remote_desktop.session_recorder import (
        SessionRecorder as SessionRecorderT,
    )
    from je_auto_control.utils.remote_desktop.webrtc_transport import (
        WebRTCConfig as WebRTCConfigT,
    )
    from je_auto_control.utils.remote_desktop.webrtc_viewer import (
        WebRTCDesktopViewer as WebRTCDesktopViewerT,
    )
else:
    MultiViewerHostT = SessionRecorderT = WebRTCConfigT = WebRTCDesktopViewerT = Any

__all__ = ["MultiViewerHostT", "SessionRecorderT", "WebRTCConfigT", "WebRTCDesktopViewerT"]
