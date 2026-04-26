"""Remote-desktop host/viewer for screen streaming and remote input.

The protocol is a minimal length-prefixed framing on raw TCP (no extra
deps). The host periodically encodes the screen as JPEG and pushes it to
authenticated viewers; viewers send back JSON input messages that the
host dispatches via the existing mouse/keyboard wrappers. Token-based
HMAC-SHA256 authentication and a default loopback bind keep casual
misuse difficult — this is *not* a hardened RDP replacement, and exposing
it to untrusted networks should be paired with an SSH tunnel or TLS
front-end.
"""
from je_auto_control.utils.remote_desktop.audio import (
    AudioBackendError, AudioCapture, AudioPlayer,
    is_audio_backend_available,
)
from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.host_id import (
    HostIdError, format_host_id, generate_host_id, load_or_create_host_id,
    parse_host_id, validate_host_id,
)
from je_auto_control.utils.remote_desktop.input_dispatch import (
    InputDispatchError, dispatch_input,
)
from je_auto_control.utils.remote_desktop.protocol import (
    AuthenticationError, MessageType, ProtocolError,
    decode_frame_header, encode_frame,
)
from je_auto_control.utils.remote_desktop.registry import registry
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer
from je_auto_control.utils.remote_desktop.ws_host import WebSocketDesktopHost
from je_auto_control.utils.remote_desktop.ws_viewer import (
    WebSocketDesktopViewer,
)

__all__ = [
    "RemoteDesktopHost", "RemoteDesktopViewer",
    "WebSocketDesktopHost", "WebSocketDesktopViewer",
    "InputDispatchError", "AuthenticationError", "ProtocolError",
    "MessageType", "encode_frame", "decode_frame_header",
    "dispatch_input", "registry",
    "HostIdError", "format_host_id", "generate_host_id",
    "load_or_create_host_id", "parse_host_id", "validate_host_id",
    "AudioBackendError", "AudioCapture", "AudioPlayer",
    "is_audio_backend_available",
]
