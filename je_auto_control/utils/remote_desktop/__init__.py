"""Remote-desktop exports with independent optional dependency outcomes."""
import sys as _sys
from typing import TYPE_CHECKING as _TYPE_CHECKING

from je_auto_control._lazy_exports import resolve_export as _resolve_export
from je_auto_control.utils.remote_desktop._export_bindings import EXPORTS as _EXPORTS
# This singleton shares its name with a child module; preserve the existing binding.
from je_auto_control.utils.remote_desktop.registry import registry


if _TYPE_CHECKING:
    from je_auto_control.utils.remote_desktop.audio import (
        AudioBackendError,
        AudioCapture,
        AudioPlayer,
        is_audio_backend_available,
    )
    from je_auto_control.utils.remote_desktop.clipboard_sync import ClipboardSyncError
    from je_auto_control.utils.remote_desktop.file_transfer import (
        FileReceiver,
        FileSendResult,
        FileTransferError,
        confine_destination,
        default_download_dir,
        send_file,
    )
    from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
    from je_auto_control.utils.remote_desktop.host_access import (
        PendingViewer,
        PendingViewerCallback,
    )
    from je_auto_control.utils.remote_desktop.host_capture import list_host_monitors
    from je_auto_control.utils.remote_desktop.host_id import (
        HostIdError,
        format_host_id,
        generate_host_id,
        load_or_create_host_id,
        parse_host_id,
        validate_host_id,
    )
    from je_auto_control.utils.remote_desktop.input_dispatch import (
        InputDispatchError,
        dispatch_input,
    )
    from je_auto_control.utils.remote_desktop.presence import (
        PresenceError,
        PresenceListener,
        PresenceRegistry,
        ROLE_CONTROLLER,
        ROLE_OBSERVER,
        ViewerPresence,
        default_presence_registry,
    )
    from je_auto_control.utils.remote_desktop.protocol import (
        AuthenticationError,
        MessageType,
        ProtocolError,
        decode_frame_header,
        encode_frame,
    )
    from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer
    from je_auto_control.utils.remote_desktop.ws_host import WebSocketDesktopHost
    from je_auto_control.utils.remote_desktop.ws_viewer import WebSocketDesktopViewer
    from je_auto_control.utils.remote_desktop import signaling_client
    from je_auto_control.utils.remote_desktop.address_book import (
        AddressBook,
        default_address_book,
        default_address_book_path,
    )
    from je_auto_control.utils.remote_desktop.trust_list import (
        TrustList,
        default_trust_list,
        default_trust_list_path,
    )
    from je_auto_control.utils.remote_desktop.fingerprint import (
        KnownHosts,
        default_known_hosts,
        fingerprint_for_display,
        load_or_create_host_fingerprint,
    )
    from je_auto_control.utils.remote_desktop.permissions import SessionPermissions
    from je_auto_control.utils.remote_desktop.viewer_id import (
        ViewerIdError,
        generate_viewer_id,
        load_or_create_viewer_id,
        validate_viewer_id,
    )
    from je_auto_control.utils.remote_desktop.wake_on_lan import (
        build_magic_packet,
        send_magic_packet,
    )
    from je_auto_control.utils.remote_desktop._optional.webrtc import (
        WebRTCDesktopHost,
        WebRTCDesktopViewer,
        WebRTCConfig,
    )
    from je_auto_control.utils.remote_desktop._optional.session_recorder import SessionRecorder
    from je_auto_control.utils.remote_desktop._optional.multi_viewer import MultiViewerHost
    from je_auto_control.utils.remote_desktop._optional.mic_uplink import (
        MicUplinkSender,
        MicUplinkReceiver,
    )
    from je_auto_control.utils.remote_desktop._optional.file_transfer import (
        FileTransferSender,
        FileTransferReceiver,
        FileTransferWebRTCError,
    )
    from je_auto_control.utils.remote_desktop._optional.hw_codec import (
        available_hardware_codecs,
        active_hardware_codec,
        install_hardware_codec,
        uninstall_hardware_codec,
    )


__all__ = [
    "RemoteDesktopHost", "RemoteDesktopViewer",
    "PendingViewer", "PendingViewerCallback", "list_host_monitors",
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
    "FileReceiver", "FileSendResult", "FileTransferError", "confine_destination",
    "default_download_dir", "send_file",
    "PresenceError", "PresenceListener", "PresenceRegistry",
    "ROLE_CONTROLLER", "ROLE_OBSERVER", "ViewerPresence",
    "default_presence_registry",
]


def is_webrtc_available() -> bool:
    """Return whether the current facade host class is available."""
    return getattr(_sys.modules[__name__], "WebRTCDesktopHost") is not None


def __getattr__(name: str) -> object:
    """Resolve one original export or its complete optional group outcome."""
    return _resolve_export(globals(), _EXPORTS, name)


def __dir__() -> list[str]:
    """List public exports without probing optional dependencies."""
    return sorted(set(globals()) | set(__all__))
