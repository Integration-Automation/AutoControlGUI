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
from je_auto_control.utils.remote_desktop.clipboard_sync import (
    ClipboardSyncError,
)
from je_auto_control.utils.remote_desktop.file_transfer import (
    FileReceiver, FileSendResult, FileTransferError, send_file,
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


def _load_webrtc():
    """Lazy-import WebRTC classes; aiortc is an optional 'webrtc' extra."""
    try:
        from je_auto_control.utils.remote_desktop.webrtc_host import (
            WebRTCDesktopHost,
        )
        from je_auto_control.utils.remote_desktop.webrtc_transport import (
            WebRTCConfig,
        )
        from je_auto_control.utils.remote_desktop.webrtc_viewer import (
            WebRTCDesktopViewer,
        )
    except ImportError:
        return None, None, None
    return WebRTCDesktopHost, WebRTCDesktopViewer, WebRTCConfig


WebRTCDesktopHost, WebRTCDesktopViewer, WebRTCConfig = _load_webrtc()

from je_auto_control.utils.remote_desktop import signaling_client  # noqa: E402
from je_auto_control.utils.remote_desktop.address_book import (  # noqa: E402
    AddressBook, default_address_book, default_address_book_path,
)
from je_auto_control.utils.remote_desktop.trust_list import (  # noqa: E402
    TrustList, default_trust_list, default_trust_list_path,
)
from je_auto_control.utils.remote_desktop.fingerprint import (  # noqa: E402
    KnownHosts, default_known_hosts, fingerprint_for_display,
    load_or_create_host_fingerprint,
)
from je_auto_control.utils.remote_desktop.permissions import (  # noqa: E402
    SessionPermissions,
)
from je_auto_control.utils.remote_desktop.viewer_id import (  # noqa: E402
    ViewerIdError, generate_viewer_id, load_or_create_viewer_id,
    validate_viewer_id,
)
from je_auto_control.utils.remote_desktop.wake_on_lan import (  # noqa: E402
    build_magic_packet, send_magic_packet,
)


def _load_session_recorder():
    try:
        from je_auto_control.utils.remote_desktop.session_recorder import (
            SessionRecorder,
        )
    except ImportError:
        return None
    return SessionRecorder


def _load_multi_viewer():
    try:
        from je_auto_control.utils.remote_desktop.multi_viewer import (
            MultiViewerHost,
        )
    except ImportError:
        return None
    return MultiViewerHost


def _load_mic_uplink():
    try:
        from je_auto_control.utils.remote_desktop.webrtc_mic import (
            MicUplinkReceiver, MicUplinkSender,
        )
    except ImportError:
        return None, None
    return MicUplinkSender, MicUplinkReceiver


def _load_file_transfer():
    try:
        from je_auto_control.utils.remote_desktop.webrtc_files import (
            FileTransferError, FileTransferReceiver, FileTransferSender,
        )
    except ImportError:
        return None, None, None
    return FileTransferSender, FileTransferReceiver, FileTransferError


def _load_hw_codec():
    try:
        from je_auto_control.utils.remote_desktop.hw_codec import (
            active_hardware_codec, available_hardware_codecs,
            install_hardware_codec, uninstall_hardware_codec,
        )
    except ImportError:
        return None, None, None, None
    return (available_hardware_codecs, active_hardware_codec,
            install_hardware_codec, uninstall_hardware_codec)


SessionRecorder = _load_session_recorder()
MultiViewerHost = _load_multi_viewer()
(available_hardware_codecs, active_hardware_codec,
 install_hardware_codec, uninstall_hardware_codec) = _load_hw_codec()
MicUplinkSender, MicUplinkReceiver = _load_mic_uplink()
FileTransferSender, FileTransferReceiver, FileTransferWebRTCError = _load_file_transfer()


def is_webrtc_available() -> bool:
    """Return True iff the optional WebRTC stack (aiortc + av) is importable."""
    return WebRTCDesktopHost is not None


__all__ = [
    "RemoteDesktopHost", "RemoteDesktopViewer",
    "WebSocketDesktopHost", "WebSocketDesktopViewer",
    "WebRTCDesktopHost", "WebRTCDesktopViewer", "WebRTCConfig",
    "is_webrtc_available", "signaling_client",
    "TrustList", "default_trust_list", "default_trust_list_path",
    "AddressBook", "default_address_book", "default_address_book_path",
    "ViewerIdError", "generate_viewer_id", "load_or_create_viewer_id",
    "validate_viewer_id",
    "build_magic_packet", "send_magic_packet",
    "SessionRecorder", "MultiViewerHost",
    "available_hardware_codecs", "active_hardware_codec",
    "install_hardware_codec", "uninstall_hardware_codec",
    "SessionPermissions", "KnownHosts", "default_known_hosts",
    "fingerprint_for_display", "load_or_create_host_fingerprint",
    "MicUplinkSender", "MicUplinkReceiver",
    "FileTransferSender", "FileTransferReceiver", "FileTransferWebRTCError",
    "InputDispatchError", "AuthenticationError", "ProtocolError",
    "MessageType", "encode_frame", "decode_frame_header",
    "dispatch_input", "registry",
    "HostIdError", "format_host_id", "generate_host_id",
    "load_or_create_host_id", "parse_host_id", "validate_host_id",
    "AudioBackendError", "AudioCapture", "AudioPlayer",
    "is_audio_backend_available",
    "ClipboardSyncError",
    "FileReceiver", "FileSendResult", "FileTransferError", "send_file",
]
