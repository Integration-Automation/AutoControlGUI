"""Tests for the AC_usb_* passthrough executor commands."""
import pytest

from je_auto_control.utils.executor import action_executor as ax
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.usb.passthrough.backend import (
    BackendDevice, FakeUsbBackend,
)

_SAMPLE = BackendDevice(vendor_id="1050", product_id="0407", serial="ABC123")

_NEW_COMMANDS = [
    "AC_usb_passthrough_enable", "AC_usb_passthrough_status",
    "AC_usb_acl_list", "AC_usb_acl_add", "AC_usb_acl_remove",
    "AC_usb_acl_set_default", "AC_usb_acl_export", "AC_usb_acl_import",
    "AC_usb_loopback_list", "AC_usb_loopback_open",
    "AC_usb_remote_list", "AC_usb_remote_open",
]


@pytest.fixture()
def temp_acl(monkeypatch, tmp_path):
    """Point UsbAcl at a temp path so the user's real ACL is untouched."""
    monkeypatch.setattr(
        "je_auto_control.utils.usb.passthrough.acl.default_acl_path",
        lambda: tmp_path / "usb_acl.json",
    )
    monkeypatch.setattr(
        "je_auto_control.utils.usb.passthrough.loopback.default_passthrough_backend",
        lambda: FakeUsbBackend(devices=[_SAMPLE]),
    )
    return tmp_path


def test_all_commands_registered():
    known = executor.known_commands()
    for name in _NEW_COMMANDS:
        assert name in known, name


def test_flag_enable_and_status():
    try:
        assert ax._usb_passthrough_enable(True)["enabled"] is True
        assert ax._usb_passthrough_status()["enabled"] is True
        assert ax._usb_passthrough_enable(False)["enabled"] is False
    finally:
        ax._usb_passthrough_enable(False)


def test_acl_add_list_remove(temp_acl):
    assert ax._usb_acl_add("1050", "0407", allow=True)["added"] is True
    listed = ax._usb_acl_list()
    assert listed["default"] == "deny"
    assert len(listed["rules"]) == 1
    assert listed["rules"][0]["vendor_id"] == "1050"
    assert ax._usb_acl_remove("1050", "0407")["removed"] is True
    assert ax._usb_acl_list()["rules"] == []


def test_acl_set_default(temp_acl):
    assert ax._usb_acl_set_default("allow")["default"] == "allow"
    assert ax._usb_acl_list()["default"] == "allow"


def test_acl_export_import(temp_acl):
    ax._usb_acl_add("1050", "0407", allow=True)
    out = temp_acl / "exp.json"
    assert ax._usb_acl_export(str(out))["exported"] is True
    ax._usb_acl_remove("1050", "0407")
    assert ax._usb_acl_import(str(out))["imported"] == 1
    assert len(ax._usb_acl_list()["rules"]) == 1


def test_loopback_list_and_open(temp_acl):
    ax._usb_acl_add("1050", "0407", allow=True)
    devices = ax._usb_loopback_list()["devices"]
    assert [d["vendor_id"] for d in devices] == ["1050"]
    opened = ax._usb_loopback_open("1050", "0407", serial="ABC123")
    assert opened["ok"] is True
    assert "descriptor" in opened
    assert isinstance(opened["descriptor_hex"], str)


def test_loopback_open_denied_without_rule(temp_acl):
    from je_auto_control.utils.usb.passthrough import UsbClientError
    # No allow rule → default deny → open fails closed.
    with pytest.raises(UsbClientError):
        ax._usb_loopback_open("1050", "0407")


def test_remote_list_without_session_raises():
    from je_auto_control.utils.remote_desktop.registry import registry
    registry._webrtc_viewer = None  # noqa: SLF001  test setup
    with pytest.raises(RuntimeError):
        ax._usb_remote_list()
