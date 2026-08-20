"""Tests for USB device enumeration (round 27)."""
import json

from je_auto_control.utils.usb.usb_devices import (
    UsbDevice, UsbEnumerationResult, list_usb_devices,
)


def test_list_returns_valid_result_object():
    result = list_usb_devices()
    assert isinstance(result, UsbEnumerationResult)
    assert isinstance(result.devices, list)
    assert isinstance(result.backend, str) and result.backend


def test_each_device_has_expected_fields():
    result = list_usb_devices()
    for device in result.devices:
        assert isinstance(device, UsbDevice)
        d = device.to_dict()
        for key in ("vendor_id", "product_id", "manufacturer",
                    "product", "serial", "bus_location", "extra"):
            assert key in d, key


def test_to_dict_is_json_serializable():
    result = list_usb_devices()
    payload = result.to_dict()
    # Round-trip through JSON to ensure no non-serializable values leaked in.
    serialized = json.dumps(payload, default=str)
    restored = json.loads(serialized)
    assert restored["backend"] == result.backend
    assert restored["count"] == len(result.devices)


def test_vendor_and_product_ids_are_4_hex_chars_when_present():
    """Per the dataclass docstring, IDs are 4-hex-digit lowercase strings."""
    result = list_usb_devices()
    for device in result.devices:
        for value in (device.vendor_id, device.product_id):
            if value is not None:
                assert len(value) == 4, value
                assert all(c in "0123456789abcdef" for c in value), value


def test_result_to_dict_count_matches_devices():
    result = list_usb_devices()
    assert result.to_dict()["count"] == len(result.devices)


# --- system_profiler id parsing (macOS shapes, checked on every platform) ---


def test_symbolic_vendor_id_is_not_smuggled_through_as_hex():
    """Apple's own devices report ``apple_vendor_id`` instead of a number.

    Its leading "a" is a valid hex digit, so a lenient parse turns it into
    ``000a`` and a pass-through returns the word itself — both of which break
    the 4-hex-digit shape ``UsbDevice`` documents. Only real macOS hardware
    produces this, which is why it went unseen while the suite ran on
    Windows alone.
    """
    from je_auto_control.utils.usb.usb_devices import _hex4_from_macos

    assert _hex4_from_macos("apple_vendor_id") is None


def test_hex_ids_from_system_profiler_are_normalised():
    from je_auto_control.utils.usb.usb_devices import _hex4_from_macos

    assert _hex4_from_macos("0x05ac") == "05ac"
    assert _hex4_from_macos("0x8600") == "8600"
    # system_profiler appends the vendor name to some entries.
    assert _hex4_from_macos("0x05AC  (Apple Inc.)") == "05ac"
    # A bare id, and one that needs padding out to four digits.
    assert _hex4_from_macos("05ac") == "05ac"
    assert _hex4_from_macos("0x1") == "0001"
    assert _hex4_from_macos(None) is None
    assert _hex4_from_macos("") is None
