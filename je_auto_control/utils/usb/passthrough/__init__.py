"""USB passthrough — Phase 2a (skeleton).

EXPERIMENTAL. Defaults to disabled. The protocol layer + backend ABC
are in place; bulk/control transfers are intentionally not implemented
yet. See ``docs/source/Eng/doc/operations_layer/usb_passthrough_design.rst``.
"""
from je_auto_control.utils.usb.passthrough.acl import (
    AclRule, UsbAcl, default_acl_path,
)
from je_auto_control.utils.usb.passthrough.backend import (
    FakeUsbBackend, LibusbBackend, UsbBackend, UsbHandle,
)
from je_auto_control.utils.usb.passthrough.flags import (
    enable_usb_passthrough, is_usb_passthrough_enabled,
)
from je_auto_control.utils.usb.passthrough.protocol import (
    Frame, Opcode, ProtocolError, decode_frame, encode_frame,
    MAX_PAYLOAD_BYTES,
)
from je_auto_control.utils.usb.passthrough.session import (
    SessionError, UsbPassthroughSession,
)
from je_auto_control.utils.usb.passthrough.viewer_client import (
    ClientHandle, UsbClientClosed, UsbClientError, UsbClientTimeout,
    UsbPassthroughClient,
)

__all__ = [
    "FakeUsbBackend", "LibusbBackend", "UsbBackend", "UsbHandle",
    "enable_usb_passthrough", "is_usb_passthrough_enabled",
    "Frame", "Opcode", "ProtocolError", "decode_frame", "encode_frame",
    "MAX_PAYLOAD_BYTES",
    "SessionError", "UsbPassthroughSession",
    "ClientHandle", "UsbClientClosed", "UsbClientError", "UsbClientTimeout",
    "UsbPassthroughClient",
    "AclRule", "UsbAcl", "default_acl_path",
]
