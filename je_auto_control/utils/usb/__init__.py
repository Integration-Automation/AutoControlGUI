"""Cross-platform USB device enumeration + hotplug + passthrough (Phase 2a)."""
from je_auto_control.utils.usb.passthrough import (
    AclRule, ClientHandle, FakeUsbBackend, Frame, LibusbBackend,
    MAX_PAYLOAD_BYTES, Opcode, ProtocolError, SessionError, UsbAcl,
    UsbBackend, UsbClientClosed, UsbClientError, UsbClientTimeout,
    UsbHandle, UsbPassthroughClient, UsbPassthroughSession, decode_frame,
    default_acl_path, enable_usb_passthrough, encode_frame,
    is_usb_passthrough_enabled,
)
from je_auto_control.utils.usb.usb_devices import (
    UsbDevice, UsbEnumerationResult, list_usb_devices,
)
from je_auto_control.utils.usb.usb_watcher import (
    UsbEvent, UsbHotplugWatcher, default_usb_watcher,
)

__all__ = [
    # Enumeration + hotplug (rounds 27 / 34)
    "UsbDevice", "UsbEnumerationResult", "list_usb_devices",
    "UsbEvent", "UsbHotplugWatcher", "default_usb_watcher",
    # Passthrough Phase 2a/2a.1/40 (rounds 37–40) — EXPERIMENTAL, default off
    "FakeUsbBackend", "Frame", "LibusbBackend", "MAX_PAYLOAD_BYTES",
    "Opcode", "ProtocolError", "SessionError", "UsbBackend", "UsbHandle",
    "UsbPassthroughSession", "decode_frame", "enable_usb_passthrough",
    "encode_frame", "is_usb_passthrough_enabled",
    # Viewer client (round 40)
    "ClientHandle", "UsbClientClosed", "UsbClientError", "UsbClientTimeout",
    "UsbPassthroughClient",
    # Phase 2d ACL (round 41)
    "AclRule", "UsbAcl", "default_acl_path",
]
