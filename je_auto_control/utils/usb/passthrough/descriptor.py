"""Parse a USB standard *device descriptor* into a readable structure.

The 18-byte device descriptor is what a host reads first from any USB
device (``GET_DESCRIPTOR`` / type ``0x01``). The passthrough GUI reads
it right after a claim as a liveness probe; this module turns the raw
bytes into a :class:`DeviceDescriptor` plus a one-line human summary so
the panel can show "Vendor 1050 / HID device" instead of raw hex.

Pure data — no I/O, no Qt.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

_DEVICE_DESCRIPTOR_TYPE = 0x01
_DEVICE_DESCRIPTOR_LEN = 18
_DEVICE_DESCRIPTOR_FORMAT = "<BBHBBBBHHHBBB B"  # 18 bytes, little-endian

# bDeviceClass at the device level (0x00 means "see interface descriptors").
_USB_CLASS_NAMES = {
    0x00: "per-interface",
    0x02: "communications",
    0x03: "HID",
    0x05: "physical",
    0x06: "image",
    0x07: "printer",
    0x08: "mass-storage",
    0x09: "hub",
    0x0A: "CDC-data",
    0x0B: "smart-card",
    0x0E: "video",
    0x0F: "personal-healthcare",
    0xDC: "diagnostic",
    0xE0: "wireless",
    0xEF: "miscellaneous",
    0xFF: "vendor-specific",
}


class DescriptorError(ValueError):
    """Raised when the supplied bytes are not a valid device descriptor."""


@dataclass(frozen=True)
class DeviceDescriptor:
    """Decoded fields of an 18-byte USB device descriptor."""

    usb_version: str          # e.g. "2.00" from bcdUSB
    device_class: int
    device_subclass: int
    device_protocol: int
    max_packet_size0: int
    vendor_id: str            # 4 hex digits
    product_id: str           # 4 hex digits
    device_version: str       # e.g. "1.00" from bcdDevice
    manufacturer_index: int
    product_index: int
    serial_index: int
    num_configurations: int

    @property
    def class_name(self) -> str:
        return _USB_CLASS_NAMES.get(self.device_class, "unknown")

    def summary(self) -> str:
        """One-line human summary for a status label."""
        return (
            f"{self.vendor_id}:{self.product_id} "
            f"{self.class_name} (USB {self.usb_version}, "
            f"{self.num_configurations} config)"
        )


def _bcd_to_str(value: int) -> str:
    """Render a BCD-coded version word (e.g. 0x0200) as "2.00"."""
    major = (value >> 8) & 0xFF
    minor = (value >> 4) & 0x0F
    patch = value & 0x0F
    return f"{major}.{minor}{patch}"


def parse_device_descriptor(data: bytes) -> DeviceDescriptor:
    """Decode an 18-byte device descriptor; raise on malformed input."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise DescriptorError("descriptor must be bytes-like")
    raw = bytes(data)
    if len(raw) < _DEVICE_DESCRIPTOR_LEN:
        raise DescriptorError(
            f"descriptor too short ({len(raw)}B); need "
            f"{_DEVICE_DESCRIPTOR_LEN}",
        )
    fields = struct.unpack(_DEVICE_DESCRIPTOR_FORMAT, raw[:_DEVICE_DESCRIPTOR_LEN])
    (b_length, b_type, bcd_usb, dev_class, dev_subclass, dev_protocol,
     max_packet, vendor, product, bcd_device, i_manuf, i_product,
     i_serial, num_configs) = fields
    if b_type != _DEVICE_DESCRIPTOR_TYPE:
        raise DescriptorError(
            f"not a device descriptor (bDescriptorType=0x{b_type:02x})",
        )
    if b_length != _DEVICE_DESCRIPTOR_LEN:
        raise DescriptorError(
            f"unexpected bLength {b_length} (want {_DEVICE_DESCRIPTOR_LEN})",
        )
    return DeviceDescriptor(
        usb_version=_bcd_to_str(bcd_usb),
        device_class=dev_class,
        device_subclass=dev_subclass,
        device_protocol=dev_protocol,
        max_packet_size0=max_packet,
        vendor_id=f"{vendor:04x}",
        product_id=f"{product:04x}",
        device_version=_bcd_to_str(bcd_device),
        manufacturer_index=i_manuf,
        product_index=i_product,
        serial_index=i_serial,
        num_configurations=num_configs,
    )


def describe_descriptor(data: bytes) -> str:
    """Best-effort one-line summary; falls back to hex on parse failure."""
    try:
        return parse_device_descriptor(data).summary()
    except DescriptorError:
        return data.hex() or "(empty)"


__all__ = [
    "DescriptorError", "DeviceDescriptor",
    "parse_device_descriptor", "describe_descriptor",
]
