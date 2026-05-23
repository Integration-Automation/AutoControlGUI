"""Phase 9.6: LibUsbBackend tests (mocked PyUSB, no real device access)."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from je_auto_control.utils.usbip import LibUsbBackend, UrbRequest
from je_auto_control.utils.usbip.libusb_backend import (
    _endpoint_address, _is_control_endpoint, _translate_error,
)


# --- helpers --------------------------------------------------------

def test_endpoint_address_combines_direction_and_ep():
    assert _endpoint_address(0, 1) == 0x01
    assert _endpoint_address(1, 1) == 0x81
    assert _endpoint_address(0, 0x7F) == 0x7F
    assert _endpoint_address(1, 0x7F) == 0xFF


def test_is_control_endpoint_only_true_for_zero():
    assert _is_control_endpoint(0) is True
    assert _is_control_endpoint(1) is False
    assert _is_control_endpoint(2) is False


def test_translate_error_handles_usb_timeout():
    err = type("USBTimeoutError", (Exception,), {})()
    assert _translate_error(err) == -110


def test_translate_error_maps_value_error_to_einval():
    assert _translate_error(ValueError("nope")) == -22


def test_translate_error_falls_back_to_protocol():
    assert _translate_error(RuntimeError("random")) == -71


def test_translate_error_uses_usberror_errno_when_available():
    err = type("USBError", (Exception,), {})()
    err.errno = 32
    assert _translate_error(err) == -32


# --- availability ---------------------------------------------------

def test_available_false_when_pyusb_missing():
    with patch(
        "je_auto_control.utils.usbip.libusb_backend._try_pyusb",
        return_value=False,
    ):
        backend = LibUsbBackend()
    assert backend.available is False
    # list / submit gracefully return [] / -ENODEV instead of crashing.
    assert backend.list_devices() == []
    response = backend.submit_urb(UrbRequest(
        seqnum=1, devid=42, direction=1, ep=1,
        setup=b"\x00" * 8, transfer_buffer=b"",
        transfer_buffer_length=0,
    ))
    assert response.status == -19


# --- submit_urb dispatch -------------------------------------------

def _backend_with_device(*, control_response=None, read_response=None,
                          write_response=None):
    """Return a LibUsbBackend with a single fake device in the cache."""
    backend = LibUsbBackend()
    backend._available = True
    fake_dev = MagicMock()
    if control_response is not None:
        fake_dev.ctrl_transfer = MagicMock(return_value=control_response)
    if read_response is not None:
        fake_dev.read = MagicMock(return_value=read_response)
    if write_response is not None:
        fake_dev.write = MagicMock(return_value=write_response)
    backend._device_cache[0x10001] = fake_dev
    return backend, fake_dev


def test_submit_unknown_devid_returns_enodev():
    backend = LibUsbBackend()
    backend._available = True
    req = UrbRequest(seqnum=1, devid=999, direction=1, ep=1,
                     setup=b"\x00" * 8, transfer_buffer=b"",
                     transfer_buffer_length=0)
    assert backend.submit_urb(req).status == -19


def test_submit_control_in_calls_ctrl_transfer():
    backend, device = _backend_with_device(
        control_response=bytearray(b"hello"),
    )
    # Standard "GET_DESCRIPTOR" setup: 0x80 0x06 ...
    setup = bytes([0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x05, 0x00])
    req = UrbRequest(
        seqnum=1, devid=0x10001, direction=1, ep=0,
        setup=setup, transfer_buffer=b"",
        transfer_buffer_length=5,
    )
    response = backend.submit_urb(req)
    assert response.status == 0
    assert response.actual_length == 5
    assert response.data == b"hello"
    device.ctrl_transfer.assert_called_once()


def test_submit_control_out_calls_ctrl_transfer_with_buffer():
    backend, device = _backend_with_device(control_response=3)
    setup = bytes([0x00, 0x09, 0x01, 0x00, 0x00, 0x00, 0x03, 0x00])
    req = UrbRequest(
        seqnum=2, devid=0x10001, direction=0, ep=0,
        setup=setup, transfer_buffer=b"abc",
        transfer_buffer_length=3,
    )
    response = backend.submit_urb(req)
    assert response.status == 0
    assert response.actual_length == 3
    # ctrl_transfer received the OUT payload bytes (5th arg).
    args = device.ctrl_transfer.call_args[0]
    assert args[4] == b"abc"


def test_submit_control_rejects_bad_setup_length():
    backend, _ = _backend_with_device(control_response=bytearray(b"x"))
    req = UrbRequest(
        seqnum=1, devid=0x10001, direction=1, ep=0,
        setup=b"\x00",  # too short
        transfer_buffer=b"", transfer_buffer_length=0,
    )
    assert backend.submit_urb(req).status == -22


def test_submit_bulk_in_calls_device_read():
    backend, device = _backend_with_device(
        read_response=bytearray(b"BULK_IN"),
    )
    req = UrbRequest(
        seqnum=3, devid=0x10001, direction=1, ep=2,
        setup=b"\x00" * 8, transfer_buffer=b"",
        transfer_buffer_length=64,
    )
    response = backend.submit_urb(req)
    assert response.status == 0
    assert response.data == b"BULK_IN"
    device.read.assert_called_once()
    # Endpoint should be 0x82 (ep=2 | IN bit).
    assert device.read.call_args[0][0] == 0x82


def test_submit_bulk_out_calls_device_write():
    backend, device = _backend_with_device(write_response=5)
    req = UrbRequest(
        seqnum=4, devid=0x10001, direction=0, ep=2,
        setup=b"\x00" * 8, transfer_buffer=b"hello",
        transfer_buffer_length=5,
    )
    response = backend.submit_urb(req)
    assert response.status == 0
    assert response.actual_length == 5
    args = device.write.call_args[0]
    # OUT endpoint should NOT have the IN bit set.
    assert args[0] == 0x02
    assert args[1] == b"hello"


def test_submit_translates_exception_into_negative_errno():
    backend = LibUsbBackend()
    backend._available = True
    device = MagicMock()
    device.read = MagicMock(side_effect=ValueError("bad ep"))
    backend._device_cache[0x10001] = device
    req = UrbRequest(
        seqnum=1, devid=0x10001, direction=1, ep=1,
        setup=b"\x00" * 8, transfer_buffer=b"",
        transfer_buffer_length=8,
    )
    response = backend.submit_urb(req)
    assert response.status == -22  # ValueError → -EINVAL


# --- list_devices --------------------------------------------------

def test_list_devices_returns_empty_when_pyusb_missing():
    with patch(
        "je_auto_control.utils.usbip.libusb_backend._try_pyusb",
        return_value=False,
    ):
        assert LibUsbBackend().list_devices() == []
