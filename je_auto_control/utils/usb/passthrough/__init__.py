"""USB passthrough.

Defaults to **disabled** (opt in via ``enable_usb_passthrough`` /
``JE_AUTOCONTROL_USB_PASSTHROUGH``). Protocol, backend ABC, libusb /
WinUSB / IOKit backends, the per-OS ``default_passthrough_backend``
factory, ACL (HMAC-signed), control/bulk/interrupt transfers,
LIST-over-channel, fragmentation, the viewer client, and an in-process
``UsbLoopback`` are all implemented. Windows / macOS transfers are
hardware-unverified; the feature stays opt-in until the Phase 2e
security sign-off. See
``docs/source/Eng/doc/operations_layer/usb_passthrough_design.rst``.
"""
from je_auto_control.utils.usb.passthrough.acl import (
    AclRule, UsbAcl, default_acl_path, export_acl_to_file,
    import_acl_from_file,
)
from je_auto_control.utils.usb.passthrough.backend import (
    FakeUsbBackend, LibusbBackend, UsbBackend, UsbHandle,
    default_passthrough_backend,
)
from je_auto_control.utils.usb.passthrough.descriptor import (
    DescriptorError, DeviceDescriptor, describe_descriptor,
    parse_device_descriptor,
)
from je_auto_control.utils.usb.passthrough.flags import (
    enable_usb_passthrough, is_usb_passthrough_enabled,
)
from je_auto_control.utils.usb.passthrough.key_provider import (
    VaultKeyProvider, dpapi_available, load_or_create_dpapi_key,
)
from je_auto_control.utils.usb.passthrough.loopback import (
    LoopbackTransport, UsbLoopback,
)
from je_auto_control.utils.usb.passthrough.protocol import (
    FLAG_EOF, Frame, Opcode, ProtocolError, decode_frame, encode_frame,
    fragment_payload, MAX_PAYLOAD_BYTES,
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
    "default_passthrough_backend",
    "LoopbackTransport", "UsbLoopback",
    "DescriptorError", "DeviceDescriptor", "describe_descriptor",
    "parse_device_descriptor",
    "enable_usb_passthrough", "is_usb_passthrough_enabled",
    "FLAG_EOF", "Frame", "Opcode", "ProtocolError",
    "decode_frame", "encode_frame", "fragment_payload",
    "MAX_PAYLOAD_BYTES",
    "SessionError", "UsbPassthroughSession",
    "ClientHandle", "UsbClientClosed", "UsbClientError", "UsbClientTimeout",
    "UsbPassthroughClient",
    "AclRule", "UsbAcl", "default_acl_path",
    "export_acl_to_file", "import_acl_from_file",
    "VaultKeyProvider", "dpapi_available", "load_or_create_dpapi_key",
]
