"""Tests for USB device-descriptor parsing."""
import struct

import pytest

from je_auto_control.utils.usb.passthrough import (
    DescriptorError, describe_descriptor, parse_device_descriptor,
)


def _descriptor(*, vendor=0x1050, product=0x0407, dev_class=0x03,
                bcd_usb=0x0200, bcd_device=0x0100, num_configs=1) -> bytes:
    return struct.pack(
        "<BBHBBBBHHHBBBB",
        18, 0x01, bcd_usb, dev_class, 0, 0, 64,
        vendor, product, bcd_device, 1, 2, 3, num_configs,
    )


def test_parse_valid_descriptor_fields():
    desc = parse_device_descriptor(_descriptor())
    assert desc.vendor_id == "1050"
    assert desc.product_id == "0407"
    assert desc.device_class == 0x03
    assert desc.class_name == "HID"
    assert desc.usb_version == "2.00"
    assert desc.device_version == "1.00"
    assert desc.num_configurations == 1
    assert desc.max_packet_size0 == 64


def test_summary_is_human_readable():
    summary = parse_device_descriptor(_descriptor()).summary()
    assert "1050:0407" in summary
    assert "HID" in summary
    assert "USB 2.00" in summary


def test_unknown_class_falls_back_to_unknown():
    desc = parse_device_descriptor(_descriptor(dev_class=0x42))
    assert desc.class_name == "unknown"


def test_vendor_specific_class():
    desc = parse_device_descriptor(_descriptor(dev_class=0xFF))
    assert desc.class_name == "vendor-specific"


def test_parse_rejects_short_buffer():
    with pytest.raises(DescriptorError):
        parse_device_descriptor(b"\x12\x01\x00")


def test_parse_rejects_wrong_descriptor_type():
    raw = bytearray(_descriptor())
    raw[1] = 0x02  # configuration descriptor type, not device
    with pytest.raises(DescriptorError):
        parse_device_descriptor(bytes(raw))


def test_parse_rejects_non_bytes():
    with pytest.raises(DescriptorError):
        parse_device_descriptor(12345)  # type: ignore[arg-type]


def test_describe_falls_back_to_hex_on_bad_input():
    assert describe_descriptor(b"\x00\x01") == "0001"
    assert describe_descriptor(b"") == "(empty)"


def test_describe_summarises_valid_descriptor():
    assert "HID" in describe_descriptor(_descriptor())
