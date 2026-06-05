"""Tests for the in-process USB loopback transport + UsbLoopback bundle."""
import pytest

from je_auto_control.utils.usb.passthrough import (
    AclRule, UsbAcl, UsbClientError, UsbLoopback,
)
from je_auto_control.utils.usb.passthrough.backend import (
    BackendDevice, FakeUsbBackend,
)


_SAMPLE = BackendDevice(vendor_id="1050", product_id="0407", serial="ABC123")
_OTHER = BackendDevice(vendor_id="2222", product_id="3333", serial=None)


def _allow_all_acl(tmp_path, *devices):
    acl = UsbAcl(path=tmp_path / "acl.json")
    for dev in devices:
        acl.add_rule(AclRule(vendor_id=dev.vendor_id,
                             product_id=dev.product_id, allow=True))
    return acl


def test_loopback_lists_devices(tmp_path):
    backend = FakeUsbBackend(devices=[_SAMPLE, _OTHER])
    acl = _allow_all_acl(tmp_path, _SAMPLE, _OTHER)
    with UsbLoopback(backend=backend, acl=acl) as loop:
        devices = loop.list_devices()
    vids = sorted(d["vendor_id"] for d in devices)
    assert vids == ["1050", "2222"]


def test_loopback_list_respects_acl_deny(tmp_path):
    backend = FakeUsbBackend(devices=[_SAMPLE, _OTHER])
    acl = _allow_all_acl(tmp_path, _SAMPLE)  # only _SAMPLE allowed
    with UsbLoopback(backend=backend, acl=acl) as loop:
        devices = loop.list_devices()
    assert [d["vendor_id"] for d in devices] == ["1050"]


def test_loopback_open_and_transfer(tmp_path):
    backend = FakeUsbBackend(devices=[_SAMPLE])
    acl = _allow_all_acl(tmp_path, _SAMPLE)
    with UsbLoopback(backend=backend, acl=acl) as loop:
        handle = loop.open(vendor_id="1050", product_id="0407")
        backend_handle = next(iter(backend._open_handles.values()))
        backend_handle.transfer_hook = lambda kind, kwargs: b"\xde\xad"
        result = handle.control_transfer(
            bm_request_type=0xC0, b_request=6, length=2,
        )
        assert result == b"\xde\xad"
        assert loop.session.active_claim_count == 1
        handle.close()
        assert loop.session.active_claim_count == 0


def test_loopback_open_denied_by_acl_raises(tmp_path):
    backend = FakeUsbBackend(devices=[_SAMPLE])
    acl = UsbAcl(path=tmp_path / "acl.json")  # default deny, no rules
    with UsbLoopback(backend=backend, acl=acl) as loop:
        with pytest.raises(UsbClientError):
            loop.open(vendor_id="1050", product_id="0407")


def test_loopback_close_is_idempotent(tmp_path):
    backend = FakeUsbBackend(devices=[_SAMPLE])
    acl = _allow_all_acl(tmp_path, _SAMPLE)
    loop = UsbLoopback(backend=backend, acl=acl)
    loop.close()
    loop.close()  # must not raise


def test_loopback_after_close_rejects_calls(tmp_path):
    backend = FakeUsbBackend(devices=[_SAMPLE])
    acl = _allow_all_acl(tmp_path, _SAMPLE)
    loop = UsbLoopback(backend=backend, acl=acl)
    loop.close()
    with pytest.raises(Exception):
        loop.list_devices()
